@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    if message.content.lower().startswith("!gemini"):
        query = message.content[7:].strip()
        if query:
            async with message.channel.typing():
                try:
                    response = model.generate_content(query)
                    if response.text:
                        await message.reply(response.text)
                    else:
                        await message.reply("Die KI hat keine Antwort generiert (Sicherheitsfilter?).")
                except Exception as e:
                    print(f"FEHLER: {e}")
                    await message.reply(f"Fehler beim Generieren: {e}")
        return

    # Übersetzungs-Teil mit Fehlerprüfung
    if len(message.content) > 2:
        async with message.channel.typing():
            try:
                prompt = f"Übersetze DE<->FR, sonst antworte NUR mit 'SKIP': {message.content}"
                response = model.generate_content(prompt)
                if response.text and "SKIP" not in response.text.upper():
                    await message.reply(f"🌍 {response.text}")
            except Exception as e:
                print(f"Übersetzungsfehler: {e}")
