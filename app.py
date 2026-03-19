import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq

app = Flask(__name__)
@app.route('/')
def home(): return "VHA Minimal Stable Online"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Diese Variable verhindert, dass der Bot auf dieselbe Nachricht 2x reagiert
processed_messages = set()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="VHA | Nur Übersetzung"))
    print(f'--- {bot.user.name} RESET & READY ---')

@bot.event
async def on_message(message):
    global processed_messages
    
    # 1. Sofort-Sperren
    if message.author == bot.user or message.id in processed_messages:
        return
    
    # Kurzzeit-Speicher für IDs (verhindert Doppel-Antworten)
    processed_messages.add(message.id)
    if len(processed_messages) > 100: processed_messages.clear()

    # 2. BEFEHLE (KI-Chat)
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                res = client.chat.completions.create(
                    messages=[{"role": "system", "content": "Antworte kurz in der Sprache des Users."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME, temperature=0.3
                )
                await message.reply(res.choices[0].message.content)
            except: pass
        return

    # 3. REINE ÜBERSETZUNG (KEIN SCHNICK-SCHNACK)
    if not message.content.startswith("!") and len(message.content) > 3:
        # Blacklist für "Haha" etc.
        if message.content.lower().strip() in ["haha", "lol", "merci", "danke"]:
            return

        try:
            t_prompt = (
                "Du bist ein Übersetzungs-Tool. \n"
                "Regel: Deutsch <-> Französisch. Andere <-> DE/FR.\n"
                "Format: [Flagge] [Übersetzung]\n"
                "STRENG: Gib NUR die Übersetzung aus. Keine Erklärungen. Kein 'DE:'.\n"
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

