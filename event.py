# ════════════════════════════════════════════════
#  Event-Cog  •  VHA Alliance
#  Erkennt Events aus Screenshots automatisch
#  und setzt Timer per Button + Sprachauswahl
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import aiohttp
import base64
import json
import logging
import time
from datetime import datetime, timezone
from pymongo import MongoClient
import os
import asyncio

log = logging.getLogger("VHABot.Event")

VISION_MODEL = "gemini-2.5-flash-lite"
GEMINI_MODEL = "gemini-2.5-flash-lite"

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

ANNOUNCEMENT_CHANNELS = [
    1466355380346028065,
    1466365703715164356,
]

ALL_LANGS = {
    "DE": {"flag": "🇩🇪", "name": "Deutsch",    "target": "German"},
    "FR": {"flag": "🇫🇷", "name": "Français",   "target": "French"},
    "PT": {"flag": "🇧🇷", "name": "Português",  "target": "Brazilian Portuguese"},
    "EN": {"flag": "🇬🇧", "name": "English",    "target": "English"},
    "JA": {"flag": "🇯🇵", "name": "日本語",      "target": "Japanese"},
}

FIXED_LANGS = {"DE", "FR"}


def get_mongo_col():
    client = MongoClient(os.getenv("MONGODB_URI"))
    return client["vhabot"]["timers"]


def get_active_langs_from_db() -> set:
    try:
        client = MongoClient(os.getenv("MONGODB_URI"))
        col = client["vhabot"]["sprachen"]
        doc = col.find_one({"_id": "settings"})
        if doc:
            active = set(doc.get("active", ["DE", "FR"]))
            active.update(FIXED_LANGS)
            return active
        return {"DE", "FR"}
    except Exception:
        return {"DE", "FR"}


async def image_to_base64(url: str) -> tuple:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.read()
            content_type = resp.content_type or "image/png"
            b64 = base64.b64encode(data).decode("utf-8")
            return b64, content_type


