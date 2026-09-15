import discord
from discord.ext import commands, tasks
import requests
import asyncio
import os


# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("No se encontró la variable TOKEN en Railway")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# USUARIOS QUE ESTAMOS VIGILANDO
# =========================================================

# Cada usuario tiene sus propios datos.
#
# {
#     user_id: {
#         "user": ...,
#         "channel": ...,
#         "mode": "watch" / "watchfind",
#         "last_status": ...,
#         "last_game_id": ...
#     }
# }

watching_users = {}


# =========================================================
# ROBLOX - OBTENER USUARIO
# =========================================================

def get_user(username):
    try:
        response = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={
                "usernames": [username],
                "excludeBannedUsers": False
            },
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not data.get("data"):
            return None

        return data["data"][0]

    except Exception as e:
        print("Error get_user:", e)
        return None


# =========================================================
# ROBLOX - PRESENCIA DE UN USUARIO
# =========================================================

def get_presence(user_id):
    try:
        response = requests.post(
            "https://presence.roblox.com/v1/presence/users",
            json={
                "userIds": [user_id]
            },
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not data.get("userPresences"):
            return None

        return data["userPresences"][0]

    except Exception as e:
        print("Error get_presence:", e)
        return None


# =========================================================
# ROBLOX - PRESENCIAS EN GRUPO
# =========================================================

def get_presences_batch(user_ids):
    """
    Obtiene las presencias de varios usuarios en una sola
    petición.

    Se dividen en grupos de 50 para evitar mandar una
    petición demasiado grande.
    """

    results = {}

    for i in range(0, len(user_ids), 50):

        chunk = user_ids[i:i + 50]

        try:
            response = requests.post(
                "https://presence.roblox.com/v1/presence/users",
                json={
                    "userIds": chunk
                },
                timeout=15
            )

            if response.status_code != 200:
                print(
                    "Error presencia batch:",
                    response.status_code
                )
                continue

            data = response.json()

            for presence in data.get("userPresences", []):
                user_id = presence.get("userId")

                if user_id is not None:
                    results[user_id] = presence

        except Exception as e:
            print("Error get_presences_batch:", e)

    return results


# =========================================================
# ROBLOX - AVATAR
# =========================================================

def get_avatar(user_id):

    try:
        response = requests.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={
                "userIds": user_id,
                "size": "420x420",
                "format": "Png",
                "isCircular": False
            },
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not data.get("data"):
            return None

        return data["data"][0].get("imageUrl")

    except Exception as e:
        print("Error get_avatar:", e)
        return None


# =========================================================
# ROBLOX - SERVIDORES PÚBLICOS
# =========================================================

def get_all_servers(place_id):

    servers = []
    cursor = None

    while True:

        try:

            params = {
                "sortOrder": "Asc",
                "limit": 100
            }

            if cursor:
                params["cursor"] = cursor

            response = requests.get(
                f"https://games.roblox.com/v1/games/{place_id}/servers/Public",
                params=params,
                timeout=15
            )

            if response.status_code != 200:
                print(
                    "Error servidores:",
                    response.status_code
                )
                break

            data = response.json()

            for server in data.get("data", []):

                servers.append(server)

            cursor = data.get("nextPageCursor")

            if not cursor:
                break

        except Exception as e:

            print("Error get_all_servers:", e)
            break

    servers.sort(
        key=lambda server: server.get("playing", 0)
    )

    return servers


# =========================================================
# LINK PARA UNIRSE AL SERVIDOR
# =========================================================

def create_join_link(place_id, game_id):

    return (
        f"roblox://experiences/start"
        f"?placeId={place_id}"
        f"&gameInstanceId={game_id}"
    )


# =========================================================
# CONVERTIR PRESENCIA A TEXTO
# =========================================================

def presence_text(presence):

    if not presence:
        return "Offline"

    presence_type = presence.get("userPresenceType", 0)

    if presence_type == 0:
        return "Offline"

    if presence_type == 1:
        return "Online"

    if presence_type == 2:
        return "Jugando"

    if presence_type == 3:
        return "En Roblox Studio"

    return "Desconocido"


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print("=" * 50)
    print(f"Bot conectado como: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("=" * 50)

    if not check_presence.is_running():
        check_presence.start()


# =========================================================
# !SNIPE
# =========================================================

@bot.command()
async def snipe(ctx, username):

    await ctx.send(
        f"🔎 Buscando a **{username}**..."
    )

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            f"❌ No encontré al usuario **{username}**."
        )

        return

    user_id = user["id"]

    presence = await asyncio.to_thread(
        get_presence,
        user_id
    )

    status = presence_text(presence)

    if status == "Offline":

        await ctx.send(
            f"⚫ **{user['name']}** está offline."
        )

        return

    if status == "Online":

        await ctx.send(
            f"🟢 **{user['name']}** está online, "
            f"pero no está jugando."
        )

        return

    if status == "En Roblox Studio":

        await ctx.send(
            f"🛠️ **{user['name']}** está en Roblox Studio."
        )

        return

    place_id = presence.get("placeId")
    game_id = presence.get("gameId")

    message = (
        f"🎯 **{user['name']} está jugando**\n\n"
        f"**User ID:** `{user_id}`\n"
        f"**Place ID:** `{place_id}`\n"
        f"**Game ID:** `{game_id}`"
    )

    if game_id and place_id:

        message += (
            f"\n\n🔗 **Join:**\n"
            f"`{create_join_link(place_id, game_id)}`"
        )

    await ctx.send(message)


# =========================================================
# !WATCH
# =========================================================

@bot.command()
async def watch(ctx, username):

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            f"❌ No encontré al usuario **{username}**."
        )

        return

    user_id = user["id"]

    watching_users[user_id] = {

        "user": user,

        "channel": ctx.channel,

        "mode": "watch",

        "last_status": None,

        "last_game_id": None
    }

    await ctx.send(
        f"👁️ Ahora estoy vigilando a "
        f"**{user['name']}**.\n\n"
        f"Revisión cada **15 segundos**."
    )


