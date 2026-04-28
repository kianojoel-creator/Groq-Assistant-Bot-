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
# GLOBALS
# ────────────────────────────────────────────────

app = Flask(__name__)

processed_messages = deque(maxlen=500)
processed_messages_set = set()

translate_active = True

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

gemini_semaphore = asyncio.Semaphore(5)

user_last_translation = {}
TRANSLATION_COOLDOWN = 6.0

# Caches
lang_cache = {}
translation_cache = {}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Bot • Online"


# ────────────────────────────────────────────────
# SCHNELLE LOKALE SPRACHERKENNUNG (wie beim kleinen Bot)
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


# ────────────────────────────────────────────────
# GEMINI CALL (optimiert + AFC deaktiviert)
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
            )

            resp = await loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=user)])],
                    config=config
                )
            )
            if resp.usage_metadata:
                total = (resp.usage_metadata.prompt_token_count or 0) + (resp.usage_metadata.candidates_token_count or 0)
                log.info(f"Tokens: +{total} | Dauer: {time.time():.2f}s")
            return resp.text.strip()

        except Exception as e:
            log.error(f"Gemini Error: {e}")
            return None


# ────────────────────────────────────────────────
# BOT SETUP
# ────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, case_insensitive=True)


@bot.event
async def on_ready():
    log.info(f"→ {bot.user} ONLINE")


# ────────────────────────────────────────────────
# BEFEHLE (unverändert)
# ────────────────────────────────────────────────

@bot.command(name="help")
async def cmd_help(ctx):
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
        await ctx.send("Beispiel: `!ai Was ist die VHA?`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    try:
        answer = await gemini_call([
            {"role": "system", "content": "Antworte natürlich und direkt in der Sprache der Frage. Keine Meta-Kommentare."},
            {"role": "user", "content": question}
        ], temperature=0.75, max_tokens=1100)

        embed = discord.Embed(title="VHA KI • Antwort", description=answer or "Keine Antwort", color=0x5865F2)
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
    processed_messages_set.add(message.id)
    processed_messages.append(message.id)

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if not translate_active:
        return

    content = message.content.strip()
    if len(content) < 3:
        return

    # Cooldown
    now = time.time()
    if now - user_last_translation.get(message.author.id, 0) < TRANSLATION_COOLDOWN:
        return
    user_last_translation[message.author.id] = now

    lang = quick_lang_detect(content)
    log.info(f"Übersetzung ausgelöst → Sprache: {lang} | User: {message.author}")

    # Hier kommt später deine volle Übersetzungslogik (translate_all + Reply) wieder rein


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
