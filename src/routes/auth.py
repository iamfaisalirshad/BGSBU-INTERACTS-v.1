"""
Authentication & Authorization Routes
=======================================
Handles user registration, login, logout, email/OTP verification,
password reset, and password change flows. All auth-related endpoints
are registered under the 'auth' Blueprint.

Routes are protected by rate limiting (via utils.security.rate_limiter)
and audit logging (via utils.audit_logger.AuditLogger).
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import Database
from utils.auth_utils import (
    hash_password, check_password, validate_email,
    validate_password_strength, validate_name, validate_phone, validate_academic_years
)
from utils.decorators import login_required
from utils.email_service import EmailService, OTPService
from utils.security import rate_limiter, get_client_ip, validate_email_format, check_duplicate_email
from utils.audit_logger import AuditLogger
from constants import ALL_DEPARTMENTS, DEGREE_SEMESTERS
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


# ==================== USER REGISTRATION ====================

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handle new user registration.

    GET:  Render registration form with department list.
    POST: Validate all input fields, hash password, generate OTP,
          insert user record (with is_approved=0 for alumni), and
          redirect to OTP verification.

    Returns:
        Redirect to dashboard if already logged in, otherwise
        renders register.html (GET) or redirects to verify_otp (POST).
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    departments = ALL_DEPARTMENTS

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'student')
        department = request.form.get('department', '').strip()
        joining_year = request.form.get('joining_year', '')
        passing_year = request.form.get('passing_year', '')
        phone = request.form.get('phone', '').strip()
        roll_number = request.form.get('roll_number', '').strip()
        semester = request.form.get('semester', '')
        degree_completed = request.form.get('degree_completed') == '1'
        currently_studying = request.form.get('currently_studying') == '1'

        errors = []

        # Validate name
        valid_name, name_msg = validate_name(name)
        if not valid_name:
            errors.append(name_msg)

        # Validate email
        if not validate_email(email):
            errors.append('Invalid email address.')

        # Check if email already exists
        existing = Database.execute_query("SELECT id FROM users WHERE email = %s", (email,), fetch_one=True)
        if existing:
            errors.append('Email already registered.')

        # Validate password strength
        valid_pwd, pwd_msg = validate_password_strength(password)
        if not valid_pwd:
            errors.append(pwd_msg)

        if password != confirm_password:
            errors.append('Passwords do not match.')

        if role not in ['student', 'alumni']:
            errors.append('Invalid role.')

        # Check if department is valid
        valid_dept = False
        for depts in ALL_DEPARTMENTS.values():
            if department in depts:
                valid_dept = True
                break

        if not department or not valid_dept:
            errors.append('Please select a valid department.')

        # Validate academic years
        valid_years, years_msg = validate_academic_years(joining_year, passing_year)
        if not valid_years:
            errors.append(years_msg)

        # Validate phone
        valid_phone, phone_msg = validate_phone(phone)
        if not valid_phone:
            errors.append(phone_msg)

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html', departments=departments, degree_semesters=DEGREE_SEMESTERS)

        hashed = hash_password(password)
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        otp_sent_at = datetime.now()
        EmailService.send_otp_email(email, otp, name, session)

        # All users require admin approval
        is_approved = 0

        try:
            jy = int(joining_year) if joining_year else None
            py = int(passing_year) if passing_year else None
            sem = int(semester) if semester else None
            if degree_completed:
                sem = 0
                currently_studying = False
            user_id = Database.execute_query(
                """INSERT INTO users (name, email, password, role, department, phone, is_approved)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (name, email, hashed, role, department, phone, is_approved), commit=True)
            if role == 'student':
                Database.execute_query(
                    """INSERT INTO student_profiles (user_id, roll_number, joining_year, passing_year, student_year, currently_studying, internships, projects)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, roll_number, jy, py, sem, 1 if currently_studying else 0, '', ''), commit=True)
                if sem == 0:
                    admins = Database.execute_query("SELECT id FROM users WHERE role='admin'", fetch_all=True)
                    if admins:
                        for a in admins:
                            Database.execute_query(
                                "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'graduation_request', 'Degree Completion Request', %s, %s)",
                                (a['id'], f'{name} has marked Degree Completed and requests alumni conversion.', url_for('admin.admin_transformation_requests', _external=True)),
                                commit=True)
            Database.execute_query(
                """INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at)
                   VALUES (%s, %s, 'email_verification', %s)""",
                (user_id, otp_hash, otp_sent_at + timedelta(minutes=10)), commit=True)
            session['pending_user_id'] = user_id
            session['pending_email'] = email
            flash('Registration successful! Please verify OTP.', 'success')
            return redirect(url_for('auth.verify_otp'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')

    return render_template('register.html', departments=departments, degree_semesters=DEGREE_SEMESTERS)


# ==================== OTP / EMAIL VERIFICATION ====================

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    """
    Verify email via OTP during registration.

    GET:  Render OTP input form.
    POST: Validate OTP against stored hash with rate limiting.
          On success: clear pending session keys, auto-login user.
          On failure: increment rate-limit counter, stay on page.

    Returns:
        Redirect to register if no pending_user_id in session,
        otherwise renders verify_otp.html or redirects to dashboard.
    """
    if 'pending_user_id' not in session:
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        user_id = session.get('pending_user_id')

        if not user_id:
            flash('Session expired. Please login again.', 'danger')
            return redirect(url_for('auth.login'))

        client_ip = get_client_ip(request)
        otp_limiter_key = f"{client_ip}:{user_id}:otp-verify"

        # Rate limiting: Allow 5 OTP attempts per 15 minutes
        if rate_limiter.is_rate_limited(otp_limiter_key):
            remaining = rate_limiter.get_remaining_time(otp_limiter_key)
            flash(f'Too many OTP attempts. Try again in {remaining} seconds.', 'danger')
            return render_template('verify_otp.html', email=session.get('pending_email', ''))

        # Get OTP record
        otp_record = Database.execute_query(
            "SELECT id, otp_hash, expires_at, attempts FROM user_otps WHERE user_id = %s AND purpose = 'email_verification' AND is_used = 0 ORDER BY id DESC LIMIT 1",
            (user_id,), fetch_one=True)
        if not otp_record:
            flash('No OTP found. Please register again.', 'danger')
            return redirect(url_for('auth.register'))

        # Check if OTP is expired
        if datetime.now() > otp_record['expires_at']:
            flash('OTP has expired. Please request a new one.', 'danger')
            return render_template('verify_otp.html', email=session.get('pending_email', ''))

        # Verify OTP against stored hash
        if OTPService.verify_otp(otp_record['otp_hash'], otp_input):
            Database.execute_query(
                "UPDATE user_otps SET is_used = 1 WHERE id = %s",
                (otp_record['id'],), commit=True)
            Database.execute_query(
                "UPDATE users SET email_verified_at = NOW() WHERE id = %s",
                (user_id,), commit=True)

            # Clear session and rate limit on success
            session.pop('pending_user_id', None)
            session.pop('pending_email', None)
            session.pop('otp_sent_time', None)
            rate_limiter.clear_attempts(otp_limiter_key)

            # Auto-login after verification
            user = Database.execute_query("SELECT * FROM users WHERE id = %s", (user_id,), fetch_one=True)
            if user and user['is_approved'] and user['is_active']:
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['role'] = user['role']
                session['email'] = user['email']
                flash('Email verified! Welcome to BGSBU Interacts!', 'success')
                if user['role'] == 'admin':
                    return redirect(url_for('admin.admin_dashboard'))
                return redirect(url_for('dashboard.dashboard'))
            else:
                flash('Email verified! Please login.', 'success')
                return redirect(url_for('auth.login'))
        else:
            Database.execute_query(
                "UPDATE user_otps SET attempts = attempts + 1 WHERE id = %s",
                (otp_record['id'],), commit=True)
            flash('Invalid OTP.', 'danger')
            rate_limiter.record_attempt(otp_limiter_key)

    return render_template('verify_otp.html', email=session.get('pending_email', ''))


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """
    Resend OTP for any pending flow (registration, password change, forgot password).

    Checks session keys to determine which flow is active:
        - pending_user_id         → registration OTP
        - password_change_user_id → password change OTP
        - forgot_password_user_id → forgot-password OTP

    Returns:
        Redirect to the appropriate OTP verification page.
    """
    if 'pending_user_id' in session:
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        user_id = session['pending_user_id']
        Database.execute_query(
            "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'email_verification'",
            (user_id,), commit=True)
        Database.execute_query(
            "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'email_verification', %s)",
            (user_id, otp_hash, datetime.now() + timedelta(minutes=10)), commit=True)
        user = Database.execute_query("SELECT name, email FROM users WHERE id = %s", (user_id,), fetch_one=True)
        if user:
            EmailService.send_otp_email(user['email'], otp, user['name'], session)
        return redirect(url_for('auth.verify_otp'))
    elif 'password_change_user_id' in session:
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        user_id = session['password_change_user_id']
        Database.execute_query(
            "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'password_change'",
            (user_id,), commit=True)
        Database.execute_query(
            "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'password_change', %s)",
            (user_id, otp_hash, datetime.now() + timedelta(minutes=10)), commit=True)
        user = Database.execute_query("SELECT name, email FROM users WHERE id = %s", (user_id,), fetch_one=True)
        if user:
            EmailService.send_otp_email(user['email'], otp, user['name'], session)
        return redirect(url_for('auth.verify_password_change_otp'))
    elif 'forgot_password_user_id' in session:
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        user_id = session['forgot_password_user_id']
        Database.execute_query(
            "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'password_reset'",
            (user_id,), commit=True)
        Database.execute_query(
            "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'password_reset', %s)",
            (user_id, otp_hash, datetime.now() + timedelta(minutes=10)), commit=True)
        user = Database.execute_query("SELECT name, email FROM users WHERE id = %s", (user_id,), fetch_one=True)
        if user:
            EmailService.send_password_reset_email(user['email'], otp, user['name'], session)
        return redirect(url_for('auth.verify_forgot_password_otp'))
    return redirect(url_for('auth.register'))


# ==================== LOGIN & LOGOUT ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Authenticate existing users with role-gated login.

    GET:  Clear any stale session, read ?role=student|alumni|admin, render form.
    POST: Validate credentials + enforce role match.
          Blocks:
          - Empty email/password
          - Invalid credentials
          - Unverified email (redirect to OTP)
          - Unapproved account
          - Deactivated account
          - Role mismatch (student trying alumni login, etc.)

    Returns:
        Renders login.html with role context or redirects on success.
    """
    login_role = request.args.get('role', '') or request.form.get('login_role', '')

    # Clear any stale session on GET so previous cookies dont auto-login
    if request.method == 'GET':
        if 'user_id' in session:
            session.clear()
        # Require a role parameter — no role = redirect to home
        if not login_role:
            return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('user_email', '').strip().lower()
        password = request.form.get('user_pass', '')
        client_ip = get_client_ip(request)

        # Rate limiting
        if rate_limiter.is_rate_limited(client_ip):
            remaining = rate_limiter.get_remaining_time(client_ip)
            flash(f'Too many login attempts. Try again in {remaining} seconds.', 'danger')
            return redirect(url_for('auth.login', role=login_role))

        if not email or not password:
            flash('Email and password required.', 'danger')
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('auth.login', role=login_role))

        if not validate_email_format(email):
            flash('Invalid email format.', 'danger')
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('auth.login', role=login_role))

        user = Database.execute_query("SELECT * FROM users WHERE email = %s", (email,), fetch_one=True)
        if not user:
            user = Database.execute_query("SELECT * FROM users WHERE LOWER(email) = LOWER(%s)", (email,), fetch_one=True)
            if not user:
                flash('Invalid email or password.', 'danger')
                AuditLogger.log_login_attempt(email, success=False, ip_address=client_ip, details='User not found')
                rate_limiter.record_attempt(client_ip)
                return redirect(url_for('auth.login', role=login_role))

        # Check password
        if not check_password(user['password'], password):
            flash('Invalid email or password.', 'danger')
            AuditLogger.log_login_attempt(email, success=False, ip_address=client_ip, details='Invalid password')
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('auth.login', role=login_role))

        # Enforce role gating — redirect to home so user picks the correct login
        if login_role and user['role'] != login_role:
            role_names = {'student': 'Student', 'alumni': 'Alumni', 'admin': 'Administrator'}
            flash(f'This login is for {role_names.get(login_role, login_role)} accounts only. Your account is registered as {role_names.get(user["role"], user["role"])}.', 'danger')
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('index'))

        if not user.get('email_verified_at'):
            session['pending_user_id'] = user['id']
            session['pending_email'] = user['email']
            otp = OTPService.generate_otp()
            otp_hash = OTPService.hash_otp(otp)
            Database.execute_query(
                "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'email_verification'",
                (user['id'],), commit=True)
            Database.execute_query(
                "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'email_verification', %s)",
                (user['id'], otp_hash, datetime.now() + timedelta(minutes=10)), commit=True)
            EmailService.send_otp_email(user['email'], otp, user['name'], session)
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('auth.verify_otp'))

        if not user['is_approved']:
            flash('Account pending admin approval.', 'warning')
            rate_limiter.record_attempt(client_ip)
            return redirect(url_for('auth.login', role=login_role))

        if not user['is_active']:
            flash('Account deactivated. Contact admin.', 'danger')
            AuditLogger.log_login_attempt(email, success=False, ip_address=client_ip, details='Account deactivated')
            return redirect(url_for('auth.login', role=login_role))

        rate_limiter.clear_attempts(client_ip)
        AuditLogger.log_login_attempt(email, success=True, ip_address=client_ip)

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['role'] = user['role']
        session['email'] = user['email']
        if user['role'] == 'admin':
            return redirect(url_for('admin.admin_dashboard'))
        return redirect(url_for('dashboard.dashboard'))

    return render_template('login.html', login_role=login_role)


