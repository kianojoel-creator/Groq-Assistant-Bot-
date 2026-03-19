import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import sys
from groq import Groq

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Online (Groq Edition)"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. Groq KI Setup
# Stell sicher, dass GROQ_API_KEY in Render hinterlegt ist!
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

auto_translate = True

@bot.event
async def on_ready():
    print(f'--- GROQ BOT ONLINE ---')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # BEFEHLE
    if message.content.lower() in ["!info", "!help"]:
        await message.reply("**🚀 Groq-Bot Aktiv**\nModell: Llama-3.3\n`!auto on/off` | `!gemini [Frage]`")
        return

    if message.content.lower() == "!auto on":
        auto_translate = True
        await message.reply("✅ Übersetzung an!")
        return
        
    if message.content.lower() == "!auto off":
        auto_translate = False
        await message.reply("😴 Übersetzung aus.")
        return

    # KI-FRAGE (Befehl bleibt gleich, damit ihr euch nicht umstellen müsst)
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        async with message.channel.typing():
            try:
                chat_completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": query}],
                    model=MODEL_NAME,
                )
                await message.reply(chat_completion.choices[0].message.content)
            except Exception as e:
                print(f"Fehler: {e}")
                await message.reply("❌ Da hakt was bei Groq.")
        return

    # 4. ÜBERSETZUNG
    if auto_translate and len(message.content) > 3 and not message.content.startswith("!"):
        try:
            prompt = (
                f"Übersetze kurz DE->FR oder FR->DE. "
                f"Antworte NUR mit 'SKIP', wenn keine Übersetzung nötig ist. "
                f"Text: {message.content}"
            )
            
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_NAME,
            )
            
            result = completion.choices[0].message.content
            if result and "SKIP" not in result.upper():
                await message.reply(f"🌍 {result}")

        except Exception as e:
            print(f"Fehler: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
