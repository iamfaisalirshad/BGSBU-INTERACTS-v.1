"""
BGSBU Interacts - Application Factory
=======================================
This module contains the Flask application factory (create_app) that
assembles all components of the platform: database connection pool,
blueprint registration, CSRF protection, security headers, context
processors, route definitions, and error handlers.
"""

import os
from datetime import datetime
from flask import Flask, redirect, url_for, session, render_template, request, send_from_directory, flash
from config import Config
from db import Database
from utils.security import CSRFProtection
from utils.auth_utils import bcrypt

# ==================== PATH CONFIGURATION ====================

# Resolve template and static directories relative to this file's location.
# This ensures Flask finds them regardless of the current working directory.
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
static_dir = os.path.join(os.path.dirname(__file__), 'static')


def create_app():
    """
    Application factory that creates, configures, and returns a fully
    assembled Flask application instance.

    Returns:
        Flask: The configured Flask application.
    """
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config.from_object(Config)

    # ==================== EXTENSION INITIALIZATION ====================

    # Initialize Flask-Bcrypt for password hashing
    bcrypt.init_app(app)

    # Create upload directories if they do not already exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    upload_images = os.path.join(app.config['UPLOAD_FOLDER'], 'images')
    os.makedirs(upload_images, exist_ok=True)

    # ==================== DATABASE CONNECTION POOL ====================

    try:
        Database.initialize_pool()
    except Exception as e:
        print(f"Database initialization failed: {e}")
        print("Make sure MySQL is running and database 'bgsbu_interacts' exists.")

    # ==================== ADMIN ACCOUNT BOOTSTRAP ====================

    def ensure_admin_exists():
        """
        Create the default administrator account in the database if one
        does not already exist. This runs once at startup.
        """
        try:
            from utils.auth_utils import hash_password
            admin_email = app.config.get('ADMIN_EMAIL', Config.ADMIN_EMAIL)
            admin_exists = Database.execute_query(
                "SELECT id FROM users WHERE email = %s",
                (admin_email,), fetch_one=True
            )
            if not admin_exists:
                with app.app_context():
                    admin_password = hash_password(app.config.get('ADMIN_PASSWORD', Config.ADMIN_PASSWORD))
                Database.execute_query(
                    """INSERT INTO users (role, name, email, password, phone, is_active, is_approved, email_verified_at)
                       VALUES ('admin', 'Administrator', %s, %s, '+91-0000000000', TRUE, TRUE, NOW())""",
                    (admin_email, admin_password), commit=True
                )
        except Exception as e:
            print(f"[WARNING] Could not ensure admin account: {e}")

    ensure_admin_exists()

    # ==================== BLUEPRINT REGISTRATION ====================

    # Import route blueprints after app creation to avoid circular imports
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.profile import profile_bp
    from routes.directory import directory_bp
    from routes.connections import connections_bp
    from routes.chat import chat_bp
    from routes.jobs import jobs_bp
    from routes.mentorship import mentorship_bp
    from routes.admin import admin_bp
    from routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(directory_bp)
    app.register_blueprint(connections_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(mentorship_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notifications_bp)

    # ==================== GLOBAL REQUEST HOOKS ====================

    @app.before_request
    def before_request():
        """
        Run before every request. Ensures a CSRF token exists in the
        session and validates CSRF tokens on state-changing methods
        (POST, PUT, DELETE), except for authentication-related routes.
        """
        from flask import request, jsonify

        # Ensure a CSRF token is always present in the user's session
        if '_csrf_token' not in session:
            session['_csrf_token'] = CSRFProtection.generate_token()
            session['_csrf_token_time'] = datetime.now().isoformat()

        # Routes that are exempt from CSRF validation (auth endpoints
        # that do not yet have an established session, and JSON API
        # endpoints already protected by @login_required)
        exempt_routes = [
            'auth.login', 'auth.register', 'auth.verify_otp', 'auth.resend_otp',
            'auth.forgot_password', 'auth.reset_password', 'auth.check_email',
            'auth.verify_forgot_password_otp', 'auth.verify_password_change_otp'
        ]

        if request.method in ['POST', 'PUT', 'DELETE']:
            if request.endpoint not in exempt_routes:
                # Skip CSRF for JSON API endpoints — they are authenticated
                # via @login_required and have their own auth checks
                if request.is_json or (request.endpoint and request.endpoint.startswith('api.')):
                    return None
                # Read the CSRF token from the form data or request headers
                csrf_token = (
                    request.form.get('_csrf_token')
                    or request.headers.get('X-CSRF-Token')
                    or request.headers.get('X-CSRF-TOKEN')
                )

                if not csrf_token or not CSRFProtection.validate_token(csrf_token):
                    if request.is_json:
                        return jsonify({'success': False, 'message': 'CSRF token validation failed'}), 403
                    else:
                        from flask import flash
                        flash('Security validation failed. Please try again.', 'danger')
                        return redirect(request.referrer or url_for('index'))

    # ==================== TEMPLATE CONTEXT PROCESSORS ====================

    @app.context_processor
    def inject_csrf_token():
        """Make the CSRF token available to all templates as {{ csrf_token }}."""
        token = CSRFProtection.get_token_from_session()
        return dict(csrf_token=token)

    @app.context_processor
    def inject_user():
        """
        Make the currently logged-in user, unread notification count, and
        unread message count available to every template. Returns None
        for all values when no user is authenticated.
        """
        user = None
        notification_count = 0
        message_count = 0
        if 'user_id' in session:
            try:
                user = Database.execute_query(
                    "SELECT id, name, email, role, profile_pic FROM users WHERE id = %s",
                    (session['user_id'],), fetch_one=True
                )
                notification_count = Database.execute_query(
                    "SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0 AND type != 'new_message'",
                    (session['user_id'],), fetch_one=True
                )['count']
                message_count = Database.execute_query(
                    "SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = 0",
                    (session['user_id'],), fetch_one=True
                )['count']
            except Exception:
                # Silently degrade if the database query fails
                pass
        return dict(
            current_user=user,
            notification_count=notification_count,
            unread_messages=message_count
        )

    # ==================== SECURITY HEADERS ====================

    @app.after_request
    def add_security_headers(response):
        """
        Attach security-related HTTP headers to every response to
        protect against common web vulnerabilities (clickjacking,
        MIME sniffing, XSS, etc.). Also disables caching for
        authenticated pages (auth, dashboard, admin).
        """
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        # Disable browser caching for sensitive page groups
        if request.endpoint and any(
            x in request.endpoint for x in ['auth.', 'dashboard.', 'admin.']
        ):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response

    # ==================== ROUTE DEFINITIONS ====================

    @app.route('/')
    def index():
        """Landing page — always shows home.html regardless of login status."""
        return render_template('home.html')

    @app.route('/home')
    def home():
        """Landing page — always shows home.html regardless of login status."""
        return render_template('home.html')

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        """Serve uploaded files (profile pictures, documents, etc.) from the upload folder."""
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ==================== ERROR HANDLERS ====================

    @app.errorhandler(404)
    def not_found(e):
        """
        Handle 404 (Not Found) errors gracefully by redirecting
        authenticated users to the dashboard and unauthenticated
        users to the login page.
        """
        if 'user_id' in session:
            flash('Page not found.', 'warning')
            return redirect(url_for('dashboard.dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(500)
    def server_error(e):
        """
        Handle 500 (Internal Server Error) errors gracefully by
        flashing a generic error message and redirecting to an
        appropriate page.
        """
        flash('An error occurred. Please try again.', 'danger')
        if 'user_id' in session:
            return redirect(url_for('dashboard.dashboard'))
        return redirect(url_for('auth.login'))

    return app


# Entry point is now at root app.py — run `python app.py` from project root.
