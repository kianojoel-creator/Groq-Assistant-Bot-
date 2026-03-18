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
# Wir definieren das Modell direkt mit dem vollen Namen
model = genai.GenerativeModel('gemini-1.5-flash')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("----------------------------")
    print(f"BOT START: {bot.user.name}")
    print("LOGS SIND JETZT AKTIV")
    print("----------------------------")
    sys.stdout.flush() # Zwingt die Logs, sofort zu erscheinen

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # JEDE Nachricht loggen, damit wir sehen, ob der Bot sie hört
    print(f"Nachricht erhalten: {message.content}")
    sys.stdout.flush()

    if message.content.lower().startswith("!test"):
        await message.reply("Test erfolgreich! Ich kann senden.")
        return

    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if not query:
            await message.reply("Frag mich was!")
            return

        async with message.channel.typing():
            try:
                print(f"KI-Anfrage wird gesendet: {query}")
                sys.stdout.flush()
                response = model.generate_content(query)
                
                if response and response.text:
                    await message.reply(response.text)
                else:
                    await message.reply("KI hat keinen Text gesendet.")
            except Exception as e:
                print(f"KRITISCHER KI FEHLER: {e}")
                sys.stdout.flush()
                await message.reply(f"Fehler: {e}")
        return

    # Automatik-Übersetzung
    if len(message.content) > 3 and not message.content.startswith("!"):
        try:
            async with message.channel.typing():
                prompt = f"Übersetze DE<->FR, sonst antworte NUR mit 'SKIP': {message.content}"
                response = model.generate_content(prompt)
                if response.text and "SKIP" not in response.text.upper():
                    await message.reply(f"🌍 {response.text}")
        except Exception as e:
            print(f"Übersetzungsfehler im Log: {e}")
            sys.stdout.flush()

if __name__ == "__main__":
    # Flask Start
    threading.Thread(target=run_flask, daemon=True).start()
    
    token = os.getenv("DISCORD_TOKEN")
    if token:
        print("Versuche Discord-Login...")
        sys.stdout.flush()
        bot.run(token)
    else:
        print("FEHLER: Kein DISCORD_TOKEN gefunden!")
        sys.stdout.flush()
