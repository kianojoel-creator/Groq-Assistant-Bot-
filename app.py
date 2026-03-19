import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): return "VHA Universal Translator - Fixed Logic"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# 2. KI Setup
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Speicher gegen Doppel-Antworten
processed_messages = set()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="Übersetzer aktiv 🌍"))
    print(f'--- {bot.user.name} LOGIK-FIX BEREIT ---')

@bot.event
async def on_message(message):
    global processed_messages
    
    if message.author == bot.user or message.id in processed_messages:
        return
    
    processed_messages.add(message.id)
    if len(processed_messages) > 100: processed_messages.clear()

    # KI-BEFEHL (!ai)
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                chat_res = client.chat.completions.create(
                    messages=[{"role": "system", "content": "Antworte hilfreich in der Sprache des Users. Bei Quatsch-Anfragen antworte kurz und witzig dreisprachig mit Flaggen."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME, temperature=0.7
                )
                await message.reply(chat_res.choices[0].message.content)
            except: pass
        return

    # AUTOMATISCHE ÜBERSETZUNG (STRENG & EINFACH)
    if not message.content.startswith("!") and len(message.content) > 3:
        low_msg = message.content.lower().strip()
        if low_msg in ["haha", "lol", "xd", "ok", "merci", "danke"]:
            return

        try:
            # Hier ist die neue, extrem scharfe Logik
            t_prompt = (
                "Du bist ein 1:1 Übersetzer. Gib NUR die Übersetzung aus.\n"
                "STRENGE LOGIK:\n"
                "1. Wenn der Text DEUTSCH ist -> Gib NUR die französische Übersetzung mit 🇫🇷 aus.\n"
                "2. Wenn der Text FRANZÖSISCH ist -> Gib NUR die deutsche Übersetzung mit 🇩🇪 aus.\n"
                "3. Wenn der Text weder DE noch FR ist -> Gib beides aus (🇩🇪 & 🇫🇷).\n"
                "4. Wiederhole NIEMALS den Text in der Sprache, in der er geschrieben wurde.\n"
                "5. KEINE Kommentare, KEIN 'DE:', KEIN 'FR:'.\n"
                f"Text: {message.content}"
            )
            
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": t_prompt}],
                model=MODEL_NAME, temperature=0.0
            )
            result = completion.choices[0].message.content
            
            if result and "SKIP" not in result.upper():
                await message.reply(result)
        except: pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