# =========================================================
# !WATCHFIND
# =========================================================

@bot.command()
async def watchfind(ctx, username):

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            f"❌ No encontré al usuario **{username}**."
        )

        return

    user_id = user["id"]

    watching_users[user_id] = {

        "user": user,

        "channel": ctx.channel,

        "mode": "watchfind",

        "last_status": None,

        "last_game_id": None
    }

    await ctx.send(
        f"🎯 Ahora estoy haciendo **WATCHFIND** "
        f"de **{user['name']}**.\n\n"
        f"Revisión cada **15 segundos**."
    )


# =========================================================
# !UNWATCH
# =========================================================

@bot.command()
async def unwatch(ctx, username=None):

    # Sin nombre = eliminar todos
    if username is None:

        amount = len(watching_users)

        watching_users.clear()

        await ctx.send(
            f"🛑 Dejé de vigilar a **todos los usuarios**.\n"
            f"Usuarios eliminados: `{amount}`"
        )

        return

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            f"❌ No encontré al usuario **{username}**."
        )

        return

    user_id = user["id"]

    if user_id not in watching_users:

        await ctx.send(
            f"⚠️ **{user['name']}** no estaba siendo vigilado."
        )

        return

    del watching_users[user_id]

    await ctx.send(
        f"🛑 Dejé de vigilar a **{user['name']}**."
    )


# =========================================================
# !WATCHLIST
# =========================================================

@bot.command()
async def watchlist(ctx):

    if not watching_users:

        await ctx.send(
            "📭 No hay usuarios siendo vigilados."
        )

        return

    lines = []

    for user_id, data in watching_users.items():

        user = data["user"]

        mode = data["mode"]

        if mode == "watch":
            mode_text = "WATCH"
        else:
            mode_text = "WATCHFIND"

        lines.append(
            f"• **{user['name']}** — `{mode_text}`"
        )

    text = (
        f"👁️ **Usuarios vigilados: "
        f"{len(watching_users)}**\n\n"
        + "\n".join(lines)
    )

    await ctx.send(text)


# =========================================================
# FIND VIEW
# =========================================================

class FindView(discord.ui.View):

    def __init__(self, join_url):

        super().__init__(timeout=None)

        self.join_url = join_url

    @discord.ui.button(
        label="🎮 Join Server",
        style=discord.ButtonStyle.green
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            f"`{self.join_url}`",
            ephemeral=True
        )


# =========================================================
# CREAR CARD DE FIND
# =========================================================

async def create_find_card(
    user,
    presence,
    server
):

    user_id = user["id"]

    avatar = await asyncio.to_thread(
        get_avatar,
        user_id
    )

    place_id = presence.get("placeId")

    game_id = server.get("id")

    playing = server.get("playing", 0)

    max_players = server.get("maxPlayers", 0)

    embed = discord.Embed(
        title="🎯 Jugador encontrado",
        description=(
            f"**{user['name']}** fue encontrado "
            f"en un servidor público."
        ),
        color=discord.Color.green()
    )

    embed.add_field(
        name="👤 Username",
        value=f"`{user['name']}`",
        inline=True
    )

    embed.add_field(
        name="🆔 User ID",
        value=f"`{user_id}`",
        inline=True
    )

    embed.add_field(
        name="📍 Place ID",
        value=f"`{place_id}`",
        inline=False
    )

    embed.add_field(
        name="👥 Players",
        value=f"`{playing}/{max_players}`",
        inline=True
    )

    embed.add_field(
        name="🎮 Job ID",
        value=f"`{game_id}`",
        inline=False
    )

    embed.add_field(
        name="🟢 Status",
        value="Jugando",
        inline=True
    )

    if avatar:

        embed.set_thumbnail(
            url=avatar
        )

    join_url = create_join_link(
        place_id,
        game_id
    )

    return embed, join_url


