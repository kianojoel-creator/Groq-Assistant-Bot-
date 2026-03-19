import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading
import sys

# 1. Webserver für Render (damit der Bot 24/7 online bleibt)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Multi-Kulti-Bot: Aktiv!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup - Gemini 2.5 Flash (Aktuellste Version 2026)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Status-Variable für die Automatik
auto_translate = True

@bot.event
async def on_ready():
    print(f'--- UNIVERSAL TRANSLATOR ONLINE ---')
    print(f'Eingeloggt als: {bot.user.name}')
    print(f'Modell: Gemini 2.5 Flash')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # BEFEHL: INFO / HELP (Multi-Kulti DE/FR/JP/TR)
    if message.content.lower() in ["!info", "!help"]:
        info_text = (
            "**🌍 Universal Translator & AI Assistant**\n"
            "__________________________________________\n\n"
            "**DE:** Ich übersetze automatisch zwischen allen Sprachen im Chat!\n"
            "**FR:** Je traduis automatiquement entre toutes les langues du chat !\n"
            "**EN:** I translate automatically between all languages in the chat!\n\n"
            "**Commands / Befehle:**\n"
            "• `!auto on`  -> Startet Übersetzung / Active la traduction ✅\n"
            "• `!auto off` -> Pausemodus / Mode pause 😴\n"
            "• `!gemini [Text]` -> Frag die KI alles / Demandez à l'IA 🤖\n\n"
            "*Hauptsprachen: DE ↔️ FR. Andere Sprachen (Japanisch, Türkisch etc.) werden für alle übersetzt!*"
        )
        await message.reply(info_text)
        return

    # STATUS-BEFEHLE
    if message.content.lower() == "!auto on":
        auto_translate = True
        await message.reply("✅ **Aktiviert!** Ich übersetze jetzt wieder alle Sprachen für die Gruppe.")
        return

    if message.content.lower() == "!auto off":
        auto_translate = False
        await message.reply("😴 **Deaktiviert.** Ich reagiere nur noch auf direkte Befehle.")
        return

    # 4. DIREKTE KI-ANFRAGE
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if not query:
            await message.reply("Frag mich etwas!")
            return

        async with message.channel.typing():
            try:
                response = model.generate_content(query)
                if response and response.text:
                    await message.reply(response.text)
            except Exception as e:
                await message.reply(f"KI Fehler: {e}")
        return

    # 5. SMART MULTI-KULTI ÜBERSETZUNG (Chat-Schonend & Spiegel-Logik)
    if auto_translate and len(message.content) > 2 and not message.content.startswith("!"):
        try:
            # Dieser Prompt sorgt dafür, dass nur das Nötigste übersetzt wird
            prompt = (
                f"Du bist ein diskreter Universal-Dolmetscher in einem internationalen Chat. "
                f"Deine Regeln:\n"
                f"1. Wenn der Text DEUTSCH ist -> übersetze NUR ins FRANZÖSISCHE.\n"
                f"2. Wenn der Text FRANZÖSISCH ist -> übersetze NUR ins DEUTSCHE.\n"
                f"3. Wenn der Text eine ANDERE SPRACHE ist (z.B. Japanisch, Türkisch, Englisch) -> übersetze ihn in DEUTSCHE UND FRANZÖSISCHE.\n"
                f"4. Wenn die Nachricht eine Antwort auf eine fremde Sprache ist -> übersetze sie ZUSÄTZLICH in diese Fremdsprache zurück.\n"
                f"Antworte NUR mit 'SKIP', wenn keine Übersetzung nötig ist (z.B. Emojis, Namen oder Haha).\n"
                f"Halte die Übersetzung kurz und direkt.\n\n"
                f"Text: {message.content}"
            )
            
            async with message.channel.typing():
                response = model.generate_content(prompt)
                if response.text and "SKIP" not in response.text.upper():
                    await message.reply(f"🌍 {response.text}")
        except Exception:
            # Bei Fehlern schweigen, um den Chat-Fluss nicht zu stören
            pass

# 6. Start-Sequenz
if __name__ == "__main__":
    # Flask in eigenem Thread starten für Render.com
    threading.Thread(target=run_flask, daemon=True).start()
    
    token = os.getenv("DISCORD_TOKEN")
    if token:
        try:
            bot.run(token)
        except Exception as e:
            print(f"START FEHLER: {e}")
    else:
        print("FEHLER: DISCORD_TOKEN nicht gefunden!")
