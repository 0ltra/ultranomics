import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands


def time_until_ready(last_claim, cooldown, now):
    """Returns the remaining timedelta if still on cooldown, or None if ready to claim."""
    if last_claim is None:
        return None
    elapsed = now - last_claim
    if elapsed >= cooldown:
        return None
    return cooldown - elapsed


def format_remaining(remaining: timedelta) -> str:
    """Formats a timedelta as a human-readable string like '1d 3h 12m'."""
    days, rem = divmod(int(remaining.total_seconds()), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    async def get_or_create_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT balance FROM users WHERE user_id = $1", user_id
            )
            if row is None:
                await conn.execute(
                    "INSERT INTO users (user_id, balance) VALUES ($1, 0)", user_id
                )
                return 0
            return row["balance"]

    async def claim_reward(
        self,
        user_id: int,
        column: str,
        cooldown: timedelta,
        reward_min: int,
        reward_max: int,
    ):
        """Generic cooldown-based reward claim. Returns (success, message, new_balance_or_None)."""
        await self.get_or_create_user(user_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {column} FROM users WHERE user_id = $1", user_id
            )
            last_claim = row[column]
            now = datetime.utcnow()

            remaining = time_until_ready(last_claim, cooldown, now)
            if remaining is not None:
                return False, format_remaining(remaining), None

            reward = random.randint(reward_min, reward_max)
            new_balance = await conn.fetchval(
                f"""
                UPDATE users
                SET balance = balance + $1, {column} = $2
                WHERE user_id = $3
                RETURNING balance
                """,
                reward,
                now,
                user_id,
            )
            return True, reward, new_balance

    @app_commands.command(name="balance", description="Check your IPC credit balance")
    async def balance(self, interaction: discord.Interaction):
        bal = await self.get_or_create_user(interaction.user.id)
        await interaction.response.send_message(
            f"💳 You have **{bal}** credits in your IPC account."
        )

    @app_commands.command(name="daily", description="Claim your daily IPC stipend")
    async def daily(self, interaction: discord.Interaction):
        success, result, new_balance = await self.claim_reward(
            interaction.user.id, "last_daily", timedelta(hours=24), 80, 120
        )
        if not success:
            await interaction.response.send_message(
                f"⏳ You've already claimed your stipend. Try again in {result}.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"💰 The IPC has deposited **{result}** credits into your account. "
            f"New balance: **{new_balance}**."
        )

    @app_commands.command(name="work", description="Do a job for the IPC")
    async def work(self, interaction: discord.Interaction):
        success, result, new_balance = await self.claim_reward(
            interaction.user.id, "last_work", timedelta(hours=1), 20, 50
        )
        if not success:
            await interaction.response.send_message(
                f"⏳ You're still on the clock. Try again in {result}.",
                ephemeral=True,
            )
            return

        flavor = random.choice(
            [
                "audited a shell corporation",
                "closed a deal on Penacony",
                "laundered credits through the Strife Ruin Engine",
                "brokered a stock trade for the Family",
            ]
        )
        await interaction.response.send_message(
            f"🧳 You {flavor} and earned **{result}** credits. "
            f"New balance: **{new_balance}**."
        )

    @app_commands.command(name="weekly", description="Claim your weekly IPC dividend")
    async def weekly(self, interaction: discord.Interaction):
        success, result, new_balance = await self.claim_reward(
            interaction.user.id, "last_weekly", timedelta(days=7), 500, 800
        )
        if not success:
            await interaction.response.send_message(
                f"⏳ Dividends already claimed this cycle. Try again in {result}.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"📈 Your IPC stock dividend has paid out **{result}** credits. "
            f"New balance: **{new_balance}**."
        )

    @app_commands.command(name="give", description="Transfer credits to another user")
    @app_commands.describe(
        user="Who to send credits to", amount="How many credits to send"
    )
    async def give(
        self, interaction: discord.Interaction, user: discord.Member, amount: int
    ):
        sender_id = interaction.user.id
        recipient_id = user.id

        if amount <= 0:
            await interaction.response.send_message(
                "⚠️ Amount must be greater than 0.", ephemeral=True
            )
            return

        if recipient_id == sender_id:
            await interaction.response.send_message(
                "⚠️ You can't send credits to yourself.", ephemeral=True
            )
            return

        await self.get_or_create_user(sender_id)
        await self.get_or_create_user(recipient_id)

        async with self.pool.acquire() as conn, conn.transaction():
            sender_balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1 FOR UPDATE",
                sender_id,
            )

            if sender_balance < amount:
                await interaction.response.send_message(
                    f"⚠️ Insufficient funds. You have **{sender_balance}** credits.",
                    ephemeral=True,
                )
                return

            await conn.execute(
                "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                amount,
                sender_id,
            )
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                amount,
                recipient_id,
            )

        await interaction.response.send_message(
            f"✅ Sent **{amount}** credits to {user.mention}."
        )

    @app_commands.command(name="leaderboard", description="View the top IPC investors")
    async def leaderboard(self, interaction: discord.Interaction):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10"
            )

        if not rows:
            await interaction.response.send_message("No IPC investors yet.")
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            user = self.bot.get_user(row["user_id"])
            name = user.display_name if user else f"User {row['user_id']}"
            lines.append(f"{prefix} **{name}** — {row['balance']} credits")

        embed = discord.Embed(
            title="💼 IPC Investor Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))
