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
from groq import Groq

# ────────────────────────────────────────────────
# LOGGING
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("groq_usage.log", encoding="utf-8"),
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

GROQ_MODEL       = "llama-3.3-70b-versatile"
BOT_LOG_CHANNEL_ID = 1484252260614537247

# ────────────────────────────────────────────────
# GLOBALS & FLASK
# ────────────────────────────────────────────────

app = Flask(__name__)

processed_messages     = deque(maxlen=500)
processed_messages_set = set()

translate_active = True

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Semaphore: max. 4 gleichzeitige Groq-Calls
groq_semaphore = asyncio.Semaphore(4)

user_last_translation: dict[int, float] = {}
TRANSLATION_COOLDOWN = 3.0

# Token-Zähler für den Tag
token_counter = {"prompt": 0, "completion": 0, "total": 0}


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


@app.route("/")
def home():
    return "VHA Translator • Online"


# ────────────────────────────────────────────────
# GROQ ASYNC WRAPPER mit Retry
# ────────────────────────────────────────────────

async def groq_call(model: str, messages: list, temperature: float = 0.15,
                    max_tokens: int = 500, retries: int = 3) -> str:
    """
    Führt einen Groq-API-Call asynchron aus.
    - Semaphore: max. 4 gleichzeitige Calls
    - Automatischer Retry bei Rate-Limit (429) oder Server-Fehler (5xx)
    - Loggt Token-Verbrauch
    """
    loop = asyncio.get_event_loop()
    wait = 2

    for attempt in range(retries):
        async with groq_semaphore:
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda: groq_client.chat.completions.create(
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        messages=messages
                    )
                )
                # Token-Verbrauch loggen
                if resp.usage:
                    token_counter["prompt"]     += resp.usage.prompt_tokens
                    token_counter["completion"] += resp.usage.completion_tokens
                    token_counter["total"]      += resp.usage.total_tokens
                    log.info(
                        f"Tokens: +{resp.usage.total_tokens} "
                        f"(heute gesamt: {token_counter['total']})"
                    )
                return resp.choices[0].message.content.strip()

            except Exception as e:
                err = str(e)
                if "429" in err or "rate" in err.lower():
                    log.warning(f"Rate-Limit (Versuch {attempt+1}/{retries}) – warte {wait}s")
                    await asyncio.sleep(wait)
                    wait *= 2
                elif "5" in err[:3]:
                    log.warning(f"Server-Fehler (Versuch {attempt+1}/{retries}) – warte {wait}s")
                    await asyncio.sleep(wait)
                    wait *= 2
                else:
                    log.error(f"Groq-Fehler: {e}")
                    raise

    raise Exception("Groq nicht erreichbar nach mehreren Versuchen")


# ────────────────────────────────────────────────
# SPRACHE ERKENNEN
# ────────────────────────────────────────────────

# Cache für kurze Texte (spart Tokens)
lang_cache: dict[str, str] = {}

async def detect_language_llm(text: str) -> str:
    """Erkennt die Sprache via Groq. Cached kurze Texte."""
    key = text.lower().strip()[:80]
    if key in lang_cache:
        return lang_cache[key]

    try:
        result = await groq_call(
            model=GROQ_MODEL,
            temperature=0.0,
            max_tokens=5,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Detect the language of the text. "
                        "Reply with ONLY the ISO 639-1 two-letter code in uppercase (DE, FR, PT, EN, JA, ES, IT, RU, ZH, AR, KO, TR, PL, NL). "
                        "If neutral (ok, lol, gg, emojis only, numbers only) reply: OTHER. "
                        "No explanation. Just the code."
                    )
                },
                {"role": "user", "content": text}
            ]
        )
        result = result.upper()
        if result == "OTHER":
            lang = "OTHER"
        elif re.match(r'^[A-Z]{2}$', result):
            lang = result
        else:
            m = re.search(r'\b([A-Z]{2})\b', result)
            lang = m.group(1) if m else "OTHER"

        # Cache nur für kurze Texte
        if len(key) < 80:
            lang_cache[key] = lang
            if len(lang_cache) > 500:
                # Älteste 100 Einträge löschen
                for k in list(lang_cache.keys())[:100]:
                    del lang_cache[k]

        return lang

    except Exception as e:
        log.error(f"Spracherkennungs-Fehler: {e}")
        return "OTHER"


