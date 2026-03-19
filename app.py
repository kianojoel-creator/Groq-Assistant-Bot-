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
translate_active = True   # ← immer aktiv beim Start


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Translator • Online"


# ────────────────────────────────────────────────
# SPRACHE ERKENNEN – extra stark für kurze Chat-Nachrichten
# ────────────────────────────────────────────────

def detect_language_simple(text: str) -> str:
def detect_language_simple(text: str) -> str:
    """
    Sehr tolerante Erkennung für Discord-Chat (kurze Sätze + Slang)
    """
    if not text or len(text.strip()) < 2:
        return "UNKNOWN"

    t = text.lower().strip()
    t_space = " " + t + " "

    # ──────────────────────────────
    # Französisch – deutlich breiter (Chat-Slang + typische kurze Antworten)
    # ──────────────────────────────
    fr_markers = [
        # Pronomen & Hilfsverben
        "je ", "j'", "tu ", "il ", "elle ", "on ", "nous ", "vous ", "ils ", "elles ",
        "suis ", "es ", "est ", "êtes ", "sommes ", "sont ", "était ", "serai ",
        # Typische Chat-Wörter / Slang
        "c'est ", "c ", "ça ", "sa ", "si ", "ouais ", "nan ", "non ", "mdr ", "ptdr ", "ahah ",
        "merci ", "stp ", "svp ", "désolé ", "deso ", "pardon ", "voilà ", "voila ", "oklm ",
        "tkt ", "tranquille ", "grave ", "ouf ", "wesh ", "frr ", "frère ", "mec ", "meuf ",
        "vas-y ", "vas ", "vasy ", "viens ", "viens-y ", "t'es ", "t'es où ", "t'es la ",
        "quoi ", "comment ", "pourquoi ", "quand ", "où ", "combien ", "combien tu ",
        "salut ", "yo ", "hey ", "coucou ", "bjr ", "bsoir ", "bientot ", "bientôt ",
        # Sehr häufige kurze Antworten
        "oui ", "nan ", "ok ", "kk ", "d'accord ", "dacc ", "nop ", "nope ", "bien ", "nickel "
    ]

    # ──────────────────────────────
    # Deutsch – bleibt ähnlich breit wie vorher
    # ──────────────────────────────
    de_markers = [
        "ich ", "du ", "er ", "sie ", "es ", "wir ", "ihr ", "bin ", "bist ", "ist ", "sind ",
        "hab ", "hast ", "hat ", "habe ", "haben ", "mach ", "mache ", "gemacht ", "versuch ",
        "gut ", "nacht ", "schlaf ", "bock ", "kein ", "mehr ", "jetzt ", "auch ", "nur ",
        "danke ", "bitte ", "klar ", "genau ", "jo ", "ey ", "np ", "kk ", "lol ", "xd ", "haha "
    ]

    # Kurze Sätze → direkt prüfen
    words = t.split()
    if len(words) <= 6:
        if any(w in t for w in fr_markers):
            return "FR"
        if any(w in t for w in de_markers):
            return "DE"

    # Längere Sätze → Wortgrenzen-Check
    if any(m in t_space for m in fr_markers):
        return "FR"
    if any(m in t_space for m in de_markers):
        return "DE"

    # Ultimativer Fallback: kurze Nachrichten (< 8 Wörter) als Deutsch annehmen
    # (weil euer Server mehrheitlich deutschsprachig ist)
    if len(words) <= 8:
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
# BEFEHLE
# ────────────────────────────────────────────────

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(title="VHA Translator – Hilfe", color=discord.Color.blue())
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(
        name="Befehle",
        value="`!translate on/off` → Automatische Übersetzung DE↔FR\n`!ai [Text]` → KI in deiner Sprache",
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
        translate_active = status.lower() in ("on", "an", "ein", "true", "1", "aktiviert", "active")

    color = discord.Color.green() if translate_active else discord.Color.red()
    embed = discord.Embed(
        title="VHA System • Übersetzung",
        description=f"**Deutsch ↔ Französisch** {'Aktiviert' if translate_active else 'Deaktiviert'}",
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

    lang = detect_language_simple(question)
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
            messages=[{"role": "system", "content": system}, {"role": "user", "content": question.strip()}]
        )
        answer = resp.choices[0].message.content.strip()
        color = 0x5865F2
    except Exception as e:
        answer = f"Fehler: {str(e)}"
        color = 0xFF0000
        footer = "Fehler"

    embed = discord.Embed(title="VHA KI • Antwort", description=answer, color=color)
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(name="→ Deine Frage", value=question[:900], inline=False)
    embed.set_footer(text=f"VHA • Groq • {GROQ_MODEL} • {footer}", icon_url=LOGO_URL)
    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# AUTOMATISCHE ÜBERSETZUNG – jetzt maximal tolerant
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

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if not translate_active:
        return

    content = message.content.strip()
    if len(content) < 2:          # fast nichts mehr blocken
        return

    low = content.lower()

    # Sehr minimale Ignore-Liste (nur extremster Spam)
    if low in {"?", "!", "xd", "lol", "ok"} and len(low) <= 3:
        return

    lang = detect_language_simple(content)

    if lang == "DE":
        flag = "🇫🇷"
        system_prompt = (
            "Du bist ein sehr natürlicher, umgangssprachlicher Übersetzer. "
            "Übersetze den folgenden deutschen Text **locker, jugendlich und idiomatisch** ins Französische. "
            "Gib **ausschließlich** die französische Übersetzung aus – KEINEN einleitenden Satz, KEIN 'Voici la traduction:', "
            "nur den reinen französischen Text."
        )
    elif lang == "FR":
        flag = "🇩🇪"
        system_prompt = (
            "Du bist ein sehr natürlicher, umgangssprachlicher Übersetzer. "
            "Übersetze den folgenden französischen Text **locker, jugendlich und idiomatisch** ins Deutsche. "
            "Gib **ausschließlich** die deutsche Übersetzung aus – KEINEN einleitenden Satz, KEIN 'Auf Deutsch:', "
            "nur den reinen deutschen Text."
        )
    else:
        return

    try:
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.15,
            max_tokens=700,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
        )

        translation = completion.choices[0].message.content.strip()

        if not translation or len(translation) < 4:
            return

        # Sehr toleranter Kopie-Check
        orig_clean = re.sub(r'[^a-zA-Z0-9äöüÄÖÜßéèêàâùûîôç ]', '', content.lower())
        trans_clean = re.sub(r'[^a-zA-Z0-9äöüÄÖÜßéèêàâùûîôç ]', '', translation.lower())

        if len(trans_clean) < 4 or abs(len(trans_clean) - len(orig_clean)) < 5:
            return

        await message.reply(f"{flag} {translation}", mention_author=False)

    except Exception as e:
        print(f"Übersetzungsfehler: {type(e).__name__} - {str(e)}")


# ────────────────────────────────────────────────
# START
# ────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True, name="Flask-KeepAlive").start()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN fehlt!")
        exit(1)

    bot.run(token)