@auth_bp.route('/logout')
def logout():
    """
    Log out the current user.

    Logs the logout event, clears the entire session, and redirects
    to the login page.

    Returns:
        Redirect to login page.
    """
    if 'user_id' in session:
        AuditLogger.log_event(AuditLogger.EVENT_LOGOUT, user_id=session['user_id'])
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


# ==================== PASSWORD RESET (FORGOT PASSWORD) ====================

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Initiate password reset flow for users who forgot their password.

    GET:  Render forgot-password form.
    POST: Validate email, check rate limit, generate OTP, store in DB,
          send reset email, and redirect to OTP verification page.
          Uses a generic message to avoid revealing whether the email exists.

    Returns:
        Redirect to dashboard if already logged in,
        otherwise renders forgot_password.html or redirects to verify_forgot_password_otp.
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        client_ip = get_client_ip(request)

        # Rate limiting: Allow 3 reset requests per IP per 15 minutes
        reset_limiter_key = f"{client_ip}:forgot-password"
        if rate_limiter.is_rate_limited(reset_limiter_key):
            remaining = rate_limiter.get_remaining_time(reset_limiter_key)
            flash(f'Too many reset attempts. Try again in {remaining} seconds.', 'warning')
            return render_template('forgot_password.html')

        if not validate_email_format(email):
            flash('Invalid email address.', 'danger')
            return render_template('forgot_password.html')

        user = Database.execute_query("SELECT id, name FROM users WHERE email = %s", (email,), fetch_one=True)
        if not user:
            # Don't reveal if email exists (security best practice)
            flash('If an account with this email exists, an OTP has been sent.', 'info')
            rate_limiter.record_attempt(reset_limiter_key)
            return render_template('forgot_password.html')

        # Generate OTP for password reset
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)

        # Save OTP in user_otps table
        Database.execute_query(
            "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'password_reset'",
            (user['id'],), commit=True)
        Database.execute_query(
            "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'password_reset', %s)",
            (user['id'], otp_hash, datetime.now() + timedelta(minutes=10)), commit=True
        )

        # Send OTP email
        EmailService.send_password_reset_email(email, otp, user['name'], session)
        session['forgot_password_user_id'] = user['id']
        session['forgot_password_email'] = email
        flash('An OTP has been sent to your email for password reset.', 'success')
        rate_limiter.record_attempt(reset_limiter_key)
        return redirect(url_for('auth.verify_forgot_password_otp'))

    return render_template('forgot_password.html')


