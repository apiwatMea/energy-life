import os
import sqlite3
import random
import json
import math
from datetime import datetime, date
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
    "non_tou_rate": 4.20,  # THB/kWh placeholder (legacy/simple)
    "tou_on_rate": 5.50,   # legacy/simple
    "tou_off_rate": 3.30,  # legacy/simple
    "on_peak_start": 9,    # 09:00
    "on_peak_end": 22      # 22:00 end exclusive
}

# ✅ Admin “คิดเงินจริง” settings (ตามฟอร์ม admin.html)
DEFAULT_BILLING_SETTINGS = {
    # Ft / VAT
    "ft_rate": 0.0,                 # สตางค์/หน่วย (ตาม label ใน UI)
    "ft_label": "manual",
    "vat_rate": 0.07,

    # Non-TOU (ขั้นบันได)
    "non_tou_tier1_kwh": 150,
    "non_tou_tier2_kwh": 400,
    "non_tou_service_fee": 24.62,
    "non_tou_rate1": 3.2484,
    "non_tou_rate2": 4.2218,
    "non_tou_rate3": 4.4217,

    # TOU
    "tou_on_rate_real": 5.7982,
    "tou_off_rate_real": 2.6369,
    "tou_service_fee": 24.62,

    "on_peak_start": 9,
    "on_peak_end": 22,
}


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

    # ✅ EV Charger
    {"key": "ev_charger", "name": "EV Charger", "icon": "🔋", "type": "ev_charger",
     "defaults": {
         "enabled": True,
         "battery_kwh": 60.0,
         "charger_kw": 7.4,
         "efficiency": 0.9,
         "soc_from": 30,
         "soc_to": 80,
         "charges_per_week": 2,
         "start_hour": 22,
         "end_hour": 2,
         "hours": 2.0
     }},
]

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

    # seed legacy tariff settings
    for k, v in DEFAULT_TARIFF.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, str(v)))

    # seed admin billing settings
    for k, v in DEFAULT_BILLING_SETTINGS.items():
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


ROOM_TEMPLATES = {
    "bedroom": ["ac", "lights"],
    "living":  ["ac", "lights", "tv"],
    "kitchen": ["lights", "microwave", "fridge"],
    "bathroom": ["water_heater", "lights"],
    "work":    ["lights", "computer"],
    "parking": ["lights", "ev_charger"]
}


def build_rooms_from_layout(layout: dict):
    rooms = {}
    for room_type, count in (layout.get("rooms") or {}).items():
        count = int(count or 0)
        for i in range(1, count + 1):
            rid = f"{room_type}_{i}"
            rooms[rid] = {
                "type": room_type,
                "label": f"{room_type.capitalize()} {i}",
                "appliances": {k: {} for k in ROOM_TEMPLATES.get(room_type, [])},
                "configured": False
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

        "ev_enabled": False,
        "ev": {
            "battery_kwh": 60,
            "charger_kw": 7.4,
            "soc_from": 30,
            "soc_to": 80,
            "charge_start_hour": 22,
            "charge_end_hour": 6
        },

        "appliances": appliances,

        "house_layout": {
            "enabled": False,
            "house_type": "condo",
            "rooms": {
                "bedroom": 1,
                "bathroom": 1,
                "living": 1,
                "kitchen": 1,
                "work": 0,
                "parking": 1
            }
        },

        "rooms": {},

        "inventory": {"furniture": [], "avatar": []},
        "day_counter": 1
    }


def _infer_room_configured(room: dict) -> bool:
    try:
        appl = room.get("appliances") or {}
        if not isinstance(appl, dict):
            return False
        for _, cfg in appl.items():
            if isinstance(cfg, dict) and len(cfg) > 0:
                return True
        return False
    except Exception:
        return False


