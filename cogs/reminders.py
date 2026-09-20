import datetime
import sqlite3
import zoneinfo
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

PKT = zoneinfo.ZoneInfo("Asia/Karachi")
TARGET_CHANNEL_ID = 1520364368284487811
DB_PATH = Path(__file__).resolve().parent.parent / "assistant.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_reminders_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS date_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                remind_datetime TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending'
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_date_reminders_user_status_dt ON date_reminders (user_id, status, remind_datetime)"
        )
        conn.commit()


def seed_initial_wispbyte_reminder(user_id: int):
    target_dt = "2026-09-25 09:00"
    msg = "Log into Wispbyte on red account to keep the bots open and prevent shutdown!"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM date_reminders
            WHERE user_id = ? AND remind_datetime = ? AND message = ?
            """,
            (user_id, target_dt, msg),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """
                INSERT INTO date_reminders (user_id, remind_datetime, message)
                VALUES (?, ?, ?)
                """,
                (user_id, target_dt, msg),
            )
            conn.commit()


def remove_reminder(reminder_id: int, user_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM date_reminders WHERE id = ? AND user_id = ? AND status IN ('pending', 'notified')",
            (reminder_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def parse_datetime_input(date_str: str, time_str: Optional[str]) -> str:
    parsed_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

    if not time_str or not time_str.strip():
        time_obj = datetime.time(0, 0)
    else:
        clean_time = time_str.strip().upper()
        try:
            time_obj = datetime.datetime.strptime(clean_time, "%H:%M").time()
        except ValueError:
            time_obj = datetime.datetime.strptime(clean_time, "%I:%M %p").time()

    dt = datetime.datetime.combine(parsed_date, time_obj)
    return dt.strftime("%Y-%m-%d %H:%M")


def get_unix_timestamp(dt_str: str) -> int:
    dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=PKT)
    return int(dt_obj.timestamp())


class ReminderInteractiveView(discord.ui.View):
    def __init__(self, reminder_id: int, user_id: int, message: str):
        super().__init__(timeout=180)
        self.reminder_id = reminder_id
        self.user_id = user_id
        self.message = message

    def disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Mark as Done ✅", style=discord.ButtonStyle.success)
    async def confirm_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder isn't for you!", ephemeral=True)
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE date_reminders SET status = 'completed' WHERE id = ?", (self.reminder_id,))
            conn.commit()

        self.disable_all()
        embed = interaction.message.embeds[0].copy()
        embed.title = "🎉 Task Completed!"
        embed.color = discord.Color.green()
        embed.description = f"**Task:** {self.message}"

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("Task marked as completed!", ephemeral=True)

    @discord.ui.button(label="Remind Me Later ⏰", style=discord.ButtonStyle.secondary)
    async def snooze_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder isn't for you!", ephemeral=True)
            return

        snooze_dt = (datetime.datetime.now(PKT) + datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE date_reminders SET remind_datetime = ?, status = 'pending' WHERE id = ? AND user_id = ?",
                (snooze_dt, self.reminder_id, self.user_id),
            )
            conn.commit()

        self.disable_all()
        embed = interaction.message.embeds[0].copy()
        embed.title = "⏰ Reminder Snoozed"
        embed.color = discord.Color.orange()
        embed.description = f"This reminder has been pushed to **{snooze_dt} (PKT)**."

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"Reminder snoozed for 15 minutes. Next alert: **{snooze_dt} (PKT)**", ephemeral=True)

    @discord.ui.button(label="Delete Reminder 🗑️", style=discord.ButtonStyle.danger)
    async def delete_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder isn't for you!", ephemeral=True)
            return

        deleted = remove_reminder(self.reminder_id, self.user_id)
        if not deleted:
            await interaction.response.send_message("This reminder was already removed or is no longer available.", ephemeral=True)
            return

        self.disable_all()
        embed = interaction.message.embeds[0].copy()
        embed.title = "🗑️ Reminder Removed"
        embed.color = discord.Color.red()
        embed.description = f"**Removed:** {self.message}"
        embed.set_footer(text="Deleted from your reminder list")

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("Reminder deleted successfully.", ephemeral=True)


class ReminderDeleteButton(discord.ui.Button):
    def __init__(self, reminder_id: int, user_id: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.red, custom_id=f"delete_reminder_{reminder_id}")
        self.reminder_id = reminder_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder isn't for you!", ephemeral=True)
            return

        if remove_reminder(self.reminder_id, self.user_id):
            await interaction.response.send_message("Reminder deleted successfully.", ephemeral=True)
        else:
            await interaction.response.send_message("This reminder was already removed.", ephemeral=True)


class ReminderListView(discord.ui.View):
    def __init__(self, reminders):
        super().__init__(timeout=180)
        for reminder_id, user_id, remind_dt, message in reminders:
            short_label = f"Delete {remind_dt[-5:]}" if len(remind_dt) >= 5 else "Delete"
            self.add_item(ReminderDeleteButton(reminder_id, user_id, short_label))


class RemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_reminders_db()
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        now_pkt = datetime.datetime.now(PKT)
        now_str = now_pkt.strftime("%Y-%m-%d %H:%M")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, message, remind_datetime FROM date_reminders
                WHERE remind_datetime <= ? AND status = 'pending'
                ORDER BY remind_datetime ASC
                """,
                (now_str,),
            )
            due_reminders = cursor.fetchall()

            for row in due_reminders:
                rem_id = row["id"]
                user_id = row["user_id"]
                message = row["message"]
                rem_dt = row["remind_datetime"]
                target_channel = self.bot.get_channel(TARGET_CHANNEL_ID)
                unix_ts = get_unix_timestamp(rem_dt)

                embed = discord.Embed(
                    title="🚨 Scheduled Task Reminder",
                    description=f"**Task:** {message}\n\nClick **Mark as Done** once finished, **Remind Me Later** to postpone, or **Delete Reminder** to remove it.",
                    color=discord.Color.gold(),
                )
                embed.set_footer(text=f"Scheduled For: {rem_dt} (PKT) | Due <t:{unix_ts}:R>")

                if target_channel:
                    view = ReminderInteractiveView(rem_id, user_id, message)
                    await target_channel.send(content=f"🔔 <@{user_id}>", embed=embed, view=view)
                    cursor.execute("UPDATE date_reminders SET status = 'notified' WHERE id = ?", (rem_id,))
                    conn.commit()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="add_reminder", description="Set a custom date/time reminder (Time is optional)")
    async def add_reminder_cmd(
        self,
        interaction: discord.Interaction,
        date: str,
        message: str,
        time: Optional[str] = None,
    ):
        try:
            target_datetime_str = parse_datetime_input(date, time)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid format! Use **YYYY-MM-DD** for date and optional **HH:MM** (or `9:00 PM`) for time.",
                ephemeral=True,
            )
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO date_reminders (user_id, remind_datetime, message) VALUES (?, ?, ?)",
                (interaction.user.id, target_datetime_str, message),
            )
            conn.commit()

        unix_ts = get_unix_timestamp(target_datetime_str)
        embed = discord.Embed(title="⏰ Reminder Set Successfully", color=discord.Color.green())
        embed.add_field(
            name="📅 Scheduled Date & Time",
            value=f"**{target_datetime_str}** (PKT)\n⏳ <t:{unix_ts}:R> (<t:{unix_ts}:f>)",
            inline=True,
        )
        embed.add_field(name="📝 Note", value=message, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reminders", description="View all your active scheduled reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, remind_datetime, message FROM date_reminders
                WHERE user_id = ? AND status IN ('pending', 'notified')
                ORDER BY remind_datetime ASC
                """,
                (interaction.user.id,),
            )
            reminders = cursor.fetchall()

        embed = discord.Embed(
            title=f"📌 {interaction.user.display_name}'s Scheduled Reminders",
            color=discord.Color.blue(),
        )

        if not reminders:
            embed.description = "No pending reminders set!"
            await interaction.response.send_message(embed=embed)
            return

        desc = ""
        for row in reminders:
            remind_dt = row["remind_datetime"]
            msg = row["message"]
            unix_ts = get_unix_timestamp(remind_dt)
            desc += f"• **{remind_dt}** (<t:{unix_ts}:R>): {msg}\n"
        embed.description = desc

        await interaction.response.send_message(embed=embed, view=ReminderListView(reminders))


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))