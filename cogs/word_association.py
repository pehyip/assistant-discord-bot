import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from groq import Groq

ALLOWED_ROLE_ID = 1530509533888380939

# Initialize Groq client using environment variable
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"

def check_has_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)


def sync_fetch_word() -> str:
    """Fetch an everyday, highly relatable topic for social banter drills."""
    response = groq_client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": (
                    "Give me EXACTLY ONE topic, object, habit, or situation for a witty social banter game. "
                    "The topic MUST be an everyday, highly relatable real-world concept "
                    "(e.g., 'Espresso', 'First Date', 'Overpricing', 'Traffic Jam', 'Gym Bro', 'Monday Morning', 'Procrastination', 'Reality TV'). "
                    "Do NOT give sci-fi, fantasy, abstract, or niche terms like 'Neon Samurai'. "
                    "Output ONLY the word or short phrase itself with no punctuation, setup, or quotes."
                )
            }
        ],
        model=MODEL_NAME,
        temperature=1.1,
        max_completion_tokens=400
    )
    
    choice = response.choices[0].message
    content = getattr(choice, 'content', None) or getattr(choice, 'reasoning_content', '')

    if not content:
        raise ValueError("Groq returned an empty response.")
    
    cleaned = content.replace('"', '').replace("'", "").replace(".", "").strip()
    return cleaned


def sync_evaluate(target_word: str, user_words: list[str]) -> str:
    """Evaluate user inputs specifically aligned with witty conversation and banter mechanics."""
    words_formatted = ", ".join(f"'{w}'" for w in user_words)
    prompt = (
        f"You are an expert witty conversation and banter coach evaluating a Free Association Drill.\n"
        f"Target Concept: '{target_word}'\n"
        f"User's Lateral Associations: {words_formatted}\n\n"
        f"Rules for evaluation:\n"
        f"- Free association for banter relies on FAST lateral leaps, emotional connection, pop culture, metaphors, or playful teases—NOT literal definitions.\n\n"
        f"Structure your output cleanly:\n"
        f"1. **Accuracy**: Brief check on whether their associations make sense in a casual conversation.\n"
        f"2. **Creativity Score (X/10)**: Rate their lateral leap quality. Then list 3 **10/10 Conversational Leaps** (1-3 word punchy associations like pop culture links, emotional vibe, or humorous angles—NOT poetic fluff).\n"
        f"3. **Segue Tip**: 1 natural, snappy line using one of their words to bridge into casual conversation."
    )
    
    response = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_NAME,
        temperature=0.7,
        max_completion_tokens=700
    )
    
    choice = response.choices[0].message
    content = getattr(choice, 'content', None) or getattr(choice, 'reasoning_content', '')
    if not content:
        raise ValueError("Groq returned an empty evaluation.")
    return content.strip()


async def fetch_groq_word() -> str:
    """Fetches target topic safely."""
    word = await asyncio.to_thread(sync_fetch_word)
    return word.title()


async def evaluate_with_groq(target_word: str, user_words: list[str]) -> str:
    try:
        feedback = await asyncio.to_thread(sync_evaluate, target_word, user_words)
        return feedback
    except Exception as e:
        print(f"Groq Evaluation Error: {e}")
        return f"⚠️ API Error: {e}"


class AIWordAssociationModal(discord.ui.Modal):
    def __init__(self, target_word: str):
        super().__init__(title=f"AI Drill: {target_word[:20]}", timeout=900)
        self.target_word = target_word
        self.words_input = discord.ui.TextInput(
            label=f"3-5 associations for: {target_word}",
            placeholder="Separate with commas (e.g. Disney, neon, bucket list, frostbite)",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.words_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        raw_text = self.words_input.value
        user_words = [w.strip() for w in raw_text.replace("\n", ",").split(",") if w.strip()]
        
        if not user_words:
            await interaction.followup.send("Please provide at least one word!", ephemeral=True)
            return

        ai_evaluation = await evaluate_with_groq(self.target_word, user_words)

        # Enforce Discord field limit (1024 max length)
        if len(ai_evaluation) > 1000:
            ai_evaluation = ai_evaluation[:995] + "\n..."

        embed = discord.Embed(
            title=f"⚡ Groq AI Verdict: {self.target_word}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="🎯 Target Word", 
            value=f"**{self.target_word}**", 
            inline=True
        )
        embed.add_field(
            name="📝 Your Inputs", 
            value=", ".join(f"`{w}`" for w in user_words), 
            inline=True
        )
        embed.add_field(
            name="🤖 AI Judgment & Feedback", 
            value=ai_evaluation, 
            inline=False
        )
        embed.set_footer(text="Powered by Groq LPU | Fast Inference")

        await interaction.followup.send(embed=embed, ephemeral=True)


class OpenModalView(discord.ui.View):
    def __init__(self, target_word: str, owner_id: int):
        super().__init__(timeout=900)
        self.target_word = target_word
        self.owner_id = owner_id

    @discord.ui.button(label="📝 Start Practice Modal", style=discord.ButtonStyle.success)
    async def open_modal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This session isn't yours!", ephemeral=True)
            return
        await interaction.response.send_modal(AIWordAssociationModal(self.target_word))


class PracticeChoiceView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(label="🎲 Generate AI Word & Practice", style=discord.ButtonStyle.primary)
    async def mode_random_practice(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This session isn't yours!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
            target_word = await fetch_groq_word()
            view = OpenModalView(target_word, interaction.user.id)
            await interaction.followup.send(
                content=f"🎯 Groq AI generated your word: **{target_word}**!\nClick below to enter your associations:",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(content=f"⚠️ Failed to generate word from Groq AI: `{e}`", ephemeral=True)


class WordAssociationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="practice_association", description="Practice free association with real-time Groq AI scoring and evaluation.")
    async def practice_association(self, interaction: discord.Interaction):
        if not check_has_role(interaction):
            await interaction.response.send_message("🔒 Access Denied: You do not have the required role to run this training tool.", ephemeral=True)
            return

        view = PracticeChoiceView(interaction.user.id)
        embed = discord.Embed(
            title="🗣️ Groq-Powered Free Association Trainer",
            description=(
                "Click below to generate a real-time AI target word.\n"
                "Type your associations in the popup modal, and Groq will judge if you are **right or wrong**, rate your creativity, provide 10/10 conversational leaps, and give banter segues!"
            ),
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(WordAssociationCog(bot))