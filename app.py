import os
import sqlite3
import random
import json
import math
from datetime import datetime
from functools import wraps

from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash

# ===== V4 Database =====
from v4_db import init_v4_db, increment_visitor, get_visitor_count

APP_NAME = "ENERGY LIFE V3"
DATABASE = os.environ.get("ENERGY_LIFE_DB", "energy_life.db")
SECRET_KEY = os.environ.get("ENERGY_LIFE_SECRET", None) or os.urandom(24).hex()

# ===== โหมดใช้งานจริง: ปิดระบบเกมก่อน =====
ENABLE_GAME = False  # <- ถ้าจะเปิดเกมทีหลัง เปลี่ยนเป็น True

# init v4 database on app start
init_v4_db()


def make_token(n=20):
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(alphabet) for _ in range(n))


DEFAULT_USER_PREFS = {
    "audio": {"bgm": True, "sfx": True, "pet": True, "tts": False, "bgm_volume": 0.6, "sfx_volume": 0.8, "pet_volume": 0.7, "tts_volume": 0.8},
    "view": {"mode": "cutaway", "rotate": True, "animations": True, "low_power": False},
    "privacy": {"share_house": True, "show_on_leaderboard": True},
    "language": {"ui": "th", "voice": "th"},
}


def current_week_id(dt=None):
    dt = dt or datetime.utcnow()
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


DEFAULT_TARIFF = {
    "non_tou_rate": 4.20,  # THB/kWh placeholder
    "tou_on_rate": 5.50,
    "tou_off_rate": 3.30,
    "on_peak_start": 9,   # 09:00
    "on_peak_end": 22     # 22:00 end exclusive
}


# =========================
# APPLIANCES CATALOG
# =========================
APPLIANCES_CATALOG = [
    {"key": "ac", "name": "แอร์", "icon": "❄️", "type": "ac",
     "defaults": {"enabled": True, "btu": 12000, "set_temp": 26, "hours": 6, "inverter": True, "start_hour": 20, "end_hour": 2}},

    {"key": "lights", "name": "ไฟ", "icon": "💡", "type": "lights",
     "defaults": {"enabled": True, "mode": "LED", "watts": 30, "hours": 5}},

    {"key": "tv", "name": "ทีวี", "icon": "📺", "type": "generic",
     "defaults": {"enabled": True, "watts": 120, "hours": 3}},

    {"key": "fridge", "name": "ตู้เย็น", "icon": "🧊", "type": "fridge",
     "defaults": {"enabled": True, "kwh_per_day": 1.2}},

    {"key": "water_heater", "name": "เครื่องทำน้ำอุ่น", "icon": "🚿", "type": "generic",
     "defaults": {"enabled": False, "watts": 3500, "hours": 0.3}},

    {"key": "washer", "name": "เครื่องซักผ้า", "icon": "🧺", "type": "generic",
     "defaults": {"enabled": False, "watts": 500, "hours": 0.5}},

    {"key": "microwave", "name": "ไมโครเวฟ", "icon": "🍳", "type": "generic",
     "defaults": {"enabled": False, "watts": 1200, "hours": 0.1}},

    {"key": "computer", "name": "คอมพิวเตอร์", "icon": "💻", "type": "generic",
     "defaults": {"enabled": False, "watts": 200, "hours": 2}},

    {"key": "standby", "name": "ไฟสแตนด์บาย", "icon": "🔌", "type": "standby",
     "defaults": {"enabled": True, "watts": 20, "hours": 24}},

    # ✅ NEW: EV Charger สำหรับห้อง Parking (โหมดแยกห้อง)
    # ใช้สูตร: kWh/ครั้ง = batt_kwh * ((soc_to - soc_from)/100)
    # kWh/วัน = (kWh/ครั้ง * charges_per_week) / 7
    {"key": "ev_charger", "name": "EV Charger", "icon": "🔋🚗", "type": "ev_charger",
     "defaults": {
         "enabled": True,
         "battery_kwh": 60,
         "charger_kw": 7.4,
         "soc_from": 30,
         "soc_to": 80,
         "efficiency": 0.90,         # 0.50–1.00
         "start_hour": 22,
         # ไม่ต้องใส่ end_hour เพราะระบบคำนวณจากพลังงานที่ต้องชาร์จ
         "charges_per_week": 3        # ✅ จำนวนครั้งชาร์จต่อสัปดาห์ (สมจริงกว่าชาร์จทุกวัน)
     }},
]

# ยังเก็บไว้เผื่อเปิดเกมทีหลัง แต่โหมดใช้งานจริงจะปิด API shop/buy
SHOP_ITEMS = [
    {"key": "sofa", "name": "โซฟา Eco", "icon": "🛋️", "cost": 120, "category": "furniture"},
    {"key": "plant", "name": "ต้นไม้เขียว", "icon": "🌿", "cost": 80, "category": "furniture"},
    {"key": "painting", "name": "รูปพลังงาน", "icon": "🖼️", "cost": 60, "category": "furniture"},
    {"key": "bed", "name": "เตียงนุ่ม", "icon": "🛏️", "cost": 150, "category": "furniture"},
    {"key": "eco_hat", "name": "หมวกโซลาร์", "icon": "🧢", "cost": 90, "category": "avatar"},
    {"key": "eco_shirt", "name": "เสื้อ ECO HERO", "icon": "👕", "cost": 110, "category": "avatar"},
    {"key": "door_stopper", "name": "ที่ปิดช่องประตู", "icon": "🚪🧊", "cost": 120, "category": "energy"},
    {"key": "uv_film", "name": "ฟิล์มกัน UV", "icon": "🪟☀️", "cost": 250, "category": "energy"},
    {"key": "thermal_curtain", "name": "ม่านกันความร้อน", "icon": "🧵🪟", "cost": 200, "category": "energy"},
    {"key": "led_pack", "name": "ชุดหลอด LED", "icon": "💡", "cost": 100, "category": "energy"},
    {"key": "smart_strip", "name": "ปลั๊กพ่วงอัจฉริยะ", "icon": "🔌✨", "cost": 220, "category": "energy"},
    {"key": "ac_clean", "name": "ล้างแอร์/ล้างฟิลเตอร์", "icon": "🧼❄️", "cost": 150, "category": "energy"},
    {"key": "pet_food_basic", "name": "อาหารสัตว์ (Basic)", "icon": "🥣", "cost": 60, "category": "pet"},
    {"key": "pet_food_premium", "name": "อาหารสัตว์ (Premium)", "icon": "🍖", "cost": 140, "category": "pet"},
    {"key": "name_change_ticket", "name": "ตั๋วเปลี่ยนชื่อ", "icon": "🎟️", "cost": 180, "category": "profile"},
]

