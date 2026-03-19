import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading
import sys
import asyncio

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Online"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash-lite')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

auto_translate = True

@bot.event
async def on_ready():
    print(f'--- BOT STARTET ---')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # BEFEHLE
    if message.content.lower() in ["!info", "!help"]:
        await message.reply("Bot ist aktiv! !auto on/off | !gemini [Frage]")
        return

    if message.content.lower() == "!auto on":
        auto_translate = True
        await message.reply("Aktiviert!")
        return
        
    if message.content.lower() == "!auto off":
        auto_translate = False
        await message.reply("Deaktiviert.")
        return

    # KI-FRAGE
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        async with message.channel.typing():
            try:
                response = model.generate_content(query)
                await message.reply(response.text)
            except Exception as e:
                if "429" in str(e):
                    await message.reply("Pause: Limit erreicht.")
                else:
                    print(f"Fehler: {e}")
        return

    # ÜBERSETZUNG
    if auto_translate and len(message.content) > 3 and not message.content.startswith("!"):
        try:
            context_msg = ""
            if message.reference:
                try:
                    referenced_msg = await message.channel.fetch_message(message.reference.message_id)
                    context_msg = f" (Kontext: {referenced_msg.content})"
                except: pass

            prompt = (
                f"Übersetze kurz DE->FR oder FR->DE. "
                f"Antworte NUR mit 'SKIP', wenn keine Übersetzung nötig ist. "
                f"Kontext: {context_msg} Text: {message.content}"
            )
            
            response = model.generate_content(prompt)
            if response.text and "SKIP" not in response.text.upper():
                await message.reply(f"🌍 {response.text}")

        except Exception as e:
            if "429" not in str(e):
                print(f"Fehler: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
