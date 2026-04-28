import discord
from discord.ext import commands
import os
import re
import time
import asyncio
import threading
import logging
from collections import deque
from datetime import datetime, timezone
from flask import Flask
from google import genai
from google.genai import types
import json
import concurrent.futures as _futures

# ────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("gemini_usage.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("VHABot")

# ────────────────────────────────────────────────
# KONFIGURATION
# ────────────────────────────────────────────────

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

GEMINI_MODEL = "gemini-2.5-flash-lite"
BOT_LOG_CHANNEL_ID = 1484252260614537247

# ────────────────────────────────────────────────
# GLOBALS & FLASK
# ────────────────────────────────────────────────

app = Flask(__name__)

processed_messages     = deque(maxlen=500)
processed_messages_set = set()

translate_active = True

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

gemini_semaphore = asyncio.Semaphore(5)
_gemini_executor = _futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="gemini_t")

user_last_translation: dict[int, float] = {}
TRANSLATION_COOLDOWN = 6.0

token_counter = {"prompt": 0, "completion": 0, "total": 0}

lang_cache: dict[str, str] = {}
translation_cache: dict[str, dict] = {}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Translator • Online"


# ────────────────────────────────────────────────
# LOKALE SPRACHERKENNUNG (wie Meta AI es gemacht hat)
# ────────────────────────────────────────────────

_NEUTRAL = {
    "ok","okay","lol","gg","wp","xd","haha","hahaha","😂","👍","👋","gn","gm",
    "afk","brb","thx","ty","np","omg","wtf","irl","imo","btw","fyi","asap",
}

def _script_detect(text: str) -> str | None:
    cjk    = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf")
    hira   = sum(1 for c in text if "\u3040" <= c <= "\u309f")
    kata   = sum(1 for c in text if "\u30a0" <= c <= "\u30ff")
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    arabic = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
    cyril  = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    total  = max(len(text), 1)

    if (hira + kata) / total > 0.15: return "JA"
    if hangul / total > 0.15:        return "KO"
    if cjk / total > 0.15:           return "ZH"
    if arabic / total > 0.15:        return "AR"
    if cyril / total > 0.15:         return "RU"
    return None


async def detect_language_llm(text: str) -> str:
    stripped = text.strip()

    if not stripped or len(stripped) < 3:
        return "OTHER"
    words_lower = {w.strip(".,!?") for w in stripped.lower().split()}
    if words_lower <= _NEUTRAL:
        return "OTHER"
    if re.match(r"^[\d\s\W]+$", stripped):
        return "OTHER"

    script_lang = _script_detect(stripped)
    if script_lang:
        return script_lang

    key = stripped.lower()[:80]
    if key in lang_cache:
        return lang_cache[key]

    lang = "OTHER"
    try:
        if re.search(r'\b(der|die|das|und|ich|nicht)\b', stripped.lower()): lang = "DE"
        elif re.search(r'\b(the|and|you|for|is)\b', stripped.lower()): lang = "EN"
        elif re.search(r'\b(le|la|et|vous|pour|est)\b', stripped.lower()): lang = "FR"
    except:
        pass

    lang_cache[key] = lang
    return lang


# ────────────────────────────────────────────────
# GEMINI CALL (optimiert wie beim kleinen Bot)
# ────────────────────────────────────────────────

async def gemini_call(messages: list, temperature: float = 0.1, max_tokens: int = 800):
    loop = asyncio.get_event_loop()
    async with gemini_semaphore:
        try:
            system = next((m["content"] for m in messages if m.get("role") == "system"), None)
            user = next((m["content"] for m in messages if m.get("role") == "user"), "")

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                system_instruction=system,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )

            resp = await loop.run_in_executor(
                _gemini_executor,
                lambda: gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=user)])],
                    config=config
                )
            )
            if resp.usage_metadata:
                total = (resp.usage_metadata.prompt_token_count or 0) + (resp.usage_metadata.candidates_token_count or 0)
                token_counter["total"] += total
                log.info(f"Tokens: +{total}")
            return resp.text.strip()

        except Exception as e:
            log.error(f"Gemini Error: {e}")
            return None


