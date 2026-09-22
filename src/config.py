"""
BGSBU Interacts - Application Configuration
=============================================
Central configuration class for the Flask application. All settings are
loaded from environment variables (via a .env file) with sensible
defaults for local development.

Secrets and environment-specific overrides should be placed in a .env
file at the project root and must never be committed to version control.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env at the project root
load_dotenv()


class Config:
    """
    Flask configuration class. Each attribute is consumed by Flask
    itself (e.g. SECRET_KEY) or by custom application code.
    """

    # ==================== SECURITY ====================
    # Flask's secret key used for signing session cookies and CSRF tokens.
    # Override with a strong random value in production.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret-key')

    # ==================== DATABASE ====================
    # MySQL connection parameters; populate via .env for sensitive values.
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'bgsbu_interacts')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))

    # ==================== FILE UPLOADS ====================
    # Directory where uploaded files (images, documents, etc.) are stored.
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    # Maximum allowed upload size: 5 MB
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    # File extensions that are permitted for upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip', 'pptx', 'xlsx'}

    # ==================== SESSION ====================
    # Store session data on the server filesystem instead of signed cookies
    SESSION_TYPE = 'filesystem'
    # Session lifetime: 1 hour (in seconds)
    PERMANENT_SESSION_LIFETIME = 3600
    # Set to True in production when serving over HTTPS
    SESSION_COOKIE_SECURE = False
    # Prevent client-side JavaScript from accessing the session cookie
    SESSION_COOKIE_HTTPONLY = True
    # SameSite=Lax provides CSRF protection for most cross-origin flows
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ==================== APPLICATION ====================
    # Public-facing base URL of the application
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')
    # Debug mode on/off
    DEBUG = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes')
    # Flask environment (development / production)
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')

    # ==================== EMAIL (SMTP) ====================
    # SMTP server details for sending emails when the Brevo API is unavailable
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'your_email@gmail.com')

    # ==================== BREVO (SENDINBLUE) API ====================
    # API key for the Brevo transactional email service (preferred over SMTP)
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')

    # ==================== ADMIN CREDENTIALS ====================
    # Default admin login; change immediately in production via .env
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@demo.com')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123')

    # ==================== OTP & TOKENS ====================
    # Time window (minutes) during which an OTP remains valid
    OTP_EXPIRY_MINUTES = 10
    # Time window (minutes) during which a password-reset token remains valid
    PASSWORD_RESET_EXPIRY_MINUTES = 30

    # ==================== MISCELLANEOUS ====================
    # URL scheme hint used in URL generation (auto-switches to https in production)
    PREFERRED_URL_SCHEME = 'https' if FLASK_ENV == 'production' else 'http'
