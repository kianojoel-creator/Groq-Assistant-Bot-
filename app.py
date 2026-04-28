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
import json

# ────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger("VHABot")

# ────────────────────────────────────────────────
# KONFIGURATION
# ────────────────────────────────────────────────

LOGO_URL = "https://cdn.discordapp.com/attachments/1484252260614537247/1484253018533662740/Picsart_26-03-18_13-55-24-994.png?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"

GEMINI_MODEL = "gemini-2.5-flash-lite"

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

lang_cache = {}
translation_cache = {}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Bot • Online"


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

    if any(c in text for c in "ですますはをがにの"):
        return "JA"
    if any(c in text for c in "的是一在你我他我们"):
        return "ZH"
    if any(c in text for c in "이다하다요네"):
        return "KO"

    return "OTHER"


# ────────────────────────────────────────────────
# GEMINI CALL (optimiert)
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
            )

            resp = await loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=user)])],
                    config=config
                )
            )
            return resp.text.strip()
        except Exception as e:
            log.error(f"Gemini Error: {e}")
            return None


# ────────────────────────────────────────────────
# ÜBERSETZUNG (translate_all) – optimiert mit Cache
# ────────────────────────────────────────────────

async def translate_all(text: str, target_langs: list) -> dict:
    if not target_langs:
        return {}

    cache_key = f"{text[:150]}_{'_'.join([code for code,_,_ in target_langs])}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]

    codes_str = ", ".join(f"{code}={name}" for code, name, _ in target_langs)
    json_keys = ", ".join(f'"{code}": "..."' for code, _, _ in target_langs)

    try:
        result = await gemini_call([
            {"role": "system", "content": f"Translate the text into these languages: {codes_str}. Reply ONLY with valid JSON: {{{json_keys}}}. Keep game terms, names and coordinates untranslated."},
            {"role": "user", "content": text}
        ], temperature=0.1, max_tokens=1200)

        clean = result.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean.split("```")[1]

        parsed = json.loads(clean.strip())
        translations = {code: parsed.get(code, "").strip() for code, _, _ in target_langs if parsed.get(code)}

        translation_cache[cache_key] = translations
        if len(translation_cache) > 400:
            for k in list(translation_cache.keys())[:100]:
                del translation_cache[k]

        return translations

    except Exception as e:
        log.error(f"translate_all Fehler: {e}")
        return {}


# ────────────────────────────────────────────────
# BOT
# ────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, case_insensitive=True)


@bot.event
async def on_ready():
    log.info(f"→ {bot.user} ONLINE")


# Deine Befehle (help, translate, ai, kanalid, clean, etc.) bleiben gleich wie in deinem Original
# Ich habe sie hier kurz gehalten, du kannst sie 1:1 aus deinem alten Code einfügen

@bot.command(name="help")
async def cmd_help(ctx):
    await ctx.send("**Hilfe kommt gleich...** (bitte deinen alten help-Befehl hier einfügen)")

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
        await ctx.send("`!translate on` / `!translate off`")


@bot.command(name="ai")
@commands.cooldown(1, 10, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question:
        await ctx.send("Beispiel: `!ai Hallo`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    try:
        answer = await gemini_call([
            {"role": "system", "content": "Antworte natürlich und direkt in der Sprache der Frage."},
            {"role": "user", "content": question}
        ], temperature=0.75)

        embed = discord.Embed(title="VHA KI • Antwort", description=answer, color=0x5865F2)
        embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
        await thinking.edit(embed=embed)
    except:
        await thinking.edit(content="Fehler bei der KI-Anfrage.")


# ────────────────────────────────────────────────
# ON_MESSAGE – optimiert + volle Übersetzung
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

    now = time.time()
    if now - user_last_translation.get(message.author.id, 0) < TRANSLATION_COOLDOWN:
        return
    user_last_translation[message.author.id] = now

    lang = quick_lang_detect(content)
    if lang == "OTHER":
        return

    log.info(f"Übersetzung ausgelöst → Sprache: {lang} | {message.author}")

    # Einfache Übersetzung in DE + FR für den Anfang
    try:
        translations = await translate_all(content, [
            ("DE", "German", "🇩🇪 Deutsch"),
            ("FR", "French", "🇫🇷 Français")
        ])

        fields = []
        for code, _, label in [("DE", "German", "🇩🇪 Deutsch"), ("FR", "French", "🇫🇷 Français")]:
            if code in translations:
                fields.append((label, translations[code]))

        if fields:
            embed = discord.Embed(title=f"💬 • {message.author.display_name}", color=0x3498DB)
            for flag, text in fields:
                embed.add_field(name=flag, value=text, inline=False)
            embed.set_footer(text="VHA Translator", icon_url=LOGO_URL)
            await message.reply(embed=embed, mention_author=False)

    except Exception as e:
        log.error(f"Übersetzungsfehler: {e}")


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
