import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Herzschlag: Aktiv!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup
# Wir konfigurieren Gemini ganz ohne Beta-Zusatz
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'--- BOT ONLINE ---')
    print(f'Eingeloggt als: {bot.user.name}')
    print(f'------------------')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # TEST-BEFEHL (Ob Discord reagiert)
    if message.content.lower().startswith("!test"):
        await message.reply("Discord-Verbindung steht!")
        return

    # GEMINI-BEFEHL
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if not query:
            await message.reply("Was möchtest du wissen?")
            return

        async with message.channel.typing():
            try:
                # Wir versuchen es mit der stabilen 1.5-flash Version
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(query)
                
                if response.text:
                    await message.reply(response.text)
                else:
                    await message.reply("KI hat keine Antwort generiert.")
            except Exception as e:
                # Wenn es immer noch hakt, versuchen wir es mit dem Modell-Präfix
                try:
                    model = genai.GenerativeModel('models/gemini-1.5-flash')
                    response = model.generate_content(query)
                    await message.reply(response.text)
                except Exception as e2:
                    print(f"KI FEHLER: {e2}")
                    await message.reply(f"Fehler: Bitte prüfe, ob dein Google-API-Key noch gültig ist. (Details: {e2})")
        return

    # AUTOMATISCHE ÜBERSETZUNG (DE <-> FR)
    if len(message.content) > 3 and not message.content.startswith("!"):
        try:
            # Kurze Verzögerung für das "Tippen"-Gefühl
            async with message.channel.typing():
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Übersetze DE<->FR, sonst antworte NUR mit 'SKIP': {message.content}"
                response = model.generate_content(prompt)
                if response.text and "SKIP" not in response.text.upper():
                    await message.reply(f"🌍 {response.text}")
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("FEHLER: DISCORD_TOKEN fehlt!")
