import threading
import telebot
from telebot import types
import database as db
import config

_bot = None
BOT_USERNAME = None


def get_bot():
    return _bot


def start_token_bot():
    global _bot, BOT_USERNAME

    if not config.BOT_TOKEN:
        print("⚠️  BOT_TOKEN تنظیم نشده — ربات توکن غیرفعال است")
        return

    _bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML", threaded=False)

    try:
        me = _bot.get_me()
        BOT_USERNAME = me.username
        print(f"🤖 ربات توکن: @{BOT_USERNAME}")
    except Exception as e:
        print(f"❌ خطا در اتصال ربات توکن: {e}")
        _bot = None
        return

    # حذف webhook قبلی و پاک کردن pending updates (جلوگیری از خطای 409)
    import time as _time
    for attempt in range(3):
        try:
            _bot.delete_webhook(drop_pending_updates=True)
            print(f"🧹 Webhook حذف شد (تلاش {attempt+1})")
            _time.sleep(5)  # صبر کافی برای قطع اتصال قدیمی
            break
        except Exception as e:
            print(f"⚠️ delete_webhook (تلاش {attempt+1}): {e}")
            _time.sleep(3)

    # ─── /start ─────────────────────────────────────────────────────────────
    @_bot.message_handler(commands=["start"])
    def cmd_start(message):
        tg_id = message.from_user.id
        parts = message.text.strip().split()
        ref_code = parts[1] if len(parts) > 1 else None

        if ref_code and ref_code.startswith("ref_"):
            try:
                referrer_id = int(ref_code[4:])
                if db.process_referral(referrer_id, tg_id):
                    referrer_tg = db.get_telegram_id_by_owner(referrer_id)
                    if referrer_tg:
                        try:
                            _bot.send_message(
                                referrer_tg,
                                f"🎉 یک نفر با لینک رفرال شما عضو شد!\n"
                                f"<b>+{config.REFERRAL_TOKENS} توکن</b> دریافت کردید 🪙",
                            )
                        except Exception:
                            pass
            except (ValueError, Exception):
                pass

        site_url = getattr(config, "SITE_URL", "")

        account = db.get_account_by_tg_id(tg_id)
        if not account:
            markup = types.InlineKeyboardMarkup()
            if site_url:
                markup.add(
                    types.InlineKeyboardButton(
                        "🌐 ورود به پنل AMEL SELF55",
                        url=site_url,
                    )
                )
            _bot.reply_to(
                message,
                "👋 <b>سلام!</b>\n\n"
                "برای استفاده از ربات توکن:\n"
                "1️⃣ در پنل <b>AMEL SELF55</b> ثبت‌نام کنید\n"
                "2️⃣ حساب تلگرام خود را وصل کنید\n"
                "3️⃣ دوباره /start بزنید\n\n"
                "📌 هر ۲ توکن = ۲ ساعت سلف‌بات روشن",
                reply_markup=markup if site_url else None,
            )
            return

        stats = db.get_token_stats(account["id"])
        markup = _main_keyboard()
        site_markup = types.InlineKeyboardMarkup()
        if site_url:
            site_markup.add(
                types.InlineKeyboardButton(
                    "🌐 باز کردن پنل مدیریت",
                    url=site_url,
                )
            )
        _bot.reply_to(
            message,
            f"👋 سلام <b>{account['username']}</b>!\n\n"
            f"🪙 موجودی: <b>{stats['balance']}</b> توکن\n"
            f"📊 کل دریافتی: <b>{stats['total_earned']}</b> توکن\n\n"
            f"⚡ هر <b>۲ توکن</b> = <b>۲ ساعت</b> سلف‌بات روشن",
            reply_markup=markup,
        )
        if site_url:
            _bot.send_message(
                message.chat.id,
                "🔗 از دکمه زیر به پنل دسترسی داشته باشید:",
                reply_markup=site_markup,
            )

    # ─── موجودی ─────────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("💰 موجودی", "/balance"))
    @_bot.message_handler(commands=["balance"])
    def cmd_balance(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد. ابتدا در پنل وصل شوید.")
            return
        stats = db.get_token_stats(account["id"])
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(
            message,
            f"🪙 <b>موجودی توکن</b>\n\n"
            f"💰 موجودی فعلی: <b>{stats['balance']}</b>\n"
            f"📊 کل دریافتی: <b>{stats['total_earned']}</b>\n"
            f"👥 رفرال‌ها: <b>{ref_count}</b> نفر\n\n"
            f"⚡ هر ۲ توکن = ۲ ساعت سلف روشن",
        )

    # ─── هدیه روزانه ────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🎁 هدیه روزانه", "/daily"))
    @_bot.message_handler(commands=["daily"])
    def cmd_daily(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد.")
            return
        success, msg = db.claim_daily_token(account["id"])
        if success:
            stats = db.get_token_stats(account["id"])
            _bot.reply_to(message, f"{msg}\n\n💰 موجودی جدید: <b>{stats['balance']}</b> توکن")
        else:
            _bot.reply_to(message, msg)

    # ─── رفرال ──────────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🔗 رفرال", "/referral"))
    @_bot.message_handler(commands=["referral"])
    def cmd_referral(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد.")
            return
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{account['id']}"
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(
            message,
            f"🔗 <b>لینک رفرال شما:</b>\n"
            f"<code>{link}</code>\n\n"
            f"👥 تعداد رفرال‌ها: <b>{ref_count}</b> نفر\n"
            f"🎁 هر رفرال = <b>{config.REFERRAL_TOKENS}</b> توکن\n\n"
            f"لینک را کپی کرده و برای دوستانتان بفرستید!",
        )

    # ─── خرید توکن ──────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🛒 خرید توکن", "/buy"))
    @_bot.message_handler(commands=["buy"])
    def cmd_buy(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        username_txt = account["username"] if account else str(message.from_user.id)

        markup = types.InlineKeyboardMarkup()
        if config.OWNER_USERNAME:
            markup.add(
                types.InlineKeyboardButton("📩 پیوی مالک", url=f"https://t.me/{config.OWNER_USERNAME}")
            )

        _bot.reply_to(
            message,
            f"🛒 <b>خرید توکن</b>\n\n"
            f"برای خرید توکن به مالک پیام بدید.\n"
            f"👤 یوزرنیم پنل شما: <b>{username_txt}</b>\n\n"
            f"💰 قیمت‌ها توسط مالک تعیین می‌شود.",
            reply_markup=markup if config.OWNER_USERNAME else None,
        )

    # ─── دستور /give (فقط مالک) ─────────────────────────────────────────────
    @_bot.message_handler(commands=["give"])
    def cmd_give(message):
        if message.from_user.id != config.OWNER_TG_ID:
            return
        parts = message.text.strip().split()
        if len(parts) < 3:
            _bot.reply_to(message, "📝 فرمت: /give [آیدی یا یوزرنیم پنل] [مقدار]\nمثال: /give 5 100")
            return
        target = parts[1].lstrip("@")
        try:
            amount = int(parts[2])
        except ValueError:
            _bot.reply_to(message, "❌ مقدار باید عدد باشد.")
            return
        if amount <= 0:
            _bot.reply_to(message, "❌ مقدار باید بزرگ‌تر از صفر باشد.")
            return

        account = None
        if target.isdigit():
            account = db.get_account(int(target))
        if not account:
            account = db.get_account_by_username(target)

        if not account:
            _bot.reply_to(message, f"❌ کاربر '{target}' پیدا نشد.")
            return

        db.add_tokens(account["id"], amount)
        new_balance = db.get_token_balance(account["id"])
        _bot.reply_to(
            message,
            f"✅ <b>{amount}</b> توکن به <b>{account['username']}</b> داده شد.\n"
            f"💰 موجودی جدید: <b>{new_balance}</b>",
        )
        tg_id = db.get_telegram_id_by_owner(account["id"])
        if tg_id:
            try:
                _bot.send_message(
                    tg_id,
                    f"🎁 <b>{amount}</b> توکن از طرف مالک دریافت کردید!\n"
                    f"💰 موجودی جدید: <b>{new_balance}</b> توکن",
                )
            except Exception:
                pass

    # ─── دستور /users (فقط مالک - لیست کاربران) ────────────────────────────
    @_bot.message_handler(commands=["users"])
    def cmd_users(message):
        if message.from_user.id != config.OWNER_TG_ID:
            return
        accounts = db.get_all_accounts()
        if not accounts:
            _bot.reply_to(message, "هیچ کاربری ثبت نشده.")
            return
        lines = [f"👥 <b>کاربران ({len(accounts)} نفر):</b>\n"]
        for acc in accounts[:20]:
            bal = db.get_token_balance(acc["id"])
            lines.append(f"• <b>{acc['username']}</b> — ID:{acc['id']} — 🪙{bal}")
        _bot.reply_to(message, "\n".join(lines))

    # ─── پیام‌های متنی ناشناخته ──────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: True)
    def cmd_unknown(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            return
        markup = _main_keyboard()
        _bot.reply_to(message, "از دکمه‌های زیر استفاده کنید:", reply_markup=markup)

    def _polling_loop():
        import time as _t
        while True:
            try:
                _bot.infinity_polling(
                    timeout=30,
                    long_polling_timeout=25,
                    restart_on_change=False,
                    skip_pending=True,
                )
            except Exception as e:
                err_str = str(e)
                if "409" in err_str or "Conflict" in err_str:
                    print("⚠️ تعارض polling (409) — ۱۰ ثانیه صبر...")
                    _t.sleep(10)
                    try:
                        _bot.delete_webhook(drop_pending_updates=True)
                        _t.sleep(2)
                    except Exception:
                        pass
                else:
                    print(f"⚠️ خطای polling: {e} — ۵ ثانیه صبر...")
                    _t.sleep(5)

    t = threading.Thread(target=_polling_loop, daemon=True)
    t.start()
    print(f"✅ ربات توکن @{BOT_USERNAME} استارت شد.")


def _main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 موجودی", "🎁 هدیه روزانه")
    markup.add("🔗 رفرال", "🛒 خرید توکن")
    return markup
