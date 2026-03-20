import discord
from discord.ext import commands
import os
import re
import time
import threading
from collections import deque
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

processed_messages = deque(maxlen=500)
processed_messages_set = set()

translate_active = True

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

user_last_translation: dict[int, float] = {}
TRANSLATION_COOLDOWN = 3.0


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Translator • Online"


# ────────────────────────────────────────────────
# SPRACHE ERKENNEN via Groq LLM
# Gibt ISO-Code zurück: "DE", "FR", "OTHER", oder z.B. "JA", "EN", "ES" ...
# ────────────────────────────────────────────────

async def detect_language_llm(text: str) -> str:
    """
    Gibt einen Sprachcode zurück:
    - 'DE'    = Deutsch
    - 'FR'    = Französisch
    - 'OTHER' = neutral (ok, lol, gg, Emojis, Zahlen ...)
    - 'EN', 'JA', 'ES', 'IT', ... = andere erkannte Sprachen
    """
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.0,
            max_tokens=10,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Detect the language of the given text. "
                        "Reply with ONLY the ISO 639-1 two-letter language code in uppercase (e.g. DE, FR, EN, JA, ES, IT, PT, RU, ZH, AR, KO, TR, PL, NL). "
                        "If the text is language-neutral (e.g. 'ok', 'lol', 'gg', emojis only, numbers only, single symbols), reply with exactly: OTHER. "
                        "No explanation. No punctuation. Just the code."
                    )
                },
                {"role": "user", "content": text}
            ]
        )
        result = resp.choices[0].message.content.strip().upper()
        # Nur gültige 2-Buchstaben-Codes oder OTHER akzeptieren
        if result == "OTHER":
            return "OTHER"
        if re.match(r'^[A-Z]{2}$', result):
            return result
        # Fallback: ersten 2-Buchstaben-Code aus der Antwort extrahieren
        match = re.search(r'\b([A-Z]{2})\b', result)
        if match:
            return match.group(1)
        return "OTHER"
    except Exception as e:
        print(f"Spracherkennungs-Fehler: {e}")
        return "OTHER"


# ────────────────────────────────────────────────
# ÜBERSETZEN via Groq LLM
# ────────────────────────────────────────────────

async def translate_text(text: str, target_lang_name: str) -> str:
    """Übersetzt text in die Zielsprache. Gibt nur die Übersetzung zurück."""
    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.15,
            max_tokens=700,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a natural, colloquial translator. "
                        f"Translate the given text into {target_lang_name}. "
                        f"Output ONLY the translation — no intro, no explanation, no quotes, no labels."
                    )
                },
                {"role": "user", "content": text}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Übersetzungsfehler ({target_lang_name}): {e}")
        return ""


# Flaggen-Mapping für bekannte Sprachen
LANG_FLAGS = {
    "DE": "🇩🇪", "FR": "🇫🇷", "EN": "🇬🇧", "JA": "🇯🇵",
    "ES": "🇪🇸", "IT": "🇮🇹", "PT": "🇵🇹", "RU": "🇷🇺",
    "ZH": "🇨🇳", "AR": "🇸🇦", "KO": "🇰🇷", "TR": "🇹🇷",
    "PL": "🇵🇱", "NL": "🇳🇱",
}

# Sprachname auf Englisch für den Übersetzungs-Prompt
LANG_NAMES = {
    "DE": "German", "FR": "French", "EN": "English", "JA": "Japanese",
    "ES": "Spanish", "IT": "Italian", "PT": "Portuguese", "RU": "Russian",
    "ZH": "Chinese", "AR": "Arabic", "KO": "Korean", "TR": "Turkish",
    "PL": "Polish", "NL": "Dutch",
}


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
    await bot.load_extension("koordinaten")
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
    embed.add_field(
        name="🇩🇪 Deutsch",
        value=(
            "`!translate on` – Automatik einschalten\n"
            "`!translate off` – Automatik ausschalten\n"
            "`!translate status` – Status anzeigen\n"
            "`!ai [Frage]` – KI direkt fragen"
        ),
        inline=False
    )
    embed.add_field(
        name="🇫🇷 Français",
        value=(
            "`!translate on` – Activer la traduction\n"
            "`!translate off` – Désactiver la traduction\n"
            "`!translate status` – Voir le statut\n"
            "`!ai [Question]` – Poser une question à l'IA"
        ),
        inline=False
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="VHA - Powering Communication", icon_url=LOGO_URL)
    await ctx.send(embed=embed)