# ────────────────────────────────────────────────
# ÜBERSETZEN
# ────────────────────────────────────────────────

async def translate_text(text: str, target_lang_name: str) -> str:
    """Übersetzt text in die Zielsprache."""
    try:
        return await groq_call(
            model=GROQ_MODEL,
            temperature=0.15,
            max_tokens=450,
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
    except Exception as e:
        log.error(f"Übersetzungsfehler ({target_lang_name}): {e}")
        return ""


# ────────────────────────────────────────────────
# FLAGGEN & SPRACHNAMEN
# ────────────────────────────────────────────────

LANG_FLAGS = {
    "DE": "🇩🇪", "FR": "🇫🇷", "PT": "🇧🇷", "EN": "🇬🇧",
    "JA": "🇯🇵", "ES": "🇪🇸", "IT": "🇮🇹", "RU": "🇷🇺",
    "ZH": "🇨🇳", "AR": "🇸🇦", "KO": "🇰🇷", "TR": "🇹🇷",
    "PL": "🇵🇱", "NL": "🇳🇱",
}

LANG_NAMES = {
    "DE": "German", "FR": "French", "PT": "Brazilian Portuguese",
    "EN": "English", "JA": "Japanese", "ES": "Spanish",
    "IT": "Italian", "RU": "Russian", "ZH": "Chinese",
    "AR": "Arabic", "KO": "Korean", "TR": "Turkish",
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


bot_ready = False  # Verhindert doppeltes Laden

@bot.event
async def on_ready():
    global bot_ready
    if bot_ready:
        return  # Bereits initialisiert → überspringen
    bot_ready = True
    errors = []

    try:
        await bot.load_extension("koordinaten")
    except Exception as e:
        errors.append(f"❌ koordinaten: {e}")

    try:
        await bot.load_extension("timer")
    except Exception as e:
        errors.append(f"❌ timer: {e}")

    try:
        from bilduebersetzer import setup as setup_bild
        await setup_bild(bot, groq_client, groq_call)
    except Exception as e:
        errors.append(f"❌ bilduebersetzer: {e}")

    try:
        await bot.load_extension("spieler")
    except Exception as e:
        errors.append(f"❌ spieler: {e}")

    try:
        from event import setup as setup_event
        await setup_event(bot, groq_call)
    except Exception as e:
        errors.append(f"❌ event: {e}")

    try:
        await bot.load_extension("log")
    except Exception as e:
        errors.append(f"❌ log: {e}")

    log.info(f"→ {bot.user}  •  ONLINE  •  {discord.utils.utcnow():%Y-%m-%d %H:%M UTC}")

    if BOT_LOG_CHANNEL_ID:
        channel = bot.get_channel(BOT_LOG_CHANNEL_ID)
        if channel:
            if errors:
                msg = "⚠️ **Bot gestartet mit Fehlern:**\n" + "\n".join(errors)
            else:
                msg = (
                    "✅ **Bot erfolgreich gestartet!**\n"
                    "🔧 koordinaten.py • geladen\n"
                    "🔧 timer.py • geladen\n"
                    "🔧 bilduebersetzer.py • geladen\n"
                    "🔧 spieler.py • geladen\n"
                    "🔧 event.py • geladen\n"
                    "🔧 log.py • geladen"
                )
            await channel.send(msg)

# ────────────────────────────────────────────────
# BEFEHLE
# ────────────────────────────────────────────────

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="VHA Bot – Befehle / Commandes / Comandos",
        color=0x5865F2
    )
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)

    embed.add_field(
        name="🌐 Übersetzer / Traducteur / Tradutor",
        value=(
            "`!translate on` / `!translate off` – An • Aus / Activer • Désactiver / Ativar • Desativar\n"
            "`!translate status` – Status / Statut / Estado\n"
            "`!ai [Text]` – KI fragen / Poser une question / Perguntar à IA\n"
            "`!übersetze` / `!traduire` – Bild übersetzen / Traduire image / Traduzir imagem"
        ),
        inline=False
    )

    embed.add_field(
        name="📍 Koordinaten / Coordonnées / Coordenadas  🔐 R5 • R4",
        value=(
            "`!koordinaten` / `!coordonnees` – Liste anzeigen / Afficher / Ver lista\n"
            "`!koordinaten add NAME R X Y` – Hinzufügen / Ajouter / Adicionar\n"
            "`!koordinaten delete NAME` – Löschen / Supprimer / Apagar"
        ),
        inline=False
    )

    embed.add_field(
        name="👥 Spieler-IDs / Joueurs / Jogadores  🔐 R5 • R4",
        value=(
            "`!spieler` / `!joueur` – Liste / Afficher / Ver lista\n"
            "`!spieler add NAME ID` – Hinzufügen / Ajouter / Adicionar\n"
            "`!spieler delete NAME` – Löschen / Supprimer / Apagar\n"
            "`!spieler suche NAME/ID` – Suchen / Rechercher / Pesquisar"
        ),
        inline=False
    )

    embed.add_field(
        name="⏱️ Timer / Rappel / Lembrete  🔐 R5 • R4",
        value=(
            "`!timer 2h Kriegsstart` / `!rappel 2h Event` – Timer setzen / Définir / Definir\n"
            "`!timer list` – Aktive Timer / Minuteurs / Lembretes ativos\n"
            "`!timer delete NAME` – Löschen / Supprimer / Apagar\n"
            "⏳ Formate: `30m` • `2h` • `1h30m` • `3d`"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Events  🔐 R5 • R4",
        value=(
            "`!event` – Event aus Screenshot erkennen & Timer setzen\n"
            "Als Reply auf Event-Screenshot tippen / En réponse à une capture / Em resposta a uma captura"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Status",
        value="`!ping` – Bot-Status / Latenz",
        inline=False
    )

    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="VHA - Powering Communication", icon_url=LOGO_URL)
    await ctx.send(embed=embed)


@bot.command(name="ping")
async def cmd_ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        color=0x57F287 if latency < 200 else 0xF39C12
    )
    embed.add_field(name="📡 Latenz / Latence", value=f"`{latency}ms`", inline=True)
    embed.add_field(name="📊 Tokens heute / Today", value=f"`{token_counter['total']}`", inline=True)
    embed.set_footer(text="VHA Bot • Online", icon_url=LOGO_URL)
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
        embed.add_field(name="Deutsch ↔ Français ↔ Português", value="Aktiviert / Activée / Ativada", inline=False)
        await ctx.send(embed=embed)

    elif action == "off":
        translate_active = False
        embed = discord.Embed(title="VHA System • Übersetzung", color=0xED4245)
        embed.add_field(name="Deutsch ↔ Français ↔ Português", value="Deaktiviert / Désactivée / Desativada", inline=False)
        await ctx.send(embed=embed)

    elif action == "status":
        if translate_active:
            embed = discord.Embed(title="VHA System • Übersetzung", color=0x57F287)
            embed.add_field(name="Deutsch ↔ Français ↔ Português", value="Aktiviert / Activée / Ativada", inline=False)
        else:
            embed = discord.Embed(title="VHA System • Übersetzung", color=0xED4245)
            embed.add_field(name="Deutsch ↔ Français ↔ Português", value="Deaktiviert / Désactivée / Desativada", inline=False)
        await ctx.send(embed=embed)

    else:
        await ctx.send(
            "❓ Unbekannte Option. Benutze: `!translate on` / `!translate off` / `!translate status`"
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
    flag = LANG_FLAGS.get(lang, "🌐")
    footer = f"Antwort in {lang}"

    try:
        answer = await groq_call(
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=1000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein freundlicher VHA-Alliance Assistent. "
                        "Antworte IMMER in derselben Sprache wie die Frage. "
                        "Natürlich und direkt."
                    )
                },
                {"role": "user", "content": question.strip()}
            ]
        )
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

    # Zu kurz, nur Link oder nur Emoji → skip
    if len(content) < 3:
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

    # Reply-Ziel Sprache prüfen
    reply_target_lang = None
    if message.reference and message.reference.resolved:
        ref = message.reference.resolved
        if isinstance(ref, discord.Message) and not ref.author.bot:
            ref_lang = await detect_language_llm(ref.content.strip())
            if ref_lang not in ("DE", "FR", "PT", "OTHER"):
                reply_target_lang = ref_lang

    author_name = message.author.display_name

    def make_multi_embed(fields: list, color: int = 0x3498DB) -> discord.Embed:
        embed = discord.Embed(title=f"💬 • {author_name}", color=color)
        for flag, text in fields:
            embed.add_field(name=flag, value=text[:1000], inline=False)
        embed.set_footer(text="VHA Translator", icon_url=LOGO_URL)
        return embed

    try:
        fields = []

        if lang == "DE":
            # Parallel übersetzen
            fr_text, pt_text = await asyncio.gather(
                translate_text(content, "French"),
                translate_text(content, "Brazilian Portuguese")
            )
            if fr_text and fr_text.lower() != content.lower():
                fields.append(("🇫🇷 Français", fr_text))
            if pt_text and pt_text.lower() != content.lower():
                fields.append(("🇧🇷 Português", pt_text))
            if reply_target_lang:
                guest_text = await translate_text(content, LANG_NAMES.get(reply_target_lang, reply_target_lang))
                guest_flag = LANG_FLAGS.get(reply_target_lang, "🌐")
                if guest_text and guest_text.lower() != content.lower():
                    fields.append((guest_flag, guest_text))

        elif lang == "FR":
            de_text, pt_text = await asyncio.gather(
                translate_text(content, "German"),
                translate_text(content, "Brazilian Portuguese")
            )
            if de_text and de_text.lower() != content.lower():
                fields.append(("🇩🇪 Deutsch", de_text))
            if pt_text and pt_text.lower() != content.lower():
                fields.append(("🇧🇷 Português", pt_text))
            if reply_target_lang:
                guest_text = await translate_text(content, LANG_NAMES.get(reply_target_lang, reply_target_lang))
                guest_flag = LANG_FLAGS.get(reply_target_lang, "🌐")
                if guest_text and guest_text.lower() != content.lower():
                    fields.append((guest_flag, guest_text))

        elif lang == "PT":
            de_text, fr_text = await asyncio.gather(
                translate_text(content, "German"),
                translate_text(content, "French")
            )
            if de_text and de_text.lower() != content.lower():
                fields.append(("🇩🇪 Deutsch", de_text))
            if fr_text and fr_text.lower() != content.lower():
                fields.append(("🇫🇷 Français", fr_text))
            if reply_target_lang:
                guest_text = await translate_text(content, LANG_NAMES.get(reply_target_lang, reply_target_lang))
                guest_flag = LANG_FLAGS.get(reply_target_lang, "🌐")
                if guest_text and guest_text.lower() != content.lower():
                    fields.append((guest_flag, guest_text))

        else:
            # Gast → alle 3 parallel
            de_text, fr_text, pt_text = await asyncio.gather(
                translate_text(content, "German"),
                translate_text(content, "French"),
                translate_text(content, "Brazilian Portuguese")
            )
            if de_text and de_text.lower() != content.lower():
                fields.append(("🇩🇪 Deutsch", de_text))
            if fr_text and fr_text.lower() != content.lower():
                fields.append(("🇫🇷 Français", fr_text))
            if pt_text and pt_text.lower() != content.lower():
                fields.append(("🇧🇷 Português", pt_text))

        if fields:
            color = 0x9B59B6 if lang not in ("DE", "FR", "PT") else 0x3498DB
            await message.reply(embed=make_multi_embed(fields, color), mention_author=False)

    except Exception as e:
        log.error(f"Übersetzungsfehler: {type(e).__name__} - {str(e)}")
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
        log.error("DISCORD_TOKEN fehlt!")
        exit(1)

    bot.run(token)
