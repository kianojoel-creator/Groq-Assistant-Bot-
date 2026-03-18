import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading
import asyncio

# 1. Webserver für Render (damit der Dienst online bleibt)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Herzschlag: Aktiv!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-pro')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'--- ERFOLG ---')
    print(f'Eingeloggt als: {bot.user.name}')
    print(f'ID: {bot.user.id}')
    print(f'--------------')

@bot.event
async def on_message(message):
    # Ignoriere eigene Nachrichten
    if message.author == bot.user:
        return

    # TEST-BEFEHL
    if message.content.lower().startswith("!test"):
        await message.reply("Ich höre dich! Der Bot kann antworten.")
        return

    # GEMINI-BEFEHL
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if not query:
            await message.reply("Bitte gib eine Frage ein.")
            return

        async with message.channel.typing():
            try:
                print(f"Anfrage an Gemini: {query}")
                response = model.generate_content(query)
                if response and response.text:
                    await message.reply(response.text)
                else:
                    await message.reply("KI gab keine Antwort zurück.")
            except Exception as e:
                print(f"KI FEHLER: {e}")
                await message.reply(f"Fehler in der KI-Verarbeitung: {e}")
        return

    # AUTOMATISCHE ÜBERSETZUNG (DE <-> FR)
    if len(message.content) > 3:
        try:
            # Wir prüfen kurz, ob es eine normale Nachricht ist (kein Bot-Befehl)
            if not message.content.startswith("!"):
                async with message.channel.typing():
                    prompt = f"Übersetze DE<->FR, sonst antworte NUR mit 'SKIP': {message.content}"
                    response = model.generate_content(prompt)
                    if response.text and "SKIP" not in response.text.upper():
                        await message.reply(f"🌍 {response.text}")
        except Exception as e:
            print(f"ÜBERSETZUNGS FEHLER: {e}")

# 4. Start-Sequenz
if __name__ == "__main__":
    # Flask in eigenem Thread starten
    threading.Thread(target=run_flask, daemon=True).start()
    
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("FEHLER: Kein DISCORD_TOKEN in den Umgebungsvariablen gefunden!")
    else:
        try:
            bot.run(token)
        except Exception as e:
            print(f"START FEHLER: {e}")
