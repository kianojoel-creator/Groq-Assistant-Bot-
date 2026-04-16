# ════════════════════════════════════════════════
#  Bild-Übersetzer Cog • VHA Alliance
#  Immer alle 4 Sprachen hartcodiert (DE, FR, EN, PT)
#  Optimiert für Mecha Fire + Discord Screenshots
#  Saubere Version – April 2026
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import aiohttp
import base64
import json
import logging
import time
import asyncio

log = logging.getLogger("VHABot.Bild")

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

IMAGE_COOLDOWN = 15.0
user_last_image: dict[int, float] = {}


async def image_to_base64(url: str) -> tuple[str | None, str | None]:
    """Lädt Bild und konvertiert zu Base64."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.read()
            content_type = resp.content_type or "image/png"
            b64 = base64.b64encode(data).decode("utf-8")
            return b64, content_type


async def extract_and_translate(groq_call_fn, image_b64: str, content_type: str) -> dict | None:
    """Extrahiert Text + übersetzt in alle 4 Sprachen."""
    prompt = (
        "Analyze the screenshot. It can be Mecha Fire chat (messages often appear twice: original + auto-translation) "
        "or a Discord chat.\n\n"
        "CRITICAL:\n"
        "1. Keep ONLY the original language version if text appears twice.\n"
        "2. Never repeat sentences.\n"
        "3. If no readable text → return {\"original\": \"NOTEXT\"}\n\n"
        "Reply with VALID JSON ONLY:\n"
        "{\n"
        '  "original": "clean extracted text, one sentence per line",\n'
        '  "lang": "ISO code of original (DE/FR/EN/PT/...)",\n'
        '  "de": "German translation",\n'
        '  "fr": "French translation",\n'
        '  "en": "English translation",\n'
        '  "pt": "Brazilian Portuguese translation"\n'
        "}\n"
        "Fill ALL four translation fields naturally."
    )

    result_str = await groq_call_fn(
        model=VISION_MODEL,
        temperature=0.0,
        max_tokens=1200,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_b64}"}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    try:
        clean = result_str.strip()
        if clean.startswith("```"):
            clean = clean.split("```", 1)[1]
            if clean.startswith("json"):
                clean = clean[4:].strip()
        clean = clean.strip()

        parsed = json.loads(clean)
        if parsed.get("original", "").upper().strip() == "NOTEXT":
            return None
        return parsed

    except Exception as e:
        log.warning(f"JSON-Parse fehlgeschlagen: {e}")
        return None


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\\n", "\n").replace("\r\n", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    seen = []
    for line in lines:
        if line not in seen:
            seen.append(line)
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
        """Übersetzt Text aus Bildern – immer alle 4 Sprachen."""
        now = time.time()
        last = user_last_image.get(ctx.author.id, 0)
        if now - last < IMAGE_COOLDOWN:
            remaining = int(IMAGE_COOLDOWN - (now - last))
            await ctx.send(f"⏳ Bitte warte noch **{remaining}s**.", delete_after=remaining)
            return
        user_last_image[ctx.author.id] = now

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
                for embed in ref.embeds:
                    if embed.image and embed.image.url:
                        image_urls.append(embed.image.url)

        if not image_urls:
            embed = discord.Embed(title="❓ Kein Bild gefunden", description="Bild hochladen und `!übersetze` schreiben\noder auf eine Nachricht mit Bild antworten.", color=0xF39C12)
            await ctx.send(embed=embed)
            return

        total = len(image_urls)
        thinking = await ctx.send(f"🔍 Analysiere {total} Bild{'er' if total > 1 else ''}...")

        async def process_single(url: str, index: int) -> discord.Embed | None:
            try:
                image_b64, content_type = await image_to_base64(url)
                if not image_b64:
                    return None

                result = await extract_and_translate(self.groq_call, image_b64, content_type)
                if not result:
                    return None

                original_lang = (result.get("lang") or "?").upper().strip()

                embed = discord.Embed(title="🖼️ Bildübersetzung / Traduction d'image", color=0x9B59B6)

                # Original
                orig = clean_text(result.get("original", ""))
                if orig:
                    embed.add_field(name=f"📜 Original ({original_lang})", value=orig[:1000], inline=False)

                # Immer alle 4 Sprachen hartcodiert
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
                        embed.add_field(name=label, value="*(keine Übersetzung verfügbar)*", inline=False)

                embed.set_footer(text="VHA Bild-Übersetzer • Mecha Fire", icon_url=LOGO_URL)
                return embed

            except Exception as e:
                log.error(f"Bild {index} Fehler: {e}")
                return None

        try:
            tasks = [process_single(url, i + 1) for i, url in enumerate(image_urls)]
            results = await asyncio.gather(*tasks)
            embeds = [r for r in results if r is not None]

            if not embeds:
                await thinking.edit(embed=discord.Embed(title="🖼️ Kein Text erkannt", description="Kein lesbarer Text im Bild gefunden.", color=0xF39C12))
                return

            await thinking.edit(content=None, embed=embeds[0])
            for e in embeds[1:]:
                await ctx.send(embed=e)

        except Exception as e:
            log.error(f"Bildübersetzer Fehler: {e}")
            await thinking.edit(embed=discord.Embed(title="⚠️ Fehler", description="Bild konnte nicht verarbeitet werden.", color=0xED4245))


async def setup(bot, groq_client, groq_call_fn):
    await bot.add_cog(BildUebersetzerCog(bot, groq_client, groq_call_fn))
