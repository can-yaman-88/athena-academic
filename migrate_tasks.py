import asyncio
import sqlite3
import os

DB_PATH = "/app/data/athena.db"

CREATE_NEW_TASKS = """
CREATE TABLE IF NOT EXISTS tasks_new (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    deadline        TEXT,
    discipline      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    estimated_hours REAL,
    category        TEXT NOT NULL DEFAULT 'daily',
    subtype         TEXT,
    parent_id       TEXT,
    progress        INTEGER NOT NULL DEFAULT 0,
    materials       TEXT NOT NULL DEFAULT '[]',
    notes           TEXT NOT NULL DEFAULT '[]',
    tags            TEXT NOT NULL DEFAULT '[]',
    is_spaced_repetition INTEGER NOT NULL DEFAULT 0,
    streak          INTEGER NOT NULL DEFAULT 0,
    ease_factor     REAL NOT NULL DEFAULT 2.5,
    interval_days   INTEGER NOT NULL DEFAULT 0,
    original_task_id TEXT
);
"""

async def migrate():
    if not os.path.exists(DB_PATH):
        print("DB does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create new table
    cursor.execute(CREATE_NEW_TASKS)
    
    # 2. Copy data
    # get columns from old tasks to be safe
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    cols_str = ", ".join(columns)
    
    try:
        cursor.execute(f"INSERT INTO tasks_new ({cols_str}) SELECT {cols_str} FROM tasks")
        print(f"Copied data into tasks_new.")
        
        # 3. Drop old table
        cursor.execute("DROP TABLE tasks")
        
        # 4. Rename new table
        cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")
        
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
