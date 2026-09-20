import sqlite3
import datetime
import zoneinfo

PKT = zoneinfo.ZoneInfo("Asia/Karachi")

def init_db():
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    
    # Template table per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS default_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task TEXT,
            priority INTEGER DEFAULT 1,
            UNIQUE(user_id, task)
        )
    """)
    
    # Active daily table per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    
    # Table to track streaks and historical data for /stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_streaks (
            user_id INTEGER PRIMARY KEY,
            current_streak INTEGER DEFAULT 0,
            last_completed_date TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completion_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            task TEXT,
            completed INTEGER
        )
    """)

    # Reminders table (added to fix the missing column crash)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            message TEXT,
            remind_datetime TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    
    # Auto-migration: Safely add 'remind_datetime' column if upgrading from an older DB version
    try:
        cursor.execute("ALTER TABLE reminders ADD COLUMN remind_datetime TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists, safe to ignore

    conn.commit()
    conn.close()

def seed_user_defaults_if_empty(user_id):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM default_tasks WHERE user_id = ?", (user_id,))
    if cursor.fetchone()[0] == 0:
        initial_tasks = [
            (user_id, "Homework", 1),
            (user_id, "Ru Course RUDN", 2),
            (user_id, "Data Science Course", 3),
            (user_id, "Words Association", 4),
            (user_id, "Book (Witty Banter) CH#11", 5),
            (user_id, "Chess with Coach", 6),
            (user_id, "Rubik's Cube Solve", 7)
        ]
        cursor.executemany("INSERT INTO default_tasks (user_id, task, priority) VALUES (?, ?, ?)", initial_tasks)
        conn.commit()
    conn.close()

def reset_daily_list(user_id=None):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    if user_id:
        cursor.execute("DELETE FROM daily_todos WHERE user_id = ?", (user_id,))
        cursor.execute("""
            INSERT INTO daily_todos (user_id, task) 
            SELECT user_id, task FROM default_tasks WHERE user_id = ? ORDER BY priority ASC
        """, (user_id,))
    else:
        cursor.execute("DELETE FROM daily_todos")
        cursor.execute("""
            INSERT INTO daily_todos (user_id, task) 
            SELECT user_id, task FROM default_tasks ORDER BY priority ASC
        """)
    conn.commit()
    conn.close()

def get_daily_tasks(user_id):
    seed_user_defaults_if_empty(user_id)
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, task, status FROM daily_todos WHERE user_id = ?", (user_id,))
    tasks = cursor.fetchall()
    
    if not tasks:
        conn.close()
        reset_daily_list(user_id)
        conn = sqlite3.connect("assistant.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, task, status FROM daily_todos WHERE user_id = ?", (user_id,))
        tasks = cursor.fetchall()

    conn.close()
    return tasks

def toggle_daily_task(task_id, user_id):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT task, status FROM daily_todos WHERE id = ? AND user_id = ?", (task_id, user_id))
    res = cursor.fetchone()
    if res:
        task_name, current_status = res
        new_status = 'completed' if current_status == 'pending' else 'pending'
        cursor.execute("UPDATE daily_todos SET status = ? WHERE id = ? AND user_id = ?", (new_status, task_id, user_id))
        conn.commit()
        
        # Log to history for analytics
        today_str = datetime.datetime.now(PKT).strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO completion_history (user_id, date, task, completed) VALUES (?, ?, ?, ?)",
                       (user_id, today_str, task_name, 1 if new_status == 'completed' else 0))
        conn.commit()

    check_and_update_streak(user_id)
    conn.close()

def check_and_update_streak(user_id):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM daily_todos WHERE user_id = ?", (user_id,))
    statuses = [r[0] for r in cursor.fetchall()]
    
    today_str = datetime.datetime.now(PKT).strftime("%Y-%m-%d")
    yesterday_str = (datetime.datetime.now(PKT) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    cursor.execute("SELECT current_streak, last_completed_date FROM user_streaks WHERE user_id = ?", (user_id,))
    streak_row = cursor.fetchone()
    
    current_streak = streak_row[0] if streak_row else 0
    last_date = streak_row[1] if streak_row else None

    if statuses and all(status == 'completed' for status in statuses):
        if last_date != today_str:
            if last_date == yesterday_str:
                current_streak += 1
            else:
                current_streak = 1
            
            cursor.execute("""
                INSERT INTO user_streaks (user_id, current_streak, last_completed_date)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    current_streak = excluded.current_streak,
                    last_completed_date = excluded.last_completed_date
            """, (user_id, current_streak, today_str))
            conn.commit()
    conn.close()

def get_streak(user_id):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT current_streak FROM user_streaks WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 0

def get_user_stats(user_id):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM completion_history WHERE user_id = ? AND completed = 1", (user_id,))
    total_completed = cursor.fetchone()[0]
    
    cursor.execute("SELECT task, COUNT(*) as cnt FROM completion_history WHERE user_id = ? AND completed = 1 GROUP BY task ORDER BY cnt DESC LIMIT 1", (user_id,))
    best_task_row = cursor.fetchone()
    best_task = best_task_row[0] if best_task_row else "None yet"

    conn.close()
    return total_completed, best_task

def add_default_task(user_id, task):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO default_tasks (user_id, task) VALUES (?, ?)", (user_id, task))
    cursor.execute("INSERT INTO daily_todos (user_id, task) VALUES (?, ?)", (user_id, task))
    conn.commit()
    conn.close()

def remove_default_task(user_id, task):
    conn = sqlite3.connect("assistant.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM default_tasks WHERE user_id = ? AND task = ?", (user_id, task))
    cursor.execute("DELETE FROM daily_todos WHERE user_id = ? AND task = ?", (user_id, task))
    conn.commit()
    conn.close()