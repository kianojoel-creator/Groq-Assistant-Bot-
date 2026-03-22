# ════════════════════════════════════════════════
#  Bild-Übersetzer Cog  •  VHA Alliance
#  Optimiert: JSON-Output, Mecha Fire Prompt,
#  Retry via groq_call wrapper
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
import aiohttp
import base64
import json
import logging

log = logging.getLogger("VHABot.Bild")

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Cooldown für !übersetze pro User (Sekunden)
IMAGE_COOLDOWN = 15.0
user_last_image: dict[int, float] = {}

import time


async def image_to_base64(url: str) -> tuple:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.read()
            content_type = resp.content_type or "image/png"
            b64 = base64.b64encode(data).decode("utf-8")
            return b64, content_type


async def extract_and_translate(groq_call_fn, image_b64: str, content_type: str) -> dict:
    """
    Liest Text aus dem Bild (Mecha Fire optimiert) und übersetzt.
    Gibt JSON zurück: {original, lang, de, fr, pt}
    """
    result_str = await groq_call_fn(
        model=VISION_MODEL,
        temperature=0.1,
        max_tokens=900,
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
                            "This image is from the mobile game Mecha Fire. "
                            "Focus especially on: event names, start/end times, rewards, levels, requirements, dates.\n"
                            "Extract ALL visible text exactly as written.\n\n"
                            "Reply with VALID JSON ONLY (no markdown, no extra text):\n"
                            '{"original": "exact text from image", "lang": "ISO code (DE/FR/PT/EN/JA/etc.)", '
                            '"de": "German translation", "fr": "French translation", "pt": "Brazilian Portuguese translation"}\n\n'
                            'If no text visible: {"original": "NOTEXT"}'
                        )
                    }
                ]
            }
        ]
    )

    # JSON parsen
    try:
        # Markdown-Backticks entfernen falls vorhanden
        clean = result_str.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
        if parsed.get("original", "").upper() == "NOTEXT":
            return None
        return parsed
    except Exception:
        log.warning(f"JSON-Parse fehlgeschlagen, versuche Fallback: {result_str[:200]}")
        # Fallback: alter Text-Parser
        parsed = {"original": "", "lang": "", "de": "", "fr": "", "pt": ""}
        for line in result_str.split("\n"):
            if line.startswith("ORIGINAL:"):
                parsed["original"] = line.replace("ORIGINAL:", "").strip()
            elif line.startswith("LANG:"):
                parsed["lang"] = line.replace("LANG:", "").strip()
            elif line.startswith("DE:"):
                parsed["de"] = line.replace("DE:", "").strip()
            elif line.startswith("FR:"):
                parsed["fr"] = line.replace("FR:", "").strip()
            elif line.startswith("PT:"):
                parsed["pt"] = line.replace("PT:", "").strip()
        return parsed if parsed.get("original") else None


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
        """Liest Text aus einem Bild und übersetzt ihn auf DE, FR und PT."""

        # Cooldown
        now = time.time()
        last = user_last_image.get(ctx.author.id, 0)
        if now - last < IMAGE_COOLDOWN:
            remaining = int(IMAGE_COOLDOWN - (now - last))
            await ctx.send(f"⏳ Bitte warte noch **{remaining}s**. / Attends encore **{remaining}s**.")
            return
        user_last_image[ctx.author.id] = now

        # Bild suchen
        image_url = None

        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image"):
                    image_url = att.url
                    break

        if not image_url and ctx.message.reference:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message) and ref.attachments:
                for att in ref.attachments:
                    if att.content_type and att.content_type.startswith("image"):
                        image_url = att.url
                        break

        if not image_url:
            embed = discord.Embed(
                title="❓ Kein Bild gefunden / Aucune image / Nenhuma imagem",
                description=(
                    "Antworte auf ein Bild und tippe `!übersetze`\n"
                    "Réponds à une image et tape `!traduire`\n"
                    "Responda a uma imagem e digite `!traduzir`"
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed)
            return

        thinking = await ctx.send("🔍 **Lese Bild...** / **Lecture...** / **Lendo...**")

        try:
            image_b64, content_type = await image_to_base64(image_url)

            if not image_b64:
                await thinking.edit(content="❌ Bild konnte nicht geladen werden.")
                return

            result = await extract_and_translate(self.groq_call, image_b64, content_type)

            if not result:
                embed = discord.Embed(
                    title="🖼️ Kein Text gefunden / Aucun texte / Nenhum texto",
                    color=0xF39C12
                )
                await thinking.edit(content=None, embed=embed)
                return

            lang = result.get("lang", "?")
            embed = discord.Embed(
                title="🖼️ Bildübersetzung / Traduction d'image / Tradução de imagem",
                color=0x9B59B6
            )

            if result.get("original"):
                embed.add_field(
                    name=f"📝 Original ({lang})",
                    value=result["original"][:1000],
                    inline=False
                )

            if result.get("de") and lang != "DE":
                embed.add_field(name="🇩🇪 Deutsch", value=result["de"][:1000], inline=False)
            elif lang == "DE":
                embed.add_field(name="🇩🇪 Deutsch (Original)", value=result["original"][:1000], inline=False)

            if result.get("fr") and lang != "FR":
                embed.add_field(name="🇫🇷 Français", value=result["fr"][:1000], inline=False)
            elif lang == "FR":
                embed.add_field(name="🇫🇷 Français (Original)", value=result["original"][:1000], inline=False)

            if result.get("pt") and lang != "PT":
                embed.add_field(name="🇧🇷 Português", value=result["pt"][:1000], inline=False)
            elif lang == "PT":
                embed.add_field(name="🇧🇷 Português (Original)", value=result["original"][:1000], inline=False)

            embed.set_footer(text="VHA Bild-Übersetzer • Mecha Fire optimiert")
            await thinking.edit(content=None, embed=embed)

        except Exception as e:
            log.error(f"Bildübersetzungs-Fehler: {type(e).__name__} - {str(e)}")
            embed = discord.Embed(
                title="⚠️ Übersetzung fehlgeschlagen",
                description=(
                    "Bild konnte nicht verarbeitet werden – versuch es nochmal!\n"
                    "Impossible de traiter l'image – réessaie!\n"
                    "Não foi possível processar a imagem – tente novamente!"
                ),
                color=0xED4245
            )
            await thinking.edit(content=None, embed=embed)


async def setup(bot, groq_client, groq_call_fn):
    await bot.add_cog(BildUebersetzerCog(bot, groq_client, groq_call_fn))
