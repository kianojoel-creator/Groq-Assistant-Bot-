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
                            "It may show: in-game chat, events, profiles, menus, alliance info.\n"
                            "Extract ALL visible text including chat bubbles on dark backgrounds.\n"
                            "IMPORTANT: Do NOT duplicate lines. Each unique sentence appears only ONCE.\n"
                            "Combine all text into a clean, deduplicated version.\n\n"
                            "Reply with VALID JSON ONLY (no markdown):\n"
                            '{"original": "clean deduplicated text", "lang": "ISO code", '
                            '"de": "German translation (no duplicates)", "fr": "French translation (no duplicates)", "pt": "Brazilian Portuguese translation (no duplicates)", "en": "English translation (no duplicates)"}\n\n'
                            'If truly no text: {"original": "NOTEXT"}'
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
        parsed = {"original": "", "lang": "", "de": "", "fr": "", "pt": "", "en": ""}
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
            elif line.startswith("EN:"):
                parsed["en"] = line.replace("EN:", "").strip()
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
        """Liest Text aus einem oder mehreren Bildern und übersetzt ihn."""

        # Cooldown
        now = time.time()
        last = user_last_image.get(ctx.author.id, 0)
        if now - last < IMAGE_COOLDOWN:
            remaining = int(IMAGE_COOLDOWN - (now - last))
            await ctx.send(f"⏳ Bitte warte noch **{remaining}s**. / Attends encore **{remaining}s**.")
            return
        user_last_image[ctx.author.id] = now

        # Alle Bilder sammeln (eigene Nachricht + Reply)
        image_urls = []

        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image"):
                    image_urls.append(att.url)

        if ctx.message.reference:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message) and ref.attachments:
                for att in ref.attachments:
                    if att.content_type and att.content_type.startswith("image"):
                        image_urls.append(att.url)

        if not image_urls:
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

        total = len(image_urls)
        thinking = await ctx.send(f"🔍 **Lese {total} Bild(er)...** / **Lecture {total} image(s)...** / **Lendo {total} imagem(ns)...**")

        import asyncio as _asyncio

        async def process_single(url: str, index: int) -> discord.Embed:
            try:
                image_b64, content_type = await image_to_base64(url)
                if not image_b64:
                    return None

                result = await extract_and_translate(self.groq_call, image_b64, content_type)
                if not result:
                    return None

                lang = result.get("lang", "?")
                title = f"🖼️ Bild {index}/{total}" if total > 1 else "🖼️ Bildübersetzung / Traduction / Tradução"
                embed = discord.Embed(title=title, color=0x9B59B6)

                # Aktive Sprachen laden
                try:
                    from sprachen import get_active_langs
                    active_langs = get_active_langs()
                except Exception:
                    active_langs = {"DE", "FR", "PT"}

                # Übersetzungen anzeigen - kein Original, nur aktive Sprachen
                # Doppelte Zeilen im Text bereinigen
                def clean_text(text: str) -> str:
                    if not text:
                        return text
                    lines = text.split("\n")
                    seen = []
                    for line in lines:
                        line_stripped = line.strip()
                        if line_stripped and line_stripped not in seen:
                            seen.append(line_stripped)
                    return "\n".join(seen)

                if "DE" in active_langs and result.get("de") and lang != "DE":
                    cleaned = clean_text(result["de"])
                    if cleaned:
                        embed.add_field(name="🇩🇪 Deutsch", value=cleaned[:1000], inline=False)

                if "FR" in active_langs and result.get("fr") and lang != "FR":
                    cleaned = clean_text(result["fr"])
                    if cleaned:
                        embed.add_field(name="🇫🇷 Français", value=cleaned[:1000], inline=False)

                if "PT" in active_langs and result.get("pt") and lang != "PT":
                    cleaned = clean_text(result["pt"])
                    if cleaned:
                        embed.add_field(name="🇧🇷 Português", value=cleaned[:1000], inline=False)

                if result.get("en") and lang != "EN":
                    cleaned = clean_text(result["en"])
                    if cleaned:
                        embed.add_field(name="🇬🇧 English", value=cleaned[:1000], inline=False)

                if not embed.fields:
                    return None

                embed.set_footer(text="VHA Bild-Übersetzer • Mecha Fire")
                return embed
            except Exception as e:
                log.error(f"Bildübersetzungs-Fehler Bild {index}: {e}")
                return None

        try:
            # Alle Bilder parallel verarbeiten
            tasks = [process_single(url, i+1) for i, url in enumerate(image_urls)]
            results = await _asyncio.gather(*tasks)

            embeds = [r for r in results if r is not None]

            if not embeds:
                embed = discord.Embed(
                    title="🖼️ Kein Text gefunden / Aucun texte / Nenhum texto",
                    color=0xF39C12
                )
                await thinking.edit(content=None, embed=embed)
                return

            # Erstes Embed als Edit, Rest als neue Nachrichten
            await thinking.edit(content=None, embed=embeds[0])
            for embed in embeds[1:]:
                await ctx.send(embed=embed)

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