async def analyze_event_image(gemini_call_fn, image_b64: str, content_type: str) -> dict:
    result_str = await gemini_call_fn(
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
                            "This is a screenshot from the mobile game Mecha Fire.\n"
                            "Extract the event name and countdown/time until it starts.\n"
                            "Reply with VALID JSON ONLY:\n"
                            '{"name": "Event name", "days": 0, "hours": 0, "minutes": 0, "seconds": 0, "found": true}\n'
                            'If no event/time found: {"found": false}'
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
        total_seconds = (
            parsed.get("days", 0) * 86400 +
            parsed.get("hours", 0) * 3600 +
            parsed.get("minutes", 0) * 60 +
            parsed.get("seconds", 0)
        )
        d = parsed.get("days", 0)
        h = parsed.get("hours", 0)
        m = parsed.get("minutes", 0)
        parts = []
        if d: parts.append(f"{d}T")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        display = " ".join(parts) if parts else "< 1m"
        return {"found": True, "name": parsed.get("name", "Unbekanntes Event"), "seconds": total_seconds, "display_time": display}
    except Exception as e:
        log.warning(f"Event JSON-Parse fehlgeschlagen: {e}")
        return {"found": False}


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
    if total_seconds > 24 * 3600: return 3600
    elif total_seconds > 3600: return 900
    elif total_seconds > 600: return 300
    else: return 0


# ────────────────────────────────────────────────
# Sprachen-Auswahl View
# ────────────────────────────────────────────────

class EventLangView(discord.ui.View):
    def __init__(self, bot, gemini_call_fn, event_name: str, seconds: int,
                 display_time: str, author: discord.Member,
                 names: dict, selected_langs: set):
        super().__init__(timeout=120)
        self.bot = bot
        self.gemini_call = gemini_call_fn
        self.event_name = event_name
        self.seconds = seconds
        self.display_time = display_time
        self.author = author
        self.names = names  # {"DE": "Magma-Ausbruch", "FR": "Éruption...", ...}
        self.selected_langs = selected_langs.copy()
        self.confirmed = False
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        for code, info in ALL_LANGS.items():
            is_selected = code in self.selected_langs
            is_fixed = code in FIXED_LANGS
            btn = discord.ui.Button(
                label=f"{info['flag']} {info['name']}",
                style=discord.ButtonStyle.success if is_selected else discord.ButtonStyle.secondary,
                emoji="✅" if is_selected else "❌",
                custom_id=f"evlang_{code}",
                disabled=is_fixed  # DE + FR immer aktiv
            )
            btn.callback = self._make_lang_callback(code)
            self.add_item(btn)

        # Timer setzen Button
        confirm_btn = discord.ui.Button(
            label="⏱️ Timer setzen",
            style=discord.ButtonStyle.primary,
            custom_id="ev_confirm",
            row=2
        )
        confirm_btn.callback = self._confirm_callback
        self.add_item(confirm_btn)

        # Abbrechen Button
        cancel_btn = discord.ui.Button(
            label="❌ Abbrechen",
            style=discord.ButtonStyle.danger,
            custom_id="ev_cancel",
            row=2
        )
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    def _make_lang_callback(self, code: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message("❌ Nur du kannst das ändern.", ephemeral=True)
                return
            if code in self.selected_langs:
                self.selected_langs.discard(code)
            else:
                self.selected_langs.add(code)
            self._build_buttons()
            await interaction.response.edit_message(view=self)
        return callback

    async def _confirm_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Nur du kannst das bestätigen.", ephemeral=True)
            return
        if self.confirmed:
            return
        self.confirmed = True

        # Fehlende Übersetzungen generieren
        missing = [code for code in self.selected_langs if code not in self.names]
        if missing:
            tasks = []
            for code in missing:
                tasks.append(self.gemini_call(
                    model=GEMINI_MODEL,
                    temperature=0.1,
                    max_tokens=50,
                    messages=[
                        {"role": "system", "content": f"Translate this game event name to {ALL_LANGS[code]['target']}. Output ONLY the translation."},
                        {"role": "user", "content": self.event_name}
                    ]
                ))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for code, result in zip(missing, results):
                if not isinstance(result, Exception):
                    self.names[code] = result.strip()
                else:
                    self.names[code] = self.event_name

        # Timer in MongoDB speichern
        try:
            col = get_mongo_col()
            end_timestamp = datetime.now(timezone.utc).timestamp() + self.seconds
            col.insert_one({
                "event": self.names.get("DE", self.event_name),
                "event_fr": self.names.get("FR", self.event_name),
                "event_pt": self.names.get("PT", self.event_name),
                "event_en": self.names.get("EN", self.event_name),
                "event_ja": self.names.get("JA", self.event_name),
                "duration_seconds": self.seconds,
                "end_timestamp": end_timestamp,
                "channel_id": interaction.channel.id,
                "author": self.author.display_name,
                "warned": False,
                "notify_langs": list(self.selected_langs)
            })
        except Exception as e:
            await interaction.response.send_message(f"❌ Fehler: {e}", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        embed = discord.Embed(
            title=f"⏱️ Timer gesetzt • {self.event_name}",
            color=0x57F287
        )
        embed.add_field(name="⏳ Zeit / Temps / Tempo", value=f"**{self.display_time}**", inline=False)
        langs_str = " • ".join([f"{ALL_LANGS[c]['flag']} {ALL_LANGS[c]['name']}" for c in self.selected_langs if c in ALL_LANGS])
        embed.add_field(name="🌐 Benachrichtigung in", value=langs_str, inline=False)
        embed.set_footer(text=f"Gesetzt von {self.author.display_name}")
        await interaction.response.send_message(embed=embed)

    async def _cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Nur du kannst abbrechen.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("❌ Timer abgebrochen.")


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class EventCog(commands.Cog):
    def __init__(self, bot, gemini_call_fn):
        self.bot = bot
        self.gemini_call = gemini_call_fn

    @commands.command(name="event", aliases=["evenement", "evento", "ev"])
    async def cmd_event(self, ctx):
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
            await ctx.send(
                "❓ Antworte auf einen Event-Screenshot und tippe `!event`\n"
                "Réponds à une capture et tape `!event`\n"
                "Responda a uma captura e digite `!event`"
            )
            return

        thinking = await ctx.send("🔍 **Analysiere Event...**")

        try:
            image_b64, content_type = await image_to_base64(image_url)
            if not image_b64:
                await thinking.edit(content="❌ Bild konnte nicht geladen werden.")
                return

            result = await analyze_event_image(self.gemini_call, image_b64, content_type)

            if not result.get("found"):
                await thinking.edit(content="❓ Kein Event erkannt im Bild.")
                return

            event_name = result["name"]
            seconds = result["seconds"]
            display_time = result["display_time"]

            # Event-Namen auf FR + PT übersetzen (DE ist Original)
            thinking_msg = await thinking.edit(content="🔄 **Übersetze Event-Namen...**")

            name_fr, name_pt = await asyncio.gather(
                self.gemini_call(
                    model=GEMINI_MODEL, temperature=0.1, max_tokens=50,
                    messages=[{"role": "system", "content": "Translate this game event name to French. Output ONLY the translation."},
                               {"role": "user", "content": event_name}]
                ),
                self.gemini_call(
                    model=GEMINI_MODEL, temperature=0.1, max_tokens=50,
                    messages=[{"role": "system", "content": "Translate this game event name to Brazilian Portuguese. Output ONLY the translation."},
                               {"role": "user", "content": event_name}]
                )
            )

            names = {
                "DE": event_name,
                "FR": name_fr.strip(),
                "PT": name_pt.strip(),
            }

            warning_sec = get_warning_seconds(seconds)
            warning_text = f"({format_duration(warning_sec)} vorher)" if warning_sec else ""

            # Aktive Sprachen als Standard vorauswählen
            active_langs = get_active_langs_from_db()

            embed = discord.Embed(
                title="⏰ Event erkannt / Événement détecté / Evento detectado",
                color=0xF39C12
            )
            embed.add_field(name="🇩🇪 Event", value=f"**{event_name}**", inline=True)
            embed.add_field(name="🇫🇷 Événement", value=f"**{names['FR']}**", inline=True)
            embed.add_field(name="🇧🇷 Evento", value=f"**{names['PT']}**", inline=True)
            embed.add_field(name="⏳ Startet in / Commence dans / Começa em",
                           value=f"**{display_time}** {warning_text}", inline=False)
            embed.set_footer(text="Wähle Sprachen für die Erinnerung und setze den Timer!")

            view = EventLangView(
                self.bot, self.gemini_call,
                event_name, seconds, display_time,
                ctx.author, names, active_langs
            )
            await thinking.edit(content=None, embed=embed, view=view)

        except Exception as e:
            log.error(f"Event-Fehler: {type(e).__name__} - {str(e)}")
            await thinking.edit(content="⚠️ Fehler beim Analysieren des Bildes.")


async def setup(bot, gemini_call_fn):
    await bot.add_cog(EventCog(bot, gemini_call_fn))
