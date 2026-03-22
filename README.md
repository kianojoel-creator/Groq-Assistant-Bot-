# 🤖 VHA Alliance Bot • Mecha Fire

Ein mehrsprachiger Discord-Bot für die **VHA Alliance** im Spiel **Mecha Fire**.  
Automatische Übersetzung, Koordinaten-Verwaltung, Spieler-IDs, Timer und KI-Assistent.

---

## 🌐 Übersetzung

Der Bot übersetzt automatisch alle Nachrichten zwischen **Deutsch 🇩🇪**, **Französisch 🇫🇷** und **Brasilianisches Portugiesisch 🇧🇷** — ohne Befehle, einfach normal schreiben.

- 🇩🇪 Deutsch → 🇫🇷 + 🇧🇷 in einem Embed
- 🇫🇷 Französisch → 🇩🇪 + 🇧🇷 in einem Embed
- 🇧🇷 Portugiesisch → 🇩🇪 + 🇫🇷 in einem Embed
- 🌍 Andere Sprachen (EN, JA, ES ...) → 🇩🇪 + 🇫🇷 + 🇧🇷 in einem Embed
- Beim **Reply auf einen Gast** → übersetzt auch in die Gastsprache

---

## 📋 Befehle

### 🌐 Übersetzer
| Befehl | Beschreibung |
|--------|-------------|
| `!translate on` | Automatische Übersetzung einschalten |
| `!translate off` | Automatische Übersetzung ausschalten |
| `!translate status` | Status anzeigen |
| `!ai [Frage]` | KI-Assistent in jeder Sprache |
| `!übersetze` / `!traduire` / `!traduzir` | Text aus Bild übersetzen (Reply auf Bild) |

### 📍 Koordinaten 🔐
| Befehl | Beschreibung |
|--------|-------------|
| `!koordinaten` / `!coordonnees` | Alle Koordinaten anzeigen |
| `!koordinaten add NAME R X Y` | Neue Koordinate hinzufügen |
| `!koordinaten delete NAME` | Koordinate löschen |

### 👥 Spieler-IDs 🔐
| Befehl | Beschreibung |
|--------|-------------|
| `!spieler` / `!joueur` | Alle Spieler anzeigen |
| `!spieler add NAME ID` | Spieler hinzufügen |
| `!spieler delete NAME` | Spieler löschen |
| `!spieler suche NAME/ID` | Spieler suchen |

### ⏱️ Timer 🔐
| Befehl | Beschreibung |
|--------|-------------|
| `!timer DAUER EVENT` / `!rappel` | Timer setzen |
| `!timer list` | Aktive Timer anzeigen |
| `!timer delete NAME` | Timer löschen |

**Zeitformate:** `30m` • `2h` • `1h30m` • `3d`  
**Vorwarnung:** automatisch je nach Timer-Länge (5min / 15min / 1h vorher)

### 📊 Status
| Befehl | Beschreibung |
|--------|-------------|
| `!ping` | Bot-Status, Latenz und Token-Verbrauch |
| `!help` | Alle Befehle anzeigen |

🔐 = Nur für **Administrator**, **R5** und **R4**

---

## 📁 Dateistruktur

```
├── app.py                # Hauptbot
├── koordinaten.py        # Koordinaten-Cog
├── koordinaten.json      # Koordinaten-Daten
├── timer.py              # Timer-Cog
├── timer.json            # Timer-Daten (automatisch erstellt)
├── bilduebersetzer.py    # Bild-Übersetzer-Cog
├── spieler.py            # Spieler-IDs-Cog
├── spieler.json          # Spieler-Daten (automatisch erstellt)
├── requirements.txt      # Python-Abhängigkeiten
└── groq_usage.log        # Token-Verbrauch Log
```

---

## ⚙️ Technische Details

- **Sprache:** Python 3.10+
- **Framework:** discord.py
- **KI:** Groq API (Llama 3.3 70B + Llama 4 Scout für Bilder)
- **Hosting:** Render (Free Tier)
- **Keep-Alive:** UptimeRobot + Flask
- **Optimierungen:**
  - Async Groq-Calls mit `asyncio`
  - Semaphore (max. 4 gleichzeitige API-Calls)
  - Automatischer Retry bei Rate-Limit
  - Sprachcache für Token-Ersparnis
  - Parallele Übersetzungen mit `asyncio.gather`

---

## 🔑 Environment Variables

| Variable | Beschreibung |
|----------|-------------|
| `DISCORD_TOKEN` | Discord Bot Token |
| `GROQ_API_KEY` | Groq API Key |

---

## 📦 Installation

```bash
pip install -r requirements.txt
python app.py
```

---

*VHA Alliance • Mecha Fire • Made with ❤️*
