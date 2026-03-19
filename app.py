import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import sys
from groq import Groq

# 1. Webserver für Render (Uptime)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "VHA Assistant Online"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. Groq KI Setup
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

auto_translate = True

@bot.event
async def on_ready():
    # Setzt den Status in Discord (International)
    activity = discord.Game(name="VHA Guard | !info", type=3)
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f'--- {bot.user.name} (VHA) IS ONLINE ---')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # HILFE / INFO (DREISPRACHIG)
    if message.content.lower() in ["!info", "!help"]:
        help_text = (
            "**🚀 VHA Assistant**\n\n"
            "🇩🇪 **DE:** Ich unterstütze diesen Server mit KI-Power.\n"
            "🇫🇷 **FR:** J'assiste ce serveur avec la puissance de l'IA.\n"
            "🇺🇸 **EN:** I assist this server with AI power.\n\n"
            "**Commands / Commandes:**\n"
            "`!ai [Text]` - AI Chat (Llama-3.3)\n"
            "`!auto on/off` - Auto Translate DE ↔ FR\n"
            "`!status` - System Status"
        )
        await message.reply(help_text)
        return

    # STATUS (DREISPRACHIG)
    if message.content.lower() == "!status":
        state_de = "AKTIV ✅" if auto_translate else "PAUSIERT 😴"
        state_fr = "ACTIF ✅" if auto_translate else "EN PAUSE 😴"
        state_en = "ACTIVE ✅" if auto_translate else "PAUSED 😴"
        
        status_msg = (
            f"🇩🇪 System: {state_de}\n"
            f"🇫🇷 Système: {state_fr}\n"
            f"🇺🇸 System: {state_en}"
        )
        await message.reply(status_msg)
        return

    # ÜBERSETZUNG AN/AUS (DREISPRACHIG ANGEPASST)
    if message.content.lower() == "!auto on":
        auto_translate = True
        msg = (
            "✅ **Übersetzung aktiviert!**\n"
            "🇫🇷 Traduction activée !\n"
            "🇺🇸 Translation activated!"
        )
        await message.reply(msg)
        return
        
    if message.content.lower() == "!auto off":
        auto_translate = False
        msg = (
            "😴 **Übersetzung pausiert.**\n"
            "🇫🇷 Traduction en pause.\n"
            "🇺🇸 Translation paused."
        )
        await message.reply(msg)
        return

    # ALLGEMEINE KI ANFRAGE
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                # KI antwortet in der Sprache des Users
                chat_completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": "You are the VHA Assistant. Answer precisely in the language the user is speaking (German, French, or English)."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME,
                    temperature=0.6
                )
                await message.reply(chat_completion.choices[0].message.content)
            except Exception as e:
                print(f"Error: {e}")
                await message.reply("❌ System-Error.")
        return

    # 4. AUTOMATISCHE ÜBERSETZUNG (DE <-> FR)
    if auto_translate and len(message.content) > 3 and not message.content.startswith("!"):
        try:
            t_prompt = (
                f"Translate briefly: French -> German (start with 🇩🇪) or German -> French (start with 🇫🇷). "
                f"Answer ONLY with the translation. Answer 'SKIP' if no translation is needed. "
                f"Text: {message.content}"
            )
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": t_prompt}],
                model=MODEL_NAME,
                temperature=0.1
            )
            result = completion.choices[0].message.content
            if result and "SKIP" not in result.upper():
                await message.reply(result)
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
