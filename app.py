import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import sys
from groq import Groq

app = Flask(__name__)
@app.route('/')
def home(): return "VHA Stable Online"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

auto_translate = True
# Wir speichern die ID der letzten Nachricht, um Doppel-Antworten physikalisch zu blockieren
last_msg_id = 0

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="VHA | Only Translating"))
    print(f'--- {bot.user.name} READY ---')

@bot.event
async def on_message(message):
    global auto_translate, last_msg_id
    
    if message.author == bot.user or message.id == last_msg_id:
        return
    
    # Sofortiger Abbruch bei ganz kurzen Nachrichten (haha, lol, ja, etc.)
    if len(message.content) < 4 and not message.content.startswith("!"):
        return

    # BEFEHLE
    if message.content.lower().startswith("!auto"):
        if "on" in message.content.lower():
            auto_translate = True
            await message.reply("✅ Auto-Translate ON")
        else:
            auto_translate = False
            await message.reply("😴 Auto-Translate OFF")
        return

    # !ai BEFEHL (Hier darf er reden)
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                chat_completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": "You are a helpful assistant. Answer briefly in the user's language."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME, temperature=0.5
                )
                last_msg_id = message.id
                await message.reply(chat_completion.choices[0].message.content)
            except: pass
        return

    # AUTOMATISCHE ÜBERSETZUNG (STRENG & RUHIG)
    if auto_translate and not message.content.startswith("!"):
        # Kurze Liste für Wörter, die gar nicht erst zur KI gehen
        blacklist = ["haha", "lol", "merci", "danke", "thanks", "okay", "super", "top"]
        if message.content.lower().strip() in blacklist:
            return

        try:
            t_prompt = (
                f"Translate the following text. Rules:\n"
                f"1. German <-> French.\n"
                f"2. Other languages -> DE + FR.\n"
                f"3. Output ONLY the translation and flags. No comments, no chatter.\n"
                f"4. If it's a joke or simple greeting, answer 'SKIP'.\n"
                f"Text: {message.content}"
            )
            
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": t_prompt}],
                model=MODEL_NAME, temperature=0.0 # 0.0 macht ihn extrem sachlich
            )
            result = completion.choices[0].message.content
            
            if result and "SKIP" not in result.upper():
                last_msg_id = message.id
                await message.reply(result)
        except: pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