HOUSE_LEVELS = [
    {"level": 1, "name": "บ้านเริ่มต้น", "need_points": 0, "badge": "🏚️"},
    {"level": 2, "name": "บ้านพออยู่", "need_points": 200, "badge": "🏠"},
    {"level": 3, "name": "บ้านประหยัด", "need_points": 450, "badge": "🏡"},
    {"level": 4, "name": "บ้านใส่ใจพลังงาน", "need_points": 750, "badge": "🏘️"},
    {"level": 5, "name": "บ้าน Eco", "need_points": 1100, "badge": "🌱"},
    {"level": 6, "name": "Smart Home", "need_points": 1500, "badge": "🤖"},
    {"level": 7, "name": "Green Home", "need_points": 1950, "badge": "🌳"},
    {"level": 8, "name": "Advanced Energy", "need_points": 2450, "badge": "⚡"},
    {"level": 9, "name": "EV Lifestyle", "need_points": 3000, "badge": "🚗"},
    {"level": 10, "name": "Energy Master", "need_points": 3600, "badge": "👑"},
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db():
    db = get_db()
    db.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_state (
        user_id INTEGER PRIMARY KEY,
        profile_json TEXT NOT NULL,
        state_json TEXT NOT NULL,
        points INTEGER NOT NULL DEFAULT 0,
        house_level INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS energy_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        kwh_total REAL NOT NULL,
        cost_thb REAL NOT NULL,
        kwh_on REAL NOT NULL,
        kwh_off REAL NOT NULL,
        kwh_solar_used REAL NOT NULL,
        kwh_ev REAL NOT NULL,
        notes_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        cost_points INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, item_key),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        pet_type TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'egg',
        hunger INTEGER NOT NULL DEFAULT 50,
        happiness INTEGER NOT NULL DEFAULT 50,
        level INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS mission_progress (
        user_id INTEGER NOT NULL,
        mission_id TEXT NOT NULL,
        week_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        progress INTEGER NOT NULL DEFAULT 0,
        target INTEGER NOT NULL DEFAULT 1,
        claimed_at TEXT,
        PRIMARY KEY (user_id, mission_id, week_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS weekly_scores (
        user_id INTEGER NOT NULL,
        week_id TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, week_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS user_prefs (
        user_id INTEGER PRIMARY KEY,
        prefs_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # seed tariff settings
    for k, v in DEFAULT_TARIFF.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
    db.commit()
    ensure_user_schema()


def ensure_user_schema():
    db = get_db()
    cols = [r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    if "display_name" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    if "share_token" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN share_token TEXT")

    db.execute("UPDATE users SET display_name = COALESCE(display_name, username)")
    db.execute("UPDATE users SET share_token = COALESCE(share_token, '')")

    rows = db.execute("SELECT id FROM users WHERE share_token = '' OR share_token IS NULL").fetchall()
    for r in rows:
        db.execute("UPDATE users SET share_token=? WHERE id=?", (make_token(24), r["id"]))
    db.commit()


def ensure_user_prefs(user_id: int):
    db = get_db()
    row = db.execute("SELECT prefs_json FROM user_prefs WHERE user_id=?", (user_id,)).fetchone()
    if row:
        try:
            return json.loads(row["prefs_json"] or "{}")
        except Exception:
            return DEFAULT_USER_PREFS
    prefs = DEFAULT_USER_PREFS
    db.execute("INSERT OR REPLACE INTO user_prefs(user_id,prefs_json,updated_at) VALUES(?,?,?)",
               (user_id, json.dumps(prefs), datetime.utcnow().isoformat()))
    db.commit()
    return prefs


def load_setting(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    val = row["value"]
    try:
        if "." in str(val):
            return float(val)
        return int(val)
    except Exception:
        return val


def save_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value))
    )
    db.commit()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or user["role"] not in roles:
                flash("ไม่มีสิทธิ์เข้าถึงหน้านี้", "error")
                return redirect(url_for("home"))
            return f(*args, **kwargs)
        return wrapper
    return deco


def default_profile():
    return {"display_name": "ผู้เล่น", "player_type": "family", "house_type": "condo", "house_size": "medium", "residents": 3}


# =========================
# ROOMS TEMPLATES
# =========================
ROOM_TEMPLATES = {
    "bedroom": ["ac", "lights"],
    "living":  ["ac", "lights", "tv"],
    "kitchen": ["lights", "microwave", "fridge"],  # ✅ ใส่ตู้เย็นในครัวตามที่ถาม
    "bathroom": ["water_heater", "lights"],
    "work":    ["lights", "computer"],
    "parking": ["lights", "ev_charger"],           # ✅ Parking มี EV Charger
}


def build_rooms_from_layout(layout: dict):
    rooms = {}
    rooms_cfg = (layout.get("rooms") or {})

    for room_type, count in rooms_cfg.items():
        count = int(count or 0)
        for i in range(1, count + 1):
            rid = f"{room_type}_{i}"
            rooms[rid] = {
                "type": room_type,
                "label": f"{room_type.capitalize()} {i}",
                "appliances": {k: {} for k in ROOM_TEMPLATES.get(room_type, [])}
            }
    return rooms


def default_state():
    appliances = {}
    for a in APPLIANCES_CATALOG:
        appliances[a["key"]] = dict(a["defaults"])

    return {
        "tariff_mode": "non_tou",
        "solar_kw": 0,
        "solar_mode": "manual",

        # (โหมดรวมทั้งบ้านเดิม ยังเก็บไว้เพื่อ backward compatible)
        "ev_enabled": False,
        "ev": {
            "battery_kwh": 60,
            "charger_kw": 7.4,
            "soc_from": 30,
            "soc_to": 80,
            "charge_start_hour": 22,
            "charge_end_hour": 6
        },

        # อุปกรณ์แบบ “รวมทั้งบ้าน” (ยังเก็บไว้)
        "appliances": appliances,

        # ===== PHASE 2: บ้าน -> ห้อง -> อุปกรณ์ =====
        "house_layout": {
            "enabled": False,
            "house_type": "condo",
            "rooms": {
                "bedroom": 1,
                "bathroom": 1,
                "living": 1,
                "kitchen": 1,
                "work": 0,
                "parking": 0,     # ✅ NEW
            }
        },

        "rooms": {},

        "inventory": {"furniture": [], "avatar": []},
        "day_counter": 1
    }


def get_or_create_user_state(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM user_state WHERE user_id=?", (user_id,)).fetchone()
    if row:
        return {
            "profile": json.loads(row["profile_json"]),
            "state": json.loads(row["state_json"]),
            "points": row["points"],
            "house_level": row["house_level"]
        }
    prof = default_profile()
    st = default_state()
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO user_state(user_id,profile_json,state_json,points,house_level,updated_at) VALUES(?,?,?,?,?,?)",
        (user_id, json.dumps(prof), json.dumps(st), 0, 1, now)
    )
    db.commit()
    return {"profile": prof, "state": st, "points": 0, "house_level": 1}


def save_user_state(user_id, profile, state, points, house_level):
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("""
        INSERT INTO user_state(user_id,profile_json,state_json,points,house_level,updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            profile_json=excluded.profile_json,
            state_json=excluded.state_json,
            points=excluded.points,
            house_level=excluded.house_level,
            updated_at=excluded.updated_at
    """, (user_id, json.dumps(profile), json.dumps(state), int(points), int(house_level), now))
    db.commit()


def calc_ac_kwh(btu, set_temp, hours, inverter=True):
    if hours <= 0:
        return 0.0
    base_kw = (btu / 12000.0) * (1.0 if inverter else 1.15)
    if set_temp < 26:
        mult = 1.0 + (26 - set_temp) * 0.06
    elif set_temp > 26:
        mult = max(0.70, 1.0 - (set_temp - 26) * 0.03)
    else:
        mult = 1.0
    return base_kw * mult * hours


def calc_generic_kwh(watts, hours):
    if hours <= 0 or watts <= 0:
        return 0.0
    return (watts / 1000.0) * hours


def normalize_hour(h):
    try:
        h = int(float(h))
    except Exception:
        h = 0
    return max(0, min(23, h))


def window_hours(start_h, end_h):
    s = normalize_hour(start_h)
    e = normalize_hour(end_h)
    if s == e:
        return []
    if s < e:
        return list(range(s, e))
    return list(range(s, 24)) + list(range(0, e))


def split_kwh_by_tou(kwh, start_h, end_h, on_start, on_end):
    hrs = window_hours(start_h, end_h)
    if not hrs:
        return 0.0, 0.0
    per = kwh / len(hrs)
    on_set = set(window_hours(on_start, on_end))
    kwh_on = sum(per for h in hrs if h in on_set)
    kwh_off = kwh - kwh_on
    return kwh_on, kwh_off


def _catalog_by_key():
    return {a["key"]: a for a in APPLIANCES_CATALOG}


def _ev_kwh_per_charge(batt_kwh: float, soc_from: float, soc_to: float) -> float:
    soc_from = max(0, min(100, float(soc_from)))
    soc_to = max(0, min(100, float(soc_to)))
    if soc_to <= soc_from:
        return 0.0
    return float(batt_kwh) * ((soc_to - soc_from) / 100.0)


def _ev_daily_from_weekly(kwh_per_charge: float, charges_per_week: float) -> float:
    charges_per_week = max(0.0, float(charges_per_week))
    return (kwh_per_charge * charges_per_week) / 7.0


def compute_daily_energy(profile, state):
    """
    ✅ เวอร์ชันนี้: ถ้ามี rooms และ house_layout.enabled => คิดรวมทั้ง "ทุกห้อง" เป็นภาพรวม
    - EV จะคิดจากห้อง parking ที่มี ev_charger เป็นหลัก (สมจริงกว่า)
    - ถ้าไม่มี rooms จะ fallback ไปคำนวณแบบรวมทั้งบ้าน (state.appliances) เหมือนเดิม
    """
    tariff_mode = state.get("tariff_mode", "non_tou")
    solar_kw = float(state.get("solar_kw", 0) or 0)

    size_factor = {"small": 0.9, "medium": 1.0, "large": 1.15}.get(profile.get("house_size", "medium"), 1.0)
    residents = max(1, int(profile.get("residents", 3)))
    resident_factor = 0.85 + min(0.6, (residents - 1) * 0.08)

    warnings = []
    insights = []
    points = 0

    # -----------------------------------
    # 1) เลือกแหล่งข้อมูลอุปกรณ์
    # -----------------------------------
    use_rooms = bool((state.get("house_layout") or {}).get("enabled")) and bool(state.get("rooms"))
    catalog = _catalog_by_key()

    # รวม breakdown เป็น key เดิม ๆ (เพื่อแสดงผลหน้า home ยังอ่านง่าย)
    kwh_breakdown = {}
    kwh_ev = 0.0

    def add_kwh(key, kwh):
        kwh_breakdown[key] = kwh_breakdown.get(key, 0.0) + float(kwh)

    # -----------------------------------
    # 2) คำนวณจากห้อง (ถ้าเปิดโหมดแยกห้อง)
    # -----------------------------------
    if use_rooms:
        rooms = state.get("rooms") or {}
        for rid, room in rooms.items():
            appl = (room.get("appliances") or {})
            for key, cfg in appl.items():
                c = catalog.get(key)

                # merge defaults กัน config บางตัวขาด
                if c:
                    merged = dict(c.get("defaults") or {})
                    if isinstance(cfg, dict):
                        merged.update(cfg)
                    cfg = merged

                if not isinstance(cfg, dict) or not cfg.get("enabled", False):
                    continue

                t = (c.get("type") if c else "generic")

                if key == "ac" or t == "ac":
                    btu = float(cfg.get("btu", 12000))
                    set_temp = float(cfg.get("set_temp", 26))
                    hours = float(cfg.get("hours", 6))
                    inverter = bool(cfg.get("inverter", True))
                    kwh = calc_ac_kwh(btu, set_temp, hours, inverter=inverter)
                    add_kwh("ac", kwh)

                    if set_temp < 25:
                        warnings.append(f"แอร์ตั้ง {int(set_temp)}°C ใช้ไฟสูง แนะนำ 26°C เพื่อประหยัด")
                    else:
                        points += 5

                elif key == "fridge" or t == "fridge":
                    kwh = float(cfg.get("kwh_per_day", 1.2))
                    add_kwh("fridge", kwh)

                elif key == "lights" or t == "lights":
                    watts = float(cfg.get("watts", 30))
                    hours = float(cfg.get("hours", 5))
                    kwh = calc_generic_kwh(watts, hours)
                    add_kwh("lights", kwh)
                    if str(cfg.get("mode", "LED")).upper() == "LED":
                        points += 2

                elif key == "ev_charger" or t == "ev_charger":
                    # ✅ EV แบบรายห้อง (Parking)
                    batt = float(cfg.get("battery_kwh", state.get("ev", {}).get("battery_kwh", 60)))
                    charger_kw = float(cfg.get("charger_kw", state.get("ev", {}).get("charger_kw", 7.4)))
                    soc_from = float(cfg.get("soc_from", state.get("ev", {}).get("soc_from", 30)))
                    soc_to = float(cfg.get("soc_to", state.get("ev", {}).get("soc_to", 80)))
                    eff = float(cfg.get("efficiency", 0.90))
                    eff = max(0.50, min(1.00, eff))
                    charges_per_week = float(cfg.get("charges_per_week", 3))

                    kwh_per_charge = _ev_kwh_per_charge(batt, soc_from, soc_to)
                    # เผื่อประสิทธิภาพ: ไฟจากปลั๊กจะมากกว่าไฟเข้าแบต => divide by efficiency
                    kwh_from_grid_per_charge = (kwh_per_charge / max(0.1, eff)) if kwh_per_charge > 0 else 0.0
                    kwh_ev_daily = _ev_daily_from_weekly(kwh_from_grid_per_charge, charges_per_week)

                    # บวกเข้า total และ breakdown
                    kwh_ev += kwh_ev_daily
                    add_kwh("ev_charger", kwh_ev_daily)

                    # insight
                    if kwh_per_charge > 0:
                        insights.append(
                            f"EV: ชาร์จ {int(soc_from)}→{int(soc_to)}% ~{kwh_per_charge:.1f} kWh/ครั้ง "
                            f"({charges_per_week:.0f} ครั้ง/สัปดาห์ ≈ {kwh_ev_daily:.1f} kWh/วัน)"
                        )

                else:
                    watts = float(cfg.get("watts", 0))
                    hours = float(cfg.get("hours", 0))
                    add_kwh(key, calc_generic_kwh(watts, hours))

        # รวมทั้งหมด
        kwh_total = sum(kwh_breakdown.values()) * size_factor * resident_factor

    # -----------------------------------
    # 3) fallback คำนวณแบบรวมทั้งบ้านเดิม
    # -----------------------------------
    else:
        appliances = state.get("appliances", {})
        for key, cfg in appliances.items():
            if not cfg.get("enabled", False):
                kwh_breakdown[key] = 0.0
                continue

            if key == "ac":
                btu = float(cfg.get("btu", 12000))
                set_temp = float(cfg.get("set_temp", 26))
                hours = float(cfg.get("hours", 6))
                inverter = bool(cfg.get("inverter", True))
                kwh = calc_ac_kwh(btu, set_temp, hours, inverter=inverter)
                kwh_breakdown[key] = kwh

            elif key == "fridge":
                kwh_breakdown[key] = float(cfg.get("kwh_per_day", 1.2))

            elif key == "lights":
                watts = float(cfg.get("watts", 30))
                hours = float(cfg.get("hours", 5))
                kwh_breakdown[key] = calc_generic_kwh(watts, hours)

            else:
                watts = float(cfg.get("watts", 0))
                hours = float(cfg.get("hours", 0))
                kwh_breakdown[key] = calc_generic_kwh(watts, hours)

        kwh_total = sum(kwh_breakdown.values()) * size_factor * resident_factor

        # EV รวมทั้งบ้านเดิม
        kwh_ev = 0.0
        if state.get("ev_enabled"):
            ev = state.get("ev", {})
            batt = float(ev.get("battery_kwh", 60))
            soc_from = float(ev.get("soc_from", 30))
            soc_to = float(ev.get("soc_to", 80))
            kwh_ev = _ev_kwh_per_charge(batt, soc_from, soc_to)
            kwh_total += kwh_ev

    # -----------------------------------
    # 4) Solar
    # -----------------------------------
    # Solar production heuristic
    kwh_solar_prod = solar_kw * 4.0
    kwh_solar_used = min(kwh_total, kwh_solar_prod * 0.75)
    kwh_net = max(0.0, kwh_total - kwh_solar_used)

    # -----------------------------------
    # 5) TOU split (ใช้แบบเดิม: ถ้าเป็น tou จะกระจาย on/off)
    # -----------------------------------
    kwh_on = 0.0
    kwh_off = 0.0
    on_start = int(load_setting("on_peak_start", 9))
    on_end = int(load_setting("on_peak_end", 22))

    if tariff_mode == "tou":
        # แยก AC แบบรวม (ถ้ามี)
        if kwh_breakdown.get("ac", 0.0) > 0:
            # ใช้ช่วงเวลาจาก “ค่าแอร์ของระบบรวม” ถ้าไม่มีก็เดาเป็น 20->2
            ac_start = 20
            ac_end = 2
            if use_rooms:
                # ถ้าใช้ rooms เราไม่รู้ชั่วโมงรวมแบบเป๊ะ ๆ จึงใช้ค่า default ช่วงกลางคืน
                pass
            else:
                ac_cfg = (state.get("appliances") or {}).get("ac", {})
                ac_start = ac_cfg.get("start_hour", 20)
                ac_end = ac_cfg.get("end_hour", 2)

            ac_kwh = kwh_breakdown.get("ac", 0.0) * size_factor * resident_factor
            ac_on, ac_off = split_kwh_by_tou(ac_kwh, ac_start, ac_end, on_start, on_end)
            kwh_on += ac_on
            kwh_off += ac_off

        # EV: ถ้ามี ev_charger breakdown ให้เอาเวลาจาก config ห้อง parking (start_hour)
        if kwh_breakdown.get("ev_charger", 0.0) > 0 and use_rooms:
            # หา start_hour จาก parking ตัวแรกที่มี ev_charger
            rooms = state.get("rooms") or {}
            start_hour = 22
            charger_kw = 7.4
            eff = 0.9
            # เอา kWh/วันของ EV
            ev_kwh_daily = kwh_breakdown.get("ev_charger", 0.0) * size_factor * resident_factor

            for _, room in rooms.items():
                if room.get("type") == "parking":
                    ec = (room.get("appliances") or {}).get("ev_charger")
                    if isinstance(ec, dict) and ec.get("enabled"):
                        start_hour = ec.get("start_hour", 22)
                        charger_kw = float(ec.get("charger_kw", 7.4))
                        eff = float(ec.get("efficiency", 0.9))
                        eff = max(0.50, min(1.00, eff))
                        break

            # เวลาในการชาร์จ (โดยประมาณ): ชั่วโมง = kWh/(kW*eff)
            needed_hours = max(0.0, ev_kwh_daily / max(0.1, charger_kw * eff))
            start = normalize_hour(start_hour)
            end = normalize_hour((start + int(math.ceil(needed_hours))) % 24) if needed_hours > 0 else start

            ev_on, ev_off = split_kwh_by_tou(ev_kwh_daily, start, end, on_start, on_end)
            kwh_on += ev_on
            kwh_off += ev_off

            if start in set(window_hours(on_start, on_end)):
                warnings.append("คุณเริ่มชาร์จ EV ช่วง On-Peak ค่าไฟแพง แนะนำเริ่มหลัง Off-Peak")
            else:
                points += 10

        elif (not use_rooms) and state.get("ev_enabled") and kwh_ev > 0:
            ev = state.get("ev", {})
            charger_kw = float(ev.get("charger_kw", 7.4))
            needed_hours = max(0.0, kwh_ev / max(0.1, charger_kw))
            start = normalize_hour(ev.get("charge_start_hour", 22))
            end = normalize_hour((start + int(math.ceil(needed_hours))) % 24) if needed_hours > 0 else start
            ev_on, ev_off = split_kwh_by_tou(kwh_ev, start, end, on_start, on_end)
            kwh_on += ev_on
            kwh_off += ev_off

        # others
        other_kwh = (kwh_net - (kwh_on + kwh_off))
        if other_kwh < 0:
            other_kwh = 0.0
        house_type = profile.get("house_type", "condo")
        base_on = 0.65 if house_type == "condo" else 0.58
        kwh_on += other_kwh * base_on
        kwh_off += other_kwh * (1.0 - base_on)

    else:
        kwh_off = kwh_net
        kwh_on = 0.0

    # -----------------------------------
    # 6) Cost
    # -----------------------------------
    if tariff_mode == "tou":
        on_rate = float(load_setting("tou_on_rate", 5.5))
        off_rate = float(load_setting("tou_off_rate", 3.3))
        cost_thb = kwh_on * on_rate + kwh_off * off_rate
    else:
        rate = float(load_setting("non_tou_rate", 4.2))
        cost_thb = kwh_off * rate

    # points baseline (กันโล่ง)
    baseline = 14.0 * size_factor * resident_factor
    if kwh_net < baseline:
        points += int((baseline - kwh_net) * 2)
        insights.append("ใช้ไฟต่ำกว่าเกณฑ์พื้นฐานวันนี้ ได้คะแนนเพิ่ม")

    # solar advisor (เดิม)
    daytime_frac = 0.45
    if profile.get("player_type") == "adult":
        daytime_frac = 0.42
    if profile.get("player_type") == "kid":
        daytime_frac = 0.48

    daytime_kwh = kwh_total * daytime_frac
    solar_reco_kw = int(round(daytime_kwh / 3.0))
    solar_reco_kw = max(0, min(10, solar_reco_kw))

    solar_mode = state.get("solar_mode", "manual")
    if solar_mode == "advisor":
        insights.append(f"Solar Advisor: แนะนำติดตั้ง ~{solar_reco_kw} kW (ปรับได้ตามพฤติกรรม)")
        solar_kw = solar_reco_kw

    return {
        "kwh_total": round(kwh_total, 3),
        "kwh_net": round(kwh_net, 3),
        "kwh_on": round(kwh_on, 3),
        "kwh_off": round(kwh_off, 3),
        "kwh_solar_used": round(kwh_solar_used, 3),
        "kwh_ev": round(kwh_breakdown.get("ev_charger", kwh_ev), 3),
        "cost_thb": round(cost_thb, 2),
        "breakdown": {k: round(v, 3) for k, v in kwh_breakdown.items()},
        "warnings": warnings[:5],
        "insights": insights[:5],
        "points_earned": int(points),
        "solar_kw": solar_kw,
        "use_rooms": bool(use_rooms),
    }


def recompute_level(points):
    lvl = 1
    for item in HOUSE_LEVELS:
        if points >= item["need_points"]:
            lvl = item["level"]
    return lvl


def ensure_admin_seed():
    db = get_db()
    admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if admin:
        return
    username = os.environ.get("ENERGY_LIFE_ADMIN_USER", "admin")
    password = os.environ.get("ENERGY_LIFE_ADMIN_PASS", "admin1234")
    email = os.environ.get("ENERGY_LIFE_ADMIN_EMAIL", "admin@example.com")
    db.execute(
        "INSERT OR IGNORE INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
        (username, email, generate_password_hash(password), "admin", datetime.utcnow().isoformat())
    )
    db.commit()


# =========================
# Flask App
# =========================
app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY


@app.before_request
def before_request():
    init_db()
    ensure_admin_seed()


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ===== landing alias (กัน template เก่าเรียก url_for('landing')) =====
@app.route("/landing")
def landing():
    return redirect(url_for("index"))


@app.route("/")
def index():
    increment_visitor()
    visitor_count = get_visitor_count()
    return render_template("index.html", visitor_count=visitor_count, app_name=APP_NAME)


# ============================================================
# HOME
# ============================================================
@app.route("/home")
@login_required
def home():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    return render_template(
        "home.html",
        user=user,
        profile=st["profile"],
        state=st["state"],
        points=st["points"],
        house_level=st["house_level"],
        levels=HOUSE_LEVELS,
        appliances_catalog=APPLIANCES_CATALOG,
        app_name=APP_NAME
    )


# =========================
# HOUSE SETUP (กำหนดโครงสร้างบ้าน)
# =========================
@app.route("/house-setup", methods=["GET", "POST"])
@login_required
def house_setup():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    state = st["state"]

    def to_int(name, default=0, min_v=0, max_v=10):
        try:
            v = int(request.form.get(name, default) or default)
        except Exception:
            v = int(default)
        return max(min_v, min(max_v, v))

    if request.method == "POST":
        house_type = request.form.get("house_type", "condo")

        bedroom  = to_int("bedroom", 1, 0, 10)
        bathroom = to_int("bathroom", 1, 0, 10)
        living   = to_int("living", 1, 0, 5)
        kitchen  = to_int("kitchen", 1, 0, 5)
        work     = to_int("work", 0, 0, 5)
        parking  = to_int("parking", 1, 0, 10)  # ✅ NEW

        state["house_layout"] = {
            "enabled": True,
            "house_type": house_type,
            "rooms": {
                "bedroom": bedroom,
                "bathroom": bathroom,
                "living": living,
                "kitchen": kitchen,
                "work": work,
                "parking": parking,  # ✅ NEW
            }
        }

        # generate rooms from layout
        state["rooms"] = build_rooms_from_layout(state["house_layout"])

        save_user_state(user["id"], st["profile"], state, st["points"], st["house_level"])
        flash("บันทึกโครงสร้างบ้านแล้ว ✅ ต่อไปตั้งค่าอุปกรณ์ตามห้องได้เลย", "success")
        return redirect(url_for("rooms_setup"))

    return render_template("house_setup.html", user=user, st=st, app_name=APP_NAME)


# =========================
# ROOMS SETUP (แสดงห้องที่สร้าง)
# =========================
@app.route("/rooms-setup", methods=["GET"])
@login_required
def rooms_setup():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    rooms = (st.get("state") or {}).get("rooms") or {}
    return render_template("rooms_setup.html", user=user, st=st, rooms=rooms, app_name=APP_NAME)


# =========================
# ROOM DETAIL (ตั้งค่าอุปกรณ์ในห้อง) ✅ เหลือแค่อันเดียว (กันชน route ซ้ำ)
# =========================
def _to_bool(v):
    return str(v).lower() in ("1", "true", "on", "yes")

def _to_int_form(name, default=0, min_v=None, max_v=None):
    try:
        v = int(request.form.get(name, default) or default)
    except Exception:
        v = int(default)
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v

def _to_float_form(name, default=0.0, min_v=None, max_v=None):
    try:
        v = float(request.form.get(name, default) or default)
    except Exception:
        v = float(default)
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v

@app.route("/room/<rid>", methods=["GET", "POST"])
@login_required
def room_detail(rid):
    user = current_user()
    st = get_or_create_user_state(user["id"])
    state = st["state"]
    rooms = state.get("rooms") or {}

    if rid not in rooms:
        flash("ไม่พบห้องนี้ (ลองกลับไปหน้า Rooms Setup)", "error")
        return redirect(url_for("rooms_setup"))

    room = rooms[rid]
    catalog = _catalog_by_key()

    # ensure appliance configs exist (merge defaults)
    appl = room.get("appliances") or {}
    for k in list(appl.keys()):
        c = catalog.get(k)
        if not c:
            continue
        if not isinstance(appl.get(k), dict) or len(appl.get(k)) == 0:
            appl[k] = dict(c["defaults"])
        else:
            merged = dict(c["defaults"])
            merged.update(appl[k])
            appl[k] = merged
    room["appliances"] = appl

    if request.method == "POST":
        for key in appl.keys():
            c = catalog.get(key)
            if not c:
                continue

            cfg = dict(appl.get(key) or c["defaults"])
            cfg["enabled"] = _to_bool(request.form.get(f"{key}__enabled", "off"))
            t = c.get("type")

            if t == "ac":
                cfg["btu"] = _to_int_form(f"{key}__btu", cfg.get("btu", 12000), 6000, 60000)
                cfg["set_temp"] = _to_int_form(f"{key}__set_temp", cfg.get("set_temp", 26), 16, 30)
                cfg["hours"] = _to_float_form(f"{key}__hours", cfg.get("hours", 6), 0, 24)
                cfg["inverter"] = _to_bool(request.form.get(f"{key}__inverter", "off"))
                cfg["start_hour"] = _to_int_form(f"{key}__start_hour", cfg.get("start_hour", 20), 0, 23)
                cfg["end_hour"] = _to_int_form(f"{key}__end_hour", cfg.get("end_hour", 2), 0, 23)

            elif t == "lights":
                cfg["mode"] = request.form.get(f"{key}__mode", cfg.get("mode", "LED"))
                cfg["watts"] = _to_float_form(f"{key}__watts", cfg.get("watts", 30), 0, 5000)
                cfg["hours"] = _to_float_form(f"{key}__hours", cfg.get("hours", 5), 0, 24)

            elif t == "fridge":
                cfg["kwh_per_day"] = _to_float_form(f"{key}__kwh_per_day", cfg.get("kwh_per_day", 1.2), 0, 30)

            elif t == "ev_charger":
                cfg["battery_kwh"] = _to_float_form(f"{key}__battery_kwh", cfg.get("battery_kwh", 60), 20, 200)
                cfg["charger_kw"] = _to_float_form(f"{key}__charger_kw", cfg.get("charger_kw", 7.4), 1, 50)
                cfg["soc_from"] = _to_int_form(f"{key}__soc_from", cfg.get("soc_from", 30), 0, 100)
                cfg["soc_to"] = _to_int_form(f"{key}__soc_to", cfg.get("soc_to", 80), 0, 100)
                cfg["efficiency"] = _to_float_form(f"{key}__efficiency", cfg.get("efficiency", 0.9), 0.5, 1.0)
                cfg["start_hour"] = _to_int_form(f"{key}__start_hour", cfg.get("start_hour", 22), 0, 23)
                cfg["charges_per_week"] = _to_int_form(f"{key}__charges_per_week", cfg.get("charges_per_week", 3), 0, 14)

            else:
                cfg["watts"] = _to_float_form(f"{key}__watts", cfg.get("watts", 100), 0, 100000)
                cfg["hours"] = _to_float_form(f"{key}__hours", cfg.get("hours", 1), 0, 24)

            appl[key] = cfg

        rooms[rid]["appliances"] = appl
        state["rooms"] = rooms
        save_user_state(user["id"], st["profile"], state, st["points"], st["house_level"])
        flash("บันทึกอุปกรณ์ในห้องแล้ว ✅", "success")
        return redirect(url_for("room_detail", rid=rid))

    return render_template(
        "room_detail.html",
        user=user,
        st=st,
        room_id=rid,
        room=room,
        catalog=catalog,
        app_name=APP_NAME
    )


# =========================
# AUTH
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? OR email=?", (username, username)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            ensure_user_prefs(user["id"])
            db.execute(
                "INSERT INTO login_log(user_id,ip,user_agent,created_at) VALUES(?,?,?,?)",
                (user["id"], request.remote_addr, request.headers.get("User-Agent", ""), datetime.utcnow().isoformat())
            )
            db.commit()
            return redirect(url_for("home"))
        flash("ชื่อผู้ใช้/รหัสผ่านไม่ถูกต้อง", "error")
    return render_template("login.html", app_name=APP_NAME)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        if len(username) < 3 or len(password) < 6:
            flash("ชื่อผู้ใช้ต้อง ≥ 3 ตัวอักษร และรหัสผ่านต้อง ≥ 6 ตัวอักษร", "error")
            return render_template("register.html", app_name=APP_NAME)

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                (username, email, generate_password_hash(password), "player", datetime.utcnow().isoformat())
            )
            db.commit()
            uid = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
            db.execute("UPDATE users SET display_name=?, share_token=? WHERE id=?", (username, make_token(24), uid))
            db.commit()
            ensure_user_prefs(uid)
        except sqlite3.IntegrityError:
            flash("ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้แล้ว", "error")
            return render_template("register.html", app_name=APP_NAME)

        flash("สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ", "success")
        return redirect(url_for("login"))

    return render_template("register.html", app_name=APP_NAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# -------- API --------
@app.route("/api/state", methods=["GET", "POST"])
@login_required
def api_state():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        profile = st["profile"]
        state = st["state"]

        profile.update({k: data.get("profile", {}).get(k, profile.get(k)) for k in profile.keys()})

        for k in ["tariff_mode", "solar_kw", "solar_mode", "ev_enabled", "day_counter"]:
            if k in data.get("state", {}):
                state[k] = data["state"][k]

        if "ev" in data.get("state", {}):
            state["ev"].update(data["state"]["ev"])

        if "appliances" in data.get("state", {}):
            for ak, av in data["state"]["appliances"].items():
                if ak in state["appliances"]:
                    state["appliances"][ak].update(av)

        save_user_state(user["id"], profile, state, st["points"], st["house_level"])
        return jsonify({"ok": True})

    return jsonify({"profile": st["profile"], "state": st["state"], "points": st["points"], "house_level": st["house_level"]})


@app.route("/api/simulate_day", methods=["POST"])
@login_required
def api_simulate_day():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    profile, state = st["profile"], st["state"]

    res = compute_daily_energy(profile, state)

    delta_points = int(res.get("points_earned", 0))
    points_new = int(st["points"]) + delta_points
    level_new = recompute_level(points_new)

    db = get_db()
    day = f"Day {int(state.get('day_counter', 1))}"
    db.execute("""
        INSERT INTO energy_daily(user_id,day,kwh_total,cost_thb,kwh_on,kwh_off,kwh_solar_used,kwh_ev,notes_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        user["id"], day, float(res["kwh_total"]), float(res["cost_thb"]),
        float(res["kwh_on"]), float(res["kwh_off"]), float(res["kwh_solar_used"]), float(res.get("kwh_ev", 0.0)),
        json.dumps({"use_rooms": res.get("use_rooms", False), "breakdown": res.get("breakdown", {})}),
        datetime.utcnow().isoformat()
    ))
    db.commit()

    state["day_counter"] = int(state.get("day_counter", 1)) + 1
    save_user_state(user["id"], profile, state, points_new, level_new)

    return jsonify({"result": res, "points": points_new, "house_level": level_new, "day_counter": state["day_counter"]})


# ปิดร้านค้าในโหมดใช้งานจริง
@app.route("/api/shop", methods=["GET"])
@login_required
def api_shop():
    return jsonify({"ok": False, "error": "Shop ถูกปิดในโหมดใช้งานจริง"}), 404


@app.route("/api/buy", methods=["POST"])
@login_required
def api_buy():
    return jsonify({"ok": False, "error": "Shop ถูกปิดในโหมดใช้งานจริง"}), 404


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    db = get_db()
    rows = db.execute("""
        SELECT day,kwh_total,cost_thb,kwh_on,kwh_off,kwh_solar_used,kwh_ev,created_at
        FROM energy_daily WHERE user_id=? ORDER BY id DESC LIMIT 30
    """, (user["id"],)).fetchall()
    return render_template("dashboard.html", user=user, st=st, rows=rows, levels=HOUSE_LEVELS)


@app.route("/admin")
@login_required
@role_required("admin", "officer")
def admin():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    active_7d = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','-7 day')").fetchone()["c"]
    active_30d = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','-30 day')").fetchone()["c"]
    todays = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','start of day')").fetchone()["c"]
    avg_kwh = db.execute("SELECT AVG(kwh_total) as a FROM energy_daily").fetchone()["a"] or 0
    avg_cost = db.execute("SELECT AVG(cost_thb) as a FROM energy_daily").fetchone()["a"] or 0
    users = db.execute("""
        SELECT u.id,u.username,u.role,us.points,us.house_level,us.updated_at
        FROM users u LEFT JOIN user_state us ON us.user_id=u.id
        ORDER BY u.id DESC LIMIT 50
    """).fetchall()
    settings = {k: load_setting(k) for k in ["non_tou_rate", "tou_on_rate", "tou_off_rate", "on_peak_start", "on_peak_end"]}
    return render_template(
        "admin.html",
        total_users=total_users,
        active_7d=active_7d,
        active_30d=active_30d,
        todays=todays,
        avg_kwh=avg_kwh,
        avg_cost=avg_cost,
        users=users,
        settings=settings
    )


@app.route("/admin/settings", methods=["POST"])
@login_required
@role_required("admin")
def admin_settings():
    for key in ["non_tou_rate", "tou_on_rate", "tou_off_rate", "on_peak_start", "on_peak_end"]:
        if key in request.form:
            save_setting(key, request.form.get(key))
    flash("อัปเดตตั้งค่าเรียบร้อย", "success")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>")
@login_required
@role_required("admin", "officer")
def admin_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        flash("ไม่พบผู้ใช้", "error")
        return redirect(url_for("admin"))
    st = get_or_create_user_state(user_id)
    rows = db.execute("""
        SELECT day,kwh_total,cost_thb,kwh_on,kwh_off,kwh_solar_used,kwh_ev,created_at
        FROM energy_daily WHERE user_id=? ORDER BY id DESC LIMIT 60
    """, (user_id,)).fetchall()
    return render_template("admin_user.html", u=user, st=st, rows=rows, levels=HOUSE_LEVELS)


# ------------------------------
# V3: Inventory / Missions / Pets / Leaderboard / Share / User Settings
# ------------------------------
def inv_get(user_id: int, item_key: str) -> int:
    db = get_db()
    row = db.execute("SELECT qty FROM inventory WHERE user_id=? AND item_key=?", (user_id, item_key)).fetchone()
    return int(row["qty"]) if row else 0


def inv_add(user_id: int, item_key: str, qty: int):
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("""
        INSERT INTO inventory(user_id,item_key,qty,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(user_id,item_key) DO UPDATE SET
            qty = qty + excluded.qty,
            updated_at = excluded.updated_at
    """, (user_id, item_key, int(qty), now))
    db.commit()


def inv_take(user_id: int, item_key: str, qty: int) -> bool:
    have = inv_get(user_id, item_key)
    if have < qty:
        return False
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE inventory SET qty = qty - ?, updated_at=? WHERE user_id=? AND item_key=?",
               (int(qty), now, user_id, item_key))
    db.commit()
    return True


def weekly_add_score(user_id: int, delta: int):
    db = get_db()
    week_id = current_week_id()
    now = datetime.utcnow().isoformat()
    db.execute("""
        INSERT INTO weekly_scores(user_id,week_id,score,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(user_id,week_id) DO UPDATE SET
            score = score + excluded.score,
            updated_at = excluded.updated_at
    """, (user_id, week_id, int(delta), now))
    db.commit()


def get_user_display(user_id: int):
    db = get_db()
    row = db.execute("SELECT display_name, share_token FROM users WHERE id=?", (user_id,)).fetchone()
    return (row["display_name"] or "ผู้เล่น", row["share_token"])


def get_user_prefs(user_id: int):
    db = get_db()
    row = db.execute("SELECT prefs_json FROM user_prefs WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return ensure_user_prefs(user_id)
    try:
        prefs = json.loads(row["prefs_json"] or "{}")
    except Exception:
        prefs = {}
    merged = json.loads(json.dumps(DEFAULT_USER_PREFS))
    for k, v in prefs.items():
        if isinstance(v, dict) and k in merged:
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def save_user_prefs(user_id: int, prefs: dict):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO user_prefs(user_id,prefs_json,updated_at) VALUES(?,?,?)",
               (user_id, json.dumps(prefs), datetime.utcnow().isoformat()))
    db.commit()


def _game_disabled_redirect():
    flash("โหมดเกมถูกปิดชั่วคราว (โหมดใช้งานจริง)", "error")
    return redirect(url_for("home"))


@app.route("/missions", methods=["GET", "POST"])
@login_required
def missions():
    if not ENABLE_GAME:
        return _game_disabled_redirect()
    return _game_disabled_redirect()


@app.route("/pets", methods=["GET", "POST"])
@login_required
def pets():
    if not ENABLE_GAME:
        return _game_disabled_redirect()
    return _game_disabled_redirect()


@app.route("/leaderboard")
@login_required
def leaderboard():
    if not ENABLE_GAME:
        return _game_disabled_redirect()
    return _game_disabled_redirect()


@app.route("/share/<token>")
def share_public(token):
    if not ENABLE_GAME:
        return render_template("share_public.html", app_name=APP_NAME, not_found=True)
    return render_template("share_public.html", app_name=APP_NAME, not_found=True)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def user_settings():
    user = current_user()
    prefs = get_user_prefs(user["id"])
    if request.method == "POST":
        for key in ["bgm", "sfx", "pet", "tts"]:
            prefs["audio"][key] = True if request.form.get(f"audio_{key}") == "on" else False
        for key in ["rotate", "animations", "low_power"]:
            prefs["view"][key] = True if request.form.get(f"view_{key}") == "on" else False
        prefs["privacy"]["share_house"] = True if request.form.get("privacy_share_house") == "on" else False
        prefs["privacy"]["show_on_leaderboard"] = True if request.form.get("privacy_show_on_leaderboard") == "on" else False
        prefs["view"]["mode"] = request.form.get("view_mode") or prefs["view"]["mode"]
        prefs["language"]["ui"] = request.form.get("lang_ui") or prefs["language"]["ui"]
        prefs["language"]["voice"] = request.form.get("lang_voice") or prefs["language"]["voice"]
        save_user_prefs(user["id"], prefs)
        flash("บันทึกการตั้งค่าแล้ว", "success")
        return redirect(url_for("user_settings"))
    return render_template("settings_user.html", app_name=APP_NAME, prefs=prefs)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    name, token = get_user_display(user["id"])
    if request.method == "POST":
        new_name = (request.form.get("display_name") or "").strip()
        if len(new_name) < 3 or len(new_name) > 16:
            flash("ชื่อที่แสดงต้องยาว 3–16 ตัวอักษร", "error")
            return redirect(url_for("profile"))

        if inv_get(user["id"], "name_change_ticket") <= 0:
            flash("ต้องมีไอเท็ม ‘ตั๋วเปลี่ยนชื่อ’ ก่อนถึงจะเปลี่ยนชื่อได้", "error")
            return redirect(url_for("profile"))
        if not inv_take(user["id"], "name_change_ticket", 1):
            flash("ตั๋วเปลี่ยนชื่อไม่พอ", "error")
            return redirect(url_for("profile"))

        db = get_db()
        db.execute("UPDATE users SET display_name=? WHERE id=?", (new_name, user["id"]))
        db.commit()
        flash("เปลี่ยนชื่อสำเร็จ", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", app_name=APP_NAME, name=name, token=token,
                           ticket=inv_get(user["id"], "name_change_ticket"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
