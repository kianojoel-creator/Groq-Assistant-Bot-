# ════════════════════════════════════════════════
#  Raumsprachen-Cog  •  VHA Alliance
#  Raum-spezifische Sprachen per Button steuern
#  Funktioniert auf jedem Server • Nur R5 / Dev
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
from pymongo import MongoClient
import os
import logging

log = logging.getLogger("VHABot.Raumsprachen")

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

# Rollen die den Befehl nutzen dürfen
ALLOWED_ROLES = {"R5", "DEV"}

# Alle wählbaren Sprachen pro Raum
ALL_ROOM_LANGS = {
    "DE": {"flag": "🇩🇪", "name": "Deutsch"},
    "FR": {"flag": "🇫🇷", "name": "Français"},
    "PT": {"flag": "🇧🇷", "name": "Português"},
    "EN": {"flag": "🇬🇧", "name": "English"},
    "JA": {"flag": "🇯🇵", "name": "日本語"},
    "ZH": {"flag": "🇨🇳", "name": "中文"},
    "KO": {"flag": "🇰🇷", "name": "한국어"},
}


_mongo_client: MongoClient | None = None

def _get_client() -> MongoClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            os.getenv("MONGODB_URI"),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
    return _mongo_client

def get_col():
    return _get_client()["vhabot"]["raumsprachen"]


def get_room_langs(channel_id: int) -> set | None:
    """
    Gibt die aktiven Sprachen für einen Raum zurück.
    - None  → kein Eintrag → globale Einstellungen verwenden
    - set() → leere Menge / disabled=True → Übersetzung deaktiviert
    - set mit Codes → nur diese Sprachen übersetzen
    """
    try:
        col = get_col()
        doc = col.find_one({"_id": str(channel_id)})
        if not doc:
            return None  # Kein Eintrag → globale Einstellungen
        if doc.get("disabled", False):
            return set()  # Explizit deaktiviert
        active = set(doc.get("active", []))
        if not active:
            return set()  # Leere Liste = deaktiviert
        return active
    except Exception as e:
        log.error(f"Fehler beim Laden der Raumsprachen: {e}")
        return None


def set_room_langs(channel_id: int, langs: set):
    """Speichert die aktiven Sprachen für einen Raum in MongoDB."""
    try:
        col = get_col()
        col.update_one(
            {"_id": str(channel_id)},
            {"$set": {"active": list(langs)}},
            upsert=True
        )
    except Exception as e:
        log.error(f"Fehler beim Speichern der Raumsprachen: {e}")


def delete_room_langs(channel_id: int):
    """Setzt den Raum auf 'deaktiviert' = leere Liste in MongoDB.
    Wichtig: NICHT löschen, sonst fällt app.py auf globale Einstellungen zurück!"""
    try:
        col = get_col()
        col.update_one(
            {"_id": str(channel_id)},
            {"$set": {"active": [], "disabled": True}},
            upsert=True
        )
    except Exception as e:
        log.error(f"Fehler beim Deaktivieren der Raumsprachen: {e}")


