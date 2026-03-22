# ════════════════════════════════════════════════
#  Event-Cog  •  VHA Alliance  •  Mecha Fire
#  Erkennt Events aus Screenshots automatisch
#  und setzt Timer per Button-Klick
#  Befehl: !event (als Reply auf Screenshot)
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import aiohttp
import base64
import json
import re
import logging
import time
from datetime import datetime, timezone

log = logging.getLogger("VHABot.Event")

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

# Kanäle für Timer-Erinnerungen (gleiche wie in timer.py)
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


# ────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────

async def image_to_base64(url: str) -> tuple:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.read()
            content_type = resp.content_type or "image/png"
            b64 = base64.b64encode(data).decode("utf-8")
            return b64, content_type


async def analyze_event_image(groq_call_fn, image_b64: str, content_type: str) -> dict:
    """
    Analysiert einen Mecha Fire Event-Screenshot.
    Gibt zurück: {name, seconds, display_time, found}
    """
    result_str = await groq_call_fn(
        model=VISION_MODEL,
        temperature=0.0,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a screenshot from the mobile game Mecha Fire showing an event.\n"
                            "Extract the event name and the countdown/time until it starts.\n\n"
                            "The time can appear as:\n"
                            "- Countdown: '00T 13St. 04Min. 04s' (T=days/Tage, St.=hours/Stunden, Min.=minutes)\n"
                            "- 'Startet in: 13:03:12' (HH:MM:SS)\n"
                            "- UTC date range like '03/23/2026-03/25/2026'\n\n"
                            "Reply with VALID JSON ONLY:\n"
                            '{"name": "Event name", "days": 0, "hours": 0, "minutes": 0, "seconds": 0, "found": true}\n\n'
                            'If no event or time found: {"found": false}'
                        )
                    }
                ]
            }
        ]
    )

    try:
        clean = result_str.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
        if not parsed.get("found", False):
            return {"found": False}

        # Gesamtsekunden berechnen
        total_seconds = (
            parsed.get("days", 0) * 86400 +
            parsed.get("hours", 0) * 3600 +
            parsed.get("minutes", 0) * 60 +
            parsed.get("seconds", 0)
        )

        # Lesbare Zeit
        d = parsed.get("days", 0)
        h = parsed.get("hours", 0)
        m = parsed.get("minutes", 0)
        parts = []
        if d: parts.append(f"{d}T")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        display = " ".join(parts) if parts else "< 1m"

        return {
            "found": True,
            "name": parsed.get("name", "Unbekanntes Event"),
            "seconds": total_seconds,
            "display_time": display
        }

    except Exception as e:
        log.warning(f"Event JSON-Parse fehlgeschlagen: {e} | {result_str[:200]}")
        return {"found": False}


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    parts = []
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
# Discord UI Buttons
# ────────────────────────────────────────────────

