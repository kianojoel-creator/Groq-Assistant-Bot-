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
# SPRACHERKENNUNG – deutlich robuster für Französisch
# ────────────────────────────────────────────────

def detect_language_simple(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return "DE"

    t = text.lower()

    # Französisch – deutlich toleranter / mehr typische Wörter & Muster
    fr_patterns = [
        r"\b(je|tu|il|elle|on|nous|vous|ils|elles)\b",
        r"\b(suis|es|est|êtes|sommes|sont|était|étais|serai|serais)\b",
        r"\b(c'|ce|c'est|ça|qu'|qui|quoi|comment|pourquoi|quand|où|combien)\b",
        r"\b(oui|non|merci|désolé|bonjour|salut|pardon|excuse|voilà)\b",
        r"\b(le|la|les|un|une|des|du|de la|de l'|au|à la|aux)\b",
        r"(\?|!|\.{3})",  # Französisch nutzt oft ? und ! direkt nach Wörtern
    ]
    if any(re.search(p, t) for p in fr_patterns):
        return "FR"

    # Deutsch
    de_patterns = [
        r"\b(ich|du|er|sie|es|wir|ihr|sie)\b",
        r"\b(bin|bist|ist|sind|war|waren|haben|hast|hat)\b",
        r"\b(der|die|das|ein|eine|einen|einem|eines)\b",
        r"\b(und|oder|aber|denn|weil|dass)\b",
    ]
    if any(re.search(p, t) for p in de_patterns):
        return "DE"

    # Englisch (minimal)
    en_patterns = [
        r"\b(i|you|he|she|it|we|they)\b",
        r"\b(am|is|are|was|were|have|has|do|does)\b",
        r"\b(the|a|an|this|that|these|those)\b",
    ]
    if any(re.search(p, t) for p in en_patterns):
        return "EN"

    # Fallback
    return "DE"


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
        color=discord.Color.blue()
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.set_thumbnail(url=LOGO_URL)

    embed.add_field(
        name="Befehle",
        value=(
            "`!translate on/off` → Automatische Übersetzung an/aus\n"
            "`!ai [Frage]` → KI antwortet in der Sprache deiner Frage"
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
        translate_active = status.lower() in ("on", "an", "ein", "true", "1", "aktiviert", "active")

    color = discord.Color.green() if translate_active else discord.Color.red()

    de_status = "Aktiviert" if translate_active else "Deaktiviert"
    fr_status = "Activée" if translate_active else "Désactivée"

    embed = discord.Embed(
        title="VHA System",
        description=f"**Übersetzung {de_status}**\n**Traduction {fr_status}**",
        color=color
    )
    embed.set_author(name="VHA System", icon_url=LOGO_URL)

    await ctx.send(embed=embed)


@bot.command(name="ai")
@commands.cooldown(1, 12, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question or not question.strip():
        embed = discord.Embed(
            description="❓ Bitte eine Frage eingeben\nBeispiel: `!ai Was ist die VHA?`  oder  `!ai Qui est la VHA ?`",
            color=discord.Color.orange()
        )
        embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
        await ctx.send(embed=embed)
        return

    thinking = await ctx.send(embed=discord.Embed(
        description="**Denke nach …** 🧠",
        color=discord.Color.blurple()
    ))

    # ─── Sprache erkennen ───────────────────────────────
    lang_code = detect_language_simple(question)

    lang_map = {
        "DE": ("Deutsch",    "auf Deutsch",     "Antwort auf Deutsch"),
        "FR": ("Französisch","auf Französisch", "Réponse en français"),
        "EN": ("Englisch",   "in English",      "Answer in English"),
    }

    display_name, prompt_lang, footer_text = lang_map.get(lang_code, ("Deutsch", "auf Deutsch", "Antwort auf Deutsch"))

    # ─── Sehr strikter Prompt ───────────────────────────────
    system_content = f"""Du bist ein hilfreicher, präziser und freundlicher Assistent der VHA Alliance.

**WICHTIG – SPRACHE REGEL:**
- Antworte AUSSCHLIESSLICH in der Sprache, in der die Frage gestellt wurde.
- Wenn die Frage auf Französisch ist → antworte komplett auf Französisch.
- Wenn die Frage auf Deutsch ist     → antworte komplett auf Deutsch.
- Wenn die Frage auf Englisch ist    → antworte komplett auf Englisch.
- Keine Erklärung zur Sprache.
- Kein Code-Switching.
- Kein Satz wie „Ich antworte auf Deutsch/Französisch“.
- Sei natürlich und direkt in der Zielsprache.
"""

    try:
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.75,
            max_tokens=1400,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user",   "content": question.strip()}
            ]
        )

        answer = completion.choices[0].message.content.strip()
        color = discord.Color.from_rgb(88, 101, 242)

    except Exception as e:
        answer = f"Fehler bei der KI-Anfrage:\n{type(e).__name__}: {str(e)}"
        color = discord.Color.red()
        footer_text = "Fehler"

    embed = discord.Embed(
        title="VHA KI • Antwort",
        description=answer[:4000],
        color=color
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.set_thumbnail(url=LOGO_URL)
    embed.add_field(name="Deine Frage", value=f"→ {question[:1000]}", inline=False)
    embed.set_footer(
        text=f"VHA • Groq • {GROQ_MODEL} • {footer_text}",
        icon_url=LOGO_URL
    )

    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# AUTOMATISCHE ÜBERSETZUNG
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

    targets = ["DE", "FR"]
    lines = []

    for tgt in targets:
        if tgt == "DE":
            prompt = "Übersetze NUR ins Deutsche. Nur die Übersetzung. Kein Kommentar. Kein Hinweis."
            flag = "🇩🇪"
        elif tgt == "FR":
            prompt = "Übersetze NUR ins Französische. Nur die Übersetzung. Kein Kommentar. Kein Hinweis."
            flag = "🇫🇷"
        else:
            continue

        try:
            groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0.0,
                max_tokens=900,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content}
                ]
            )
            tr = completion.choices[0].message.content.strip()
            if tr and tr.lower() != content.lower():
                lines.append(f"{flag} {tr}")
        except Exception as e:
            print(f"Übersetzungsfehler {tgt}: {e.__class__.__name__}")
            continue

    if lines:
        await message.reply("\n".join(lines), mention_author=False)


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
