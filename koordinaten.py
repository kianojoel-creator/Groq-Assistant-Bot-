# ════════════════════════════════════════════════
#  Koordinaten-Cog  •  Mecha Fire
#  Separate Datei – wird von app.py geladen
#  Erlaubte Rollen: Administrator, R5, R4
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import json
import os

# Pfad zur JSON-Datei (liegt im selben Ordner wie app.py)
DATA_FILE = "koordinaten.json"

# Rollen die Koordinaten hinzufügen/löschen dürfen
ALLOWED_ROLES = {"R5", "R4"}


# ────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────

def load_data() -> list:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("koordinaten", [])


def save_data(koordinaten: list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"koordinaten": koordinaten}, f, indent=2, ensure_ascii=False)


def has_permission(member: discord.Member) -> bool:
    """Prüft ob der User Administrator oder R5/R4 ist."""
    if member.guild_permissions.administrator:
        return True
    return any(r.name in ALLOWED_ROLES for r in member.roles)


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class KoordinatenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── !koordinaten ─────────────────────────────
    @commands.group(name="koordinaten", aliases=["coord", "coords", "koordinate", "coordonnees", "coordonnée", "coordonnées"], invoke_without_command=True)
    async def koordinaten(self, ctx):
        """Zeigt alle gespeicherten Koordinaten an."""
        data = load_data()

        if not data:
            await ctx.send(
                "📭 Keine Koordinaten gespeichert.\n"
                "Aucune coordonnée enregistrée."
            )
            return

        # Auflistung als Embed
        embed = discord.Embed(
            title="📍 Koordinaten • Mecha Fire",
            color=0x2ECC71
        )

        # Koordinaten als schöne Tabelle formatieren
        lines = []
        for k in sorted(data, key=lambda x: x["name"].lower()):
            lines.append(f"`{k['name']:<6}` R:{k['r']}, X:{k['x']}, Y:{k['y']}")

        # Discord Embed Felder max. 1024 Zeichen → aufteilen falls nötig
        chunk = ""
        field_num = 1
        for line in lines:
            if len(chunk) + len(line) + 1 > 1000:
                embed.add_field(
                    name=f"Allianzen {field_num}" if field_num > 1 else "Allianzen / Alliances",
                    value=chunk,
                    inline=False
                )
                chunk = line + "\n"
                field_num += 1
            else:
                chunk += line + "\n"

        if chunk:
            embed.add_field(
                name=f"Allianzen {field_num}" if field_num > 1 else "Allianzen / Alliances",
                value=chunk,
                inline=False
            )

        embed.set_footer(text=f"Gesamt / Total: {len(data)} • !koordinaten add/delete")
        await ctx.send(embed=embed)

    # ── !koordinaten add ─────────────────────────
    @koordinaten.command(name="add", aliases=["hinzufügen", "ajouter", "ajout"])
    async def koordinaten_add(self, ctx, name: str, r: int, x: int, y: int):
        """
        Fügt eine neue Koordinate hinzu.
        Nutzung: !koordinaten add NAME R X Y
        Beispiel: !koordinaten add VHA 75 217 802
        """
        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation",
                description=(
                    "Nur **Administrator**, **R5** und **R4** dürfen Koordinaten hinzufügen.\n"
                    "Seuls les **Administrateur**, **R5** et **R4** peuvent ajouter des coordonnées."
                ),
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        data = load_data()

        # Prüfen ob Name schon existiert
        if any(k["name"].lower() == name.lower() for k in data):
            embed = discord.Embed(
                title="⚠️ Bereits vorhanden / Déjà existant",
                description=(
                    f"`{name}` existiert bereits. Zuerst löschen mit `!koordinaten delete {name}`\n"
                    f"`{name}` existe déjà. Supprime d'abord avec `!koordinaten delete {name}`"
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed)
            return

        data.append({"name": name, "r": r, "x": x, "y": y})
        save_data(data)

        embed = discord.Embed(
            title="✅ Koordinate hinzugefügt / Coordonnée ajoutée",
            color=0x57F287
        )
        embed.add_field(
            name=name,
            value=f"R:{r}, X:{x}, Y:{y}",
            inline=False
        )
        embed.set_footer(text=f"Hinzugefügt von / Ajouté par {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @koordinaten_add.error
    async def add_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "❓ Nutzung: `!koordinaten add NAME R X Y`\n"
                "Exemple: `!koordinaten add VHA 75 217 802`"
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                "❌ R, X und Y müssen Zahlen sein.\n"
                "R, X et Y doivent être des nombres."
            )

    # ── !koordinaten delete ──────────────────────
    @koordinaten.command(name="delete", aliases=["löschen", "supprimer", "effacer", "del", "remove"])
    async def koordinaten_delete(self, ctx, *, name: str):
        """
        Löscht eine Koordinate.
        Nutzung: !koordinaten delete NAME
        """
        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation",
                description=(
                    "Nur **Administrator**, **R5** und **R4** dürfen Koordinaten löschen.\n"
                    "Seuls les **Administrateur**, **R5** et **R4** peuvent supprimer des coordonnées."
                ),
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        data = load_data()
        original_len = len(data)
        data = [k for k in data if k["name"].lower() != name.lower()]

        if len(data) == original_len:
            embed = discord.Embed(
                title="⚠️ Nicht gefunden / Introuvable",
                description=(
                    f"`{name}` wurde nicht gefunden.\n"
                    f"`{name}` n'a pas été trouvé."
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed)
            return

        save_data(data)

        embed = discord.Embed(
            title="🗑️ Koordinate gelöscht / Coordonnée supprimée",
            description=f"`{name}` wurde erfolgreich entfernt.\n`{name}` a été supprimé avec succès.",
            color=0xED4245
        )
        embed.set_footer(text=f"Gelöscht von / Supprimé par {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── !koordinaten help ────────────────────────
    @koordinaten.command(name="help", aliases=["hilfe", "aide", "aider"])
    async def koordinaten_help(self, ctx):
        embed = discord.Embed(
            title="📍 Koordinaten – Hilfe / Aide",
            color=0x3498DB
        )
        embed.add_field(
            name="🇩🇪 Befehle",
            value=(
                "`!koordinaten` – Alle Koordinaten anzeigen\n"
                "`!koordinaten add NAME R X Y` – Neue hinzufügen\n"
                "`!koordinaten delete NAME` – Löschen\n\n"
                "**Beispiel:** `!koordinaten add VHA 75 217 802`"
            ),
            inline=False
        )
        embed.add_field(
            name="🇫🇷 Commandes",
            value=(
                "`!koordinaten` – Afficher toutes les coordonnées\n"
                "`!koordinaten add NOM R X Y` – Ajouter\n"
                "`!koordinaten delete NOM` – Supprimer\n\n"
                "**Exemple:** `!koordinaten add VHA 75 217 802`"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Berechtigung / Permission",
            value="Administrator, R5, R4",
            inline=False
        )
        await ctx.send(embed=embed)


# ────────────────────────────────────────────────
# Setup – wird von app.py aufgerufen
# ────────────────────────────────────────────────

async def setup(bot):
    await bot.add_cog(KoordinatenCog(bot))
