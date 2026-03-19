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

FR_INDICATORS = {
    "c'est", "ce", "est", "suis", "es", "sommes", "êtes", "sont",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "oui", "non", "pas", "ne", "le", "la", "les", "un", "une", "des",
    "et", "ou", "mais", "que", "qui", "pour", "dans", "sur", "avec", "à"
}

DE_INDICATORS = {
    "ist", "bin", "bist", "sind", "seid", "ich", "du", "er", "sie", "es",
    "wir", "ihr", "Sie", "ja", "nein", "nicht", "kein", "der", "die", "das",
    "ein", "eine", "und", "oder", "aber", "dass", "für", "mit", "auf", "in", "zu"
}

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
# SPRACHERKENNUNG (nur DE/FR zuverlässig)
# ────────────────────────────────────────────────

def detect_language_simple(text: str) -> str | None:
    if not text.strip():
        return None
    t = text.lower()
    fr_score = sum(1 for w in FR_INDICATORS if re.search(rf'\b{w}\b', t))
    de_score = sum(1 for w in DE_INDICATORS if re.search(rf'\b{w}\b', t))
    if fr_score > de_score + 1:
        return "FR"
    if de_score > fr_score + 1:
        return "DE"
    return None


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
    embed = discord.Embed(
        title="VHA Translator – Hilfe",
        color=discord.Color.blue(),
        description=(
            "**Befehle**\n\n"
            "`!translate on` / `!translate off`   → Automatische Übersetzung\n"
            "`!ai [Frage]`                        → Direkte KI-Anfrage\n\n"
        )
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="VHA • Powering Communication", icon_url=LOGO_URL)
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
        title="Übersetzungs-Modus",
        description=(
            f"**{'Aktiviert' if translate_active else 'Deaktiviert'}**  🇩🇪\n"
            f"**{'Activée' if translate_active else 'Désactivée'}**  🇫🇷"
        ),
        color=color
    )
    embed.set_author(name="VHA System", icon_url=LOGO_URL)
    await ctx.send(embed=embed)


@bot.command(name="ai")
@commands.cooldown(1, 10, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question or not question.strip():
        embed = discord.Embed(
            description="❓ Bitte eine Frage eingeben\nBeispiel: `!ai Was ist die VHA Alliance?`",
            color=discord.Color.orange()
        )
        embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
        await ctx.send(embed=embed)
        return

    thinking = await ctx.send(embed=discord.Embed(
        description="**Denke nach …** 🧠",
        color=discord.Color.blurple()
    ))

    try:
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.75,
            max_tokens=1400,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein hilfreicher, präziser und freundlicher Assistent der VHA Alliance. "
                        "Antworte klar, natürlich und **immer auf Deutsch**, außer der User fragt explizit in einer anderen Sprache."
                    )
                },
                {"role": "user", "content": question}
            ]
        )
        answer = completion.choices[0].message.content.strip()
        color = discord.Color.from_rgb(88, 101, 242)

    except Exception as e:
        answer = f"Fehler bei der KI-Anfrage:\n{type(e).__name__}: {str(e)}"
        color = discord.Color.red()

    embed = discord.Embed(
        title="VHA KI • Antwort",
        description=answer[:4000],
        color=color
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.set_thumbnail(url=LOGO_URL)
    embed.add_field(name="Deine Frage", value=f"→ {question[:1000]}", inline=False)
    embed.set_footer(text="VHA • Groq • llama-3.3-70b-versatile", icon_url=LOGO_URL)

    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# HAUPT-ÜBERSETZUNGS-LOGIK (mit Reply-Support)
# ────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    global processed_messages, translate_active

    if message.author.bot:
        return

    if message.id in processed_messages:
        return

    processed_messages.add(message.id)
    if len(processed_messages) > 250:
        processed_messages.clear()

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    content = message.content.strip()
    if not translate_active or len(content) < 2:
        return

    lower = content.lower()
    if lower in {"ok", "lol", "xd", "haha", "oui", "ja", "nein", "danke", "merci", "?", "!", "😂", "😅", "gg"}:
        return

    # ────────────────────────────────
    # Welche Sprachen sollen wir ausgeben?
    # ────────────────────────────────
    targets = ["DE", "FR"]
    ref_lang = None
    ref_text = ""

    # Reply → Sprache der referenzierten Nachricht ermitteln
    if message.reference and message.reference.message_id:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            ref_text = ref_msg.content.strip()
            if ref_text and len(ref_text) > 3:
                ref_lang = detect_language_simple(ref_text)
                if not ref_lang:  # nicht DE/FR → als "fremd" behandeln
                    ref_lang = "OTHER"
        except:
            pass

    if ref_lang == "OTHER":
        targets.append("ORIGINAL")

    # ────────────────────────────────
    # Übersetzungen erzeugen
    # ────────────────────────────────
    translations = {}

    for tgt in targets:
        if tgt == "DE":
            prompt = "Übersetze NUR ins Deutsche. Nur die Übersetzung. Kein Kommentar."
            flag = "🇩🇪"
        elif tgt == "FR":
            prompt = "Übersetze NUR ins Französische. Nur die Übersetzung. Kein Kommentar."
            flag = "🇫🇷"
        else:  # ORIGINAL
            prompt = (
                "Übersetze NUR in die Sprache des folgenden Originaltexts. "
                "Gib NUR die Übersetzung aus. Kein Kommentar, kein Sprachhinweis."
            )
            flag = "🌐"

        try:
            groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0.1,
                max_tokens=1100,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Kontext (nicht übersetzen):\n{ref_text}\n\nText:\n{content}"}
                ]
            )
            translated = completion.choices[0].message.content.strip()

            if translated and translated.lower() != content.lower() and translated.lower() != ref_text.lower():
                translations[tgt] = (flag, translated)

        except Exception as e:
            print(f"Übersetzungsfehler {tgt}: {e.__class__.__name__}")
            continue

    # ────────────────────────────────
    # Ergebnis senden
    # ────────────────────────────────
    if translations:
        embed = discord.Embed(color=discord.Color.from_rgb(88, 101, 242))

        for lang, (flag, text) in translations.items():
            embed.add_field(
                name=f"{flag} Übersetzung",
                value=text[:1010] + (" …" if len(text) > 1010 else ""),
                inline=False
            )

        if "ORIGINAL" in translations:
            embed.set_footer(text="→ Auch in die Sprache der Originalnachricht übersetzt")

        await message.reply(embed=embed, mention_author=False)


# ────────────────────────────────────────────────
# START
# ────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True, name="Flask-KeepAlive").start()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN fehlt in den Umgebungsvariablen!")
        exit(1)

    bot.run(token)
