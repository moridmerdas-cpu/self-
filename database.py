import sqlite3
import hashlib
import os
import datetime
from config import DATABASE_PATH


def get_conn():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ─── حساب‌های پنل ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # افزودن ستون telegram_user_id اگر قبلاً نبوده (برای دیتابیس‌های قدیمی)
    try:
        c.execute("ALTER TABLE accounts ADD COLUMN telegram_user_id INTEGER")
    except Exception:
        pass

    # ─── تنظیمات (per-user) ───────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            owner_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (owner_id, key)
        )
    """)

    # ─── دشمن ─────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS enemies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner_id, user_id)
        )
    """)

    # ─── دوست ─────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner_id, user_id)
        )
    """)

    # ─── سایلنت چت ────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS silent_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner_id, chat_id)
        )
    """)

    # ─── سایلنت کاربر ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS silent_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner_id, user_id)
        )
    """)

    # ─── پیام‌های ذخیره‌شده ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS saved_messages (
            owner_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,
            content TEXT,
            media_path TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (owner_id, slot)
        )
    """)

    # ─── پیام‌های حذف‌شده ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS deleted_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            chat_id INTEGER,
            sender_id INTEGER,
            sender_name TEXT,
            message TEXT,
            media_type TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── پیام‌های زمان‌بندی‌شده ───────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            send_at TIMESTAMP NOT NULL,
            sent INTEGER DEFAULT 0
        )
    """)

    # ─── توکن‌ها ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            owner_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            last_daily TEXT DEFAULT NULL,
            total_earned INTEGER DEFAULT 0
        )
    """)

    # ─── رفرال‌ها ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_owner_id INTEGER NOT NULL,
            referred_tg_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ─── مدیریت حساب ──────────────────────────────────────────────────────────────
def create_account(username: str, password: str):
    """ایجاد حساب جدید — هر مرحله با connection جداگانه تا هیچ خطایی cascade نشه"""
    # مرحله ۱: ثبت حساب
    new_id = None
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
            (username.strip(), _hash_pw(password)),
        )
        new_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        return None  # یوزرنیم تکراری
    except Exception:
        return None
    finally:
        conn.close()

    # مرحله ۲: ایجاد رکورد توکن (connection جداگانه)
    _init_tokens_by_id(new_id)
    return new_id


def _init_tokens_by_id(owner_id: int):
    """ایجاد رکورد توکن با connection مستقل"""
    from config import WELCOME_TOKENS
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO tokens (owner_id, balance, total_earned) VALUES (?, ?, ?)",
            (owner_id, WELCOME_TOKENS, WELCOME_TOKENS),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# برای سازگاری با کدهای قدیمی
def _init_tokens(conn, owner_id: int):
    from config import WELCOME_TOKENS
    try:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO tokens (owner_id, balance, total_earned) VALUES (?, ?, ?)",
            (owner_id, WELCOME_TOKENS, WELCOME_TOKENS),
        )
        conn.commit()
    except Exception:
        pass


def verify_account(username: str, password: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM accounts WHERE username = ? AND password_hash = ?",
        (username.strip(), _hash_pw(password)),
    )
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None


