import discord
from discord.ext import commands, tasks
import requests
import asyncio
import os

# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("TOKEN", "").strip()

print("TOKEN existe:", bool(TOKEN))
print("TOKEN longitud:", len(TOKEN))

if not TOKEN:
    raise RuntimeError("No se encontró la variable TOKEN en Railway")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =========================================================
# VARIABLES DE WATCH
# =========================================================

watching_user = None
watching_channel = None
last_status = None

# Para !watchfind
watchfind_enabled = False
watchfind_last_game_id = None


# =========================================================
# ROBLOX - BUSCAR USUARIO
# =========================================================

def get_user(username):
    try:
        response = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={
                "usernames": [username],
                "excludeBannedUsers": False
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        users = response.json().get("data", [])

        if not users:
            return None

        return users[0]

    except Exception as error:
        print("Error buscando usuario:", error)
        return None


# =========================================================
# ROBLOX - PRESENCIA
# =========================================================

def get_presence(user_id):
    try:
        response = requests.post(
            "https://presence.roblox.com/v1/presence/users",
            json={
                "userIds": [user_id]
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        presences = response.json().get("userPresences", [])

        if not presences:
            return None

        return presences[0]

    except Exception as error:
        print("Error obteniendo presencia:", error)
        return None


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
                "isCircular": "false"
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        data = response.json().get("data", [])

        if not data:
            return None

        return data[0].get("imageUrl")

    except Exception as error:
        print("Error obteniendo avatar:", error)
        return None


# =========================================================
# ROBLOX - OBTENER TODOS LOS SERVIDORES PÚBLICOS
# =========================================================

def get_all_servers(place_id):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public"

    all_servers = []
    cursor = None

    while True:
        params = {
            "sortOrder": "Asc",
            "limit": 100
        }

        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(
                url,
                params=params,
                timeout=15
            )

        except Exception as error:
            print("Error consultando servidores:", error)
            break

        if response.status_code != 200:
            print(
                "Roblox respondió:",
                response.status_code,
                response.text[:500]
            )
            break

        data = response.json()

        servers = data.get("data", [])

        all_servers.extend(servers)

        cursor = data.get("nextPageCursor")

        if not cursor:
            break

    # Ordenar de más vacío a más lleno
    all_servers.sort(
        key=lambda server: server.get("playing", 0)
    )

    return all_servers


# =========================================================
# CREAR LINK PARA UNIRSE AL SERVIDOR
# =========================================================

def create_join_link(place_id, game_id):
    return (
        "roblox://experiences/start?"
        f"placeId={place_id}&"
        f"gameInstanceId={game_id}"
    )


# =========================================================
# BOT LISTO
# =========================================================

@bot.event
async def on_ready():

    print(f"Bot conectado como {bot.user}")

    try:
        await bot.change_presence(
            activity=discord.Game(
                name="Roblox Sniper"
            )
        )
    except Exception:
        pass


# =========================================================
# !SNIPE
# =========================================================

@bot.command()
async def snipe(ctx, username):

    await ctx.send(
        f"🔎 Buscando a `{username}` en Roblox..."
    )

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:
        await ctx.send(
            "❌ No encontré ese usuario."
        )
        return

    user_id = user["id"]

    presence = await asyncio.to_thread(
        get_presence,
        user_id
    )

    if not presence:
        await ctx.send(
            "❌ No pude comprobar la presencia."
        )
        return

    status = presence.get(
        "userPresenceType"
    )

    # Offline
    if status == 0:

        await ctx.send(
            f"🔴 `{user['name']}` está desconectado."
        )

        return

    # Online pero sin jugar
    if status == 1:

        await ctx.send(
            f"🟡 `{user['name']}` está en Roblox, "
            "pero no está jugando."
        )

        return

    # Roblox Studio
    if status == 3:

        await ctx.send(
            f"🟡 `{user['name']}` está en Roblox Studio."
        )

        return

    # Jugando
    if status == 2:

        place_id = presence.get("placeId")
        game_id = presence.get("gameId")

        message = (
            f"🟢 **{user['name']} está jugando!**\n\n"
            f"**User ID:** `{user_id}`\n"
            f"**Place ID:** `{place_id}`\n"
            f"**Game ID:** `{game_id}`"
        )

        if place_id and game_id:

            join_link = create_join_link(
                place_id,
                game_id
            )

            message += (
                f"\n\n🔗 **Intentar unirse:**\n"
                f"{join_link}"
            )

        await ctx.send(message)


# =========================================================
# !WATCH
# =========================================================

@bot.command()
async def watch(ctx, username):

    global watching_user
    global watching_channel
    global last_status
    global watchfind_enabled
    global watchfind_last_game_id

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            "❌ No encontré ese usuario."
        )

        return

    watching_user = user
    watching_channel = ctx.channel

    last_status = None

    watchfind_enabled = False
    watchfind_last_game_id = None

    await ctx.send(
        f"👁️ Ahora estoy vigilando a "
        f"**{user['name']}**.\n"
        "Comprobaré su presencia automáticamente "
        "cada 15 segundos."
    )

    if not check_presence.is_running():
        check_presence.start()


# =========================================================
# !WATCHFIND
# =========================================================

@bot.command()
async def watchfind(ctx, username):

    global watching_user
    global watching_channel
    global last_status
    global watchfind_enabled
    global watchfind_last_game_id

    user = await asyncio.to_thread(
        get_user,
        username
    )

    if not user:

        await ctx.send(
            "❌ No encontré ese usuario."
        )

        return

    watching_user = user
    watching_channel = ctx.channel

    last_status = None

    watchfind_enabled = True
    watchfind_last_game_id = None

    await ctx.send(
        f" **WatchFind activado para `{user['name']}`**\n\n"
        " Comprobaré su presencia cada 15 segundos.\n"
        " Cuando empiece a jugar, buscaré su servidor "
        "entre los servidores públicos y te avisaré."
    )

    if not check_presence.is_running():
        check_presence.start()


# =========================================================
# !UNWATCH
# =========================================================

@bot.command()
async def unwatch(ctx):

    global watching_user
    global watching_channel
    global last_status
    global watchfind_enabled
    global watchfind_last_game_id

    watching_user = None
    watching_channel = None

    last_status = None

    watchfind_enabled = False
    watchfind_last_game_id = None

    await ctx.send(
        "🛑 Dejé de vigilar al usuario."
    )


# =========================================================
# CREAR TARJETA DE !FIND
# =========================================================

class FindView(discord.ui.View):

    def __init__(
        self,
        ctx,
        username,
        place_id,
        game_id
    ):

        super().__init__(timeout=300)

        self.ctx = ctx
        self.username = username
        self.place_id = place_id
        self.game_id = game_id

        self.join_url = create_join_link(
            place_id,
            game_id
        )

    @discord.ui.button(
        label="Unirse al servidor",
        emoji="🎮",
        style=discord.ButtonStyle.success
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.user.id != self.ctx.author.id:

            await interaction.response.send_message(
                "❌ Solo la persona que ejecutó "
                "el comando puede usar este botón.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"🎮 **Servidor encontrado**\n\n"
            f"🔗 {self.join_url}",
            ephemeral=True
        )


async def create_find_card(
    ctx,
    user,
    presence,
    server
):

    user_id = user["id"]
    username = user["name"]

    place_id = presence.get("placeId")
    game_id = presence.get("gameId")

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
        "Desconocido"
    )

    avatar_url = await asyncio.to_thread(
        get_avatar,
        user_id
    )

    embed = discord.Embed(
        title="🎯 Usuario encontrado",
        description=(
            f"🟢 **{username} está jugando actualmente**"
        )
    )

    if avatar_url:

        embed.set_thumbnail(
            url=avatar_url
        )

    embed.add_field(
        name="👤 Usuario",
        value=f"`{username}`",
        inline=False
    )

    embed.add_field(
        name="🆔 User ID",
        value=f"`{user_id}`",
        inline=False
    )

    embed.add_field(
        name="🎮 Place ID",
        value=f"`{place_id}`",
        inline=False
    )

    embed.add_field(
        name="👥 Jugadores",
        value=f"`{playing}/{max_players}`",
        inline=False
    )

    embed.add_field(
        name="🆔 Job ID",
        value=f"`{job_id}`",
        inline=False
    )

    embed.add_field(
        name="📡 Estado",
        value="🟢 Jugando",
        inline=False
    )

    embed.set_footer(
        text="Roblox Server Finder"
    )

    view = FindView(
        ctx,
        username,
        place_id,
        game_id
    )

    return embed, view


# =========================================================
# !FIND
# =========================================================

@bot.command()
async def find(ctx, username):

    searching = await ctx.send(
        f"🔎 **Buscando a `{username}`...**\n"
        "Obteniendo información de Roblox."
    )

    try:

        user = await asyncio.to_thread(
            get_user,
            username
        )

        if not user:

            await searching.edit(
                content=(
                    f"❌ No encontré al usuario "
                    f"`{username}`."
                )
            )

            return

        user_id = user["id"]

        presence = await asyncio.to_thread(
            get_presence,
            user_id
        )

        if not presence:

            await searching.edit(
                content=(
                    "❌ No pude obtener la "
                    "presencia del usuario."
                )
            )

            return

        status = presence.get(
            "userPresenceType"
        )

        # Offline
        if status == 0:

            await searching.edit(
                content=(
                    f"🔴 **{user['name']}** "
                    "está desconectado."
                )
            )

            return

        # Online
        if status == 1:

            await searching.edit(
                content=(
                    f"🟡 **{user['name']}** está "
                    "en Roblox, pero actualmente "
                    "no está jugando."
                )
            )

            return

        # Studio
        if status == 3:

            await searching.edit(
                content=(
                    f"🟡 **{user['name']}** "
                    "está en Roblox Studio."
                )
            )

            return

        # No jugando
        if status != 2:

            await searching.edit(
                content=(
                    "❌ Estado de presencia "
                    "desconocido."
                )
            )

            return

        place_id = presence.get(
            "placeId"
        )

        game_id = presence.get(
            "gameId"
        )

        if not place_id or not game_id:

            await searching.edit(
                content=(
                    f"🟡 **{user['name']}** está jugando, "
                    "pero Roblox no proporcionó "
                    "el servidor."
                )
            )

            return

        await searching.edit(
            content=(
                f"🔎 **{user['name']} está jugando.**\n"
                "Buscando su servidor entre los "
                "servidores públicos..."
            )
        )

        servers = await asyncio.to_thread(
            get_all_servers,
            int(place_id)
        )

        found_server = None

        for server in servers:

            if server.get("id") == game_id:

                found_server = server

                break

        # No encontrado
        if found_server is None:

            embed = discord.Embed(
                title="🟡 Usuario encontrado",
                description=(
                    f"**{user['name']}** está jugando, "
                    "pero su servidor no apareció "
                    "en la lista pública."
                )
            )

            avatar_url = await asyncio.to_thread(
                get_avatar,
                user_id
            )

            if avatar_url:

                embed.set_thumbnail(
                    url=avatar_url
                )

            embed.add_field(
                name="👤 Usuario",
                value=f"`{user['name']}`",
                inline=False
            )

            embed.add_field(
                name="🆔 User ID",
                value=f"`{user_id}`",
                inline=False
            )

            embed.add_field(
                name="🎮 Place ID",
                value=f"`{place_id}`",
                inline=False
            )

            embed.add_field(
                name="🆔 Game ID",
                value=f"`{game_id}`",
                inline=False
            )

            embed.set_footer(
                text=(
                    f"Se revisaron "
                    f"{len(servers)} servidores públicos."
                )
            )

            await searching.edit(
                content=None,
                embed=embed,
                view=None
            )

            return

        # Encontrado
        embed, view = await create_find_card(
            ctx,
            user,
            presence,
            found_server
        )

        await searching.edit(
            content=None,
            embed=embed,
            view=view
        )

    except Exception as error:

        print(
            "ERROR EN !find:",
            error
        )

        await searching.edit(
            content=(
                "❌ Ocurrió un error al "
                "buscar el servidor."
            ),
            embed=None,
            view=None
        )


# =========================================================
# WATCHFIND - CREAR TARJETA
# =========================================================

async def send_watchfind_result(
    channel,
    user,
    presence
):

    user_id = user["id"]
    username = user["name"]

    place_id = presence.get(
        "placeId"
    )

    game_id = presence.get(
        "gameId"
    )

    if not place_id or not game_id:

        await channel.send(
            f"🟡 **{username}** está jugando, "
            "pero Roblox no proporcionó "
            "el servidor."
        )

        return

    await channel.send(
        f"🔎 **{username} está jugando!**\n"
        "Buscando su servidor público..."
    )

    servers = await asyncio.to_thread(
        get_all_servers,
        int(place_id)
    )

    found_server = None

    for server in servers:

        if server.get("id") == game_id:

            found_server = server

            break

    # No apareció en servidores públicos
    if found_server is None:

        embed = discord.Embed(
            title="🟡 Usuario jugando",
            description=(
                f"**{username}** está jugando, "
                "pero su servidor no apareció "
                "en la lista pública."
            )
        )

        avatar_url = await asyncio.to_thread(
            get_avatar,
            user_id
        )

        if avatar_url:

            embed.set_thumbnail(
                url=avatar_url
            )

        embed.add_field(
            name="👤 Usuario",
            value=f"`{username}`",
            inline=False
        )

        embed.add_field(
            name="🆔 User ID",
            value=f"`{user_id}`",
            inline=False
        )

        embed.add_field(
            name="🎮 Place ID",
            value=f"`{place_id}`",
            inline=False
        )

        embed.add_field(
            name="🆔 Game ID",
            value=f"`{game_id}`",
            inline=False
        )

        embed.set_footer(
            text=(
                f"Se revisaron {len(servers)} "
                "servidores públicos."
            )
        )

        await channel.send(
            embed=embed
        )

        return

    # Servidor encontrado
    playing = found_server.get(
        "playing",
        0
    )

    max_players = found_server.get(
        "maxPlayers",
        0
    )

    job_id = found_server.get(
        "id",
        "Desconocido"
    )

    avatar_url = await asyncio.to_thread(
        get_avatar,
        user_id
    )

    embed = discord.Embed(
        title="🎯 ¡SERVIDOR ENCONTRADO!",
        description=(
            f"🟢 **{username} está jugando actualmente**"
        )
    )

    if avatar_url:

        embed.set_thumbnail(
            url=avatar_url
        )

    embed.add_field(
        name="👤 Usuario",
        value=f"`{username}`",
        inline=False
    )

    embed.add_field(
        name="🆔 User ID",
        value=f"`{user_id}`",
        inline=False
    )

    embed.add_field(
        name="🎮 Place ID",
        value=f"`{place_id}`",
        inline=False
    )

    embed.add_field(
        name="👥 Jugadores",
        value=f"`{playing}/{max_players}`",
        inline=False
    )

    embed.add_field(
        name="🆔 Job ID",
        value=f"`{job_id}`",
        inline=False
    )

    embed.add_field(
        name="📡 Estado",
        value="🟢 Jugando",
        inline=False
    )

    embed.set_footer(
        text="Roblox WatchFind"
    )

    join_url = create_join_link(
        place_id,
        game_id
    )

    view = discord.ui.View(
        timeout=300
    )

    button = discord.ui.Button(
        label="Unirse al servidor",
        emoji="🎮",
        style=discord.ButtonStyle.success
    )

    async def join_callback(
        interaction: discord.Interaction
    ):

        await interaction.response.send_message(
            f"🎮 **Servidor encontrado**\n\n"
            f"🔗 {join_url}",
            ephemeral=True
        )

    button.callback = join_callback

    view.add_item(button)

    await channel.send(
        embed=embed,
        view=view
    )


# =========================================================
# LOOP DE WATCH / WATCHFIND
# =========================================================

@tasks.loop(seconds=15)
async def check_presence():

    global last_status
    global watchfind_last_game_id

    if watching_user is None:
        return

    if watching_channel is None:
        return

    presence = await asyncio.to_thread(
        get_presence,
        watching_user["id"]
    )

    if not presence:
        return

    status = presence.get(
        "userPresenceType"
    )

    # =====================================================
    # WATCHFIND
    # =====================================================

    if watchfind_enabled:

        if status == 2:

            place_id = presence.get(
                "placeId"
            )

            game_id = presence.get(
                "gameId"
            )

            # Si no hay game ID
            if not game_id:

                return

            # Ya avisamos de este servidor
            if game_id == watchfind_last_game_id:

                return

            # Nuevo servidor
            watchfind_last_game_id = game_id

            await send_watchfind_result(
                watching_channel,
                watching_user,
                presence
            )

            return

        # Si dejó de jugar,
        # permitimos detectar nuevamente
        # cuando vuelva a entrar.
        if status != 2:

            watchfind_last_game_id = None

        return

    # =====================================================
    # WATCH NORMAL
    # =====================================================

    if status == last_status:

        return

    last_status = status

    if status == 0:

        await watching_channel.send(
            f"🔴 **{watching_user['name']}** "
            "está desconectado."
        )

    elif status == 1:

        await watching_channel.send(
            f"🟡 **{watching_user['name']}** "
            "está en Roblox, pero no jugando."
        )

    elif status == 2:

        place_id = presence.get(
            "placeId"
        )

        game_id = presence.get(
            "gameId"
        )

        message = (
            f"🟢 **{watching_user['name']} está jugando!**\n\n"
            f"**Place ID:** `{place_id}`\n"
            f"**Game ID:** `{game_id}`"
        )

        if place_id and game_id:

            join_link = create_join_link(
                place_id,
                game_id
            )

            message += (
                f"\n\n🔗 **Intentar unirse:**\n"
                f"{join_link}"
            )

        await watching_channel.send(
            message
        )

    elif status == 3:

        await watching_channel.send(
            f"🟡 **{watching_user['name']}** "
            "está en Roblox Studio."
        )


# =========================================================
# SERVIDORES - PAGINACIÓN
# =========================================================

class ServerPages(discord.ui.View):

    def __init__(
        self,
        ctx,
        place_id,
        servers
    ):

        super().__init__(
            timeout=300
        )

        self.ctx = ctx
        self.place_id = place_id
        self.servers = servers

        self.page = 0
        self.per_page = 10
        self.message = None

        self.update_buttons()

    @property
    def total_pages(self):

        return max(
            1,
            (
                len(self.servers)
                + self.per_page
                - 1
            )
            // self.per_page
        )

    def update_buttons(self):

        self.previous_button.disabled = (
            self.page <= 0
        )

        self.next_button.disabled = (
            self.page >= self.total_pages - 1
        )

    def create_embed(self):

        start = (
            self.page
            * self.per_page
        )

        end = start + self.per_page

        current_servers = self.servers[
            start:end
        ]

        embed = discord.Embed(
            title="🎮 Servidores públicos",
            description=(
                f"**Place ID:** `{self.place_id}`\n"
                "📊 Más vacío → más lleno\n"
                f"📦 Servidores: **{len(self.servers)}**"
            )
        )

        for i, server in enumerate(
            current_servers,
            start=start + 1
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
                "Desconocido"
            )

            embed.add_field(
                name=(
                    f"#{i}  👥 "
                    f"{playing}/{max_players}"
                ),
                value=(
                    f"Job ID: `{job_id}`"
                ),
                inline=False
            )

        embed.set_footer(
            text=(
                f"Página "
                f"{self.page + 1}/"
                f"{self.total_pages}"
            )
        )

        return embed

    @discord.ui.button(
        label="Anterior",
        emoji="⬅️",
        style=discord.ButtonStyle.secondary
    )
    async def previous_button(
        self,
        interaction,
        button
    ):

        if interaction.user.id != self.ctx.author.id:

            await interaction.response.send_message(
                "❌ No puedes controlar esta búsqueda.",
                ephemeral=True
            )

            return

        if self.page > 0:

            self.page -= 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )

    @discord.ui.button(
        label="Siguiente",
        emoji="➡️",
        style=discord.ButtonStyle.secondary
    )
    async def next_button(
        self,
        interaction,
        button
    ):

        if interaction.user.id != self.ctx.author.id:

            await interaction.response.send_message(
                "❌ No puedes controlar esta búsqueda.",
                ephemeral=True
            )

            return

        if self.page < self.total_pages - 1:

            self.page += 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self
        )

    @discord.ui.button(
        label="Actualizar",
        emoji="🔄",
        style=discord.ButtonStyle.primary
    )
    async def refresh_button(
        self,
        interaction,
        button
    ):

        if interaction.user.id != self.ctx.author.id:

            await interaction.response.send_message(
                "❌ No puedes controlar esta búsqueda.",
                ephemeral=True
            )

            return

        await interaction.response.defer()

        self.servers = await asyncio.to_thread(
            get_all_servers,
            self.place_id
        )

        self.page = 0

        self.update_buttons()

        await interaction.edit_original_response(
            embed=self.create_embed(),
            view=self
        )

    async def on_timeout(self):

        for item in self.children:

            item.disabled = True

        if self.message:

            try:

                await self.message.edit(
                    view=self
                )

            except Exception:
                pass


# =========================================================
# !SERVERS
# =========================================================

@bot.command()
async def servers(ctx, place_id: int):

    searching = await ctx.send(
        f"🔎 Buscando servidores públicos "
        f"de `{place_id}`..."
    )

    try:

        servers = await asyncio.to_thread(
            get_all_servers,
            place_id
        )

        if not servers:

            await searching.edit(
                content=(
                    "❌ No encontré "
                    "servidores públicos."
                ),
                embed=None,
                view=None
            )

            return

        view = ServerPages(
            ctx,
            place_id,
            servers
        )

        embed = view.create_embed()

        await searching.edit(
            content=None,
            embed=embed,
            view=view
        )

        view.message = searching

    except Exception as error:

        print(
            "ERROR EN !servers:",
            error
        )

        await searching.edit(
            content=(
                "❌ Ocurrió un error al "
                "consultar los servidores."
            ),
            embed=None,
            view=None
        )


# =========================================================
# INICIAR BOT
# =========================================================

bot.run(TOKEN)