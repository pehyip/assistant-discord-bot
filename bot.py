import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class AssistantBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="!", 
            intents=intents,
            status=discord.Status.dnd,
            activity=discord.Game(name="♟️ Plotting the next move...")
        )

    async def setup_hook(self):
        database.init_db()
        await self.load_extension("cogs.to_do")
        await self.load_extension("cogs.reminders")
        await self.load_extension("cogs.word_association") # Added
        await self.tree.sync()

bot = AssistantBot()

@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Game(name="♟️ Plotting the next move...")
    )
    print(f"Bot connected as {bot.user} (Status: DND)")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN environment variable is missing in .env file!")
    bot.run(TOKEN)