@auth_bp.route('/verify-forgot-password-otp', methods=['GET', 'POST'])
def verify_forgot_password_otp():
    """
    Verify OTP for forgot password flow.

    GET:  Render OTP input form.
    POST: Validate OTP with rate limiting. On success, set
          pending_password_reset in session and redirect to reset_password.

    Returns:
        Redirect to forgot_password if no session data,
        otherwise renders verify_forgot_password_otp.html
        or redirects to reset_password.
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if 'forgot_password_user_id' not in session:
        return redirect(url_for('auth.forgot_password'))

    email = session.get('forgot_password_email', '')

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        user_id = session.get('forgot_password_user_id')

        if not user_id:
            flash('Session expired. Please try again.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        client_ip = get_client_ip(request)
        otp_limiter_key = f"{client_ip}:{user_id}:forgot-pwd-otp"

        # Rate limiting: Allow 5 OTP attempts per 15 minutes
        if rate_limiter.is_rate_limited(otp_limiter_key):
            remaining = rate_limiter.get_remaining_time(otp_limiter_key)
            flash(f'Too many OTP attempts. Try again in {remaining} seconds.', 'danger')
            return render_template('verify_forgot_password_otp.html', email=email)

        # Get OTP record
        otp_record = Database.execute_query(
            "SELECT id, otp_hash, expires_at, attempts FROM user_otps WHERE user_id = %s AND purpose = 'password_reset' AND is_used = 0 ORDER BY id DESC LIMIT 1",
            (user_id,), fetch_one=True)
        if not otp_record:
            flash('No OTP found. Please request a new one.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        # Check if OTP is expired
        if datetime.now() > otp_record['expires_at']:
            flash('OTP has expired. Please request a new one.', 'danger')
            return render_template('verify_forgot_password_otp.html', email=email)

        # Verify OTP
        if OTPService.verify_otp(otp_record['otp_hash'], otp_input):
            Database.execute_query(
                "UPDATE user_otps SET is_used = 1 WHERE id = %s",
                (otp_record['id'],), commit=True)

            # Set pending password reset in session
            session['pending_password_reset'] = user_id
            session.pop('forgot_password_user_id', None)
            session.pop('forgot_password_email', None)
            rate_limiter.clear_attempts(otp_limiter_key)

            return redirect(url_for('auth.reset_password'))
        else:
            Database.execute_query(
                "UPDATE user_otps SET attempts = attempts + 1 WHERE id = %s",
                (otp_record['id'],), commit=True)
            flash('Invalid OTP.', 'danger')
            rate_limiter.record_attempt(otp_limiter_key)

    return render_template('verify_forgot_password_otp.html', email=email)


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """
    Set a new password after forgot-password OTP verification.

    GET:  Render new-password form.
    POST: Validate password strength and match, update the password
          hash in the database, log the event, and redirect to login.

    Returns:
        Redirect to forgot_password if no pending_password_reset in session,
        otherwise renders reset_password.html or redirects to login on success.
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if 'pending_password_reset' not in session:
        flash('Unauthorized access. Please request a password reset.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validate password strength
        valid_pwd, pwd_msg = validate_password_strength(password)
        if not valid_pwd:
            flash(pwd_msg, 'danger')
            return render_template('reset_password.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html')

        # Update password
        hashed = hash_password(password)
        Database.execute_query(
            "UPDATE users SET password = %s WHERE id = %s",
            (hashed, session['pending_password_reset']), commit=True
        )

        AuditLogger.log_event(AuditLogger.EVENT_PASSWORD_RESET, user_id=session['pending_password_reset'])

        user_role = Database.execute_query(
            "SELECT role FROM users WHERE id=%s", (session['pending_password_reset'],), fetch_one=True)
        role_param = user_role['role'] if user_role else ''
        session.pop('pending_password_reset', None)

        flash('Password reset successful! Please login with your new password.', 'success')
        return redirect(url_for('auth.login', role=role_param))

    return render_template('reset_password.html')


# ==================== UTILITY ENDPOINTS ====================

@auth_bp.route('/clear-dev-otp', methods=['POST'])
def clear_dev_otp():
    """
    Clear development OTP from session (dev-only convenience endpoint).

    Returns:
        Redirect to the referring page or login.
    """
    session.pop('dev_otp', None)
    return redirect(request.referrer or url_for('auth.login'))


@auth_bp.route('/check-email', methods=['POST'])
def check_email():
    """
    AJAX endpoint to check if an email is already registered.

    Used by the registration form for real-time validation.

    Returns:
        JSON: {'exists': True/False}
    """
    email = request.json.get('email', '').strip().lower()
    existing = Database.execute_query("SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", (email,), fetch_one=True)
    return jsonify({'exists': existing is not None})


# ==================== CHANGE PASSWORD (LOGGED-IN USER) ====================

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Change password for an already logged-in user (requires OTP verification).

    GET:  Render change-password form.
    POST: Verify current password, validate new password strength and match,
          generate OTP, send OTP email, hash and temporarily store the new
          password in session, redirect to OTP verification step.

    Returns:
        Renders change_password.html or redirects to verify_password_change_otp.
    """
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Get user
        user = Database.execute_query("SELECT id, password, email, name FROM users WHERE id=%s",
                                      (session['user_id'],), fetch_one=True)

        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('dashboard.dashboard'))

        # Verify current password
        if not check_password(user['password'], current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')

        # Validate new password strength
        valid_pwd, pwd_msg = validate_password_strength(new_password)
        if not valid_pwd:
            flash(pwd_msg, 'danger')
            return render_template('change_password.html')

        # Check password match
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')

        # Check if new password is same as old
        if check_password(user['password'], new_password):
            flash('New password must be different from current password.', 'danger')
            return render_template('change_password.html')

        # Generate OTP for verification
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)

        # Store OTP in user_otps table
        Database.execute_query(
            "UPDATE user_otps SET is_used = 1 WHERE user_id = %s AND purpose = 'password_change'",
            (session['user_id'],), commit=True)
        Database.execute_query(
            "INSERT INTO user_otps (user_id, otp_hash, purpose, expires_at) VALUES (%s, %s, 'password_change', %s)",
            (session['user_id'], otp_hash, datetime.now() + timedelta(minutes=10)), commit=True)

        # Send OTP email for password change
        EmailService.send_password_change_otp_email(user['email'], otp, user['name'], session)

        # Store the new password temporarily (hashed) in session for verification
        session['pending_password_change'] = hash_password(new_password)
        session['password_change_user_id'] = session['user_id']

        return redirect(url_for('auth.verify_password_change_otp'))

    return render_template('change_password.html')


@auth_bp.route('/verify-password-change-otp', methods=['GET', 'POST'])
@login_required
def verify_password_change_otp():
    """
    Verify OTP for password change flow.

    GET:  Render OTP input form.
    POST: Validate OTP with rate limiting. On success, update the
          password in the database, clear session keys, and log event.

    Returns:
        Redirect to change_password if no pending_password_change in session,
        otherwise renders verify_password_change_otp.html
        or redirects to dashboard on success.
    """
    if 'pending_password_change' not in session:
        return redirect(url_for('auth.change_password'))

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        user_id = session.get('password_change_user_id')

        if not user_id:
            flash('Session expired. Please try again.', 'danger')
            return redirect(url_for('auth.change_password'))

        client_ip = get_client_ip(request)
        otp_limiter_key = f"{client_ip}:{user_id}:pwd-change-otp"

        # Rate limiting: Allow 5 OTP attempts per 15 minutes
        if rate_limiter.is_rate_limited(otp_limiter_key):
            remaining = rate_limiter.get_remaining_time(otp_limiter_key)
            flash(f'Too many OTP attempts. Try again in {remaining} seconds.', 'danger')
            return render_template('verify_password_change_otp.html')

        # Get OTP record
        otp_record = Database.execute_query(
            "SELECT id, otp_hash, expires_at, attempts FROM user_otps WHERE user_id = %s AND purpose = 'password_change' AND is_used = 0 ORDER BY id DESC LIMIT 1",
            (user_id,), fetch_one=True)
        if not otp_record:
            flash('No OTP found. Please try again.', 'danger')
            return redirect(url_for('auth.change_password'))

        # Check if OTP is expired
        if datetime.now() > otp_record['expires_at']:
            flash('OTP has expired. Please request a new one.', 'danger')
            return render_template('verify_password_change_otp.html')

        # Verify OTP against stored hash
        if OTPService.verify_otp(otp_record['otp_hash'], otp_input):
            # Update password
            new_hashed_password = session.get('pending_password_change')
            Database.execute_query("UPDATE users SET password=%s WHERE id=%s",
                (new_hashed_password, user_id), commit=True)
            Database.execute_query(
                "UPDATE user_otps SET is_used = 1 WHERE id = %s",
                (otp_record['id'],), commit=True)

            # Clear session
            session.pop('pending_password_change', None)
            session.pop('password_change_user_id', None)
            rate_limiter.clear_attempts(otp_limiter_key)

            # Log event
            AuditLogger.log_event(AuditLogger.EVENT_PASSWORD_CHANGE, user_id=user_id)

            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash('Invalid OTP.', 'danger')
            rate_limiter.record_attempt(otp_limiter_key)
            return render_template('verify_password_change_otp.html')

    return render_template('verify_password_change_otp.html')
