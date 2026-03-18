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

# Wir probieren hier die direkteste Form ohne Präfixe
model = genai.GenerativeModel('gemini-1.5-flash')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("----------------------------")
    print(f"BOT ONLINE: {bot.user.name}")
    print("----------------------------")
    sys.stdout.flush()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Debug-Log
    print(f"Nachricht von {message.author}: {message.content}")
    sys.stdout.flush()

    if message.content.lower().startswith("!test"):
        await message.reply("Ich höre dich! Test erfolgreich.")
        return

    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if not query:
            await message.reply("Frag mich etwas!")
            return

        async with message.channel.typing():
            try:
                # Einfacher Aufruf ohne extra Argumente
                response = model.generate_content(query)
                
                if response and response.text:
                    await message.reply(response.text)
                else:
                    await message.reply("KI hat keine Antwort geliefert.")
            except Exception as e:
                print(f"KI FEHLER: {e}")
                sys.stdout.flush()
                # Wir geben den Fehler aus, um zu sehen was passiert
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
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("FEHLER: DISCORD_TOKEN fehlt!")
