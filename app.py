import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from groq import Groq
import re

app = Flask(__name__)
@app.route('/')
def home(): return "VHA Translator - Context Master 2.0"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

processed_messages = set()

def detect_language_manually(text):
    t = text.lower()
    # Französisch
    if any(re.search(rf'\b{w}\b', t) for w in ["c'est", "oui", "je", "suis", "pas", "le", "la", "et", "que", "pour", "dans", "est"]):
        return "FR"
    # Deutsch
    if any(re.search(rf'\b{w}\b', t) for w in ["ist", "ja", "ich", "bin", "nicht", "das", "die", "und", "dass", "für", "mit", "auch"]):
        return "DE"
    # Englisch (nur zur Erkennung, nicht zum Sperren)
    if any(re.search(rf'\b{w}\b', t) for w in ["is", "the", "and", "not", "with", "have", "you", "this"]):
        return "EN"
    return "UNKNOWN"

@bot.event
async def on_message(message):
    global processed_messages
    if message.author == bot.user or message.id in processed_messages:
        return
    processed_messages.add(message.id)
    if len(processed_messages) > 150: processed_messages.clear()

    # !ai Befehl (unverändert)
    if message.content.lower().startswith("!ai "):
        query = message.content[4:].strip()
        async with message.channel.typing():
            try:
                res = client.chat.completions.create(
                    messages=[{"role": "system", "content": "Antworte kurz und witzig."},
                              {"role": "user", "content": query}],
                    model=MODEL_NAME, temperature=0.7
                )
                await message.reply(res.choices[0].message.content)
            except: pass
        return

    # ÜBERSETZUNG MIT EXTREMER KONTEXT-TREUE
    text = message.content.strip()
    if not text.startswith("!") and len(text) > 2:
        if text.lower() in ["haha", "lol", "ok", "merci", "danke"]: return

        # Kontext holen
        replied_text = ""
        is_reply = False
        if message.reference and message.reference.message_id:
            try:
                replied_to = await message.channel.fetch_message(message.reference.message_id)
                replied_text = replied_to.content
                is_reply = True
            except: pass

        input_lang = detect_language_manually(text)
        
        # Den Befehl für die KI bauen
        if is_reply:
            sys_msg = (
                f"Der User antwortet auf diese Nachricht: '{replied_text}'. "
                "1. Erkenne die Sprache dieser Originalnachricht. "
                "2. Übersetze die neue Antwort des Users ('{text}') in: "
                "- Deutsch (🇩🇪) "
                "- Französisch (🇫🇷) "
                "- UND in die exakte Sprache der Originalnachricht (falls diese nicht DE oder FR ist). "
                "Regel: Gib NUR die Übersetzungen mit Flaggen aus. KEIN Englisch, außer es wurde explizit danach gefragt oder die Originalnachricht war Englisch."
            )
        elif input_lang == "FR":
            sys_msg = "Übersetze NUR ins Deutsche (🇩🇪). Keine anderen Sprachen."
        elif input_lang == "DE":
            sys_msg = "Übersetze NUR ins Französische (🇫🇷). Keine anderen Sprachen."
        elif input_lang == "EN":
            sys_msg = "Der Input ist Englisch. Übersetze in Deutsch (🇩🇪) UND Französisch (🇫🇷)."
        else:
            sys_msg = "Übersetze in Deutsch (🇩🇪) UND Französisch (🇫🇷). Gib nur die Übersetzungen aus."

        try:
            completion = client.chat.completions.create(
                messages=[{"role": "system", "content": "Du bist ein präziser Allianz-Übersetzer. Kein Smalltalk, keine unnötigen Sprachen."},
                          {"role": "user", "content": sys_msg + f"\n\nText zum Übersetzen: {text}"}],
                model=MODEL_NAME, temperature=0.0
            )
            result = completion.choices[0].message.content.strip()
            
            # Strenger Filter gegen doppelte Sätze (Echos)
            lines = result.split('\n')
            final_lines = []
            for line in lines:
                clean_line = line.replace("🇩🇪", "").replace("🇫🇷", "").replace("🇬🇧", "").strip().lower()
                # Wenn die Zeile fast identisch mit deinem Input ist -> weg damit
                if text.lower() not in clean_line or len(clean_line) > len(text.lower()) + 2:
                    final_lines.append(line)
            
            output = "\n".join(final_lines).strip()
            if output:
                await message.reply(output)
        except: pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
