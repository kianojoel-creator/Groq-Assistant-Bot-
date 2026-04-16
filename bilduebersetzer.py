# ════════════════════════════════════════════════
#  Bild-Übersetzer Cog  •  VHA Alliance
#  Komplett überarbeitet — besserer Prompt
#  Behandelt zweisprachige Screenshots (Spiel-Übersetzer)
#  Discord-Screenshots, Mecha Fire Chats, etc.
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import aiohttp
import base64
import json
import logging
import time

log = logging.getLogger("VHABot.Bild")

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

IMAGE_COOLDOWN = 15.0
user_last_image: dict[int, float] = {}


async def image_to_base64(url: str) -> tuple:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.read()
            content_type = resp.content_type or "image/png"
            b64 = base64.b64encode(data).decode("utf-8")
            return b64, content_type


async def extract_and_translate(groq_call_fn, image_b64: str, content_type: str) -> dict | None:
    """
    Liest Text aus dem Bild und übersetzt ihn.
    Speziell optimiert für:
    - Mecha Fire in-game Chat (mit eingebautem Übersetzer → 2 Sprachen pro Nachricht)
    - Discord Screenshots
    - Alliance Info / Events / Profile
    """

    result_str = await groq_call_fn(
        model=VISION_MODEL,
        temperature=0.1,
        max_tokens=1200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            "You are analyzing a screenshot. It may be from:\n"
                            "- A mobile game chat (Mecha Fire) where messages often appear TWICE "
                            "(original language + auto-translation below it — keep only ONE version per message)\n"
                            "- A Discord chat with multiple users and messages\n"
                            "- Game menus, profiles, alliance info, events\n\n"

                            "CRITICAL RULES:\n"
                            "1. If a message appears in TWO languages (original + game translation), "
                            "keep ONLY the ORIGINAL (first) version — ignore the auto-translated duplicate\n"
                            "2. For Discord screenshots: extract each message separately with the username if visible\n"
                            "3. Do NOT repeat the same sentence twice\n"
                            "4. Do NOT mix languages in a single translation field\n"
                            "5. If there is truly no readable text, return {\"original\": \"NOTEXT\"}\n\n"

                            "OUTPUT FORMAT — reply with VALID JSON ONLY, no markdown, no explanation:\n"
                            "{\n"
                            "  \"original\": \"clean extracted text, one sentence per line, no duplicates\",\n"
                            "  \"lang\": \"ISO 639-1 code of the original text (DE/FR/EN/ZH/KO/etc)\",\n"
                            "  \"de\": \"German translation\",\n"
                            "  \"fr\": \"French translation\",\n"
                            "  \"en\": \"English translation\",\n"
                            "  \"pt\": \"Brazilian Portuguese translation\"\n"
                            "}\n\n"
                            "Translate naturally and colloquially. Each field must be in ONE language only."
                        )
                    }
                ]
            }
        ]
    )

    try:
        clean = result_str.strip()
        # Markdown-Backticks entfernen
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        parsed = json.loads(clean)

        if parsed.get("original", "").upper().strip() == "NOTEXT":
            return None

        return parsed

    except Exception:
        log.warning(f"JSON-Parse fehlgeschlagen: {result_str[:300]}")

        # Fallback: versuche Felder manuell zu extrahieren
        parsed = {"original": "", "lang": "?", "de": "", "fr": "", "pt": "", "en": ""}
        for line in result_str.split("\n"):
            for key in ["original", "lang", "de", "fr", "pt", "en"]:
                prefix = f'"{key}":'
                if prefix in line.lower():
                    val = line.split(":", 1)[-1].strip().strip('",')
                    parsed[key] = val
        return parsed if parsed.get("original") else None


def clean_text(text: str) -> str:
    """Entfernt doppelte Zeilen und bereinigt den Text."""
    if not text:
        return ""
    lines = text.split("\n")
    seen = []
    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.append(stripped)
    return "\n".join(seen)


LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)


