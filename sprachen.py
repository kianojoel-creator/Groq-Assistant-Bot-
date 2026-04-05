# ════════════════════════════════════════════════
#  Sprachen-Cog  •  VHA Alliance
#  Sprachen per Button ein/ausschalten
#  DE + FR immer aktiv
#  PT, EN, JA, ZH, KO per Button steuerbar
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
from pymongo import MongoClient
import os
import logging

log = logging.getLogger("VHABot.Sprachen")

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

# Sprachen die immer aktiv sind
FIXED_LANGS = {"DE", "FR"}

# Sprachen die ein/ausschaltbar sind
OPTIONAL_LANGS = {
    "PT": {"flag": "🇧🇷", "name": "Português"},
    "EN": {"flag": "🇬🇧", "name": "English"},
    "JA": {"flag": "🇯🇵", "name": "日本語"},
    "ZH": {"flag": "🇨🇳", "name": "中文"},
    "KO": {"flag": "🇰🇷", "name": "한국어"},
}

ALLOWED_ROLES = {"R5", "R4", "dev"}


def get_col():
    client = MongoClient(os.getenv("MONGODB_URI"))
    return client["vhabot"]["sprachen"]


def get_active_langs() -> set:
    """Gibt alle aktuell aktiven Sprachen zurück."""
    try:
        col = get_col()
        doc = col.find_one({"_id": "settings"})
        if not doc:
            # Standard: nur PT aktiv
            return {"DE", "FR", "PT"}
        active = set(doc.get("active", ["DE", "FR", "PT"]))
        # DE und FR immer erzwingen
        active.update(FIXED_LANGS)
        return active
    except Exception as e:
        log.error(f"Fehler beim Laden der Sprachen: {e}")
        return {"DE", "FR", "PT"}


def set_active_langs(langs: set):
    """Speichert die aktiven Sprachen in MongoDB."""
    try:
        col = get_col()
        langs.update(FIXED_LANGS)  # DE + FR immer drin
        col.update_one(
            {"_id": "settings"},
            {"$set": {"active": list(langs)}},
            upsert=True
        )
    except Exception as e:
        log.error(f"Fehler beim Speichern der Sprachen: {e}")


def has_permission(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_roles = {r.name.upper() for r in member.roles}
    allowed_upper = {r.upper() for r in ALLOWED_ROLES}
    return bool(member_roles & allowed_upper)


# ────────────────────────────────────────────────
# Button View
# ────────────────────────────────────────────────

class SprachenView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=120)
        self.author = author
        self._update_buttons()

    def _update_buttons(self):
        """Buttons neu erstellen basierend auf aktuellem Status."""
        self.clear_items()
        active = get_active_langs()

        for code, info in OPTIONAL_LANGS.items():
            is_active = code in active
            btn = discord.ui.Button(
                label=f"{info['flag']} {info['name']}",
                style=discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary,
                emoji="✅" if is_active else "❌",
                custom_id=f"lang_{code}"
            )
            btn.callback = self._make_callback(code)
            self.add_item(btn)

    def _make_callback(self, code: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "❌ Nur derjenige der den Befehl ausgeführt hat kann Änderungen vornehmen.",
                    ephemeral=True
                )
                return

            # Direkt aus MongoDB lesen
            try:
                col = get_col()
                doc = col.find_one({"_id": "settings"})
                active = set(doc.get("active", ["DE", "FR"])) if doc else {"DE", "FR"}
                active.update({"DE", "FR"})  # immer drin
            except Exception:
                active = {"DE", "FR"}

            if code in active:
                active.discard(code)
                action = "deaktiviert / désactivé / desativado"
            else:
                active.add(code)
                action = "aktiviert / activé / ativado"

            # Direkt in MongoDB schreiben
            try:
                col = get_col()
                col.update_one(
                    {"_id": "settings"},
                    {"$set": {"active": list(active)}},
                    upsert=True
                )
            except Exception as e:
                await interaction.response.send_message(f"❌ Fehler: {e}", ephemeral=True)
                return

            info = OPTIONAL_LANGS[code]
            self._update_buttons()
            embed = self._make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(
                f"{info['flag']} **{info['name']}** {action}!",
                ephemeral=True
            )

        return callback

    def _make_embed(self) -> discord.Embed:
        active = get_active_langs()
        embed = discord.Embed(
            title="🌐 Spracheinstellungen / Paramètres de langue / Configurações de idioma",
            color=0x3498DB
        )

        # Feste Sprachen
        embed.add_field(
            name="🔒 Immer aktiv / Toujours actif / Sempre ativo",
            value="🇩🇪 Deutsch • 🇫🇷 Français",
            inline=False
        )

        # Schaltbare Sprachen
        status_lines = []
        for code, info in OPTIONAL_LANGS.items():
            status = "✅ Aktiv" if code in active else "❌ Inaktiv"
            status_lines.append(f"{info['flag']} {info['name']}: **{status}**")

        embed.add_field(
            name="🔄 Ein/Ausschaltbar / Activable / Ativável",
            value="\n".join(status_lines),
            inline=False
        )

        embed.set_footer(text="Klicke auf einen Button um eine Sprache ein/auszuschalten")
        return embed


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class SprachenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sprachen", aliases=["languages", "langues", "idiomas", "lang"])
    async def cmd_sprachen(self, ctx):
        """Zeigt Spracheinstellungen mit Buttons."""
        if not has_permission(ctx.author):
            await ctx.send("❌ Keine Berechtigung / Pas d'autorisation / Sem permissão", delete_after=5)
            return

        view = SprachenView(ctx.author)
        embed = view._make_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(SprachenCog(bot))
