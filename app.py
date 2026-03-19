import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq
import re

# ==========================================================
# DEIN LOGO-LINK (Discord-CDN)
LOGO_URL = "https://cdn.discordapp.com/attachments/1484252260614537247/1484253018533662740/Picsart_26-03-18_13-55-24-994.png?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&" 
# ==========================================================

app = Flask(__name__)
@app.route('/')
def home(): return "VHA Translator - Final Version 2026"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

translate_active = True
processed_messages = set()

def detect_language_manually(text):
    t = text.lower()
    if any(re.search(rf'\b{w}\b', t) for w in ["c'est", "oui", "je", "suis", "pas", "le", "la", "et", "que", "pour", "est", "dans"]):
        return "FR"
    if any(re.search(rf'\b{w}\b', t) for w in ["ist", "ja", "ich", "bin", "nicht", "das", "die", "und", "dass", "für", "mit", "auch"]):
        return "DE"
    if any(re.search(rf'\b{w}\b', t) for w in ["is", "the", "and", "have", "you", "this", "with", "what", "good"]):
        return "EN"
    return "UNKNOWN"

@bot.event
async def on_ready():
    print(f'--- {bot.user.name} ONLINE (VHA BRANDING ACTIVE) ---')

# --- DREISPRACHIGES HILFE MENÜ ---
@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(
        title="VHA Translator - Help / Aide / Hilfe", 
        color=discord.Color.blue(),
        description="Official Alliance Translation Bot"
    )
    # Allianz Branding
    embed.set_author(name="VHA ALLIANCE", icon_url=LOGO_URL)
    embed.set_thumbnail(url=LOGO_URL)
    
    embed.add_field(name="🇩🇪 Deutsch", value="`!translate on/off`: Automatik an/aus\n`!ai [Frage]`: KI direkt fragen", inline=False)
    embed.add_field(name="🇫🇷 Français", value="`!translate on/off`: Activer/Désactiver\n`!ai [Question]`: Demander à l'IA", inline=False)
    embed.add_field(name="🇬🇧 English", value="`!translate on/off`: Toggle translation\n`!ai [Question]`: Ask the AI", inline=False)
    
    embed.set_footer(text="VHA - Powering Communication", icon_url=LOGO_URL)
    await ctx.send(embed=embed)

@bot.command(name="translate")
async def toggle_translate(ctx, status: str):
    global translate_active
    translate_active = (status.lower() == "on")
    status_msg = "Translation Active / Traduction activée / Aktiviert" if translate_active else "Translation Disabled / Traduction désactivée / Deaktiviert"
    await ctx.send(f"{'✅' if translate_active else '😴'} **{status_msg}**")

@bot.event
async def on_message(message):
    global processed_messages, translate_active
    if message.author == bot.user or message.id in processed_messages:
        return
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    
    text = message.content.strip()
    if not translate_active or len(text) <= 2:
        return
    
    # Auto-Ignore
    if text.lower() in ["haha", "lol", "ok", "merci", "danke", "thanks", "ja", "oui", "yes"]:
        return

    processed_messages.add(message.id)
    if len(processed_messages) > 150: processed_messages.clear()

    # Reply Check
    is_reply = False
    replied_text = ""
    if message.reference and message.reference.message_id:
        try:
            replied_to = await message.channel.fetch_message(message.reference.message_id)
            replied_text = replied_to.content
            is_reply = True
        except: pass

    input_lang = detect_language_manually(text)
    
    if is_reply:
        sys_msg = (f"Übersetze in DE (🇩🇪), FR (🇫🇷) und die Sprache von '{replied_text}'. "
                   "Regel: NUR Übersetzungen. KEINE Erklärungen.")
    elif input_lang == "FR":
        sys_msg = "Übersetze NUR ins Deutsche (🇩🇪) und Englische (🇬🇧)."
    elif input_lang == "DE":
        sys_msg = "Übersetze NUR ins Französische (🇫🇷) und Englische (🇬🇧)."
    elif input_lang == "EN":
        sys_msg = "Übersetze NUR ins Deutsche (🇩🇪) und Französische (🇫🇷)."
    else:
        sys_msg = "Übersetze in DE (🇩🇪), FR (🇫🇷) und EN (🇬🇧). NUR Ergebnisse."

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "system", "content": "Du bist ein stummer Übersetzer. Gib nur Zieltexte aus."},
                      {"role": "user", "content": f"{sys_msg}\n\nText: {text}"}],
            model=MODEL_NAME, temperature=0.0
        )
        result = completion.choices[0].message.content.strip()
        
        # Filter
        lines = [line for line in result.split('\n') if not any(x in line.lower() for x in ["sprache ist", "identisch", "bleibt gleich", "original"])]
        final_lines = [line for line in lines if line.replace("🇩🇪", "").replace("🇫🇷", "").replace("🇬🇧", "").strip().lower() != text.lower() and len(line) > 0]
        
        output = "\n".join(final_lines).strip()
        if output:
            await message.reply(output)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
