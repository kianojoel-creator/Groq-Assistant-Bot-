# ════════════════════════════════════════════════
#  Spieler-Cog  •  VHA Alliance  •  Mecha Fire
#  MongoDB für persistente Speicherung
#  Spieler-IDs bleiben auch nach Neustart erhalten!
# ════════════════════════════════════════════════

import discord
from discord.ext import commands
from pymongo import MongoClient
import os
import logging
from log import add_log

log = logging.getLogger("VHABot.Spieler")

ALLOWED_ROLES = {"R5", "R4"}

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1484252260614537247/"
    "1484253018533662740/Picsart_26-03-18_13-55-24-994.png"
    "?ex=69bd8dd7&is=69bc3c57&hm=de6fea399dd30f97d2a14e1515c9e7f91d81d0d9ea111f13e0757d42eb12a0e5&"
)


# ────────────────────────────────────────────────
# MongoDB
# ────────────────────────────────────────────────

def get_col():
    client = MongoClient(os.getenv("MONGODB_URI"))
    return client["vhabot"]["spieler"]


# ────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────

def has_permission(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_roles = {r.name.upper() for r in member.roles}
    allowed_upper = {r.upper() for r in ALLOWED_ROLES}
    return bool(member_roles & allowed_upper)


# ────────────────────────────────────────────────
# Cog
# ────────────────────────────────────────────────

class SpielerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── !spieler ─────────────────────────────────
    @commands.group(name="spieler", aliases=["joueur", "joueurs", "player", "players", "ids"], invoke_without_command=True)
    async def spieler(self, ctx):
        try:
            col = get_col()
            data = list(col.find().sort("name", 1))
        except Exception as e:
            await ctx.send("❌ Fehler beim Laden der Spieler.")
            return

        if not data:
            await ctx.send(
                "📭 Keine Spieler gespeichert.\n"
                "Aucun joueur enregistré.\n"
                "Nenhum jogador registrado."
            )
            return

        embed = discord.Embed(title="👥 Spieler-IDs • Mecha Fire", color=0x2ECC71)

        lines = []
        for s in data:
            lines.append(f"`{s['name']:<15}` ID: `{s['id']}`")

        chunk = ""
        field_num = 1
        for line in lines:
            if len(chunk) + len(line) + 1 > 1000:
                embed.add_field(
                    name="Spieler / Joueurs / Jogadores" if field_num == 1 else f"... {field_num}",
                    value=chunk,
                    inline=False
                )
                chunk = line + "\n"
                field_num += 1
            else:
                chunk += line + "\n"

        if chunk:
            embed.add_field(
                name="Spieler / Joueurs / Jogadores" if field_num == 1 else f"... {field_num}",
                value=chunk,
                inline=False
            )

        embed.set_footer(text=f"Gesamt / Total: {len(data)} • !spieler add/delete")
        await ctx.send(embed=embed)

    # ── !spieler add ──────────────────────────────
    @spieler.command(name="add", aliases=["hinzufügen", "ajouter", "adicionar"])
    async def spieler_add(self, ctx, name: str, spieler_id: str):
        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation / Sem permissão",
                description="Nur **Administrator**, **R5** und **R4** dürfen Spieler hinzufügen.",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        if not spieler_id.isdigit():
            await ctx.send("❌ Die ID muss eine Zahl sein. / L'ID doit être un nombre. / O ID deve ser um número.")
            return

        try:
            col = get_col()

            # Prüfen ob Name oder ID schon existiert
            if col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}):
                await ctx.send(f"⚠️ `{name}` existiert bereits. Zuerst löschen mit `!spieler delete {name}`")
                return
            if col.find_one({"id": spieler_id}):
                existing = col.find_one({"id": spieler_id})
                await ctx.send(f"⚠️ ID `{spieler_id}` ist bereits **{existing['name']}** zugeordnet.")
                return

            col.insert_one({"name": name, "id": spieler_id})
        except Exception as e:
            await ctx.send("❌ Fehler beim Speichern.")
            return

        embed = discord.Embed(title="✅ Spieler hinzugefügt / Joueur ajouté / Jogador adicionado", color=0x57F287)
        embed.add_field(name="👤 Name", value=name, inline=True)
        embed.add_field(name="🆔 ID", value=spieler_id, inline=True)
        add_log("Spieler hinzugefügt", ctx.author.display_name, f"{name} (ID: {spieler_id})")
        embed.set_footer(text=f"Hinzugefügt von / Ajouté par / Adicionado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @spieler_add.error
    async def add_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❓ Nutzung: `!spieler add NAME ID`\nExemple: `!spieler add Noxxi 3881385`")

    # ── !spieler delete ───────────────────────────
    @spieler.command(name="delete", aliases=["löschen", "supprimer", "del", "remove", "apagar"])
    async def spieler_delete(self, ctx, *, name: str):
        if not has_permission(ctx.author):
            embed = discord.Embed(
                title="❌ Keine Berechtigung / Pas d'autorisation / Sem permissão",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        try:
            col = get_col()
            result = col.delete_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        except Exception as e:
            await ctx.send("❌ Fehler beim Löschen.")
            return

        if result.deleted_count == 0:
            await ctx.send(f"⚠️ `{name}` nicht gefunden. / `{name}` introuvable. / `{name}` não encontrado.")
            return

        embed = discord.Embed(
            title=f"🗑️ Spieler gelöscht / Joueur supprimé / Jogador apagado • {name}",
            color=0xED4245
        )
        add_log("Spieler gelöscht", ctx.author.display_name, name)
        embed.set_footer(text=f"Gelöscht von / Supprimé par / Apagado por {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── !spieler suche ────────────────────────────
    @spieler.command(name="suche", aliases=["search", "chercher", "find", "id", "pesquisar"])
    async def spieler_suche(self, ctx, *, suche: str):
        try:
            col = get_col()
            gefunden = list(col.find({
                "$or": [
                    {"name": {"$regex": suche, "$options": "i"}},
                    {"id": suche}
                ]
            }))
        except Exception as e:
            await ctx.send("❌ Fehler bei der Suche.")
            return

        if not gefunden:
            await ctx.send(f"🔍 Kein Spieler mit `{suche}` gefunden. / Aucun joueur trouvé. / Nenhum jogador encontrado.")
            return

        embed = discord.Embed(title=f"🔍 Suchergebnis / Résultat / Resultado • {suche}", color=0x3498DB)
        for s in gefunden:
            embed.add_field(name=f"👤 {s['name']}", value=f"🆔 `{s['id']}`", inline=False)
        await ctx.send(embed=embed)

    # ── !spieler help ─────────────────────────────
    @spieler.command(name="help", aliases=["hilfe", "aide", "ajuda"])
    async def spieler_help(self, ctx):
        embed = discord.Embed(title="👥 Spieler-IDs – Hilfe / Aide / Ajuda", color=0x3498DB)
        embed.add_field(
            name="🇩🇪 Befehle",
            value=(
                "`!spieler` – Alle anzeigen\n"
                "`!spieler add NAME ID` – Hinzufügen\n"
                "`!spieler delete NAME` – Löschen\n"
                "`!spieler suche NAME/ID` – Suchen\n"
                "**Beispiel:** `!spieler add Noxxi 3881385`"
            ),
            inline=False
        )
        embed.add_field(
            name="🇫🇷 Commandes",
            value=(
                "`!joueur` – Afficher tous\n"
                "`!joueur ajouter NOM ID` – Ajouter\n"
                "`!joueur supprimer NOM` – Supprimer\n"
                "`!joueur chercher NOM/ID` – Rechercher"
            ),
            inline=False
        )
        embed.add_field(
            name="🇧🇷 Comandos",
            value=(
                "`!jogador` – Ver todos\n"
                "`!spieler adicionar NOME ID` – Adicionar\n"
                "`!spieler apagar NOME` – Apagar\n"
                "`!spieler pesquisar NOME/ID` – Pesquisar"
            ),
            inline=False
        )
        embed.add_field(name="🔐 Berechtigung / Permission", value="Administrator, R5, R4", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SpielerCog(bot))
