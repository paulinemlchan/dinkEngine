import os

from werkzeug.security import generate_password_hash

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# Default password is "changeme123" unless overridden via the ADMIN_PASSWORD env var.
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "changeme123"))

DATABASE = os.environ.get("DATABASE", os.path.join(os.path.dirname(__file__), "dinkengine.sqlite3"))

MAX_PLAYERS = 32
MAX_COURTS = 20
MAX_MATCHES_PER_COURT = 5
MAX_EXCEPTIONS = 5

THEME_BANNER_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads", "theme_banners")
THEME_BANNER_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB cap on any upload, including theme banners
