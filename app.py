import discord
from discord.ext import commands
import os
import re
import time
import asyncio
import threading
import logging
from collections import deque
from flask import Flask
from google import genai
from google.genai import types

# ────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("main_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("VHAMainBot")

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
# GLOBALS
# ────────────────────────────────────────────────

app = Flask(__name__)

processed_messages = deque(maxlen=600)
translate_active = True

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

gemini_semaphore = asyncio.Semaphore(5)
_gemini_executor = None  # wird später initialisiert

user_last_translation = {}
TRANSLATION_COOLDOWN = 6.0

lang_cache = {}
translation_cache = {}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Main Bot • Online"


# ────────────────────────────────────────────────
# SCHNELLE LOKALE SPRACHERKENNUNG
# ────────────────────────────────────────────────

_NEUTRAL = {"ok","lol","gg","xd","haha","😂","👍","gn","gm","afk","brb","thx","ty"}

def quick_lang_detect(text: str) -> str:
    if not text or len(text) < 4:
        return "OTHER"
    
    t = text.lower()

    if any(w in t for w in ["ist", "ich", "du", "wir", "nicht", "für", "mit", "auf", "das", "die"]):
        return "DE"
    if any(w in t for w in ["je", "tu", "c'est", "est", "pas", "oui", "vous", "le", "la"]):
        return "FR"
    if any(w in t for w in ["the", "is", "you", "i", "and", "to", "what", "how"]):
        return "EN"

    # Skript-Erkennung
    if any(c in text for c in "ですますはをがにの"):
        return "JA"
    if any(c in text for c in "的是一在你我他我们"):
        return "ZH"
    if any(c in text for c in "이다하다요네"):
        return "KO"

    return "OTHER"


async def detect_language(text: str) -> str:
    key = text[:100].lower()
    if key in lang_cache:
        return lang_cache[key]

    lang = quick_lang_detect(text)
    if lang != "OTHER":
        lang_cache[key] = lang
        return lang

    # Sehr selten LLM nutzen
    try:
        result = await gemini_call(
            model=GEMINI_MODEL,
            temperature=0.0,
            max_tokens=8,
            messages=[
                {"role": "system", "content": "Detect language. Reply ONLY with 2-letter code: DE FR EN ES PT JA ZH KO RU AR TR. If unsure: OTHER"},
                {"role": "user", "content": text[:250]}
            ]
        )
        detected = result.strip().upper()[:2]
        if detected in {"DE","FR","EN","ES","PT","JA","ZH","KO","RU","AR","TR"}:
            lang_cache[key] = detected
            return detected
    except:
        pass

    lang_cache[key] = "OTHER"
    return "OTHER"


# ────────────────────────────────────────────────
# GEMINI CALL (optimiert)
# ────────────────────────────────────────────────

async def gemini_call(model: str, messages: list, temperature: float = 0.1, max_tokens: int = 800):
    global _gemini_executor
    if _gemini_executor is None:
        import concurrent.futures
        _gemini_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")

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
            )

            resp = await loop.run_in_executor(
                _gemini_executor,
                lambda: gemini_client.models.generate_content(
                    model=model,
                    contents=[types.Content(role="user", parts=[types.Part(text=user)])],
                    config=config
                )
            )
            return resp.text.strip()

        except Exception as e:
            log.warning(f"Gemini Error: {type(e).__name__} - {e}")
            raise


# ────────────────────────────────────────────────
# BOT SETUP
# ────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    case_insensitive=True
)


@bot.event
async def on_ready():
    log.info(f"→ {bot.user} ONLINE")


# ────────────────────────────────────────────────
# !ai – schneller & sprachsensitiv
# ────────────────────────────────────────────────

@bot.command(name="ai")
@commands.cooldown(1, 8, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question:
        await ctx.send("Beispiel: `!ai Qui es-tu ?` oder `!ai What is VHA?`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    try:
        answer = await gemini_call(
            model=GEMINI_MODEL,
            temperature=0.75,
            max_tokens=1100,
            messages=[
                {"role": "system", "content": "Antworte natürlich und direkt in der gleichen Sprache wie die Frage. Keine Meta-Kommentare."},
                {"role": "user", "content": question}
            ]
        )
        color = 0x5865F2
    except Exception:
        answer = "Fehler bei der KI-Anfrage."
        color = 0xED4245

    embed = discord.Embed(title="VHA KI • Antwort", description=answer, color=color)
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(name="Frage", value=question[:900], inline=False)
    embed.set_footer(text=f"VHA • Gemini • {GEMINI_MODEL}", icon_url=LOGO_URL)

    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# ON_MESSAGE – stark optimiert für Geschwindigkeit
# ────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not translate_active:
        return

    if message.id in processed_messages:
        return
    processed_messages.append(message.id)

    content = message.content.strip()
    if len(content) < 3:
        return

    # Cooldown pro User
    now = time.time()
    if now - user_last_translation.get(message.author.id, 0) < TRANSLATION_COOLDOWN:
        return
    user_last_translation[message.author.id] = now

    try:
        lang = await detect_language(content)
        if lang == "OTHER":
            return

        log.info(f"Übersetzung ausgelöst → Sprache: {lang} | User: {message.author}")

        # Hier kommt später deine volle Übersetzungslogik (translate_all) wieder rein
        # Für den Moment nur Logging, damit wir die Geschwindigkeit messen können

    except Exception as e:
        log.error(f"on_message Fehler: {e}")


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