def get_account(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, telegram_user_id, created_at FROM accounts WHERE id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_account_by_username(username: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, telegram_user_id, created_at FROM accounts WHERE username = ?", (username.strip(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_account_by_tg_id(tg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, telegram_user_id, created_at FROM accounts WHERE telegram_user_id = ?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_accounts():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, created_at FROM accounts ORDER BY created_at")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def account_exists():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM accounts")
    row = c.fetchone()
    conn.close()
    return row["cnt"] > 0


def save_telegram_user_id(owner_id: int, tg_user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE accounts SET telegram_user_id = ? WHERE id = ?", (tg_user_id, owner_id))
    conn.commit()
    conn.close()


def get_telegram_id_by_owner(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_user_id FROM accounts WHERE id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["telegram_user_id"] if row else None


# ─── تنظیمات ──────────────────────────────────────────────────────────────────
SETTING_DEFAULTS = {
    "self_bot_active": "0",
    "secretary_active": "0",
    "anti_delete_active": "0",
    "anti_link_active": "0",
    "auto_seen_active": "0",
    "auto_reaction_active": "0",
    "private_lock_active": "0",
    "enemy_reply_active": "0",
    "auto_save_media": "0",
    "clock_name_active": "0",
    "clock_bio_active": "0",
    "selected_font": "0",
    "secretary_message": "در حال حاضر در دسترس نیستم، بعداً پیام بگذارید.",
    "auto_reaction_emoji": "❤️",
    "typing_style": "0",
    "spam_active": "0",
    "channel_save_active": "0",
    "spam_count": "10",
    "spam_delay": "2",
    "spam_text": "",
    "session_data": "",
    "logged_in": "0",
}


def init_user_settings(owner_id: int):
    conn = get_conn()
    try:
        c = conn.cursor()
        for key, value in SETTING_DEFAULTS.items():
            c.execute(
                "INSERT OR IGNORE INTO settings (owner_id, key, value) VALUES (?, ?, ?)",
                (owner_id, key, value),
            )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    # توکن با connection مستقل
    _init_tokens_by_id(owner_id)


def get_setting(owner_id: int, key: str, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE owner_id = ? AND key = ?", (owner_id, key))
    row = c.fetchone()
    conn.close()
    if row:
        return row["value"]
    return SETTING_DEFAULTS.get(key, default)


def set_setting(owner_id: int, key: str, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings (owner_id, key, value) VALUES (?, ?, ?)",
        (owner_id, key, str(value)),
    )
    conn.commit()
    conn.close()


def toggle_setting(owner_id: int, key: str):
    current = get_setting(owner_id, key, "0")
    new_val = "0" if current == "1" else "1"
    set_setting(owner_id, key, new_val)
    return new_val == "1"


def get_all_logged_in_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT owner_id FROM settings WHERE key = 'logged_in' AND value = '1'"
    )
    rows = [r["owner_id"] for r in c.fetchall()]
    conn.close()
    return rows


# ─── سیستم توکن ───────────────────────────────────────────────────────────────
def _ensure_tokens_row(conn, owner_id: int):
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO tokens (owner_id, balance, total_earned) VALUES (?, 0, 0)", (owner_id,))
    conn.commit()


def get_token_balance(owner_id: int) -> int:
    conn = get_conn()
    _ensure_tokens_row(conn, owner_id)
    c = conn.cursor()
    c.execute("SELECT balance FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["balance"] if row else 0


def add_tokens(owner_id: int, amount: int):
    conn = get_conn()
    _ensure_tokens_row(conn, owner_id)
    c = conn.cursor()
    c.execute(
        "UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ? WHERE owner_id = ?",
        (amount, amount, owner_id),
    )
    conn.commit()
    conn.close()


def deduct_tokens(owner_id: int, amount: int) -> bool:
    conn = get_conn()
    _ensure_tokens_row(conn, owner_id)
    c = conn.cursor()
    c.execute("SELECT balance FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    if not row or row["balance"] < amount:
        conn.close()
        return False
    c.execute("UPDATE tokens SET balance = balance - ? WHERE owner_id = ?", (amount, owner_id))
    conn.commit()
    conn.close()
    return True


def claim_daily_token(owner_id: int):
    from config import DAILY_TOKEN_GIFT
    conn = get_conn()
    _ensure_tokens_row(conn, owner_id)
    c = conn.cursor()
    c.execute("SELECT last_daily FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    today = datetime.date.today().isoformat()
    if row and row["last_daily"] == today:
        conn.close()
        return False, "⏰ امروز قبلاً هدیه روزانه دریافت کردید.\nفردا دوباره بیایید."
    c.execute(
        "UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ?, last_daily = ? WHERE owner_id = ?",
        (DAILY_TOKEN_GIFT, DAILY_TOKEN_GIFT, today, owner_id),
    )
    conn.commit()
    conn.close()
    return True, f"🎁 {DAILY_TOKEN_GIFT} توکن روزانه دریافت کردید!"


def process_referral(referrer_owner_id: int, referred_tg_id: int) -> bool:
    from config import REFERRAL_TOKENS
    conn = get_conn()
    c = conn.cursor()
    try:
        # چک کن این تلگرام ایدی قبلاً رفرال نشده
        c.execute("SELECT 1 FROM referrals WHERE referred_tg_id = ?", (referred_tg_id,))
        if c.fetchone():
            conn.close()
            return False
        # چک کن referrer_owner_id معتبر است
        c.execute("SELECT 1 FROM accounts WHERE id = ?", (referrer_owner_id,))
        if not c.fetchone():
            conn.close()
            return False
        # ثبت رفرال
        c.execute(
            "INSERT INTO referrals (referrer_owner_id, referred_tg_id) VALUES (?, ?)",
            (referrer_owner_id, referred_tg_id),
        )
        conn.commit()
        # اضافه کردن توکن به رفررر
        _ensure_tokens_row(conn, referrer_owner_id)
        c.execute(
            "UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ? WHERE owner_id = ?",
            (REFERRAL_TOKENS, REFERRAL_TOKENS, referrer_owner_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def get_referral_count(owner_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_token_stats(owner_id: int) -> dict:
    conn = get_conn()
    _ensure_tokens_row(conn, owner_id)
    c = conn.cursor()
    c.execute("SELECT balance, last_daily, total_earned FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"balance": 0, "last_daily": None, "total_earned": 0}
    today = datetime.date.today().isoformat()
    can_claim = row["last_daily"] != today
    return {
        "balance": row["balance"],
        "last_daily": row["last_daily"],
        "total_earned": row["total_earned"],
        "can_claim_daily": can_claim,
    }


# ─── دشمن ─────────────────────────────────────────────────────────────────────
def add_enemy(owner_id: int, user_id: int, username=None, name=None):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR REPLACE INTO enemies (owner_id, user_id, username, name) VALUES (?, ?, ?, ?)",
            (owner_id, user_id, username, name),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_enemy(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM enemies WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_enemies(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM enemies WHERE owner_id = ? ORDER BY added_at DESC", (owner_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def is_enemy(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM enemies WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def clear_enemies(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM enemies WHERE owner_id = ?", (owner_id,))
    conn.commit()
    conn.close()


# ─── دوست ─────────────────────────────────────────────────────────────────────
def add_friend(owner_id: int, user_id: int, username=None, name=None):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR REPLACE INTO friends (owner_id, user_id, username, name) VALUES (?, ?, ?, ?)",
            (owner_id, user_id, username, name),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_friend(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM friends WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_friends(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM friends WHERE owner_id = ? ORDER BY added_at DESC", (owner_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def is_friend(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM friends WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def clear_friends(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM friends WHERE owner_id = ?", (owner_id,))
    conn.commit()
    conn.close()


# ─── سایلنت ───────────────────────────────────────────────────────────────────
def add_silent_chat(owner_id: int, chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO silent_chats (owner_id, chat_id) VALUES (?, ?)", (owner_id, chat_id))
    conn.commit()
    conn.close()


def remove_silent_chat(owner_id: int, chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM silent_chats WHERE owner_id = ? AND chat_id = ?", (owner_id, chat_id))
    conn.commit()
    conn.close()


def is_silent_chat(owner_id: int, chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM silent_chats WHERE owner_id = ? AND chat_id = ?", (owner_id, chat_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def add_silent_user(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO silent_users (owner_id, user_id) VALUES (?, ?)", (owner_id, user_id))
    conn.commit()
    conn.close()


def remove_silent_user(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM silent_users WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    conn.commit()
    conn.close()


def is_silent_user(owner_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM silent_users WHERE owner_id = ? AND user_id = ?", (owner_id, user_id))
    row = c.fetchone()
    conn.close()
    return row is not None


# ─── پیام‌های ذخیره‌شده ────────────────────────────────────────────────────────
def save_message_slot(owner_id: int, slot: int, content, media_path=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO saved_messages (owner_id, slot, content, media_path) VALUES (?, ?, ?, ?)",
        (owner_id, slot, content, media_path),
    )
    conn.commit()
    conn.close()


def get_message_slot(owner_id: int, slot: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM saved_messages WHERE owner_id = ? AND slot = ?", (owner_id, slot))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ─── پیام‌های حذف‌شده ─────────────────────────────────────────────────────────
def log_deleted_message(owner_id: int, chat_id, sender_id, sender_name, message, media_type=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO deleted_messages (owner_id, chat_id, sender_id, sender_name, message, media_type) VALUES (?, ?, ?, ?, ?, ?)",
        (owner_id, chat_id, sender_id, sender_name, message, media_type),
    )
    conn.commit()
    conn.close()


def get_deleted_messages(owner_id: int, limit=50):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM deleted_messages WHERE owner_id = ? ORDER BY deleted_at DESC LIMIT ?",
        (owner_id, limit),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ─── پیام‌های زمان‌بندی‌شده ───────────────────────────────────────────────────
def add_scheduled_message(owner_id: int, chat_id, message, send_at):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO scheduled_messages (owner_id, chat_id, message, send_at) VALUES (?, ?, ?, ?)",
        (owner_id, chat_id, message, send_at),
    )
    last_id = c.lastrowid
    conn.commit()
    conn.close()
    return last_id


def get_pending_scheduled(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM scheduled_messages WHERE owner_id = ? AND sent = 0 AND send_at <= datetime('now') ORDER BY send_at",
        (owner_id,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_scheduled_sent(msg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE scheduled_messages SET sent = 1 WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