def get_or_create_user_state(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM user_state WHERE user_id=?", (user_id,)).fetchone()
    if row:
        profile = json.loads(row["profile_json"])
        state = json.loads(row["state_json"])

        changed = False
        rooms = (state.get("rooms") or {})
        if isinstance(rooms, dict) and rooms:
            for rid, room in rooms.items():
                if isinstance(room, dict) and "configured" not in room:
                    room["configured"] = _infer_room_configured(room)
                    rooms[rid] = room
                    changed = True
            if changed:
                state["rooms"] = rooms
                now = datetime.utcnow().isoformat()
                db.execute("""
                    UPDATE user_state SET state_json=?, updated_at=?
                    WHERE user_id=?
                """, (json.dumps(state), now, user_id))
                db.commit()

        return {
            "profile": profile,
            "state": state,
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


def calc_ev_kwh_per_charge(battery_kwh, soc_from, soc_to, efficiency):
    try:
        battery_kwh = float(battery_kwh or 0)
        soc_from = float(soc_from or 0)
        soc_to = float(soc_to or 0)
        efficiency = float(efficiency or 0.9)
    except Exception:
        return 0.0

    efficiency = max(0.5, min(1.0, efficiency))
    delta = max(0.0, min(100.0, soc_to) - max(0.0, soc_from))
    return (battery_kwh * (delta / 100.0)) / max(0.01, efficiency)


def calc_ev_hours(kwh_from_grid, charger_kw):
    try:
        kwh_from_grid = float(kwh_from_grid or 0)
        charger_kw = float(charger_kw or 0)
    except Exception:
        return 0.0
    if charger_kw <= 0:
        return 0.0
    return max(0.0, kwh_from_grid / charger_kw)


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


# ============================================================
# ✅ Billing (คิดเงินจริง) — ใช้ค่าจากหน้า Admin
# ============================================================
def _to_float_safe(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_int_safe(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _load_billing_settings():
    s = {}
    for k, dv in DEFAULT_BILLING_SETTINGS.items():
        s[k] = load_setting(k, dv)
    return s


def bill_non_tou_month(kwh_month: float, settings: dict):
    kwh = max(0.0, _to_float_safe(kwh_month, 0.0))

    tier1 = _to_int_safe(settings.get("non_tou_tier1_kwh", 150), 150)
    tier2 = _to_int_safe(settings.get("non_tou_tier2_kwh", 400), 400)
    r1 = _to_float_safe(settings.get("non_tou_rate1", 3.2484), 3.2484)
    r2 = _to_float_safe(settings.get("non_tou_rate2", 4.2218), 4.2218)
    r3 = _to_float_safe(settings.get("non_tou_rate3", 4.4217), 4.4217)
    service_fee = _to_float_safe(settings.get("non_tou_service_fee", 24.62), 24.62)

    ft_satang = _to_float_safe(settings.get("ft_rate", 0.0), 0.0)
    ft_thb_per_kwh = ft_satang / 100.0  # สตางค์ -> บาท
    vat_rate = _to_float_safe(settings.get("vat_rate", 0.07), 0.07)

    a1 = min(kwh, max(0, tier1))
    a2 = min(max(0.0, kwh - a1), max(0, tier2 - tier1))
    a3 = max(0.0, kwh - a1 - a2)

    base_energy = a1 * r1 + a2 * r2 + a3 * r3
    ft = kwh * ft_thb_per_kwh

    # ตามหมายเหตุในหน้า Admin: Ft และ VAT จาก (ค่าไฟฐาน + Ft)
    sub = base_energy + ft
    vat = sub * vat_rate
    total = sub + vat + service_fee

    return {
        "kwh": kwh,
        "base_energy": base_energy,
        "ft": ft,
        "vat": vat,
        "service_fee": service_fee,
        "total": total,
    }


def bill_tou_month(kwh_on_month: float, kwh_off_month: float, settings: dict):
    on = max(0.0, _to_float_safe(kwh_on_month, 0.0))
    off = max(0.0, _to_float_safe(kwh_off_month, 0.0))
    kwh = on + off

    on_rate = _to_float_safe(settings.get("tou_on_rate_real", 5.7982), 5.7982)
    off_rate = _to_float_safe(settings.get("tou_off_rate_real", 2.6369), 2.6369)
    service_fee = _to_float_safe(settings.get("tou_service_fee", 24.62), 24.62)

    ft_satang = _to_float_safe(settings.get("ft_rate", 0.0), 0.0)
    ft_thb_per_kwh = ft_satang / 100.0
    vat_rate = _to_float_safe(settings.get("vat_rate", 0.07), 0.07)

    base_energy = on * on_rate + off * off_rate
    ft = kwh * ft_thb_per_kwh
    sub = base_energy + ft
    vat = sub * vat_rate
    total = sub + vat + service_fee

    return {
        "kwh": kwh,
        "kwh_on": on,
        "kwh_off": off,
        "base_energy": base_energy,
        "ft": ft,
        "vat": vat,
        "service_fee": service_fee,
        "total": total,
    }


def bill_day_from_month_obj(month_obj: dict):
    # เฉลี่ยรายวันจาก (total/30) ใช้เพื่อแสดง “ค่าไฟวันนี้”
    try:
        return float(month_obj.get("total", 0.0)) / 30.0
    except Exception:
        return 0.0


def compute_daily_energy(profile, state):
    tariff_mode = state.get("tariff_mode", "non_tou")
    solar_kw = float(state.get("solar_kw", 0) or 0)

    size_factor = {"small": 0.9, "medium": 1.0, "large": 1.15}.get(profile.get("house_size", "medium"), 1.0)
    residents = max(1, int(profile.get("residents", 3)))
    resident_factor = 0.85 + min(0.6, (residents - 1) * 0.08)

    warnings = []
    insights = []
    points = 0

    # ✅ ช่วง On/Off (ยังใช้จาก settings)
    on_start = int(load_setting("on_peak_start", 9))
    on_end = int(load_setting("on_peak_end", 22))

    def _room_calc_breakdown(appliances_dict: dict):
        kwh_breakdown = {}
        for key, cfg in (appliances_dict or {}).items():
            if not isinstance(cfg, dict):
                cfg = {}

            if not cfg.get("enabled", False):
                kwh_breakdown[key] = 0.0
                continue

            if key == "ac":
                btu = float(cfg.get("btu", 12000))
                set_temp = float(cfg.get("set_temp", 26))
                hours = float(cfg.get("hours", 6))
                inverter = bool(cfg.get("inverter", True))
                kwh_breakdown[key] = calc_ac_kwh(btu, set_temp, hours, inverter=inverter)

            elif key == "fridge":
                kwh_breakdown[key] = float(cfg.get("kwh_per_day", 1.2))

            elif key == "lights":
                watts = float(cfg.get("watts", 30))
                hours = float(cfg.get("hours", 5))
                kwh_breakdown[key] = calc_generic_kwh(watts, hours)

            elif key == "ev_charger":
                batt = cfg.get("battery_kwh", 60.0)
                soc_from = cfg.get("soc_from", 30)
                soc_to = cfg.get("soc_to", 80)
                eff = cfg.get("efficiency", 0.9)
                kwh_breakdown[key] = calc_ev_kwh_per_charge(batt, soc_from, soc_to, eff)

            else:
                watts = float(cfg.get("watts", 0))
                hours = float(cfg.get("hours", 0))
                kwh_breakdown[key] = calc_generic_kwh(watts, hours)

        return kwh_breakdown

    def _ev_month_kwh_from_cfg(ev_cfg: dict):
        if not isinstance(ev_cfg, dict) or not ev_cfg.get("enabled", False):
            return 0.0, 0.0
        batt = ev_cfg.get("battery_kwh", 60.0)
        soc_from = ev_cfg.get("soc_from", 30)
        soc_to = ev_cfg.get("soc_to", 80)
        eff = ev_cfg.get("efficiency", 0.9)
        charges_per_week = ev_cfg.get("charges_per_week", 2)

        try:
            charges_per_week = float(charges_per_week or 0)
        except Exception:
            charges_per_week = 0.0
        charges_per_week = max(0.0, min(14.0, charges_per_week))

        kwh_per_charge = calc_ev_kwh_per_charge(batt, soc_from, soc_to, eff)
        kwh_month = kwh_per_charge * charges_per_week * 4.0
        return kwh_per_charge, kwh_month

    def _tou_split_from_room_breakdown(room_breakdown_scaled: dict, room_cfg: dict):
        kwh_on = 0.0
        kwh_off = 0.0

        ac_cfg = (room_cfg.get("appliances") or {}).get("ac", {})
        if isinstance(ac_cfg, dict) and ac_cfg.get("enabled", False):
            ac_kwh = float(room_breakdown_scaled.get("ac", 0.0))
            ac_on, ac_off = split_kwh_by_tou(
                ac_kwh,
                ac_cfg.get("start_hour", 20),
                ac_cfg.get("end_hour", 2),
                on_start, on_end
            )
            kwh_on += ac_on
            kwh_off += ac_off

        ev_cfg = (room_cfg.get("appliances") or {}).get("ev_charger", {})
        if isinstance(ev_cfg, dict) and ev_cfg.get("enabled", False):
            ev_kwh = float(room_breakdown_scaled.get("ev_charger", 0.0))
            start_h = ev_cfg.get("start_hour", 22)
            end_h = ev_cfg.get("end_hour", None)
            if end_h is None:
                charger_kw = ev_cfg.get("charger_kw", 7.4)
                hours = calc_ev_hours(ev_kwh, charger_kw)
                dur = int(max(1, math.ceil(hours))) if hours > 0 else 1
                end_h = (normalize_hour(start_h) + dur) % 24

            ev_on, ev_off = split_kwh_by_tou(ev_kwh, start_h, end_h, on_start, on_end)
            kwh_on += ev_on
            kwh_off += ev_off

        return kwh_on, kwh_off

    rooms = (state.get("rooms") or {})
    use_rooms = isinstance(rooms, dict) and len(rooms) > 0

    rooms_breakdown = {}
    kwh_total_raw = 0.0

    rooms_enabled = bool(use_rooms)
    kwh_by_room = {}
    kwh_month_by_room = {}
    kwh_ev_by_room = {}
    kwh_ev_month_by_room = {}

    if use_rooms:
        for rid, room in rooms.items():
            if not isinstance(room, dict):
                continue

            appl = room.get("appliances") or {}
            bd = _room_calc_breakdown(appl)
            room_kwh = sum(bd.values())

            room_kwh_scaled = room_kwh * size_factor * resident_factor
            kwh_total_raw += room_kwh_scaled

            ev_cfg = (appl or {}).get("ev_charger", {})
            ev_day, ev_month = _ev_month_kwh_from_cfg(ev_cfg)
            ev_day_scaled = ev_day * size_factor * resident_factor
            ev_month_scaled = ev_month * size_factor * resident_factor

            non_ev_day_scaled = max(0.0, room_kwh_scaled - ev_day_scaled)
            room_month_scaled = non_ev_day_scaled * 30.0 + ev_month_scaled

            kwh_by_room[rid] = round(room_kwh_scaled, 3)
            kwh_month_by_room[rid] = round(room_month_scaled, 3)
            kwh_ev_by_room[rid] = round(ev_day_scaled, 3)
            kwh_ev_month_by_room[rid] = round(ev_month_scaled, 3)

            rooms_breakdown[rid] = {
                "type": room.get("type", ""),
                "label": room.get("label", rid),
                "kwh_total": round(room_kwh_scaled, 3),
                "kwh_month_total": round(room_month_scaled, 3),
                "kwh_ev_month": round(ev_month_scaled, 3),
                "breakdown": {k: round(v * size_factor * resident_factor, 3) for k, v in bd.items()}
            }
    else:
        bd = _room_calc_breakdown(state.get("appliances") or {})
        kwh_total_raw = sum(bd.values()) * size_factor * resident_factor
        rooms_breakdown = {}

    kwh_total = kwh_total_raw

    daytime_frac = 0.45
    if profile.get("player_type") == "adult":
        daytime_frac = 0.42
    if profile.get("player_type") == "kid":
        daytime_frac = 0.48

    daytime_kwh = kwh_total * daytime_frac
    solar_reco_kw = int(round(daytime_kwh / 3.0))
    solar_reco_kw = max(0, min(10, solar_reco_kw))

    kwh_solar_prod = solar_kw * 4.0
    kwh_solar_used = min(kwh_total, kwh_solar_prod * 0.75)
    kwh_net = max(0.0, kwh_total - kwh_solar_used)

    kwh_on = 0.0
    kwh_off = 0.0

    if tariff_mode == "tou":
        if use_rooms:
            temp_on = 0.0
            temp_off = 0.0

            for rid, room in rooms.items():
                rb_scaled = rooms_breakdown.get(rid, {}).get("breakdown", {})
                room_on, room_off = _tou_split_from_room_breakdown(rb_scaled, room)
                temp_on += room_on
                temp_off += room_off

            known = temp_on + temp_off
            other = max(0.0, kwh_net - known)

            house_type = profile.get("house_type", "condo")
            base_on = 0.65 if house_type == "condo" else 0.58
            kwh_on = temp_on + other * base_on
            kwh_off = temp_off + other * (1.0 - base_on)
        else:
            other_kwh = kwh_net
            house_type = profile.get("house_type", "condo")
            base_on = 0.65 if house_type == "condo" else 0.58
            kwh_on = other_kwh * base_on
            kwh_off = other_kwh * (1.0 - base_on)
    else:
        kwh_off = kwh_net
        kwh_on = 0.0

    solar_mode = state.get("solar_mode", "manual")
    if solar_mode == "advisor":
        insights.append(f"Solar Advisor: แนะนำติดตั้ง ~{solar_reco_kw} kW (ปรับได้ตามพฤติกรรม)")
        solar_kw = solar_reco_kw

    # ✅ EV day total
    kwh_ev_total_day = 0.0
    if use_rooms:
        kwh_ev_total_day = sum(float(v or 0) for v in kwh_ev_by_room.values())

    # ============================================================
    # ✅ คิดเงินจริง: คำนวณ “รายเดือน” ทั้ง Non-TOU และ TOU เพื่อ Compare
    # ============================================================
    billing = _load_billing_settings()

    # kWh/เดือน (ถ้าตั้งค่าแยกห้อง เรามี monthly จริงต่อห้องอยู่แล้ว)
    if use_rooms and kwh_month_by_room:
        kwh_month_total = sum(float(v or 0) for v in kwh_month_by_room.values())
    else:
        kwh_month_total = kwh_total * 30.0

    # TOU split รายเดือน (ใช้ daily split ×30 เป็น baseline)
    kwh_on_month = kwh_on * 30.0
    kwh_off_month = kwh_off * 30.0

    bill_nt = bill_non_tou_month(kwh_month_total, billing)
    bill_t = bill_tou_month(kwh_on_month, kwh_off_month, billing)

    diff_month = float(bill_nt["total"]) - float(bill_t["total"])  # + = TOU ถูกกว่า
    recommend = "tou" if bill_t["total"] < bill_nt["total"] else "non_tou"

    # ✅ ค่าไฟวันนี้: ใช้ “โหมดที่เลือก” แต่คิดจากบิลจริง (รวม Ft/VAT และเฉลี่ยค่าบริการ/30)
    if tariff_mode == "tou":
        cost_thb = bill_day_from_month_obj(bill_t)
    else:
        cost_thb = bill_day_from_month_obj(bill_nt)

    # เพิ่มอินไซต์สั้นๆ
    if recommend == "tou":
        insights.append("แนะนำ TOU: โดยรวมถูกกว่า (จากการประมาณรายเดือน)")
    else:
        insights.append("แนะนำ Non-TOU: โดยรวมถูกกว่า (จากการประมาณรายเดือน)")

    # คะแนน baseline
    baseline = 14.0 * size_factor * resident_factor
    if kwh_net < baseline:
        points += int((baseline - kwh_net) * 2)
        insights.append("ใช้ไฟต่ำกว่าเกณฑ์พื้นฐานวันนี้ ได้คะแนนเพิ่ม")

    if use_rooms:
        insights.append("คำนวณจากอุปกรณ์แยกรายห้องแล้ว ✅")

    return {
        "kwh_total": round(kwh_total, 3),
        "kwh_net": round(kwh_net, 3),
        "kwh_on": round(kwh_on, 3),
        "kwh_off": round(kwh_off, 3),
        "kwh_solar_used": round(kwh_solar_used, 3),
        "kwh_ev": round(kwh_ev_total_day, 3),

        # ✅ ค่าไฟวันนี้แบบคิดเงินจริง
        "cost_thb": round(cost_thb, 2),

        "warnings": warnings[:5],
        "insights": insights[:6],
        "points_earned": int(points),
        "solar_kw": solar_kw,

        "rooms_enabled": rooms_enabled,
        "kwh_by_room": kwh_by_room,
        "kwh_month_by_room": kwh_month_by_room,
        "kwh_ev_by_room": kwh_ev_by_room,
        "kwh_ev_month_by_room": kwh_ev_month_by_room,
        "rooms_breakdown": rooms_breakdown,

        # ✅ schema ใหม่ให้ app.js ใช้ (compare)
        "compare": {
            "non_tou_month": round(float(bill_nt["total"]), 2),
            "tou_month": round(float(bill_t["total"]), 2),
            "diff_month": round(float(diff_month), 2),
            "recommend": recommend,
            "meta": {
                "ft_satang_per_kwh": float(billing.get("ft_rate", 0.0)),
                "vat_rate": float(billing.get("vat_rate", 0.07)),
                "ft_label": str(billing.get("ft_label", "manual")),
            }
        }
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


@app.route("/landing")
def landing():
    return redirect(url_for("index"))


@app.route("/")
def index():
    increment_visitor()
    visitor_count = get_visitor_count()
    return render_template("index.html", visitor_count=visitor_count, app_name=APP_NAME)


# ============================================================
# A) HOME
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
        parking  = to_int("parking", 1, 0, 10)

        state["house_layout"] = {
            "enabled": True,
            "house_type": house_type,
            "rooms": {
                "bedroom": bedroom,
                "bathroom": bathroom,
                "living": living,
                "kitchen": kitchen,
                "work": work,
                "parking": parking
            }
        }

        state["rooms"] = build_rooms_from_layout(state["house_layout"])

        save_user_state(user["id"], st["profile"], state, st["points"], st["house_level"])
        flash("บันทึกโครงสร้างบ้านแล้ว ✅ ต่อไปตั้งค่าอุปกรณ์ตามห้องได้เลย", "success")
        return redirect(url_for("home"))

    return render_template("house_setup.html", user=user, st=st, app_name=APP_NAME)


@app.route("/rooms-setup", methods=["GET"])
@login_required
def rooms_setup():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    rooms = (st.get("state") or {}).get("rooms") or {}

    return render_template(
        "rooms_setup.html",
        user=user,
        st=st,
        rooms=rooms,
        app_name=APP_NAME
    )


def _catalog_by_key():
    return {a["key"]: a for a in APPLIANCES_CATALOG}


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
                cfg["battery_kwh"] = _to_float_form(f"{key}__battery_kwh", cfg.get("battery_kwh", 60.0), 10, 200)
                cfg["charger_kw"] = _to_float_form(f"{key}__charger_kw", cfg.get("charger_kw", 7.4), 0.1, 50)
                cfg["efficiency"] = _to_float_form(f"{key}__efficiency", cfg.get("efficiency", 0.9), 0.5, 1.0)
                cfg["soc_from"] = _to_int_form(f"{key}__soc_from", cfg.get("soc_from", 30), 0, 100)
                cfg["soc_to"] = _to_int_form(f"{key}__soc_to", cfg.get("soc_to", 80), 0, 100)
                cfg["charges_per_week"] = _to_int_form(f"{key}__charges_per_week", cfg.get("charges_per_week", 2), 0, 14)
                cfg["start_hour"] = _to_int_form(f"{key}__start_hour", cfg.get("start_hour", 22), 0, 23)

                kwh_per_charge = calc_ev_kwh_per_charge(cfg["battery_kwh"], cfg["soc_from"], cfg["soc_to"], cfg["efficiency"])
                hours = calc_ev_hours(kwh_per_charge, cfg["charger_kw"])
                cfg["hours"] = round(hours, 2)

                dur = int(max(1, math.ceil(hours))) if hours > 0 else 1
                cfg["end_hour"] = (normalize_hour(cfg["start_hour"]) + dur) % 24

            else:
                cfg["watts"] = _to_float_form(f"{key}__watts", cfg.get("watts", 100), 0, 100000)
                cfg["hours"] = _to_float_form(f"{key}__hours", cfg.get("hours", 1), 0, 24)

            appl[key] = cfg

        rooms[rid]["appliances"] = appl
        rooms[rid]["configured"] = True

        state["rooms"] = rooms
        save_user_state(user["id"], st["profile"], state, st["points"], st["house_level"])
        flash("บันทึกอุปกรณ์ในห้องแล้ว ✅", "success")
        return redirect(url_for("home"))

    return render_template(
        "room_detail.html",
        user=user,
        st=st,
        room_id=rid,
        room=room,
        catalog=catalog,
        app_name=APP_NAME
    )


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

    delta_points = int(res["points_earned"])
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
        None, datetime.utcnow().isoformat()
    ))
    db.commit()

    state["day_counter"] = int(state.get("day_counter", 1)) + 1
    save_user_state(user["id"], profile, state, points_new, level_new)

    return jsonify({"result": res, "points": points_new, "house_level": level_new, "day_counter": state["day_counter"]})


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

    settings_keys = [
        "ft_rate", "ft_label", "vat_rate",
        "non_tou_tier1_kwh", "non_tou_tier2_kwh",
        "non_tou_service_fee", "non_tou_rate1", "non_tou_rate2", "non_tou_rate3",
        "tou_on_rate_real", "tou_off_rate_real", "tou_service_fee",
        "on_peak_start", "on_peak_end",
        "non_tou_rate", "tou_on_rate", "tou_off_rate",
    ]
    settings = {k: load_setting(k, DEFAULT_BILLING_SETTINGS.get(k, DEFAULT_TARIFF.get(k))) for k in settings_keys}

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
    keys = [
        "ft_rate", "ft_label", "vat_rate",
        "non_tou_tier1_kwh", "non_tou_tier2_kwh",
        "non_tou_service_fee", "non_tou_rate1", "non_tou_rate2", "non_tou_rate3",
        "tou_on_rate_real", "tou_off_rate_real", "tou_service_fee",
        "on_peak_start", "on_peak_end",
    ]
    for key in keys:
        if key in request.form:
            save_setting(key, request.form.get(key))

    flash("อัปเดตตั้งค่าเรียบร้อย ✅", "success")
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