@bot.command(name="translate")
@commands.has_permissions(manage_messages=True)
async def cmd_translate(ctx, action: str = None):
    global translate_active

    if action is None:
        await ctx.send(
            "❓ Benutzung: `!translate on` / `!translate off` / `!translate status`\n"
            "Usage: `!translate on` / `!translate off` / `!translate status`"
        )
        return

    action = action.lower()

    if action == "on":
        translate_active = True
        embed = discord.Embed(title="VHA System • Übersetzung", color=0x57F287)
        embed.add_field(name="Deutsch ↔ Français", value="Aktiviert / Activée", inline=False)
        await ctx.send(embed=embed)

    elif action == "off":
        translate_active = False
        embed = discord.Embed(title="VHA System • Übersetzung", color=0xED4245)
        embed.add_field(name="Deutsch ↔ Français", value="Deaktiviert / Désactivée", inline=False)
        await ctx.send(embed=embed)

    elif action == "status":
        if translate_active:
            embed = discord.Embed(title="VHA System • Übersetzung", color=0x57F287)
            embed.add_field(name="Deutsch ↔ Français", value="Aktiviert / Activée", inline=False)
        else:
            embed = discord.Embed(title="VHA System • Übersetzung", color=0xED4245)
            embed.add_field(name="Deutsch ↔ Français", value="Deaktiviert / Désactivée", inline=False)
        await ctx.send(embed=embed)

    else:
        await ctx.send(
            "❓ Unbekannte Option. Benutze: `!translate on` / `!translate off` / `!translate status`\n"
            "Option inconnue. Utilise: `!translate on` / `!translate off` / `!translate status`"
        )


@cmd_translate.error
async def translate_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Du hast keine Berechtigung dafür. / Tu n'as pas la permission.")


