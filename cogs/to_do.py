import discord
from discord.ext import commands, tasks
from discord import app_commands
import database
import datetime
import zoneinfo

PKT = zoneinfo.ZoneInfo("Asia/Karachi")

class AddTaskModal(discord.ui.Modal, title="Add Task"):
    task_name = discord.ui.TextInput(label="Task Name", placeholder="e.g., Pimsleur Lesson", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        database.add_default_task(interaction.user.id, self.task_name.value)
        view = DailyTodoView(interaction.user.id)
        embed = view.create_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=view)

class RemoveTaskModal(discord.ui.Modal, title="Remove Task"):
    task_name = discord.ui.TextInput(label="Task Name to Remove", placeholder="Exact task name as shown above", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        database.remove_default_task(interaction.user.id, self.task_name.value)
        view = DailyTodoView(interaction.user.id)
        embed = view.create_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=view)

class TaskButton(discord.ui.Button):
    def __init__(self, task_id, label, is_completed, owner_id):
        style = discord.ButtonStyle.green if is_completed else discord.ButtonStyle.secondary
        super().__init__(label=f"{'✅' if is_completed else '⬛'} {label}", style=style, custom_id=f"task_{task_id}")
        self.task_id = task_id
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This is not your menu! Type `/today` to open your own.", ephemeral=True)
            return

        await interaction.response.defer()
        database.toggle_daily_task(self.task_id, interaction.user.id)
        view = DailyTodoView(interaction.user.id)
        embed = view.create_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=view)

class ActionButton(discord.ui.Button):
    def __init__(self, label, style, action_type, owner_id):
        super().__init__(label=label, style=style)
        self.action_type = action_type
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This is not your menu! Type `/today` to open your own.", ephemeral=True)
            return

        if self.action_type == "add":
            await interaction.response.send_modal(AddTaskModal())
        elif self.action_type == "remove":
            await interaction.response.send_modal(RemoveTaskModal())
        elif self.action_type == "reset":
            await interaction.response.defer()
            database.reset_daily_list(interaction.user.id)
            view = DailyTodoView(interaction.user.id)
            embed = view.create_embed(interaction.user)
            await interaction.edit_original_response(embed=embed, view=view)

class DailyTodoView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        tasks = database.get_daily_tasks(user_id)
        
        for task_id, task_text, status in tasks[:20]:
            self.add_item(TaskButton(task_id, task_text, status == 'completed', user_id))
            
        self.add_item(ActionButton("➕ Add Item", discord.ButtonStyle.blurple, "add", user_id))
        self.add_item(ActionButton("➖ Remove Item", discord.ButtonStyle.grey, "remove", user_id))
        self.add_item(ActionButton("🔄 Force Reset", discord.ButtonStyle.danger, "reset", user_id))

    def create_embed(self, user):
        now = datetime.datetime.now(PKT)
        date_str = now.strftime("%d %b %Y")
        tasks = database.get_daily_tasks(self.user_id)
        streak = database.get_streak(self.user_id)
        
        embed = discord.Embed(title=f"📅 {user.display_name}'s Routine — {date_str}", color=discord.Color.gold())
        if not tasks:
            embed.description = "No tasks set! Click **➕ Add Item** below to create one."
            return embed

        done_count = sum(1 for _, _, status in tasks if status == 'completed')
        
        desc = ""
        for _, task, status in tasks:
            icon = "✅" if status == 'completed' else "⬛"
            desc += f"{icon} **{task}**\n"

        embed.description = desc
        embed.set_footer(text=f"Progress: {done_count}/{len(tasks)} | 🔥 Streak: {streak} Days | Auto-resets at midnight PKT")
        return embed

class TodoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_reset.start()
        self.evening_nudge.start()

    def cog_unload(self):
        self.daily_reset.cancel()
        self.evening_nudge.cancel()

    # Midnight Reset
    @tasks.loop(time=datetime.time(hour=0, minute=0, second=0, tzinfo=PKT))
    async def daily_reset(self):
        database.reset_daily_list()

    # 9:00 PM PKT Evening Nudge
    @tasks.loop(time=datetime.time(hour=21, minute=0, second=0, tzinfo=PKT))
    async def evening_nudge(self):
        for guild in self.bot.guilds:
            channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
            if channel:
                for member in guild.members:
                    if not member.bot:
                        tasks = database.get_daily_tasks(member.id)
                        pending = [t[1] for t in tasks if t[2] == 'pending']
                        if pending:
                            pending_str = ", ".join(f"**{t}**" for t in pending)
                            await channel.send(f"🔔 <@{member.id}> **Evening Nudge (9:00 PM PKT):** You have {len(pending)} tasks remaining today: {pending_str}. Finish strong!")
                break

    @app_commands.command(name="today", description="Show your personal interactive daily routine dashboard")
    async def today(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = DailyTodoView(interaction.user.id)
        embed = view.create_embed(interaction.user)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="stats", description="View your productivity progress and completion analytics")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        total_completed, best_task = database.get_user_stats(interaction.user.id)
        streak = database.get_streak(interaction.user.id)
        
        embed = discord.Embed(title=f"📊 Productivity Analytics — {interaction.user.display_name}", color=discord.Color.blue())
        embed.add_field(name="🔥 Current Streak", value=f"**{streak} Days**", inline=True)
        embed.add_field(name="✅ Total Tasks Completed", value=f"**{total_completed} Tasks**", inline=True)
        embed.add_field(name="🏆 Most Completed Task", value=f"**{best_task}**", inline=False)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TodoCog(bot))