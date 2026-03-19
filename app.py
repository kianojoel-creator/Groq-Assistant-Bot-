import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading
import sys

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Herzschlag: Aktiv!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Variable für den Status (Standardmäßig an)
auto_translate = True

@bot.event
async def on_ready():
    print(f'--- BOT IST LIVE ---')
    print(f'Eingeloggt als: {bot.user.name}')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # BEFEHL: AUTO-ÜBERSETZUNG AN
    if message.content.lower() == "!auto on":
        auto_translate = True
        await message.reply("✅ **Übersetzung aktiviert!** Ich bin da und helfe euch beim Chatten.")
        return

    # BEFEHL: AUTO-ÜBERSETZUNG AUS
    if message.content.lower() == "!auto off":
        auto_translate = False
        await message.reply("😴 **Übersetzung deaktiviert.** Ich bin jetzt im Standby. Sag `!auto on`, wenn du mich wieder brauchst!")
        return

    # Direkte KI-Anfrage mit !gemini (funktioniert immer)
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        async with message.channel.typing():
            try:
                response = model.generate_content(query)
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"Fehler: {e}")
        return

    # INTELLIGENTE AUTO-ÜBERSETZUNG (nur wenn auto_translate auf True ist)
    if auto_translate and len(message.content) > 2 and not message.content.startswith("!"):
        try:
            prompt = (
                f"Handle als Übersetzer. Wenn der Text DEUTSCH ist, übersetze ihn ins FRANZÖSISCHE. "
                f"Wenn der Text FRANZÖSISCH ist, übersetze ihn ins DEUTSCHE. "
                f"Wenn es eine andere Sprache ist oder kein Sinn ergibt, antworte NUR mit 'SKIP'. "
                f"Hier ist der Text: {message.content}"
            )
            
            async with message.channel.typing():
                response = model.generate_content(prompt)
                if response.text and "SKIP" not in response.text.upper():
                    await message.reply(f"🔄 {response.text}")
        except Exception:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