class BildUebersetzerCog(commands.Cog):
    def __init__(self, bot, groq_client, groq_call_fn):
        self.bot = bot
        self.groq_client = groq_client
        self.groq_call = groq_call_fn

    @commands.command(name="übersetze", aliases=["uebersetze", "traduire", "traduzir", "ocr", "lese", "lire"])
    async def uebersetze_bild(self, ctx):
        """Liest Text aus einem Bild und übersetzt ihn."""

        # Cooldown
        now = time.time()
        last = user_last_image.get(ctx.author.id, 0)
        if now - last < IMAGE_COOLDOWN:
            remaining = int(IMAGE_COOLDOWN - (now - last))
            await ctx.send(
                f"⏳ Bitte warte noch **{remaining}s**. / Attends encore **{remaining}s**.",
                delete_after=remaining
            )
            return
        user_last_image[ctx.author.id] = now

        # Bilder sammeln — eigene Nachricht + Reply
        image_urls = []

        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image"):
                    image_urls.append(att.url)

        if ctx.message.reference:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message):
                for att in ref.attachments:
                    if att.content_type and att.content_type.startswith("image"):
                        image_urls.append(att.url)
                # Auch Embeds mit Bild-URL prüfen (z.B. Discord-Screenshots als Link)
                for embed in ref.embeds:
                    if embed.image and embed.image.url:
                        image_urls.append(embed.image.url)

        if not image_urls:
            embed = discord.Embed(
                title="❓ Kein Bild gefunden / Aucune image",
                description=(
                    "**So verwenden / Comment utiliser:**\n"
                    "1️⃣ Bild hochladen und `!übersetze` dazu tippen\n"
                    "2️⃣ Auf eine Nachricht mit Bild antworten und `!übersetze` tippen\n\n"
                    "💡 Funktioniert mit: Spielscreenshots, Discord-Screenshots, Fotos"
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed)
            return

        total = len(image_urls)
        thinking = await ctx.send(
            f"🔍 **Analysiere {total} Bild{'er' if total > 1 else ''}...** "
            f"/ **Analyse en cours...**"
        )

        import asyncio as _asyncio

        async def process_single(url: str, index: int) -> discord.Embed | None:
            try:
                image_b64, content_type = await image_to_base64(url)
                if not image_b64:
                    return None

                result = await extract_and_translate(self.groq_call, image_b64, content_type)
                if not result:
                    return None

                lang = (result.get("lang") or "?").upper().strip()

                title = (
                    f"🖼️ Bild {index}/{total} • Bildübersetzung"
                    if total > 1
                    else "🖼️ Bildübersetzung / Traduction d'image"
                )
                embed = discord.Embed(title=title, color=0x9B59B6)

                # Original-Text immer zuerst anzeigen
                original_text = clean_text(result.get("original", ""))
                if original_text:
                    embed.add_field(
                        name=f"📜 Original ({lang})",
                        value=original_text[:1000],
                        inline=False
                    )

                # Immer alle 4 Sprachen hartcodiert – unabhängig von sprachen.py
                lang_map = [
                    ("DE", "🇩🇪 Deutsch",     result.get("de", "")),
                    ("FR", "🇫🇷 Français",    result.get("fr", "")),
                    ("EN", "🇬🇧 English",     result.get("en", "")),
                    ("PT", "🇧🇷 Português",   result.get("pt", "")),
                ]

                for code, label, text in lang_map:
                    cleaned = clean_text(text)
                    if cleaned:
                        embed.add_field(name=label, value=cleaned[:1000], inline=False)
                    else:
                        embed.add_field(
                            name=label,
                            value="*(keine Übersetzung verfügbar)*",
                            inline=False
                        )

                embed.set_footer(text="VHA Bild-Übersetzer • Mecha Fire", icon_url=LOGO_URL)
                return embed

            except Exception as e:
                log.error(f"Bildübersetzungs-Fehler Bild {index}: {e}")
                return None

        try:
            tasks = [process_single(url, i + 1) for i, url in enumerate(image_urls)]
            results = await _asyncio.gather(*tasks)
            embeds = [r for r in results if r is not None]

            if not embeds:
                embed = discord.Embed(
                    title="🖼️ Kein Text erkannt / Aucun texte détecté",
                    description=(
                        "Im Bild wurde kein lesbarer Text gefunden.\n"
                        "Aucun texte lisible n'a été trouvé dans l'image.\n\n"
                        "💡 Tipp: Bild muss scharf und gut lesbar sein."
                    ),
                    color=0xF39C12
                )
                await thinking.edit(content=None, embed=embed)
                return

            await thinking.edit(content=None, embed=embeds[0])
            for embed in embeds[1:]:
                await ctx.send(embed=embed)

        except Exception as e:
            log.error(f"Bildübersetzungs-Fehler: {type(e).__name__} - {str(e)}")
            embed = discord.Embed(
                title="⚠️ Fehler / Erreur",
                description=(
                    "Bild konnte nicht verarbeitet werden — bitte nochmal versuchen.\n"
                    "Impossible de traiter l'image — réessaie."
                ),
                color=0xED4245
            )
            await thinking.edit(content=None, embed=embed)


async def setup(bot, groq_client, groq_call_fn):
    await bot.add_cog(BildUebersetzerCog(bot, groq_client, groq_call_fn))