@bot.command(name="ai")
@commands.cooldown(1, 12, commands.BucketType.user)
async def cmd_ai(ctx, *, question: str = None):
    if not question or not question.strip():
        await ctx.send("Beispiel: `!ai Qui est la VHA ?`  oder  `!ai Was ist die VHA?`")
        return

    thinking = await ctx.send("**Denke nach …** 🧠")

    lang = await detect_language_llm(question)

    # Antwort immer in der Sprache der Frage — egal welche Sprache
    # Groq bekommt die Frage direkt, ohne festes Sprach-Limit im System-Prompt
    # Das Modell antwortet automatisch in der Sprache der Frage
    flag = LANG_FLAGS.get(lang, "🌐")
    footer = f"Antwort in {lang}" if lang not in ("OTHER",) else "Antwort"

    system = (
        "Du bist ein freundlicher VHA-Alliance Assistent. "
        "Antworte IMMER in derselben Sprache wie die Frage des Nutzers. "
        "Keine Sprachhinweise. Natürlich und direkt."
    )

    try:
        resp = groq_client.chat.completions.create(
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

    embed = discord.Embed(title=f"VHA KI • Antwort {flag}", description=answer, color=color)
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.add_field(name="→ Deine Frage", value=question[:900], inline=False)
    embed.set_footer(text=f"VHA • Groq • {GROQ_MODEL} • {footer}", icon_url=LOGO_URL)
    await thinking.edit(embed=embed)


# ────────────────────────────────────────────────
# AUTOMATISCHE ÜBERSETZUNG
# ────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    global processed_messages, processed_messages_set, translate_active

    if message.author.bot:
        return

    # Gleitendes Fenster gegen Duplikate
    if message.id in processed_messages_set:
        return
    if len(processed_messages) == processed_messages.maxlen:
        oldest = processed_messages[0]
        processed_messages_set.discard(oldest)
    processed_messages.append(message.id)
    processed_messages_set.add(message.id)

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if not translate_active:
        return

    content = message.content.strip()

    if len(content) < 2:
        return
    if re.match(r'^https?://', content):
        return

    # Cooldown pro User
    now = time.time()
    last = user_last_translation.get(message.author.id, 0)
    if now - last < TRANSLATION_COOLDOWN:
        return
    user_last_translation[message.author.id] = now

    # Sprache erkennen
    lang = await detect_language_llm(content)

    if lang == "OTHER":
        return

    # ── Logik: was wird wohin übersetzt ──────────────────────────────────────
    #
    # DE → nur FR
    # FR → nur DE
    # Andere Sprache (EN, JA, ES, ...) → DE + FR
    #
    # Beim Antworten auf eine andere Sprache:
    #   Wenn du (DE) auf einen Japaner antwortest → Antwort auf FR + JA übersetzen (nicht nochmal DE)
    #   Wenn du (FR) auf einen Japaner antwortest → Antwort auf DE + JA übersetzen (nicht nochmal FR)
    # ─────────────────────────────────────────────────────────────────────────

    # Prüfen ob diese Nachricht eine Antwort auf eine andere Nachricht ist
    # und die Originalsprache des "Eltern-Nachrichten"-Autors ermitteln
    reply_target_lang = None
    if message.reference and message.reference.resolved:
        ref = message.reference.resolved
        if isinstance(ref, discord.Message) and not ref.author.bot:
            ref_lang = await detect_language_llm(ref.content.strip())
            if ref_lang not in ("DE", "FR", "OTHER"):
                reply_target_lang = ref_lang  # z.B. "JA" – Gast-Sprache

    # Absendername für Embed-Titel
    author_name = message.author.display_name

    def make_embed(flag: str, translation: str, color: int, target_lang: str = "") -> discord.Embed:
        """Erstellt ein sauberes Übersetzungs-Embed."""
        embed = discord.Embed(
            title=f"{flag} • {author_name}",
            description=translation,
            color=color
        )
        embed.set_footer(text="VHA Translator", icon_url=LOGO_URL)
        return embed

    def make_guest_embed(de_text: str, fr_text: str) -> discord.Embed:
        """Gast-Embed mit DE + FR in einem Kasten."""
        embed = discord.Embed(
            title=f"🌍 • {author_name}",
            color=0x9B59B6  # Lila für Gäste
        )
        if de_text:
            embed.add_field(name="🇩🇪 Deutsch", value=de_text, inline=False)
        if fr_text:
            embed.add_field(name="🇫🇷 Français", value=fr_text, inline=False)
        embed.set_footer(text="VHA Translator", icon_url=LOGO_URL)
        return embed

    try:
        # ── Fall 1: Deutsch geschrieben ──────────────────────────────────
        if lang == "DE":
            if reply_target_lang:
                # Antwort auf Gast → FR + Gastsprache (kein DE nochmal)
                fr_text = await translate_text(content, "French")
                guest_text = await translate_text(content, LANG_NAMES.get(reply_target_lang, reply_target_lang))
                guest_flag = LANG_FLAGS.get(reply_target_lang, "🌐")
                if fr_text and fr_text.lower() != content.lower():
                    await message.reply(embed=make_embed("🇫🇷", fr_text, 0x3498DB), mention_author=False)
                if guest_text and guest_text.lower() != content.lower():
                    await message.reply(embed=make_embed(guest_flag, guest_text, 0x3498DB), mention_author=False)
            else:
                # Normaler deutscher Text → nur FR
                fr_text = await translate_text(content, "French")
                if fr_text and fr_text.lower() != content.lower():
                    await message.reply(embed=make_embed("🇫🇷", fr_text, 0x3498DB), mention_author=False)

        # ── Fall 2: Französisch geschrieben ──────────────────────────────
        elif lang == "FR":
            if reply_target_lang:
                # Antwort auf Gast → DE + Gastsprache (kein FR nochmal)
                de_text = await translate_text(content, "German")
                guest_text = await translate_text(content, LANG_NAMES.get(reply_target_lang, reply_target_lang))
                guest_flag = LANG_FLAGS.get(reply_target_lang, "🌐")
                if de_text and de_text.lower() != content.lower():
                    await message.reply(embed=make_embed("🇩🇪", de_text, 0x3498DB), mention_author=False)
                if guest_text and guest_text.lower() != content.lower():
                    await message.reply(embed=make_embed(guest_flag, guest_text, 0x3498DB), mention_author=False)
            else:
                # Normaler französischer Text → nur DE
                de_text = await translate_text(content, "German")
                if de_text and de_text.lower() != content.lower():
                    await message.reply(embed=make_embed("🇩🇪", de_text, 0x3498DB), mention_author=False)

        # ── Fall 3: Andere Sprache (Gast) → alles in einem Embed ─────────
        else:
            de_text = await translate_text(content, "German")
            fr_text = await translate_text(content, "French")
            de_ok = de_text and de_text.lower() != content.lower()
            fr_ok = fr_text and fr_text.lower() != content.lower()
            if de_ok or fr_ok:
                await message.reply(
                    embed=make_guest_embed(
                        de_text if de_ok else "",
                        fr_text if fr_ok else ""
                    ),
                    mention_author=False
                )

    except Exception as e:
        print(f"Übersetzungsfehler: {type(e).__name__} - {str(e)}")
        try:
            await message.add_reaction("⚠️")
        except Exception:
            pass


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
