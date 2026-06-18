import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "amel_self55_secret_key_change_me")
PORT = int(os.environ.get("PORT", 5000))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "amel.db")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_TG_ID = int(os.environ.get("OWNER_TG_ID", "8296865861"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "amele55")
# شماره تلفن مالک برای تشخیص قطعی (مثال: +989123456789)
OWNER_PHONE = os.environ.get("OWNER_PHONE", "").lstrip("+")
# اگر SITE_URL تنظیم نشده، از hostname خودکار Render تشخیص بده
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
SITE_URL = os.environ.get("SITE_URL", f"https://{_render_host}" if _render_host else "")

BOT_NAME = "AMEL SELF55"
BOT_VERSION = "1.2.0"

WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

TOKENS_PER_SESSION = 2
SESSION_HOURS = 2
DAILY_TOKEN_GIFT = 1
REFERRAL_TOKENS = 50
WELCOME_TOKENS = 10