# =========================================================
# !FIND
# =========================================================

@bot.command()
async def find(ctx, username):

    await ctx.send(
        f"🔎 Buscando a **{username}**..."
    )

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            f"❌ No encontré al usuario **{username}**."
        )

        return

    user_id = user["id"]

    presence = await asyncio.to_thread(
        get_presence,
        user_id
    )

    if not presence:

        await ctx.send(
            f"⚫ **{user['name']}** está offline."
        )

        return

    status = presence_text(presence)

    if status != "Jugando":

        await ctx.send(
            f"⚠️ **{user['name']}** no está jugando.\n"
            f"Estado: **{status}**"
        )

        return

    place_id = presence.get("placeId")
    game_id = presence.get("gameId")

    if not place_id:

        await ctx.send(
            f"⚠️ No pude obtener el Place ID."
        )

        return

    await ctx.send(
        f"🎮 **{user['name']}** está jugando.\n"
        f"Buscando su servidor público..."
    )

    servers = await asyncio.to_thread(
        get_all_servers,
        place_id
    )

    target_server = None

    for server in servers:

        if server.get("id") == game_id:

            target_server = server

            break

    if not target_server:

        await ctx.send(
            f"⚠️ Encontré el Game ID de "
            f"**{user['name']}**, pero no aparece "
            f"en la lista de servidores públicos.\n\n"
            f"**Game ID:** `{game_id}`"
        )

        return

    embed, join_url = await create_find_card(
        user,
        presence,
        target_server
    )

    view = FindView(join_url)

    await ctx.send(
        embed=embed,
        view=view
    )


# =========================================================
# WATCHFIND - ENCONTRAR SERVIDOR
# =========================================================

async def send_watchfind_result(
    data,
    presence
):

    user = data["user"]

    channel = data["channel"]

    place_id = presence.get("placeId")

    game_id = presence.get("gameId")

    if not place_id or not game_id:

        return

    await channel.send(
        f"🔎 **{user['name']}** está jugando.\n"
        f"Buscando servidor público..."
    )

    servers = await asyncio.to_thread(
        get_all_servers,
        place_id
    )

    target_server = None

    for server in servers:

        if server.get("id") == game_id:

            target_server = server

            break

    if not target_server:

        await channel.send(
            f"⚠️ No encontré el servidor público "
            f"de **{user['name']}**.\n\n"
            f"**Game ID:** `{game_id}`"
        )

        return

    embed, join_url = await create_find_card(
        user,
        presence,
        target_server
    )

    view = FindView(join_url)

    await channel.send(
        embed=embed,
        view=view
    )


# =========================================================
# LOOP PRINCIPAL
# =========================================================

@tasks.loop(seconds=15)
async def check_presence():

    if not watching_users:
        return

    # Copiamos los usuarios actuales para que podamos
    # modificar watching_users sin romper el loop.
    users_to_check = list(watching_users.items())

    user_ids = [
        user_id
        for user_id, data in users_to_check
    ]

    # =====================================================
    # UNA SOLA CONSULTA AGRUPADA PARA TODOS
    # =====================================================

    presences = await asyncio.to_thread(
        get_presences_batch,
        user_ids
    )

    # =====================================================
    # PROCESAR CADA USUARIO
    # =====================================================

    for user_id, data in users_to_check:

        # Puede que alguien haya usado !unwatch mientras
        # estábamos procesando.
        if user_id not in watching_users:
            continue

        user = data["user"]

        channel = data["channel"]

        mode = data["mode"]

        presence = presences.get(user_id)

        status = presence_text(presence)

        last_status = data["last_status"]

        last_game_id = data["last_game_id"]

        current_game_id = None

        if presence:
            current_game_id = presence.get("gameId")

        # =================================================
        # WATCH NORMAL
        # =================================================

        if mode == "watch":

            if last_status is None:

                data["last_status"] = status

                data["last_game_id"] = current_game_id

                continue

            if status != last_status:

                if status == "Jugando":

                    place_id = (
                        presence.get("placeId")
                        if presence else None
                    )

                    message = (
                        f"🟢 **{user['name']}** "
                        f"ahora está jugando."
                    )

                    if place_id:

                        message += (
                            f"\n📍 Place ID: `{place_id}`"
                        )

                    if current_game_id:

                        message += (
                            f"\n🎮 Game ID: `{current_game_id}`"
                        )

                    await channel.send(message)

                elif status == "Offline":

                    await channel.send(
                        f"⚫ **{user['name']}** "
                        f"ahora está offline."
                    )

                elif status == "Online":

                    await channel.send(
                        f"🟡 **{user['name']}** "
                        f"está online pero no jugando."
                    )

                elif status == "En Roblox Studio":

                    await channel.send(
                        f"🛠️ **{user['name']}** "
                        f"está en Roblox Studio."
                    )

                else:

                    await channel.send(
                        f"ℹ️ **{user['name']}** cambió "
                        f"de estado a **{status}**."
                    )

            data["last_status"] = status

            data["last_game_id"] = current_game_id

        # =================================================
        # WATCHFIND
        # =================================================

        elif mode == "watchfind":

            # Primera comprobación.
            if last_status is None:

                data["last_status"] = status

                data["last_game_id"] = current_game_id

                # Si ya estaba jugando cuando empezamos
                # a vigilarlo, intentamos encontrarlo.
                if (
                    status == "Jugando"
                    and current_game_id
                ):

                    await send_watchfind_result(
                        data,
                        presence
                    )

                continue

            # Entró a jugar.
            started_playing = (
                status == "Jugando"
                and last_status != "Jugando"
            )

            # Cambió de servidor.
            changed_server = (
                status == "Jugando"
                and current_game_id
                and current_game_id != last_game_id
            )

            if started_playing or changed_server:

                await send_watchfind_result(
                    data,
                    presence
                )

            # Si dejó de jugar.
            if (
                last_status == "Jugando"
                and status != "Jugando"
            ):

                await channel.send(
                    f"⚫ **{user['name']}** "
                    f"dejó de jugar.\n"
                    f"Estado: **{status}**"
                )

            data["last_status"] = status

            data["last_game_id"] = current_game_id


