import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq

# ────────────────────────────────────────────────
#  Webserver für Render (Keep-Alive)
# ────────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "VHA Translator - Strict Mode 2026"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# ────────────────────────────────────────────────
#  Groq / KI Setup
# ────────────────────────────────────────────────
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"          # oder llama-3.1-70b je nach Verfügbarkeit

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Gegen Echo / Doppelverarbeitung
processed_messages = set()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌍 DE ↔ FR Übersetzer"))
    print(f'--- {bot.user.name} ONLINE | Strict Mode ---')

@bot.event
async def on_message(message):
    global processed_messages
    
    if message.author == bot.user or message.id in processed_messages:
        return
    
    processed_messages.add(message.id)
    if len(processed_messages) > 150:
        processed_messages.clear()

    # ────────────────────────────────────────────────
    # 1. Freie KI-Antwort mit !ai
    # ────────────────────────────────────────────────
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                chat_res = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "Antworte kurz in der Sprache des Users. Bei Unsinn/Witzen/Kaffee-Anfragen → kurz, witzig, dreisprachig mit Flaggen."},
                        {"role": "user", "content": query}
                    ],
                    model=MODEL_NAME,
                    temperature=0.7,
                    max_tokens=400
                )
                await message.reply(chat_res.choices[0].message.content)
            except Exception as e:
                print(f"!ai Fehler: {e}")
        return

    # ────────────────────────────────────────────────
    # 2. Reine 1:1 Übersetzung – sehr strenger Modus
    # ────────────────────────────────────────────────
    if not message.content.startswith("!") and len(message.content.strip()) > 2:
        low_msg = message.content.lower().strip()
        blacklist = ["haha", "lol", "xd", "ok", "oui", "ja", "nein", "merci", "danke", "top", "gut", "👍", "👌"]
        if low_msg in blacklist or len(low_msg) < 3:
            return

        t_prompt = f"""Du bist ein **streng regelkonformer 1:1-Übersetzer**. Du darfst **niemals** vom folgenden Format abweichen.

ABSOLUTE VERBOTS-REGELN – VERLETZE SIE NIE:
- Keine Erklärungen, Begründungen, Meta-Kommentare, Sätze wie „ist nicht erforderlich“, „da der Input…“, „deshalb“, „korrekte Antwort ist“, „ich gebe nur…“, „Input ist…“, „Regel…“
- Kein einziges Wort über deine Regeln, den Input oder warum du etwas tust oder nicht tust.
- Kein „denke laut“, kein Chain-of-Thought sichtbar.
- Deine **gesamte Antwort** besteht **ausschließlich** aus 1 oder genau 2 Zeilen mit Flagge + Übersetzung. Sonst **gar nichts**.

Regeln (unveränderlich):
1. Input DEUTSCH          → NUR: 🇫🇷 [Französische Übersetzung]
2. Input FRANZÖSISCH      → NUR: 🇩🇪 [Deutsche Übersetzung]
3. Input ANDERE SPRACHE   → genau zwei Zeilen:
   🇩🇪 [Deutsche Übersetzung]
   🇫🇷 [Französische Übersetzung]

Weitere HARTE REGELN:
- Reine, wörtliche Übersetzung – nichts umformulieren, verbessern oder hinzufügen.
- Wiederhole **niemals** ein Wort des Originals.
- Nur die Flaggen 🇩🇪 🇫🇷 verwenden – keine anderen Emojis.
- Antwort = **maximal** 2 Zeilen. Kein zusätzlicher Text davor, dazwischen oder danach.

Text: {message.content}"""

        try:
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Du bist ein roboterhafter Übersetzer. Du denkst lautlos. Du schreibst **nur** das exakte geforderte Format. Kein einziges anderes Wort."},
                    {"role": "user", "content": t_prompt}
                ],
                model=MODEL_NAME,
                temperature=0.0,
                max_tokens=300
            )
            
            result = completion.choices[0].message.content.strip()
            
            if not result or "SKIP" in result.upper():
                return

            # ────────────────────────────────────────────────
            # Verbessertes Cleaning – Meta-Sätze rausfiltern
            # ────────────────────────────────────────────────
            forbidden_starts = [
                "nicht erforderlich", "da der input", "daher ist", "deshalb", "deswegen",
                "korrekte antwort", "ich gebe", "nur diese", "regel", "regeln", "input ist",
                "da input", "weil", "denke", "denkprozess"
            ]

            lines = [line.strip() for line in result.split('\n') if line.strip()]
            cleaned = []

            original_lower = message.content.lower()

            for line in lines:
                lower_line = line.lower()
                
                # Meta-Sätze komplett ignorieren
                if any(phrase in lower_line for phrase in forbidden_starts):
                    continue
                
                # Zu ähnlich zum Original → wahrscheinlich Quelltext durchgerutscht
                clean_content = line.replace("🇩🇪", "").replace("🇫🇷", "").strip().lower()
                if len(clean_content) > 4:
                    overlap = sum(1 for w in original_lower.split() if w in clean_content) / max(1, len(original_lower.split()))
                    if original_lower in clean_content or overlap > 0.65:
                        continue
                
                # Nur Zeilen mit Flagge behalten
                if '🇩🇪' in line or '🇫🇷' in line:
                    cleaned.append(line)

            output = '\n'.join(cleaned).strip()
            
            if output:
                await message.reply(output)
                    
        except Exception as e:
            print(f"Übersetzungsfehler: {e}")

    await bot.process_commands(message)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
