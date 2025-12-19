import os
import sqlite3
import random
from datetime import datetime, date
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
APP_NAME = "ENERGY LIFE V3"
DATABASE = os.environ.get("ENERGY_LIFE_DB", "energy_life.db")
SECRET_KEY = os.environ.get("ENERGY_LIFE_SECRET", None) or os.urandom(24).hex()
def make_token(n=20):
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(alphabet) for _ in range(n))
DEFAULT_USER_PREFS = {
    "audio": {
        "bgm": True,
        "sfx": True,
        "pet": True,
        "tts": False,
        "bgm_volume": 0.6,
        "sfx_volume": 0.8,
        "pet_volume": 0.7,
        "tts_volume": 0.8
    },
    "view": {
        "mode": "cutaway",
        "rotate": True,
        "animations": True,
        "low_power": False
    },
    "privacy": {
        "share_house": True,
        "show_on_leaderboard": True
    },
    "language": {
        "ui": "th",
        "voice": "th"
    }
}
def current_week_id(dt=None):
    dt = dt or datetime.utcnow()
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
DEFAULT_TARIFF = {
    "non_tou_rate": 4.20,   # THB/kWh (placeholder; can be adjusted in admin)
    "tou_on_rate": 5.50,
    "tou_off_rate": 3.30,
    # simple TOU schedule for MVP:
    "on_peak_start": 9,     # 09:00
    "on_peak_end": 22       # 22:00 (end is exclusive)
}
APPLIANCES_CATALOG = [
    {
        "key": "ac",
        "name": "แอร์",
        "icon": "❄️",
        "type": "ac",
        "defaults": {"enabled": True, "btu": 12000, "set_temp": 26, "hours": 6, "inverter": True, "start_hour": 20, "end_hour": 2}
    },
    {
        "key": "lights",
        "name": "ไฟ",
        "icon": "💡",
        "type": "lights",
        "defaults": {"enabled": True, "mode": "LED", "watts": 30, "hours": 5}
    },
    {
        "key": "tv",
        "name": "ทีวี",
        "icon": "📺",
        "type": "generic",
        "defaults": {"enabled": True, "watts": 120, "hours": 3}
    },
    {
        "key": "fridge",
        "name": "ตู้เย็น",
        "icon": "🧊",
        "type": "fridge",
        "defaults": {"enabled": True, "kwh_per_day": 1.2}
    },
    {
        "key": "water_heater",
        "name": "เครื่องทำน้ำอุ่น",
        "icon": "🚿",
        "type": "generic",
        "defaults": {"enabled": False, "watts": 3500, "hours": 0.3}
    },
    {
        "key": "washer",
        "name": "เครื่องซักผ้า",
        "icon": "🧺",
        "type": "generic",
        "defaults": {"enabled": False, "watts": 500, "hours": 0.5}
    },
    {
        "key": "microwave",
        "name": "ไมโครเวฟ",
        "icon": "🍳",
        "type": "generic",
        "defaults": {"enabled": False, "watts": 1200, "hours": 0.1}
    },
    {
        "key": "computer",
        "name": "คอมพิวเตอร์",
        "icon": "💻",
        "type": "generic",
        "defaults": {"enabled": False, "watts": 200, "hours": 2}
    },
    {
        "key": "standby",
        "name": "ไฟสแตนด์บาย",
        "icon": "🔌",
        "type": "standby",
        "defaults": {"enabled": True, "watts": 20, "hours": 24}
    },
]
SHOP_ITEMS = [
    {"key": "sofa", "name": "โซฟา Eco", "icon": "🛋️", "cost": 120, "category": "furniture"},
    {"key": "plant", "name": "ต้นไม้เขียว", "icon": "🌿", "cost": 80, "category": "furniture"},
    {"key": "painting", "name": "รูปพลังงาน", "icon": "🖼️", "cost": 60, "category": "furniture"},
    {"key": "bed", "name": "เตียงนุ่ม", "icon": "🛏️", "cost": 150, "category": "furniture"},
    {"key": "eco_hat", "name": "หมวกโซลาร์", "icon": "🧢", "cost": 90, "category": "avatar"},
    {"key": "eco_shirt", "name": "เสื้อ ECO HERO", "icon": "👕", "cost": 110, "category": "avatar"},
    # V3 energy-saving items & platform items
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
    {"level": 1, "name": "บ้านเริ่มต้น", "need_points": 0,   "badge": "🏚️"},
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
def ensure_user_prefs(user_id:int):
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
    # attempt numeric parse
    try:
        if "." in val:
            return float(val)
        return int(val)
    except Exception:
        return val
def save_setting(key, value):
    db = get_db()
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
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
    return {
        "display_name": "ผู้เล่น",
        "player_type": "family",   # kid / adult / family
        "house_type": "condo",     # condo / single_1 / single_2
        "house_size": "medium",    # small / medium / large
        "residents": 3
    }
def default_state():
    appliances = {}
    for a in APPLIANCES_CATALOG:
        appliances[a["key"]] = dict(a["defaults"])
    return {
        "tariff_mode": "non_tou",  # non_tou / tou
        "solar_kw": 0,             # 0, 3, 5, 10 (เลือกเอง)
        "solar_mode": "manual",    # manual / advisor
        "ev_enabled": False,
        "ev": {
            "battery_kwh": 60,
            "charger_kw": 7.4,
            "soc_from": 30,
            "soc_to": 80,
            "charge_start_hour": 22,  # default off-peak
            "charge_end_hour": 6
        },
        "appliances": appliances,
        "inventory": {
            "furniture": [],
            "avatar": []
        },
        "day_counter": 1
    }
def get_or_create_user_state(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM user_state WHERE user_id=?", (user_id,)).fetchone()
    if row:
        import json
        return {
            "profile": json.loads(row["profile_json"]),
            "state": json.loads(row["state_json"]),
            "points": row["points"],
            "house_level": row["house_level"]
        }
    import json
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
    import json
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
    """
    MVP heuristic:
    - base kW roughly: BTU/12000 * 1.0 (inverter) or *1.15 (non-inverter)
    - temperature penalty: each degree below 26 increases 6%, above 26 decreases 3% (floor 0.7x)
    """
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
    return (watts/1000.0) * hours
def normalize_hour(h):
    try:
        h = int(float(h))
    except Exception:
        h = 0
    return max(0, min(23, h))
def window_hours(start_h, end_h):
    """
    Returns list of hours (0-23) covered by a daily window.
    If end_h == start_h => 0 hours.
    If crosses midnight, wraps.
    Example: 20->2 covers [20,21,22,23,0,1]
    """
    s = normalize_hour(start_h)
    e = normalize_hour(end_h)
    if s == e:
        return []
    if s < e:
        return list(range(s, e))
    return list(range(s, 24)) + list(range(0, e))
def split_kwh_by_tou(kwh, start_h, end_h, on_start, on_end):
    """
    Split kWh across on/off-peak based on hourly window.
    Assumes uniform consumption over the active hours.
    """
    hrs = window_hours(start_h, end_h)
    if not hrs:
        return 0.0, 0.0
    per = kwh / len(hrs)
    on_set = set(window_hours(on_start, on_end))
    kwh_on = sum(per for h in hrs if h in on_set)
    kwh_off = kwh - kwh_on
    return kwh_on, kwh_off
def tou_split_kwh(total_kwh, charge_hours_map):
    """
    For MVP, we don't simulate hour-by-hour for all appliances.
    We approximate split based on a user-supplied hourly usage distribution map:
    charge_hours_map: dict hour->fraction (0..1 sum=1)
    For simplicity in MVP, we assume:
    - If TOU: 70% usage falls in on-peak for daytime-centric households; tweak by house type.
    - EV charging uses explicit hours and is split accurately.
    """
    return total_kwh
def compute_daily_energy(profile, state):
    """
    Returns:
      totals: dict with kwh_total, kwh_on, kwh_off, kwh_solar_used, kwh_ev, cost_thb, insights, warnings, points_earned
    """
    tariff_mode = state.get("tariff_mode", "non_tou")
    solar_kw = float(state.get("solar_kw", 0) or 0)
    appliances = state.get("appliances", {})
    # Base household factor
    size_factor = {"small": 0.9, "medium": 1.0, "large": 1.15}.get(profile.get("house_size","medium"), 1.0)
    residents = max(1, int(profile.get("residents", 3)))
    resident_factor = 0.85 + min(0.6, (residents-1)*0.08)  # gentle scaling
    kwh_breakdown = {}
    warnings = []
    insights = []
    points = 0
    # Appliances
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
            if set_temp < 25:
                warnings.append(f"แอร์ตั้ง {int(set_temp)}°C ใช้ไฟสูง แนะนำ 26°C เพื่อประหยัด")
            elif set_temp >= 26:
                points += 10  # reward good practice
                insights.append("ตั้งแอร์ 26°C ขึ้นไป = ประหยัดดี ได้คะแนนโบนัส")
        elif key == "fridge":
            kwh = float(cfg.get("kwh_per_day", 1.2))
            kwh_breakdown[key] = kwh
        elif key == "lights":
            watts = float(cfg.get("watts", 30))
            hours = float(cfg.get("hours", 5))
            kwh = calc_generic_kwh(watts, hours)
            kwh_breakdown[key] = kwh
            if cfg.get("mode") == "LED":
                points += 5
            else:
                warnings.append("ไฟเป็นหลอดธรรมดา แนะนำเปลี่ยนเป็น LED")
        else:
            watts = float(cfg.get("watts", 0))
            hours = float(cfg.get("hours", 0))
            kwh_breakdown[key] = calc_generic_kwh(watts, hours)
    # Apply household factors modestly
    kwh_total = sum(kwh_breakdown.values()) * size_factor * resident_factor
    # EV charging
    kwh_ev = 0.0
    if state.get("ev_enabled"):
        ev = state.get("ev", {})
        batt = float(ev.get("battery_kwh", 60))
        soc_from = float(ev.get("soc_from", 30))
        soc_to = float(ev.get("soc_to", 80))
        soc_from = max(0, min(100, soc_from))
        soc_to = max(0, min(100, soc_to))
        if soc_to > soc_from:
            kwh_ev = batt * ((soc_to - soc_from)/100.0)
            kwh_total += kwh_ev
            insights.append(f"EV ชาร์จจาก {int(soc_from)}% → {int(soc_to)}% ใช้ไฟ ~{kwh_ev:.1f} kWh/ครั้ง")
        else:
            warnings.append("ตั้งค่า EV ชาร์จไม่ถูกต้อง (เปอร์เซ็นต์ปลายทางต้องมากกว่าต้นทาง)")
    
    # Solar Advisor (แนะนำขนาดอย่างง่าย)
    solar_reco_kw = 0
    # ประมาณโหลดกลางวัน = 45% ของ kWh_total (บ้านทั่วไป) ปรับตามประเภทผู้เล่น
    daytime_frac = 0.45
    if profile.get("player_type") == "adult":
        daytime_frac = 0.42
    if profile.get("player_type") == "kid":
        daytime_frac = 0.48
    daytime_kwh = kwh_total * daytime_frac
    # สมมติ 1 kW ผลิตใช้เองได้ ~ 3.0 kWh/วัน (หลังหักข้อจำกัด) -> แนะนำ kw
    solar_reco_kw = int(round(daytime_kwh / 3.0))
    solar_reco_kw = max(0, min(10, solar_reco_kw))
# Solar production (very simple heuristic: 1 kW ~ 4 kWh/day usable)
    kwh_solar_prod = solar_kw * 4.0
    # Assume self-consumption 75% in MVP; clamp by usage
    kwh_solar_used = min(kwh_total, kwh_solar_prod * 0.75)
    kwh_net = max(0.0, kwh_total - kwh_solar_used)
    # TOU split (รายชั่วโมงแบบง่าย)
    kwh_on = 0.0
    kwh_off = 0.0
    on_start = int(load_setting("on_peak_start", 9))
    on_end = int(load_setting("on_peak_end", 22))
    if tariff_mode == "tou":
        # 1) แอร์: ใช้ช่วงเวลา start/end (ถ้าใส่)
        ac_cfg = appliances.get("ac", {})
        if ac_cfg.get("enabled", False):
            ac_kwh = kwh_breakdown.get("ac", 0.0) * size_factor * resident_factor
            # ใช้ start/end ถ้ามี ไม่งั้นอิง start=20 end=2
            ac_on, ac_off = split_kwh_by_tou(
                ac_kwh,
                ac_cfg.get("start_hour", 20),
                ac_cfg.get("end_hour", 2),
                on_start, on_end
            )
            # เราเคยรวม ac ใน kwh_total แล้ว ดังนั้นที่นี่แบ่งเฉพาะสำหรับ on/off
            kwh_on += ac_on
            kwh_off += ac_off
        # 2) EV: ใช้ charge_start_hour และคำนวณตามจำนวนชั่วโมงชาร์จ (MVP)
        if state.get("ev_enabled") and kwh_ev > 0:
            ev = state.get("ev", {})
            charger_kw = float(ev.get("charger_kw", 7.4))
            needed_hours = max(0.0, kwh_ev / max(0.1, charger_kw))
            start = normalize_hour(ev.get("charge_start_hour", 22))
            end = normalize_hour((start + int(math.ceil(needed_hours))) % 24) if needed_hours > 0 else start
            ev_on, ev_off = split_kwh_by_tou(kwh_ev, start, end, on_start, on_end)
            kwh_on += ev_on
            kwh_off += ev_off
            # แจ้งเตือนหากเริ่มชาร์จช่วง On-Peak
            if start in set(window_hours(on_start, on_end)):
                warnings.append("คุณเริ่มชาร์จ EV ช่วง On‑Peak ค่าไฟแพง แนะนำเริ่มหลัง Off‑Peak")
            else:
                points += 15
                insights.append("ชาร์จ EV ช่วง Off‑Peak = ประหยัดดี ได้คะแนนโบนัส")
        # 3) อุปกรณ์อื่น ๆ: สมมติใช้งานช่วงกลางวัน/เย็น (heuristic) เพื่อแบ่ง on/off
        other_kwh = (kwh_net - (kwh_on + kwh_off))
        if other_kwh < 0:
            other_kwh = 0.0
        # สัดส่วน On‑Peak ของอุปกรณ์อื่นตามประเภทบ้าน (ง่ายแต่พอใช้งานจริง)
        house_type = profile.get("house_type", "condo")
        base_on = 0.65 if house_type == "condo" else 0.58
        kwh_on += other_kwh * base_on
        kwh_off += other_kwh * (1.0 - base_on)
    else:
        kwh_off = kwh_net
        kwh_on = 0.0
    # Cost
    if tariff_mode == "tou":
        on_rate = float(load_setting("tou_on_rate", 5.5))
        off_rate = float(load_setting("tou_off_rate", 3.3))
        cost_thb = kwh_on * on_rate + kwh_off * off_rate
    else:
        rate = float(load_setting("non_tou_rate", 4.2))
        cost_thb = kwh_off * rate
    # Additional points: saving effect vs a baseline (rough)
    baseline = 14.0 * size_factor * resident_factor
    if kwh_net < baseline:
        points += int((baseline - kwh_net) * 2)  # 2 points per kWh saved under baseline
        insights.append("ใช้ไฟต่ำกว่าเกณฑ์พื้นฐานวันนี้ ได้คะแนนเพิ่ม")
    
    if solar_mode := state.get("solar_mode", "manual"):
        if solar_mode == "advisor":
            insights.append(f"Solar Advisor: แนะนำติดตั้ง ~{solar_reco_kw} kW (ปรับได้ตามพฤติกรรม)")
            # auto set solar_kw to recommendation for simulation (virtual)
            solar_kw = solar_reco_kw
        # warning on oversize/undersize if user selected manually
        if state.get("solar_mode","manual") == "manual" and solar_kw > 0:
            if solar_reco_kw > 0 and solar_kw >= solar_reco_kw + 4:
                warnings.append("Solar อาจใหญ่เกินความจำเป็นสำหรับการใช้ไฟกลางวัน (ลองลดขนาดเพื่อคุ้มทุน)")
            if solar_kw > 0 and solar_reco_kw >= solar_kw + 4:
                warnings.append("Solar อาจเล็กไป หากต้องการลดบิลมากขึ้น ลองเพิ่มขนาดตามคำแนะนำ")
    return {
        "kwh_total": round(kwh_total, 3),
        "kwh_net": round(kwh_net, 3),
        "kwh_on": round(kwh_on, 3),
        "kwh_off": round(kwh_off, 3),
        "kwh_solar_used": round(kwh_solar_used, 3),
        "kwh_ev": round(kwh_ev, 3),
        "cost_thb": round(cost_thb, 2),
        "breakdown": {k: round(v, 3) for k, v in kwh_breakdown.items()},
        "warnings": warnings[:5],
        "insights": insights[:5],
        "points_earned": int(points),
        "solar_kw": solar_kw
    }
def recompute_level(points):
    lvl = 1
    for item in HOUSE_LEVELS:
        if points >= item["need_points"]:
            lvl = item["level"]
    return lvl
def ensure_admin_seed():
    """
    If no admin exists, create one with default credentials.
    IMPORTANT: change after first run.
    """
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
@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("landing.html", app_name=APP_NAME)
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
        shop_items=SHOP_ITEMS,
        appliances_catalog=APPLIANCES_CATALOG
    )
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? OR email=?", (username, username)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            ensure_user_prefs(user["id"])
            db.execute(
                "INSERT INTO login_log(user_id,ip,user_agent,created_at) VALUES(?,?,?,?)",
                (user["id"], request.remote_addr, request.headers.get("User-Agent",""), datetime.utcnow().isoformat())
            )
            db.commit()
            return redirect(url_for("home"))
        flash("ชื่อผู้ใช้/รหัสผ่านไม่ถูกต้อง", "error")
    return render_template("login.html", app_name=APP_NAME)
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email = request.form.get("email","").strip() or None
        password = request.form.get("password","")
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
    return redirect(url_for("landing"))
# -------- API --------
@app.route("/api/state", methods=["GET","POST"])
@login_required
def api_state():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        profile = st["profile"]
        state = st["state"]
        # update allowed fields
        profile.update({k: data.get("profile", {}).get(k, profile.get(k)) for k in profile.keys()})
        # state safe updates
        for k in ["tariff_mode", "solar_kw", "solar_mode", "ev_enabled", "day_counter"]:
            if k in data.get("state", {}):
                state[k] = data["state"][k]
        if "ev" in data.get("state", {}):
            state["ev"].update(data["state"]["ev"])
        if "appliances" in data.get("state", {}):
            # deep update per appliance
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
    # update points and level
    delta_points = int(res["points_earned"])
    points_new = int(st["points"]) + delta_points
    level_new = recompute_level(points_new)
    # persist daily
    db = get_db()
    day = f"Day {int(state.get('day_counter', 1))}"
    db.execute("""
        INSERT INTO energy_daily(user_id,day,kwh_total,cost_thb,kwh_on,kwh_off,kwh_solar_used,kwh_ev,notes_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        user["id"], day, float(res["kwh_total"]), float(res["cost_thb"]),
        float(res["kwh_on"]), float(res["kwh_off"]), float(res["kwh_solar_used"]), float(res["kwh_ev"]),
        None, datetime.utcnow().isoformat()
    ))
    db.commit()
    # V3: weekly leaderboard score
    weekly_add_score(user["id"], delta_points)
    # increment day counter
    state["day_counter"] = int(state.get("day_counter", 1)) + 1
    save_user_state(user["id"], profile, state, points_new, level_new)
    return jsonify({"result": res, "points": points_new, "house_level": level_new, "day_counter": state["day_counter"]})
@app.route("/api/shop", methods=["GET"])
@login_required
def api_shop():
    return jsonify({"items": SHOP_ITEMS})
@app.route("/api/buy", methods=["POST"])
@login_required
def api_buy():
    user = current_user()
    st = get_or_create_user_state(user["id"])
    data = request.get_json(force=True) or {}
    item_key = data.get("item_key")
    item = next((x for x in SHOP_ITEMS if x["key"] == item_key), None)
    if not item:
        return jsonify({"ok": False, "error": "ไม่พบไอเท็ม"}), 400
    cost = int(item["cost"])
    if st["points"] < cost:
        return jsonify({"ok": False, "error": "คะแนนไม่พอ"}), 400
    # add to inventory
    profile, state = st["profile"], st["state"]
    if item.get("category") in ("furniture", "avatar"):
        inv = state.get("inventory", {"furniture": [], "avatar": []})
        inv.setdefault(item["category"], [])
        inv[item["category"]].append(item_key)
        state["inventory"] = inv
    else:
        # Config-driven items (energy/pet/profile etc.) are stored in DB inventory (won't break old players)
        inv_add(user["id"], item_key, 1)
    points_new = st["points"] - cost
    level_new = recompute_level(points_new)  # (optional: levels only go up; MVP keeps simple)
    # persist purchase
    db = get_db()
    db.execute(
        "INSERT INTO purchases(user_id,item_key,cost_points,created_at) VALUES(?,?,?,?)",
        (user["id"], item_key, cost, datetime.utcnow().isoformat())
    )
    db.commit()
    save_user_state(user["id"], profile, state, points_new, max(st["house_level"], level_new))
    return jsonify({"ok": True, "points": points_new, "inventory": state["inventory"], "house_level": max(st["house_level"], level_new)})
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
    return render_template(
        "dashboard.html",
        user=user,
        st=st,
        rows=rows,
        levels=HOUSE_LEVELS
    )
@app.route("/admin")
@login_required
@role_required("admin","officer")
def admin():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    active_7d = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','-7 day')").fetchone()["c"]
    active_30d = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','-30 day')").fetchone()["c"]
    todays = db.execute("SELECT COUNT(DISTINCT user_id) as c FROM login_log WHERE created_at >= datetime('now','start of day')").fetchone()["c"]
    # usage aggregates
    avg_kwh = db.execute("SELECT AVG(kwh_total) as a FROM energy_daily").fetchone()["a"] or 0
    avg_cost = db.execute("SELECT AVG(cost_thb) as a FROM energy_daily").fetchone()["a"] or 0
    # top appliances via last known state snapshot (approx)
    # We'll compute from last simulation per user? For MVP show recent 100 daily rows distribution not available; keep simple.
    # Users list
    users = db.execute("""
        SELECT u.id,u.username,u.role,us.points,us.house_level,us.updated_at
        FROM users u LEFT JOIN user_state us ON us.user_id=u.id
        ORDER BY u.id DESC LIMIT 50
    """).fetchall()
    settings = {k: load_setting(k) for k in ["non_tou_rate","tou_on_rate","tou_off_rate","on_peak_start","on_peak_end"]}
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
    # update tariff settings
    for key in ["non_tou_rate","tou_on_rate","tou_off_rate","on_peak_start","on_peak_end"]:
        if key in request.form:
            save_setting(key, request.form.get(key))
    flash("อัปเดตตั้งค่าเรียบร้อย", "success")
    return redirect(url_for("admin"))
@app.route("/admin/user/<int:user_id>")
@login_required
@role_required("admin","officer")
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
def inv_get(user_id:int, item_key:str) -> int:
    db = get_db()
    row = db.execute("SELECT qty FROM inventory WHERE user_id=? AND item_key=?", (user_id, item_key)).fetchone()
    return int(row["qty"]) if row else 0
def inv_add(user_id:int, item_key:str, qty:int):
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        """
        INSERT INTO inventory(user_id,item_key,qty,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(user_id,item_key) DO UPDATE SET
            qty = qty + excluded.qty,
            updated_at = excluded.updated_at
        """,
        (user_id, item_key, int(qty), now)
    )
def inv_take(user_id:int, item_key:str, qty:int) -> bool:
    have = inv_get(user_id, item_key)
    if have < qty:
        return False
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE inventory SET qty = qty - ?, updated_at=? WHERE user_id=? AND item_key=?",
               (int(qty), now, user_id, item_key))
    return True
def weekly_add_score(user_id:int, delta:int):
    db = get_db()
    week_id = current_week_id()
    now = datetime.utcnow().isoformat()
    db.execute(
        """
        INSERT INTO weekly_scores(user_id,week_id,score,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(user_id,week_id) DO UPDATE SET
            score = score + excluded.score,
            updated_at = excluded.updated_at
        """,
        (user_id, week_id, int(delta), now)
    )
def get_user_display(user_id:int):
    db = get_db()
    row = db.execute("SELECT display_name, share_token FROM users WHERE id=?", (user_id,)).fetchone()
    return (row["display_name"] or "ผู้เล่น", row["share_token"])
def get_user_prefs(user_id:int):
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
def save_user_prefs(user_id:int, prefs:dict):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO user_prefs(user_id,prefs_json,updated_at) VALUES(?,?,?)",
               (user_id, json.dumps(prefs), datetime.utcnow().isoformat()))
    db.commit()
def compute_weekly_kwh(user_id:int, days:int=7, offset:int=0):
    db = get_db()
    rows = db.execute(
        "SELECT kwh_total FROM energy_daily WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
        (user_id, days, offset)
    ).fetchall()
    return float(sum(r["kwh_total"] for r in rows)) if rows else 0.0
def missions_for(user_id:int):
    st = get_or_create_user_state(user_id)
    profile, state = st["profile"], st["state"]
    week_id = current_week_id()
    db = get_db()
    existing = {r["mission_id"]: r for r in db.execute(
        "SELECT * FROM mission_progress WHERE user_id=? AND week_id=?",
        (user_id, week_id)
    ).fetchall()}
    def claimed(mid:str) -> bool:
        return (mid in existing) and (existing[mid]["status"] == "claimed")
    def upsert_active(mid:str, target:int=1):
        if mid not in existing:
            db.execute(
                """
                INSERT OR IGNORE INTO mission_progress(user_id,mission_id,week_id,status,progress,target)
                VALUES(?,?,?,?,?,?)
                """,
                (user_id, mid, week_id, "active", 0, int(target))
            )
    missions = []
    appliances = state.get("appliances", {}) or {}
    ac = appliances.get("aircon") or appliances.get("ac") or appliances.get("air") or {}
    ac_temp = int(ac.get("temp_c", ac.get("temp", 26)) or 26)
    ac_hours = float(ac.get("hours", 0) or 0)
    mid = "M_AC_26"
    upsert_active(mid)
    ok = (ac_hours > 0 and ac_temp >= 26)
    missions.append({
        "id": mid,
        "type": "daily",
        "title": "แอร์ประหยัดไฟ 26°C",
        "desc": "ตั้งแอร์ที่ 26°C หรือมากกว่า (และใช้งานอย่างน้อย 1 ชั่วโมง)",
        "reward_points": 120,
        "reward_item": {"key": "pet_food_basic", "qty": 1},
        "available": ok,
        "claimed": claimed(mid),
    })
    mid = "M_STANDBY_ZERO"
    upsert_active(mid)
    has_strip = inv_get(user_id, "smart_strip") > 0
    missions.append({
        "id": mid,
        "type": "daily",
        "title": "ตัดไฟแฝง",
        "desc": "มีปลั๊กพ่วงอัจฉริยะเพื่อช่วยลดไฟแฝง",
        "reward_points": 80,
        "reward_item": {"key": "pet_food_basic", "qty": 1},
        "available": has_strip,
        "claimed": claimed(mid),
    })
    mid = "M_TOU_MODE"
    upsert_active(mid)
    ok = (state.get("tariff_mode") == "tou")
    missions.append({
        "id": mid,
        "type": "weekly",
        "title": "เปิดโหมด TOU",
        "desc": "เปิดโหมด TOU เพื่อเรียนรู้การใช้ไฟช่วง On/Off-Peak",
        "reward_points": 150,
        "reward_item": {"key": "name_change_ticket", "qty": 1},
        "available": ok,
        "claimed": claimed(mid),
    })
    mid = "M_EV_OFFPEAK"
    upsert_active(mid)
    ev = state.get("ev", {}) or {}
    start_hr = int(ev.get("charge_start_hour", 22) or 22)
    ev_ok = bool(state.get("ev_enabled")) and (start_hr >= 22 or start_hr < 6)
    missions.append({
        "id": mid,
        "type": "weekly",
        "title": "ชาร์จ EV ช่วง Off-Peak",
        "desc": "ตั้งเวลาชาร์จรถเริ่มช่วง 22:00–06:00",
        "reward_points": 200,
        "reward_item": {"key": "pet_food_premium", "qty": 1},
        "available": ev_ok,
        "claimed": claimed(mid),
    })
    mid = "M_WEEKLY_REDUCE"
    upsert_active(mid)
    last7 = compute_weekly_kwh(user_id, 7, 0)
    prev7 = compute_weekly_kwh(user_id, 7, 7)
    reduce_ok = (prev7 > 0 and last7 <= prev7 * 0.95)
    missions.append({
        "id": mid,
        "type": "weekly",
        "title": "ลดการใช้ไฟ 5% (เทียบสัปดาห์ก่อน)",
        "desc": "ทำให้ไฟรวม 7 วันล่าสุดลดลง ≥ 5% เทียบ 7 วันก่อนหน้า",
        "reward_points": 400,
        "reward_item": {"key": "pet_egg", "qty": 1},
        "available": reduce_ok,
        "claimed": claimed(mid),
    })
    db.commit()
    return missions
def claim_mission(user_id:int, mission_id:str):
    week_id = current_week_id()
    db = get_db()
    row = db.execute(
        "SELECT * FROM mission_progress WHERE user_id=? AND mission_id=? AND week_id=?",
        (user_id, mission_id, week_id)
    ).fetchone()
    if row and row["status"] == "claimed":
        return False, "ภารกิจนี้รับรางวัลไปแล้ว"
    ms = {m["id"]: m for m in missions_for(user_id)}
    if mission_id not in ms:
        return False, "ไม่พบภารกิจ"
    m = ms[mission_id]
    if not m["available"]:
        return False, "ยังไม่ผ่านเงื่อนไขภารกิจ"
    st = get_or_create_user_state(user_id)
    points_new = int(st["points"]) + int(m["reward_points"])
    level_new = recompute_level(points_new)
    db.execute(
        """
        INSERT INTO mission_progress(user_id,mission_id,week_id,status,progress,target,claimed_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(user_id,mission_id,week_id) DO UPDATE SET
            status='claimed',
            claimed_at=excluded.claimed_at
        """,
        (user_id, mission_id, week_id, "claimed", 1, 1, datetime.utcnow().isoformat())
    )
    item = m.get("reward_item")
    if item and item.get("key"):
        inv_add(user_id, item["key"], int(item.get("qty", 1)))
        if item["key"] == "pet_egg":
            has_pet = db.execute("SELECT 1 FROM pets WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
            if not has_pet:
                db.execute(
                    "INSERT INTO pets(user_id,pet_type,stage,hunger,happiness,level,created_at) VALUES(?,?,?,?,?,?,?)",
                    (user_id, "dog", "egg", 50, 50, 1, datetime.utcnow().isoformat())
                )
    weekly_add_score(user_id, int(m["reward_points"]))
    save_user_state(user_id, st["profile"], st["state"], points_new, level_new)
    db.commit()
    return True, "รับรางวัลสำเร็จ"
@app.route("/missions", methods=["GET","POST"])
@login_required
def missions():
    user = current_user()
    ensure_user_prefs(user["id"])
    if request.method == "POST":
        mid = request.form.get("mission_id")
        ok, msg = claim_mission(user["id"], mid)
        flash(msg, "success" if ok else "error")
        return redirect(url_for("missions"))
    missions = missions_for(user["id"])
    st = get_or_create_user_state(user["id"])
    return render_template("missions.html", app_name=APP_NAME, missions=missions, points=st["points"], house_level=st["house_level"])
@app.route("/pets", methods=["GET","POST"])
@login_required
def pets():
    user = current_user()
    ensure_user_prefs(user["id"])
    db = get_db()
    pet = db.execute("SELECT * FROM pets WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
    if request.method == "POST":
        action = request.form.get("action")
        if not pet:
            flash("ยังไม่มีสัตว์เลี้ยง ลองทำภารกิจรายสัปดาห์เพื่อรับไข่สัตว์เลี้ยงนะ", "error")
            return redirect(url_for("pets"))
        if action == "hatch" and pet["stage"] == "egg":
            db.execute("UPDATE pets SET stage='baby', happiness=MIN(100,happiness+10) WHERE id=?", (pet["id"],))
            db.commit()
            flash("ฟักไข่สำเร็จ! ได้สัตว์เลี้ยงตัวแรกแล้ว 🐾", "success")
            return redirect(url_for("pets"))
        if action == "feed":
            food = request.form.get("food")
            if food not in ("pet_food_basic","pet_food_premium"):
                flash("เลือกอาหารไม่ถูกต้อง", "error")
                return redirect(url_for("pets"))
            if not inv_take(user["id"], food, 1):
                flash("อาหารไม่พอ ลองทำภารกิจหรือซื้อในร้านค้า", "error")
                return redirect(url_for("pets"))
            delta_h = 15 if food == "pet_food_basic" else 30
            delta_hp = 10 if food == "pet_food_basic" else 20
            db.execute(
                "UPDATE pets SET hunger=MIN(100,hunger+?), happiness=MIN(100,happiness+?) WHERE id=?",
                (delta_h, delta_hp, pet["id"])
            )
            db.commit()
            flash("ให้อาหารเรียบร้อย สัตว์เลี้ยงแฮปปี้ขึ้นแล้ว 😊", "success")
            return redirect(url_for("pets"))
    inv = {
        "pet_food_basic": inv_get(user["id"], "pet_food_basic"),
        "pet_food_premium": inv_get(user["id"], "pet_food_premium"),
        "name_change_ticket": inv_get(user["id"], "name_change_ticket"),
    }
    return render_template("pets.html", app_name=APP_NAME, pet=pet, inv=inv)
@app.route("/leaderboard")
@login_required
def leaderboard():
    user = current_user()
    ensure_user_prefs(user["id"])
    week_id = current_week_id()
    db = get_db()
    rows = db.execute(
        """
        SELECT u.display_name, ws.score, up.prefs_json
        FROM weekly_scores ws
        JOIN users u ON u.id = ws.user_id
        LEFT JOIN user_prefs up ON up.user_id = ws.user_id
        WHERE ws.week_id=?
        ORDER BY ws.score DESC, u.id ASC
        LIMIT 50
        """,
        (week_id,)
    ).fetchall()
    board = []
    for r in rows:
        show = True
        try:
            prefs = json.loads(r["prefs_json"] or "{}") if r["prefs_json"] else {}
            show = prefs.get("privacy", {}).get("show_on_leaderboard", True)
        except Exception:
            show = True
        if show:
            board.append({"name": r["display_name"] or "ผู้เล่น", "score": int(r["score"])})
    return render_template("leaderboard.html", app_name=APP_NAME, week_id=week_id, board=board)
@app.route("/share/<token>")
def share_public(token):
    db = get_db()
    u = db.execute("SELECT id, display_name FROM users WHERE share_token=?", (token,)).fetchone()
    if not u:
        return render_template("share_public.html", app_name=APP_NAME, not_found=True)
    st = db.execute("SELECT points, house_level FROM user_state WHERE user_id=?", (u["id"],)).fetchone()
    pet = db.execute(
        "SELECT pet_type, stage, hunger, happiness, level FROM pets WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (u["id"],)
    ).fetchone()
    return render_template("share_public.html", app_name=APP_NAME, not_found=False, name=u["display_name"], st=st, pet=pet)
@app.route("/settings", methods=["GET","POST"])
@login_required
def user_settings():
    user = current_user()
    prefs = get_user_prefs(user["id"])
    if request.method == "POST":
        for key in ["bgm","sfx","pet","tts"]:
            prefs["audio"][key] = True if request.form.get(f"audio_{key}") == "on" else False
        for key in ["rotate","animations","low_power"]:
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
@app.route("/profile", methods=["GET","POST"])
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
    return render_template("profile.html", app_name=APP_NAME, name=name, token=token, ticket=inv_get(user["id"], "name_change_ticket"))
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))