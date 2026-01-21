import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("v4_data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_v4_db():
    conn = get_conn()
    cur = conn.cursor()

    # เก็บค่าล่าสุดของ Member (แบบรวมชุดเดียว)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_last_input (
        user_id TEXT PRIMARY KEY,
        data TEXT,
        updated_at TEXT
    )
    """)

    # เมนูที่แอดมินสร้างเอง
    cur.execute("""
    CREATE TABLE IF NOT EXISTS menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        link TEXT,
        visible INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0
    )
    """)

    # เอกสารดาวน์โหลด
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        file_url TEXT,
        created_at TEXT
    )
    """)

    # Feedback
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rating INTEGER,
        reason TEXT,
        comment TEXT,
        created_at TEXT
    )
    """)

    # Visitor Counter
    cur.execute("""
    CREATE TABLE IF NOT EXISTS visitor_counter (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        count INTEGER
    )
    """)

    # ใส่ค่าเริ่มต้น visitor = 0
    cur.execute("""
    INSERT OR IGNORE INTO visitor_counter (id, count)
    VALUES (1, 0)
    """)

    conn.commit()
    conn.close()

def increment_visitor():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE visitor_counter SET count = count + 1 WHERE id = 1")
    conn.commit()
    conn.close()

def get_visitor_count():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count FROM visitor_counter WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["count"] if row else 0
