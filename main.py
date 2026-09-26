import logging
import os

import asyncpg
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ultranomics")

intents = discord.Intents.default()
intents.message_content = True


class UltranomicsBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.pool = None

    async def setup_hook(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL)
        logger.info("Database connection pool created")

        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                await self.load_extension(f"cogs.{filename[:-3]}")
                logger.info(f"Loaded cog: {filename}")

        try:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to sync commands: {e}")

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
        await super().close()


bot = UltranomicsBot()


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    command_name = interaction.command.name if interaction.command else "unknown"
    logger.error(f"Error in /{command_name}: {error}")

    error_message = "⚠️ Something went wrong running that command. Please try again."

    if isinstance(error, discord.app_commands.CommandOnCooldown):
        error_message = (
            f"⏳ That command is on cooldown. Try again in {error.retry_after:.1f}s."
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)
    except discord.errors.InteractionResponded:
        pass


bot.run(TOKEN)