def has_permission(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_roles = {r.name.upper() for r in member.roles}
    return bool(member_roles & ALLOWED_ROLES)


# ────────────────────────────────────────────────
# Button View
# ────────────────────────────────────────────────

class RaumSprachenView(discord.ui.View):
    def __init__(self, author: discord.Member, channel_id: int, channel_name: str):
        super().__init__(timeout=180)
        self.author = author
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._update_buttons()

    def _update_buttons(self):
        """Buttons neu erstellen basierend auf aktuellem Status."""
        self.clear_items()
        active = get_room_langs(self.channel_id) or set()

        for code, info in ALL_ROOM_LANGS.items():
            is_active = code in active
            btn = discord.ui.Button(
                label=f"{info['flag']} {info['name']}",
                style=discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary,
                emoji="✅" if is_active else "❌",
                custom_id=f"raumsprache_{self.channel_id}_{code}",
                row=0 if code in ("DE", "FR", "PT", "EN") else 1
            )
            btn.callback = self._make_callback(code)
            self.add_item(btn)

        # Button: Übersetzung für diesen Raum deaktivieren
        disable_btn = discord.ui.Button(
            label="🚫 Übersetzung deaktivieren",
            style=discord.ButtonStyle.danger,
            custom_id=f"raumsprache_{self.channel_id}_DISABLE",
            row=2
        )
        disable_btn.callback = self._disable_callback
        self.add_item(disable_btn)

        # Button: Raum auf globale Einstellungen zurücksetzen
        global_btn = discord.ui.Button(
            label="🌐 Globale Einstellungen",
            style=discord.ButtonStyle.secondary,
            custom_id=f"raumsprache_{self.channel_id}_GLOBAL",
            row=2
        )
        global_btn.callback = self._global_callback
        self.add_item(global_btn)

    def _make_callback(self, code: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "❌ Nur derjenige der den Befehl ausgeführt hat kann Änderungen vornehmen.",
                    ephemeral=True
                )
                return

            # Aktuelle Einstellungen laden
            active = get_room_langs(self.channel_id) or set()

            if code in active:
                active.discard(code)
                action = "deaktiviert"
            else:
                active.add(code)
                action = "aktiviert"

            set_room_langs(self.channel_id, active)

            info = ALL_ROOM_LANGS[code]
            self._update_buttons()
            embed = self._make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(
                f"{info['flag']} **{info['name']}** in <#{self.channel_id}> {action}!",
                ephemeral=True
            )

        return callback

    async def _disable_callback(self, interaction: discord.Interaction):
        """Übersetzung für diesen Raum komplett deaktivieren (in MongoDB gespeichert)."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Nur derjenige der den Befehl ausgeführt hat kann Änderungen vornehmen.",
                ephemeral=True
            )
            return

        delete_room_langs(self.channel_id)  # Speichert disabled=True in MongoDB
        self._update_buttons()
        embed = self._make_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"🚫 Übersetzung für <#{self.channel_id}> **deaktiviert** (bleibt nach Neustart deaktiviert).",
            ephemeral=True
        )

    async def _global_callback(self, interaction: discord.Interaction):
        """Raum auf globale Einstellungen zurücksetzen (Eintrag aus MongoDB löschen)."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Nur derjenige der den Befehl ausgeführt hat kann Änderungen vornehmen.",
                ephemeral=True
            )
            return

        try:
            col = get_col()
            col.delete_one({"_id": str(self.channel_id)})
        except Exception as e:
            await interaction.response.send_message(f"❌ Fehler: {e}", ephemeral=True)
            return

        self._update_buttons()
        embed = self._make_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"🌐 <#{self.channel_id}> nutzt jetzt wieder die **globalen Spracheinstellungen**.",
            ephemeral=True
        )

    def _make_embed(self) -> discord.Embed:
        active = get_room_langs(self.channel_id)
        embed = discord.Embed(
            title=f"🌐 Raumsprachen • #{self.channel_name}",
            description=f"Kanal: <#{self.channel_id}>",
            color=0x3498DB
        )

        if not active:
            embed.add_field(
                name="⚠️ Status",
                value="**Keine Übersetzung aktiv** – dieser Raum wird nicht übersetzt.",
                inline=False
            )
        else:
            aktiv_str = " • ".join(
                f"{ALL_ROOM_LANGS[c]['flag']} {ALL_ROOM_LANGS[c]['name']}"
                for c in ALL_ROOM_LANGS if c in active
            )
            inaktiv_str = " • ".join(
                f"{ALL_ROOM_LANGS[c]['flag']} {ALL_ROOM_LANGS[c]['name']}"
                for c in ALL_ROOM_LANGS if c not in active
            ) or "—"
            embed.add_field(name="✅ Aktiv", value=aktiv_str, inline=False)
            embed.add_field(name="❌ Inaktiv", value=inaktiv_str, inline=False)

        embed.set_footer(
            text="Klicke auf eine Sprache um sie ein/auszuschalten • Nur für diesen Raum",
            icon_url=LOGO_URL
        )
        return embed


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class RaumSprachenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="raumsprachen", aliases=["roomlang", "chanallang"])
    async def cmd_raumsprachen(self, ctx, channel_id: int = None):
        """
        Stellt raum-spezifische Sprachen ein.
        Nur R5 / Dev. Funktioniert auf jedem Server.
        Verwendung: !raumsprachen [Kanal-ID]
        """

        # Berechtigungsprüfung
        if not has_permission(ctx.author):
            await ctx.send("❌ Keine Berechtigung – nur R5 / Dev.", delete_after=5)
            return

        # Kanal bestimmen
        if channel_id is None:
            await ctx.send(
                "❓ **Verwendung:** `!raumsprachen [Kanal-ID]`\n"
                "Beispiel: `!raumsprachen 1234567890123456789`\n\n"
                "💡 Tipp: Rechtsklick auf einen Kanal → *ID kopieren* (Entwicklermodus nötig)",
                delete_after=15
            )
            return

        # Kanal im Server suchen
        channel = ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(f"❌ Kanal mit ID `{channel_id}` nicht gefunden.", delete_after=8)
            return

        view = RaumSprachenView(ctx.author, channel_id, channel.name)
        embed = view._make_embed()
        await ctx.send(embed=embed, view=view)

    @cmd_raumsprachen.error
    async def raumsprachen_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("❌ Ungültige Kanal-ID. Bitte eine gültige Zahl eingeben.", delete_after=8)


async def setup(bot):
    await bot.add_cog(RaumSprachenCog(bot))
