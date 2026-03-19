import discord
from discord.ext import commands
import os
import re
import threading
from flask import Flask
from groq import Groq

# ────────────────────────────────────────────────
# KONFIGURATION
# ────────────────────────────────────────────────

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)

GROQ_MODEL = "llama-3.3-70b-versatile"

# ────────────────────────────────────────────────
# GLOBALS & FLASK
# ────────────────────────────────────────────────

app = Flask(__name__)
processed_messages = set()
translate_active = True


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Translator • Online"


# ────────────────────────────────────────────────
# SPRACHE ERKENNEN – für automatische Übersetzung
# ────────────────────────────────────────────────

def detect_language_simple(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return "UNKNOWN"

    t = text.lower().strip()

    # Französisch – relativ zuverlässig
    fr_indicators = [
        "je", "tu", "il", "elle", "nous", "vous", "ils", "est", "suis", "c'est",
        "ça", "qui", "quoi", "comment", "pourquoi", "merci", "salut", "oui", "non",
        "le ", "la ", "les ", "un ", "une ", "des "
    ]
    if any(w in t for w in fr_indicators):
        return "FR"

    # Deutsch
    de_indicators = [
        "ich", "du", "er", "sie", "es", "wir", "ihr", "ist", "bin", "bist",
        "der ", "die ", "das ", "ein ", "eine ", "und", "oder", "aber", "dass",
        "was", "wie", "warum", "bitte", "danke"
    ]
    if any(w in t for w in de_indicators):
        return "DE"

    return "UNKNOWN"


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
    print(f"→ {bot.user}  •  ONLINE  •  {discord.utils.utcnow():%Y-%m-%d %H:%M UTC}")


# ────────────────────────────────────────────────
# BEFEHLE (help, translate, ai) – bleiben weitgehend gleich
# ────────────────────────────────────────────────

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="VHA Translator – Hilfe",
        color=discord.Color.blue()
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(
        name="Befehle",
        value=(
            "`!translate on/off` → Automatische Übersetzung DE↔FR an/aus\n"
            "`!ai [Text]` → KI-Frage (antwortet in der Sprache der Frage)"
        ),
        inline=False
    )
    embed.set_footer(text="VHA - Powering Communication", icon_url=LOGO_URL)
    await ctx.send(embed=embed)


@bot.command(name="translate")
async def cmd_toggle_translate(ctx, status: str = None):
    global translate_active
    if status is None:
        translate_active = not translate_active
    else:
        translate_active = status.lower() in ("on", "an", "ein", "true", "1", "aktiviert")

    color = discord.Color.green() if translate_active else discord.Color.red()
    de = "Aktiviert" if translate_active else "Deaktiviert"
    fr = "Activée" if translate_active else "Désactivée"

    embed = discord.Embed(
        title="VHA System • Übersetzung",
        description=f"**Deutsch ↔ Französisch** {de} / {fr}",
        color=color
    )
    await ctx.send(embed=embed)


@bot.command(name="ai")
@commands.cooldown(1, 12, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question or not question.strip():
        await ctx.send("Beispiel: `!ai Qui est la VHA ?`  oder  `!ai Was ist die VHA?`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    lang = detect_language_simple(question)  # hier nur DE/FR/UNKNOWN

    lang_map = {
        "DE": ("Deutsch",    "auf Deutsch",     "Antwort auf Deutsch"),
        "FR": ("Französisch","auf Französisch", "Réponse en français"),
    }
    _, prompt_lang, footer = lang_map.get(lang, ("Deutsch", "auf Deutsch", "Antwort auf Deutsch"))

    system = f"""Du bist ein freundlicher VHA-Alliance Assistent.
Antworte **ausschließlich** {prompt_lang}.
Keine Sprachhinweise. Natürlich und direkt."""

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=1400,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": question.strip()}
            ]
        )
        answer = resp.choices[0].message.content.strip()
        color = 0x5865F2
    except Exception as e:
        answer = f"Fehler: {str(e)}"
        color = 0xFF0000
        footer = "Fehler"

    embed = discord.Embed(
        title="VHA KI • Antwort",
        description=answer,
        color=color
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(name="→ Deine Frage", value=question[:900], inline=False)
    embed.set_footer(text=f"VHA • Groq • {GROQ_MODEL} • {footer}", icon_url=LOGO_URL)

    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# WICHTIG: AUTOMATISCHE ÜBERSETZUNG – NUR DE→FR oder FR→DE
# ────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    global processed_messages, translate_active

    if message.author.bot:
        return

    if message.id in processed_messages:
        return
    processed_messages.add(message.id)
    if len(processed_messages) > 300:
        processed_messages.clear()

    # Befehle verarbeiten
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    if not translate_active:
        return

    content = message.content.strip()
    if len(content) < 4:
        return

    low = content.lower()
    if low in {"ok", "lol", "xd", "haha", "ja", "nein", "oui", "non", "danke", "merci", "gg", "?", "!", "😂", "😅"}:
        return

    lang = detect_language_simple(content)

    if lang == "DE":
        # Deutsch → nur ins Französische übersetzen
        system_prompt = (
            "Du bist ein sehr natürlicher Übersetzer. "
            "Übersetze den folgenden deutschen Satz **idiomatisch und locker** ins Französische. "
            "Gib **nur** die französische Übersetzung aus – kein Einleitungssatz, kein Hinweis, nichts weiter."
        )
        flag = "🇫🇷"
    elif lang == "FR":
        # Französisch → nur ins Deutsche übersetzen
        system_prompt = (
            "Du bist ein sehr natürlicher Übersetzer. "
            "Übersetze den folgenden französischen Satz **idiomatisch und locker** ins Deutsche. "
            "Gib **nur** die deutsche Übersetzung aus – kein Einleitungssatz, kein Hinweis, nichts weiter."
        )
        flag = "🇩🇪"
    else:
        # andere Sprachen → gar nichts machen
        return

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.1,           # sehr deterministisch
            max_tokens=600,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": content}
            ]
        )
        translation = resp.choices[0].message.content.strip()

        # Vermeide doppelte / gleiche Übersetzung
        if translation.lower() == content.lower():
            return

        await message.reply(f"{flag} {translation}", mention_author=False)

    except Exception as e:
        print(f"Übersetzungsfehler: {e}")
        # stiller Fehler → kein Crash


# ────────────────────────────────────────────────
# START
# ────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN fehlt!")
        exit(1)
    bot.run(token)
