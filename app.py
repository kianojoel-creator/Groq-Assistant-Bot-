import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
import threading
import sys
import asyncio

# 1. Webserver für Render (hält den Bot online)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Multi-Kulti-Bot LITE: Aktiv!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. KI Setup - Wechsel auf das LITE Modell für maximale Gratis-Limits
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# 'gemini-2.0-flash-lite' ist der stabilste Name für die schnellere Version
model = genai.GenerativeModel('gemini-2.0-flash-lite')

# 3. Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

auto_translate = True

@bot.event
async def on_ready():
    print(f'--- LITE TRANSLATOR ONLINE ---')
    print(f'Eingeloggt als: {bot.user.name}')
    sys.stdout.flush()

@bot.event
async def on_message(message):
    global auto_translate
    if message.author == bot.user:
        return

    # BEFEHLE (INFO / STATUS)
    if message.content.lower() in ["!info", "!help"]:
        info_text = (
            "**