# =========================================================
# SERVERS PAGINADOS
# =========================================================

class ServerPages(discord.ui.View):

    def __init__(
        self,
        servers,
        place_id
    ):

        super().__init__(timeout=180)

        self.servers = servers

        self.place_id = place_id

        self.page = 0

        self.per_page = 10

        self.update_buttons()

    def update_buttons(self):

        self.previous.disabled = (
            self.page <= 0
        )

        self.next.disabled = (
            (self.page + 1)
            * self.per_page
            >= len(self.servers)
        )

    def get_embed(self):

        start = (
            self.page
            * self.per_page
        )

        end = start + self.per_page

        page_servers = self.servers[start:end]

        total_pages = max(
            1,
            (
                len(self.servers)
                + self.per_page
                - 1
            )
            // self.per_page
        )

        embed = discord.Embed(
            title=f"🎮 Servidores públicos",
            description=(
                f"Place ID: `{self.place_id}`\n"
                f"Página `{self.page + 1}/{total_pages}`"
            ),
            color=discord.Color.blurple()
        )

        if not page_servers:

            embed.add_field(
                name="Sin servidores",
                value="No se encontraron servidores.",
                inline=False
            )

        else:

            for index, server in enumerate(
                page_servers,
                start=1
            ):

                playing = server.get(
                    "playing",
                    0
                )

                max_players = server.get(
                    "maxPlayers",
                    0
                )

                job_id = server.get(
                    "id",
                    "Unknown"
                )

                embed.add_field(
                    name=(
                        f"{index}. "
                        f"{playing}/{max_players} jugadores"
                    ),
                    value=(
                        f"Job ID:\n"
                        f"`{job_id}`"
                    ),
                    inline=False
                )

        return embed

    @discord.ui.button(
        label="⬅️",
        style=discord.ButtonStyle.gray
    )
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.page > 0:

            self.page -= 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self
        )

    @discord.ui.button(
        label="➡️",
        style=discord.ButtonStyle.gray
    )
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        max_page = (
            len(self.servers)
            + self.per_page
            - 1
        ) // self.per_page - 1

        if self.page < max_page:

            self.page += 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self
        )


# =========================================================
# !SERVERS
# =========================================================

@bot.command()
async def servers(ctx, place_id):

    await ctx.send(
        f"🔎 Buscando servidores públicos "
        f"para `{place_id}`..."
    )

    all_servers = await asyncio.to_thread(
        get_all_servers,
        place_id
    )

    if not all_servers:

        await ctx.send(
            "❌ No encontré servidores públicos."
        )

        return

    view = ServerPages(
        all_servers,
        place_id
    )

    await ctx.send(
        embed=view.get_embed(),
        view=view
    )


# =========================================================
# ERRORES DE COMANDOS
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ Te falta un argumento.\n\n"
            "Ejemplo:\n"
            "`!watch Builderman`"
        )

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    print(
        "Error de comando:",
        repr(error)
    )


# =========================================================
# INICIAR BOT
# =========================================================

bot.run(TOKEN)