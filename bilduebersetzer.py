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
                            "It may show: in-game chat, events, profiles, menus, alliance info.\\n"
                            "IMPORTANT FORMATTING:\\n"
                            "- Each chat message on its OWN line, separated by a blank line (\\n\\n)\\n"
                            "- Format: [SenderName]: message text\\n"
                            "- NEVER merge multiple messages into one block\\n"
                            "- No duplicate lines\\n\\n"
                            "Reply VALID JSON ONLY (no markdown, no backticks):\\n"
                            "{\"original\": \"[Name1]: msg1\\n\\n[Name2]: msg2\", \"lang\": \"ISO\", "
                            "\"de\": \"[Name1]: german1\\n\\n[Name2]: german2\", "
                            "\"fr\": \"[Name1]: french1\\n\\n[Name2]: french2\", "
                            "\"pt\": \"[Name1]: port1\\n\\n[Name2]: port2\", "
                            "\"en\": \"[Name1]: english1\\n\\n[Name2]: english2\"}\\n\\n"
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

        # Sprachen einmal laden (gilt für alle Bilder)
        try:
            from sprachen import get_active_langs
            active_langs = get_active_langs()
        except Exception:
            active_langs = {"DE", "FR", "PT"}
        # EN immer anzeigen beim Bildübersetzer
        active_langs = active_langs | {"EN"}

        # Sprach-Mapping: Code → (Flagge, Name)
        LANG_DISPLAY = {
            "DE": ("🇩🇪", "Deutsch"),
            "FR": ("🇫🇷", "Français"),
            "PT": ("🇧🇷", "Português"),
            "EN": ("🇬🇧", "English"),
        }
        ORIG_FLAGS = {
            "DE": "🇩🇪", "FR": "🇫🇷", "PT": "🇧🇷", "EN": "🇬🇧",
            "JA": "🇯🇵", "ZH": "🇨🇳", "KO": "🇰🇷", "ES": "🇪🇸",
            "IT": "🇮🇹", "RU": "🇷🇺", "AR": "🇸🇦", "TR": "🇹🇷",
        }

        def clean_text(text: str) -> str:
            """Entfernt Duplikate aber behält Leerzeilen zwischen Nachrichten."""
            if not text:
                return ""
            # Nachrichten-Blöcke splitten (doppelter Zeilenumbruch = Trenner)
            blocks = text.split("\n\n")
            seen = []
            result = []
            for block in blocks:
                block = block.strip()
                if block and block not in seen:
                    seen.append(block)
                    result.append(block)
            return "\n\n".join(result)

        async def process_single(url: str, index: int) -> discord.Embed:
            try:
                image_b64, content_type = await image_to_base64(url)
                if not image_b64:
                    return None

                result = await extract_and_translate(self.groq_call, image_b64, content_type)
                if not result:
                    return None

                lang = (result.get("lang") or "?").upper()
                orig_flag = ORIG_FLAGS.get(lang, "🌐")

                # Titel
                if total > 1:
                    title = f"🖼️ Bild {index} / {total}"
                else:
                    title = "🖼️ Bild-Übersetzer • Mecha Fire"

                embed = discord.Embed(title=title, color=0x9B59B6)
                embed.set_author(name="VHA Bild-Übersetzer", icon_url=LOGO_URL)

                # Original-Text oben — kompakt, max 800 Zeichen
                orig = clean_text(result.get("original", ""))
                if orig:
                    orig_display = orig[:800] + ("…" if len(orig) > 800 else "")
                    embed.add_field(
                        name=f"{orig_flag} Originaltext ({lang})",
                        value=f"```{orig_display}```",
                        inline=False
                    )

                # Trennlinie als leeres Feld
                embed.add_field(name="​", value="─────────────────", inline=False)

                # Übersetzungen — nur aktive Sprachen, nicht wenn gleich wie Original
                has_translation = False
                for code, (flag, name) in LANG_DISPLAY.items():
                    if code not in active_langs:
                        continue
                    if code == lang:
                        continue
                    text = clean_text(result.get(code.lower(), ""))
                    if not text:
                        continue
                    display = text[:1000] + ("…" if len(text) > 1000 else "")
                    embed.add_field(name=f"{flag} {name}", value=display, inline=False)
                    has_translation = True

                if not has_translation:
                    return None

                embed.set_footer(
                    text=f"VHA Bild-Übersetzer • Erkannte Sprache: {lang}",
                    icon_url=LOGO_URL
                )
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
