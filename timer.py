# ════════════════════════════════════════════════
#  Timer-Cog  •  VHA Alliance
#  MongoDB für persistente Timer-Speicherung
#  Timer bleiben auch nach Bot-Neustart erhalten!
# ════════════════════════════════════════════════

import discord
from discord.ext import commands, tasks
import os
import asyncio
import logging
from datetime import datetime, timezone
from pymongo import MongoClient

log = logging.getLogger("VHABot.Timer")

ALLOWED_ROLES = {"R5", "R4"}

ANNOUNCEMENT_CHANNELS = [
    1466363028902645914,
    1466355380346028065,
    1466365877275459615,
    1476917139972689941,
    1479051097199874211,
    1466355380346028066,
    1466365703715164356,
    1466370291901927649,
    1466365749843984396,
    1466364051322830932,
    1479390903901618197,
]

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

# ────────────────────────────────────────────────
# MongoDB Verbindung
# ────────────────────────────────────────────────

def get_db():
    client = MongoClient(os.getenv("MONGODB_URI"))
    return client["vhabot"]["timers"]


# ────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────

def has_permission(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_roles = {r.name.upper() for r in member.roles}
    allowed_upper = {r.upper() for r in ALLOWED_ROLES}
    return bool(member_roles & allowed_upper)


def parse_duration(duration_str: str) -> int:
    import re
    duration_str = duration_str.lower().strip()
    total_seconds = 0
    pattern = re.findall(r'(\d+)\s*([dhms])', duration_str)
    if not pattern:
        if duration_str.isdigit():
            return int(duration_str) * 60
        return -1
    for value, unit in pattern:
        value = int(value)
        if unit == 'd':
            total_seconds += value * 86400
        elif unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds if total_seconds > 0 else -1


def format_duration(seconds: int) -> str:
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    parts = []
    if d: parts.append(f"{d}T")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return " ".join(parts) if parts else "< 1m"


def get_warning_seconds(total_seconds: int) -> int:
    if total_seconds > 24 * 3600:
        return 3600
    elif total_seconds > 3600:
        return 900
    elif total_seconds > 600:
        return 300
    else:
        return 0


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class TimerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_timers.start()

    def cog_unload(self):
        self.check_timers.cancel()

    @tasks.loop(seconds=30)
    async def check_timers(self):
        try:
            col = get_db()
            now = datetime.now(timezone.utc).timestamp()

            timers = list(col.find())
            fired = [t for t in timers if now >= t["end_timestamp"]]
            to_warn = [t for t in timers if not t.get("warned", False) and
                       now >= t["end_timestamp"] - get_warning_seconds(t["duration_seconds"]) and
                       get_warning_seconds(t["duration_seconds"]) > 0 and
                       now < t["end_timestamp"]]

            # Vorwarnungen senden
            for t in to_warn:
                try:
                    time_left = format_duration(int(t["end_timestamp"] - now))
                    name_de = t["event"]
                    name_fr = t.get("event_fr", name_de)
                    name_pt = t.get("event_pt", name_de)
                    embed = discord.Embed(
                        title=f"⚠️ Vorwarnung / Avertissement / Aviso • {name_de}",
                        color=0xF39C12
                    )
                    embed.add_field(name="🇩🇪 Startet in", value=f"**{name_de}** in **{time_left}**! Macht euch bereit! ⚔️", inline=False)
                    embed.add_field(name="🇫🇷 Commence dans", value=f"**{name_fr}** dans **{time_left}** ! Préparez-vous ! ⚔️", inline=False)
                    embed.add_field(name="🇧🇷 Começa em", value=f"**{name_pt}** em **{time_left}**! Preparem-se! ⚔️", inline=False)
                    embed.set_footer(text=f"Gesetzt von / Défini par / Definido por {t['author']}")

                    for channel_id in ANNOUNCEMENT_CHANNELS:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.send("@everyone", embed=embed)
                            except Exception:
                                pass

                    col.update_one({"_id": t["_id"]}, {"$set": {"warned": True}})
                except Exception as e:
                    log.error(f"Vorwarnungs-Fehler: {e}")

            # Finale Erinnerungen senden und Timer löschen
            for t in fired:
                try:
                    name_de = t["event"]
                    name_fr = t.get("event_fr", name_de)
                    name_pt = t.get("event_pt", name_de)
                    embed = discord.Embed(
                        title=f"⏰ Erinnerung / Rappel / Lembrete • {name_de}",
                        color=0xE74C3C
                    )
                    embed.add_field(name="🇩🇪 Deutsch", value=f"**{name_de}** beginnt jetzt! ⚔️", inline=False)
                    embed.add_field(name="🇫🇷 Français", value=f"**{name_fr}** commence maintenant ! ⚔️", inline=False)
                    embed.add_field(name="🇧🇷 Português", value=f"**{name_pt}** começa agora! ⚔️", inline=False)
                    embed.set_footer(text=f"Gesetzt von / Défini par / Definido por {t['author']}")

                    for channel_id in ANNOUNCEMENT_CHANNELS:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.send("@everyone", embed=embed)
                            except Exception:
                                pass

                    col.delete_one({"_id": t["_id"]})
                except Exception as e:
                    log.error(f"Timer-Fehler: {e}")

        except Exception as e:
            log.error(f"check_timers Fehler: {e}")

    @check_timers.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── !timer ───────────────────────────────────
    @commands.group(name="timer", aliases=["rappel", "erinnerung", "reminder", "lembrete"], invoke_without_command=True)
    async def timer(self, ctx, duration: str = None, *, event: str = None):
        if duration is None or event is None:
            await ctx.send(
                "❓ Nutzung: `!timer DAUER EVENT`\n"
                "Exemple: `!timer 2h Kriegsstart` / `!timer 30m Meeting`\n"
                "Zeitformate / Formats: `30m`, `2h`, `1h30m`, `3d`"
            )
            return

        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation / Sem permissão",
                description="Nur **Administrator**, **R5** und **R4** dürfen Timer setzen.",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        seconds = parse_duration(duration)
        if seconds <= 0:
            await ctx.send("❌ Ungültiges Format. Beispiele: `30m`, `2h`, `1h30m`, `3d`")
            return

        end_timestamp = datetime.now(timezone.utc).timestamp() + seconds

        try:
            col = get_db()
            col.insert_one({
                "event": event,
                "duration_seconds": seconds,
                "end_timestamp": end_timestamp,
                "channel_id": ctx.channel.id,
                "author": ctx.author.display_name,
                "warned": False
            })
        except Exception as e:
            log.error(f"MongoDB Speicher-Fehler: {e}")
            await ctx.send("❌ Fehler beim Speichern des Timers.")
            return

        embed = discord.Embed(
            title=f"⏱️ Timer gesetzt / Minuteur défini / Lembrete definido • {event}",
            color=0x57F287
        )
        embed.add_field(name="🇩🇪 Erinnerung in", value=f"**{format_duration(seconds)}**", inline=True)
        embed.add_field(name="🇫🇷 Rappel dans", value=f"**{format_duration(seconds)}**", inline=True)
        embed.add_field(name="🇧🇷 Lembrete em", value=f"**{format_duration(seconds)}**", inline=True)
        embed.add_field(name="📍 Event", value=event, inline=False)
        embed.set_footer(text=f"Gesetzt von / Défini par / Definido por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── !timer list ──────────────────────────────
    @timer.command(name="list", aliases=["liste", "all", "alle", "lista"])
    async def timer_list(self, ctx):
        try:
            col = get_db()
            now = datetime.now(timezone.utc).timestamp()
            timers = list(col.find({"end_timestamp": {"$gt": now}}))
        except Exception as e:
            await ctx.send("❌ Fehler beim Laden der Timer.")
            return

        if not timers:
            await ctx.send("📭 Keine aktiven Timer. / Aucun minuteur actif. / Nenhum lembrete ativo.")
            return

        embed = discord.Embed(title="⏱️ Aktive Timer / Minuteurs actifs / Lembretes ativos", color=0x3498DB)
        for t in timers:
            remaining = int(t["end_timestamp"] - now)
            name_de = t["event"]
            name_fr = t.get("event_fr", name_de)
            name_pt = t.get("event_pt", name_de)
            embed.add_field(
                name=f"🇩🇪 {name_de} / 🇫🇷 {name_fr} / 🇧🇷 {name_pt}",
                value=f"⏳ Noch / Reste / Falta: **{format_duration(remaining)}**\n👤 {t['author']}",
                inline=False
            )
        embed.set_footer(text=f"Gesamt / Total: {len(timers)}")
        await ctx.send(embed=embed)

    # ── !timer delete ────────────────────────────
    @timer.command(name="delete", aliases=["löschen", "supprimer", "del", "remove", "cancel", "abbrechen", "annuler", "apagar"])
    async def timer_delete(self, ctx, *, event: str):
        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation / Sem permissão",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        try:
            col = get_db()
            result = col.delete_one({"event": {"$regex": f"^{event}$", "$options": "i"}})
        except Exception as e:
            await ctx.send("❌ Fehler beim Löschen.")
            return

        if result.deleted_count == 0:
            await ctx.send(f"⚠️ Kein Timer `{event}` gefunden. / Aucun minuteur `{event}` trouvé.")
            return

        embed = discord.Embed(
            title=f"🗑️ Timer gelöscht / Minuteur supprimé / Lembrete apagado • {event}",
            color=0xED4245
        )
        embed.set_footer(text=f"Gelöscht von / Supprimé par / Apagado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── !timer help ──────────────────────────────
    @timer.command(name="help", aliases=["hilfe", "aide", "ajuda"])
    async def timer_help(self, ctx):
        embed = discord.Embed(title="⏱️ Timer – Hilfe / Aide / Ajuda", color=0x3498DB)
        embed.add_field(
            name="🇩🇪 Befehle",
            value=(
                "`!timer DAUER EVENT` – Timer setzen\n"
                "`!timer list` – Aktive Timer\n"
                "`!timer delete NAME` – Löschen\n"
                "**Formate:** `30m` `2h` `1h30m` `3d`"
            ),
            inline=False
        )
        embed.add_field(
            name="🇫🇷 Commandes",
            value=(
                "`!rappel DURÉE EVENT` – Définir\n"
                "`!rappel list` – Minuteurs actifs\n"
                "`!rappel supprimer NAME` – Supprimer"
            ),
            inline=False
        )
        embed.add_field(
            name="🇧🇷 Comandos",
            value=(
                "`!lembrete DURAÇÃO EVENT` – Definir\n"
                "`!lembrete list` – Lembretes ativos\n"
                "`!lembrete apagar NAME` – Apagar"
            ),
            inline=False
        )
        embed.add_field(name="🔐 Berechtigung", value="Administrator, R5, R4", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TimerCog(bot))