class EventTimerView(discord.ui.View):
    def __init__(self, bot, event_name: str, seconds: int, display_time: str, author: discord.Member):
        super().__init__(timeout=60)  # 60 Sekunden zum Klicken
        self.bot = bot
        self.event_name = event_name
        self.seconds = seconds
        self.display_time = display_time
        self.author = author
        self.responded = False

    @discord.ui.button(label="✅ Timer setzen", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Nur derjenige der den Befehl ausgeführt hat kann bestätigen.",
                ephemeral=True
            )
            return

        if self.responded:
            return
        self.responded = True

        # Timer in MongoDB speichern
        from pymongo import MongoClient
        import os

        try:
            client = MongoClient(os.getenv("MONGODB_URI"))
            col = client["vhabot"]["timers"]

            end_timestamp = datetime.now(timezone.utc).timestamp() + self.seconds

            col.insert_one({
                "event": self.event_name,
                "duration_seconds": self.seconds,
                "end_timestamp": end_timestamp,
                "channel_id": interaction.channel.id,
                "author": self.author.display_name,
                "warned": False
            })

            # Buttons deaktivieren
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)

            embed = discord.Embed(
                title=f"⏱️ Timer gesetzt / Minuteur défini / Lembrete definido • {self.event_name}",
                color=0x57F287
            )
            embed.add_field(name="🇩🇪 Erinnerung in", value=f"**{self.display_time}**", inline=True)
            embed.add_field(name="🇫🇷 Rappel dans", value=f"**{self.display_time}**", inline=True)
            embed.add_field(name="🇧🇷 Lembrete em", value=f"**{self.display_time}**", inline=True)
            embed.set_footer(text=f"Gesetzt von / Défini par / Definido por {self.author.display_name}")
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            log.error(f"Timer-Speicher-Fehler: {e}")
            await interaction.response.send_message("❌ Fehler beim Speichern des Timers.", ephemeral=True)

    @discord.ui.button(label="❌ Abbrechen", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Nur derjenige der den Befehl ausgeführt hat kann abbrechen.",
                ephemeral=True
            )
            return

        if self.responded:
            return
        self.responded = True

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("❌ Timer abgebrochen. / Minuteur annulé. / Lembrete cancelado.")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class EventCog(commands.Cog):
    def __init__(self, bot, groq_call_fn):
        self.bot = bot
        self.groq_call = groq_call_fn

    @commands.command(name="event", aliases=["evenement", "evento", "ev"])
    async def cmd_event(self, ctx):
        """
        Erkennt ein Event aus einem Screenshot und setzt Timer per Button.
        Nutzung: Als Reply auf einen Event-Screenshot tippen: !event
        """
        # Bild suchen
        image_url = None

        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image"):
                    image_url = att.url
                    break

        if not image_url and ctx.message.reference:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message) and ref.attachments:
                for att in ref.attachments:
                    if att.content_type and att.content_type.startswith("image"):
                        image_url = att.url
                        break

        if not image_url:
            embed = discord.Embed(
                title="❓ Kein Bild gefunden",
                description=(
                    "Antworte auf einen Event-Screenshot und tippe `!event`\n"
                    "Réponds à une capture d'écran d'événement et tape `!event`\n"
                    "Responda a uma captura de tela de evento e digite `!event`"
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed)
            return

        thinking = await ctx.send("🔍 **Analysiere Event...** / **Analyse...** / **Analisando...**")

        try:
            image_b64, content_type = await image_to_base64(image_url)
            if not image_b64:
                await thinking.edit(content="❌ Bild konnte nicht geladen werden.")
                return

            result = await analyze_event_image(self.groq_call, image_b64, content_type)

            if not result.get("found"):
                embed = discord.Embed(
                    title="❓ Kein Event erkannt",
                    description=(
                        "Kein Event oder keine Zeit im Bild gefunden.\n"
                        "Aucun événement ou temps trouvé dans l'image.\n"
                        "Nenhum evento ou tempo encontrado na imagem."
                    ),
                    color=0xF39C12
                )
                await thinking.edit(content=None, embed=embed)
                return

            event_name = result["name"]
            seconds = result["seconds"]
            display_time = result["display_time"]

            # Event-Name auf FR und PT übersetzen
            await thinking.edit(content="🔍 **Übersetze Event-Name...** / **Traduction...** / **Traduzindo...**")
            try:
                import asyncio as _asyncio
                name_fr, name_pt = await _asyncio.gather(
                    self.groq_call(
                        model="llama-3.3-70b-versatile",
                        temperature=0.1,
                        max_tokens=50,
                        messages=[
                            {"role": "system", "content": "Translate this game event name to French. Output ONLY the translation, nothing else."},
                            {"role": "user", "content": event_name}
                        ]
                    ),
                    self.groq_call(
                        model="llama-3.3-70b-versatile",
                        temperature=0.1,
                        max_tokens=50,
                        messages=[
                            {"role": "system", "content": "Translate this game event name to Brazilian Portuguese. Output ONLY the translation, nothing else."},
                            {"role": "user", "content": event_name}
                        ]
                    )
                )
            except Exception:
                name_fr = event_name
                name_pt = event_name

            # Vorwarnung berechnen
            warning_sec = get_warning_seconds(seconds)
            warning_text = f"({format_duration(warning_sec)} vorher)" if warning_sec else ""

            embed = discord.Embed(
                title=f"⏰ Event erkannt / Événement détecté / Evento detectado",
                color=0xF39C12
            )
            embed.add_field(name="🇩🇪 Event", value=f"**{event_name}**", inline=True)
            embed.add_field(name="🇫🇷 Événement", value=f"**{name_fr}**", inline=True)
            embed.add_field(name="🇧🇷 Evento", value=f"**{name_pt}**", inline=True)
            embed.add_field(name="🇩🇪 Startet in", value=f"**{display_time}** {warning_text}", inline=True)
            embed.add_field(name="🇫🇷 Commence dans", value=f"**{display_time}**", inline=True)
            embed.add_field(name="🇧🇷 Começa em", value=f"**{display_time}**", inline=True)
            embed.set_footer(text="Timer setzen? / Définir un minuteur? / Definir lembrete?")

            view = EventTimerView(self.bot, event_name, seconds, display_time, ctx.author)
            msg = await thinking.edit(content=None, embed=embed, view=view)
            view.message = thinking

        except Exception as e:
            log.error(f"Event-Fehler: {type(e).__name__} - {str(e)}")
            embed = discord.Embed(
                title="⚠️ Fehler beim Analysieren",
                description=(
                    "Das Bild konnte nicht analysiert werden – versuch es nochmal!\n"
                    "Impossible d'analyser l'image – réessaie!\n"
                    "Não foi possível analisar a imagem – tente novamente!"
                ),
                color=0xED4245
            )
            await thinking.edit(content=None, embed=embed)


# ────────────────────────────────────────────────
# Setup
# ────────────────────────────────────────────────

async def setup(bot, groq_call_fn):
    await bot.add_cog(EventCog(bot, groq_call_fn))