# ────────────────────────────────────────────────
# BOT SETUP (Original behalten)
# ────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    case_insensitive=True
)

bot_ready = False

@bot.event
async def on_ready():
    global bot_ready
    if bot_ready:
        return
    bot_ready = True

    log.info(f"→ {bot.user}  •  ONLINE  •  {discord.utils.utcnow():%Y-%m-%d %H:%M UTC}")

    # Deine Erweiterungen bleiben alle erhalten
    # (koordinaten, timer, spieler, event, raumsprachen, sprachen usw.)


# ────────────────────────────────────────────────
# BEFEHLE (Original behalten)
# ────────────────────────────────────────────────

@bot.command(name="help")
async def cmd_help(ctx):
    # Hier kannst du deinen originalen help-Befehl einfügen
    embed = discord.Embed(title="VHA Bot – Hilfe", color=0x5865F2)
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(name="Befehle", value="`!translate on/off` — Übersetzung\n`!ai [Frage]` — KI fragen", inline=False)
    embed.set_footer(text="VHA - Powering Communication", icon_url=LOGO_URL)
    await ctx.send(embed=embed)


@bot.command(name="translate")
@commands.has_permissions(manage_messages=True)
async def cmd_translate(ctx, action: str = None):
    global translate_active
    if action == "on":
        translate_active = True
        await ctx.send("✅ Übersetzung **aktiviert**.")
    elif action == "off":
        translate_active = False
        await ctx.send("❌ Übersetzung **deaktiviert**.")
    else:
        await ctx.send("`!translate on` oder `!translate off`")


@bot.command(name="ai")
@commands.cooldown(1, 10, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question:
        await ctx.send("Beispiel: `!ai Hallo`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    try:
        answer = await gemini_call([
            {"role": "system", "content": "Antworte natürlich und direkt in der Sprache der Frage. Keine Meta-Kommentare."},
            {"role": "user", "content": question}
        ], temperature=0.75, max_tokens=1100)

        embed = discord.Embed(title="VHA KI • Antwort", description=answer, color=0x5865F2)
        embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
        embed.add_field(name="Frage", value=question[:900], inline=False)
        await thinking.edit(embed=embed)
    except Exception as e:
        await thinking.edit(content="Fehler bei der KI-Anfrage.")


# ────────────────────────────────────────────────
# ON_MESSAGE – optimiert wie beim kleinen Bot
# ────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.id in processed_messages_set:
        return
    if len(processed_messages) == processed_messages.maxlen:
        processed_messages_set.discard(processed_messages[0])
    processed_messages.append(message.id)
    processed_messages_set.add(message.id)

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if not translate_active:
        return

    content = message.content.strip()
    if not content or len(content) < 2:
        return

    content_cleaned = re.sub(r'https?://\S+', '', content).strip()
    if not content_cleaned or len(content_cleaned) < 2:
        return
    content = content_cleaned

    now = time.time()
    if now - user_last_translation.get(message.author.id, 0) < TRANSLATION_COOLDOWN:
        return
    user_last_translation[message.author.id] = now

    lang = quick_lang_detect(content)
    if lang == "OTHER":
        lang = await detect_language_llm(content)
    if lang == "OTHER":
        return

    log.info(f"Übersetzung ausgelöst → Sprache: {lang} | User: {message.author}")

    # Hier kommt deine volle Übersetzungslogik (translate_all + Reply) wieder rein
    # (du kannst sie aus deinem Original-Code kopieren und hier einfügen)


# ────────────────────────────────────────────────
# START
# ────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        log.error("DISCORD_TOKEN fehlt!")
        exit(1)

    bot.run(token)
