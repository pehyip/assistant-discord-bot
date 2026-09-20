# Productivity Assistant Discord Bot

A Discord bot written in Python with discord.py. It tracks a daily routine, sends reminders, and includes an AI practice tool powered by the Groq API. Data is stored in a local SQLite database.

## Features

**Daily routine tracker** (`cogs/to_do.py`)
- `/today` shows a personal dashboard with one button per task; press a button to mark it done.
- Add or remove tasks from the dashboard, or force a reset.
- `/stats` shows your current streak, total tasks completed and most completed task.
- The list resets automatically at midnight (Pakistan time), and the bot sends an evening nudge at 9 PM for unfinished tasks.

**Reminders** (`cogs/reminders.py`)
- `/add_reminder` sets a reminder for a date (`YYYY-MM-DD`) and an optional time.
- `/reminders` lists your reminders with delete buttons.
- A background task checks every minute. When a reminder is due, the bot posts a message with **Mark as Done**, **Remind Me Later** (snooze for 15 minutes) and **Delete** buttons.

**AI word-association trainer** (`cogs/word_association.py`)
- `/practice_association` (restricted to one role) asks the Groq API for a random everyday topic. You type your associations in a pop-up form, and the AI scores them and gives feedback.
- API calls run in a separate thread so the bot stays responsive.

## Tech stack

Python 3, discord.py (slash commands, buttons, modals, background tasks), SQLite, Groq API, python-dotenv.

## Setup

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications) and copy its token.
2. Get a free API key from the [Groq console](https://console.groq.com).
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a file named `.env` in the project folder with your two keys (see `.env.example`):
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   GROQ_API_KEY=your_groq_api_key_here
   ```
5. Run the bot from the project folder. The database file `assistant.db` is created there automatically:
   ```bash
   python bot.py
   ```

## Notes

- Channel and role IDs in `cogs/reminders.py` and `cogs/word_association.py` are set for my own server. Change them for yours.
- Never commit your `.env` file or the `.db` database.

## Project structure

```
assistant-discord-bot/
  bot.py            entry point, loads the cogs
  database.py       SQLite tables and queries
  cogs/
    to_do.py
    reminders.py
    word_association.py
  requirements.txt
  .env.example
```

Author: Muhammad Farhan
