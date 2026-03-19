import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq

# 1. Webserver für Render
app = Flask(__name__)
@app.route('/')
def home(): return "VHA Translator - Fixed Final"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# 2. KI Setup
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Speicher gegen Doppel-Antworten (Echo-Effekt)
processed_messages = set()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌍 Präzise Übersetzung"))
    print(f'--- {bot.user.name} SYSTEM REPARIERT ---')

@bot.event
async def on_message(message):
    global processed_messages
    
    # 1. Sicherheits-Checks
    if message.author == bot.user or message.id in processed_messages:
        return
    
    # ID speichern
    processed_messages.add(message.id)
    if len(processed_messages) > 100: processed_messages.clear()

    # 2. KI-BEFEHL (!ai) - Nur hier darf er reden
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                chat_res = client.chat.completions.create(
                    messages=[{"role": "system", "content": "Antworte kurz in der Sprache des Users. Bei Quatsch-Anfragen (Kaffee, Witze) antworte kurz und witzig dreisprachig mit Flaggen."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME, temperature=0.6
                )
                await message.reply(chat_res.choices[0].message.content)
            except: pass
        return

    # 3. REINE ÜBERSETZUNG (STRENGER MODUS)
    if not message.content.startswith("!") and len(message.content) > 2:
        # Kurze Filter für Reaktionen
        low_msg = message.content.lower().strip()
        blacklist = ["haha", "lol", "xd", "ok", "merci", "danke", "top", "gut"]
        if low_msg in blacklist:
            return

        try:
            t_prompt = (
                "Du bist ein 1:1 Übersetzungs-Tool. Regeln:\n"
                "1. Wenn Input DEUTSCH -> NUR Französisch (🇫🇷) ausgeben.\n"
                "2. Wenn Input FRANZÖSISCH -> NUR Deutsch (🇩🇪) ausgeben.\n"
                "3. Wenn Input eine andere Sprache -> Beides (🇩🇪 & 🇫🇷) ausgeben.\n"
                "4. NIEMALS den Originaltext wiederholen.\n"
                "5. NUR Flagge und Übersetzung ausgeben. Keine Kommentare.\n"
                f"Text: {message.content}"
            )
            
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": t_prompt}],
                model=MODEL_NAME, 
                temperature=0.0 # Absolut keine Kreativität
            )
            result = completion.choices[0].message.content
            
            if result and "SKIP" not in result.upper():
                # Sicherheits-Check: Falls die KI trotzdem das Originalwort wiederholt
                lines = result.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Wenn die Zeile NICHT das exakte Originalwort (ohne Flagge) enthält
                    if message.content.lower() not in line.lower().replace("🇩🇪", "").replace("🇫🇷", "").strip():
                        cleaned_lines.append(line)
                
                output = "\n".join(cleaned_lines).strip()
                if output:
                    await message.reply(output)
        except: pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
