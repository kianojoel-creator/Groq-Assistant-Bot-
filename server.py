# ════════════════════════════════════════════════
#  server.py  •  VHA Alliance
#  Server-Struktur exportieren & importieren
#  Speichert Kategorien + Kanäle in MongoDB
#  Nur R5 / Administrator
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
from pymongo import MongoClient
import os
import logging
import asyncio

log = logging.getLogger("VHABot.Server")

ALLOWED_ROLES = {"R5", "DEV"}

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

# ────────────────────────────────────────────────
# MongoDB
# ────────────────────────────────────────────────

_mongo_client = None

def get_col():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(os.getenv("MONGODB_URI"))
    return _mongo_client["vhabot"]["server_struktur"]


# ────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────

def has_permission(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_roles = {r.name.upper() for r in member.roles}
    return bool(member_roles & ALLOWED_ROLES)


def channel_type_str(ch) -> str:
    if isinstance(ch, discord.TextChannel):
        return "text"
    elif isinstance(ch, discord.VoiceChannel):
        return "voice"
    elif isinstance(ch, discord.ForumChannel):
        return "forum"
    elif isinstance(ch, discord.StageChannel):
        return "stage"
    else:
        return "text"


# ────────────────────────────────────────────────
# Bestätigungs-View für Import
# ────────────────────────────────────────────────

class ImportConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member, struktur: dict):
        super().__init__(timeout=60)
        self.author = author
        self.struktur = struktur
        self.confirmed = False

    @discord.ui.button(label="✅ Ja, importieren", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Nur der Aufrufer kann bestätigen.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(
            content="⏳ **Import läuft...** Bitte warten.",
            embed=None,
            view=None
        )

    @discord.ui.button(label="❌ Abbrechen", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Nur der Aufrufer kann abbrechen.", ephemeral=True)
            return
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(
            content="❌ Import abgebrochen.",
            embed=None,
            view=None
        )


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class ServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="server", invoke_without_command=True)
    async def server(self, ctx):
        embed = discord.Embed(
            title="🏗️ Server-Struktur • Befehle",
            color=0x5865F2
        )
        embed.add_field(
            name="📤 Exportieren",
            value="`!server export` – Aktuelle Server-Struktur in MongoDB speichern",
            inline=False
        )
        embed.add_field(
            name="📋 Vorschau",
            value="`!server preview` – Gespeicherte Struktur anzeigen",
            inline=False
        )
        embed.add_field(
            name="📥 Importieren",
            value="`!server import` – Struktur auf diesem Server erstellen",
            inline=False
        )
        embed.add_field(
            name="🔐 Berechtigung",
            value="Administrator • R5",
            inline=False
        )
        embed.set_footer(text="VHA Alliance • Server-Tool", icon_url=LOGO_URL)
        await ctx.send(embed=embed)

    # ── !server export ────────────────────────────
    @server.command(name="export")
    async def server_export(self, ctx):
        if not has_permission(ctx.author):
            await ctx.send("❌ Keine Berechtigung.", delete_after=5)
            return

        msg = await ctx.send("⏳ **Exportiere Server-Struktur...**")

        try:
            struktur = {
                "guild_name": ctx.guild.name,
                "guild_id": str(ctx.guild.id),
                "exported_by": ctx.author.display_name,
                "kategorien": []
            }

            # Kategorien + Kanäle in Reihenfolge
            for category, channels in ctx.guild.by_category():
                kat_data = {
                    "name": category.name if category else "Ohne Kategorie",
                    "position": category.position if category else -1,
                    "kanaele": []
                }

                for ch in sorted(channels, key=lambda c: c.position):
                    ch_data = {
                        "name": ch.name,
                        "type": channel_type_str(ch),
                        "position": ch.position,
                        "topic": getattr(ch, "topic", None) or "",
                        "nsfw": getattr(ch, "nsfw", False),
                        "slowmode": getattr(ch, "slowmode_delay", 0),
                    }
                    kat_data["kanaele"].append(ch_data)

                struktur["kategorien"].append(kat_data)

            # In MongoDB speichern (überschreibt vorherigen Export)
            col = get_col()
            col.replace_one({"_id": "export"}, {"_id": "export", **struktur}, upsert=True)

            # Statistik
            total_cats = len(struktur["kategorien"])
            total_channels = sum(len(k["kanaele"]) for k in struktur["kategorien"])

            embed = discord.Embed(
                title="✅ Server-Struktur exportiert!",
                color=0x57F287
            )
            embed.add_field(name="🏠 Server", value=ctx.guild.name, inline=True)
            embed.add_field(name="📁 Kategorien", value=str(total_cats), inline=True)
            embed.add_field(name="💬 Kanäle", value=str(total_channels), inline=True)
            embed.add_field(
                name="💾 Gespeichert",
                value="MongoDB • `server_struktur`\nMit `!server import` auf neuem Server einspielen",
                inline=False
            )
            embed.set_footer(text=f"Exportiert von {ctx.author.display_name}", icon_url=LOGO_URL)
            await msg.edit(content=None, embed=embed)

        except Exception as e:
            log.error(f"Export-Fehler: {e}")
            await msg.edit(content=f"❌ Fehler beim Exportieren: {e}")

    # ── !server preview ───────────────────────────
    @server.command(name="preview")
    async def server_preview(self, ctx):
        if not has_permission(ctx.author):
            await ctx.send("❌ Keine Berechtigung.", delete_after=5)
            return

        try:
            col = get_col()
            doc = col.find_one({"_id": "export"})
        except Exception as e:
            await ctx.send(f"❌ Fehler beim Laden: {e}")
            return

        if not doc:
            await ctx.send("📭 Kein Export gefunden. Zuerst `!server export` ausführen.")
            return

        embed = discord.Embed(
            title=f"📋 Server-Struktur • {doc.get('guild_name', 'Unbekannt')}",
            color=0x3498DB
        )

        total_channels = 0
        for kat in doc.get("kategorien", []):
            kanaele = kat.get("kanaele", [])
            total_channels += len(kanaele)

            if not kanaele:
                continue

            # Kanal-Liste aufbauen
            lines = []
            for ch in kanaele:
                icon = "💬" if ch["type"] == "text" else "🔊" if ch["type"] == "voice" else "📋"
                lines.append(f"{icon} {ch['name']}")

            # Aufteilen falls zu lang
            value = "\n".join(lines)
            if len(value) > 1000:
                value = value[:997] + "..."

            embed.add_field(
                name=f"📁 {kat['name']} ({len(kanaele)} Kanäle)",
                value=value,
                inline=False
            )

        embed.set_footer(
            text=f"Gesamt: {len(doc.get('kategorien', []))} Kategorien • {total_channels} Kanäle • "
                 f"Exportiert von {doc.get('exported_by', '?')}",
            icon_url=LOGO_URL
        )
        await ctx.send(embed=embed)

    # ── !server import ────────────────────────────
    @server.command(name="import")
    async def server_import(self, ctx):
        if not has_permission(ctx.author):
            await ctx.send("❌ Keine Berechtigung.", delete_after=5)
            return

        # Export laden
        try:
            col = get_col()
            doc = col.find_one({"_id": "export"})
        except Exception as e:
            await ctx.send(f"❌ Fehler beim Laden: {e}")
            return

        if not doc:
            await ctx.send("📭 Kein Export gefunden. Zuerst `!server export` auf dem alten Server ausführen.")
            return

        total_cats = len(doc.get("kategorien", []))
        total_channels = sum(len(k["kanaele"]) for k in doc.get("kategorien", []))

        # Bestätigung einholen
        embed = discord.Embed(
            title="⚠️ Server-Import bestätigen",
            description=(
                f"Es werden **{total_cats} Kategorien** und **{total_channels} Kanäle** "
                f"auf **{ctx.guild.name}** erstellt.\n\n"
                "⚠️ Bestehende Kanäle werden **nicht gelöscht** — nur neue hinzugefügt.\n"
                "Bist du sicher?"
            ),
            color=0xF39C12
        )
        embed.add_field(
            name="📤 Quelle",
            value=doc.get("guild_name", "Unbekannt"),
            inline=True
        )
        embed.add_field(
            name="📥 Ziel",
            value=ctx.guild.name,
            inline=True
        )

        view = ImportConfirmView(ctx.author, doc)
        confirm_msg = await ctx.send(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            return

        # Import durchführen
        created_cats = 0
        created_channels = 0
        errors = []

        try:
            for kat in sorted(doc.get("kategorien", []), key=lambda k: k.get("position", 0)):
                kat_name = kat["name"]

                # Kategorie erstellen (falls nicht vorhanden)
                if kat_name == "Ohne Kategorie":
                    category_obj = None
                else:
                    # Prüfen ob Kategorie bereits existiert
                    category_obj = discord.utils.get(ctx.guild.categories, name=kat_name)
                    if category_obj is None:
                        try:
                            category_obj = await ctx.guild.create_category(
                                name=kat_name,
                                position=kat.get("position", 0)
                            )
                            created_cats += 1
                            await asyncio.sleep(0.5)  # Rate-Limit vermeiden
                        except Exception as e:
                            errors.append(f"Kategorie '{kat_name}': {e}")
                            continue

                # Kanäle erstellen
                for ch in sorted(kat.get("kanaele", []), key=lambda c: c.get("position", 0)):
                    ch_name = ch["name"]
                    ch_type = ch.get("type", "text")

                    # Prüfen ob Kanal bereits existiert
                    existing = discord.utils.get(ctx.guild.channels, name=ch_name)
                    if existing:
                        continue  # Bereits vorhanden → überspringen

                    try:
                        kwargs = {
                            "name": ch_name,
                            "category": category_obj,
                            "position": ch.get("position", 0),
                        }

                        if ch_type == "text":
                            if ch.get("topic"):
                                kwargs["topic"] = ch["topic"]
                            if ch.get("nsfw"):
                                kwargs["nsfw"] = ch["nsfw"]
                            if ch.get("slowmode"):
                                kwargs["slowmode_delay"] = ch["slowmode"]
                            await ctx.guild.create_text_channel(**kwargs)

                        elif ch_type == "voice":
                            await ctx.guild.create_voice_channel(**kwargs)

                        elif ch_type == "forum":
                            await ctx.guild.create_forum(**kwargs)

                        elif ch_type == "stage":
                            await ctx.guild.create_stage_channel(**kwargs)

                        created_channels += 1
                        await asyncio.sleep(0.5)  # Rate-Limit vermeiden

                    except Exception as e:
                        errors.append(f"Kanal '{ch_name}': {e}")

        except Exception as e:
            log.error(f"Import-Fehler: {e}")
            await confirm_msg.edit(content=f"❌ Fehler beim Import: {e}")
            return

        # Ergebnis
        embed = discord.Embed(
            title="✅ Import abgeschlossen!",
            color=0x57F287 if not errors else 0xF39C12
        )
        embed.add_field(name="📁 Kategorien erstellt", value=str(created_cats), inline=True)
        embed.add_field(name="💬 Kanäle erstellt", value=str(created_channels), inline=True)

        if errors:
            error_text = "\n".join(errors[:10])
            if len(errors) > 10:
                error_text += f"\n... und {len(errors) - 10} weitere"
            embed.add_field(name="⚠️ Fehler", value=error_text, inline=False)

        embed.set_footer(
            text=f"Importiert von {ctx.author.display_name}",
            icon_url=LOGO_URL
        )
        await confirm_msg.edit(content=None, embed=embed, view=None)


async def setup(bot):
    await bot.add_cog(ServerCog(bot))
