"""
Email communication and OTP services for BGSBU Interacts

Provides email sending via Brevo API or SMTP fallback, along with
OTP generation, hashing, and expiration checking utilities.
"""

import smtplib
import secrets
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from config import Config
import hashlib


# =============================================================================
# Email Service
# =============================================================================

class EmailService:
    """Handle all email communications for the application.

    Supports sending verification OTPs, password reset OTPs, and password
    change confirmation OTPs via the Brevo API (primary) with SMTP fallback.
    Falls back to printing OTPs to console in development environments when
    no mail backend is configured.
    """

    @staticmethod
    def send_otp_email(recipient_email: str, otp: str, name: str, session=None) -> bool:
        """Send email verification OTP to a newly registering user.

        Constructs an HTML email with the OTP prominently displayed. If the
        email cannot be sent (no backend configured), prints the OTP to the
        console for development purposes and optionally stores it in the
        Flask session for testing.

        Args:
            recipient_email (str): The recipient's email address.
            otp (str): The one-time password string.
            name (str): The recipient's display name for the greeting.
            session (Flask session, optional): If provided, stores the OTP
                in session['dev_otp'] as a development fallback.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Email Verification"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #007bff;">Welcome to BGSBU Interacts!</h2>
                        <p>Hello {name},</p>
                        <p>Your email verification OTP is:</p>
                        <div style="background-color: #007bff; color: white; padding: 15px; border-radius: 5px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 3px;">
                            {otp}
                        </div>
                        <p>This OTP will expire in 10 minutes.</p>
                        <p>If you didn't request this, please ignore this email.</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Team</strong></p>
                    </div>
                </body>
            </html>
            """

            result = EmailService._send_email(recipient_email, subject, body)
            if not result:
                print(f"\n[DEV] OTP for {recipient_email}: {otp}\n")
                if session:
                    session['dev_otp'] = otp
            return result
        except Exception as e:
            print(f"Error sending OTP email: {str(e)}")
            print(f"\n[DEV] OTP for {recipient_email}: {otp}\n")
            if session:
                session['dev_otp'] = otp
            return False

    @staticmethod
    def send_password_reset_email(recipient_email: str, otp: str, name: str, session=None) -> bool:
        """Send password reset OTP to a user requesting a password reset.

        Args:
            recipient_email (str): The recipient's email address.
            otp (str): The one-time password string.
            name (str): The recipient's display name for the greeting.
            session (Flask session, optional): If provided, stores the OTP
                in session['dev_otp'] as a development fallback.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Password Reset OTP"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #007bff;">Password Reset Request</h2>
                        <p>Hello {name},</p>
                        <p>We received a request to reset your password. Use the OTP below to proceed:</p>
                        <div style="background-color: #007bff; color: white; padding: 15px; border-radius: 5px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 3px;">
                            {otp}
                        </div>
                        <p>This OTP will expire in 10 minutes.</p>
                        <p>If you didn't request this, please ignore this email.</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Team</strong></p>
                    </div>
                </body>
            </html>
            """

            result = EmailService._send_email(recipient_email, subject, body)
            if not result:
                print(f"\n[DEV] Password Reset OTP for {recipient_email}: {otp}\n")
                if session:
                    session['dev_otp'] = otp
            return result
        except Exception as e:
            print(f"Error sending password reset email: {str(e)}")
            print(f"\n[DEV] Password Reset OTP for {recipient_email}: {otp}\n")
            if session:
                session['dev_otp'] = otp
            return False

    @staticmethod
    def send_password_change_otp_email(recipient_email: str, otp: str, name: str, session=None) -> bool:
        """Send OTP to verify a password change requested by an authenticated user.

        Args:
            recipient_email (str): The recipient's email address.
            otp (str): The one-time password string.
            name (str): The recipient's display name for the greeting.
            session (Flask session, optional): If provided, stores the OTP
                in session['dev_otp'] as a development fallback.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Confirm Password Change"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #007bff;">Password Change Verification</h2>
                        <p>Hello {name},</p>
                        <p>To confirm your password change, please use this OTP:</p>
                        <div style="background-color: #007bff; color: white; padding: 15px; border-radius: 5px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 3px;">
                            {otp}
                        </div>
                        <p>This OTP will expire in 10 minutes.</p>
                        <p>If you didn't request this, please ignore this email.</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Team</strong></p>
                    </div>
                </body>
            </html>
            """

            result = EmailService._send_email(recipient_email, subject, body)
            if not result:
                print(f"\n[DEV] Password Change OTP for {recipient_email}: {otp}\n")
                if session:
                    session['dev_otp'] = otp
            return result
        except Exception as e:
            print(f"Error sending password change OTP email: {str(e)}")
            print(f"\n[DEV] Password Change OTP for {recipient_email}: {otp}\n")
            if session:
                session['dev_otp'] = otp
            return False

    @staticmethod
    def _send_email(recipient: str, subject: str, body: str) -> bool:
        """Internal method to send emails via API or SMTP fallback.

        Tries the Brevo (formerly Sendinblue) transactional email API first
        if BREVO_API_KEY is configured. Falls back to standard SMTP using
        MAIL_USERNAME / MAIL_PASSWORD if those are set and not default
        placeholder values.

        Args:
            recipient (str): The recipient email address.
            subject (str): The email subject line.
            body (str): The HTML body content of the email.

        Returns:
            bool: True if the email was sent successfully via any channel;
                  False otherwise.
        """
        try:
            # Send using Brevo API if configured
            if Config.BREVO_API_KEY:
                import requests
                url = "https://api.brevo.com/v3/smtp/email"
                headers = {
                    "accept": "application/json",
                    "api-key": Config.BREVO_API_KEY,
                    "content-type": "application/json"
                }
                payload = {
                    "sender": {"name": "BGSBU Interacts", "email": Config.MAIL_DEFAULT_SENDER},
                    "to": [{"email": recipient}],
                    "subject": subject,
                    "htmlContent": body
                }

                response = requests.post(url, json=payload, headers=headers)
                if response.status_code in [200, 201, 202]:
                    return True
                else:
                    print(f"API Email Error: {response.text}")

            # Fallback to standard SMTP if username/password exist
            if Config.MAIL_USERNAME and Config.MAIL_PASSWORD and not Config.MAIL_USERNAME.startswith('your-'):
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = Config.MAIL_DEFAULT_SENDER
                msg['To'] = recipient
                msg.attach(MIMEText(body, 'html'))

                server = smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT, timeout=10)
                if Config.MAIL_USE_TLS:
                    server.starttls()
                server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                server.sendmail(Config.MAIL_DEFAULT_SENDER, recipient, msg.as_string())
                server.quit()
                return True

            else:
                print(f"Error: Email credentials/API not configured. Cannot send to {recipient}")
                return False

        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False

    @staticmethod
    def send_account_approved_email(recipient_email: str, name: str) -> bool:
        """Send approval confirmation email to a newly approved user.

        Args:
            recipient_email (str): The recipient's email address.
            name (str): The recipient's display name for the greeting.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Account Approved!"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #28a745;">Welcome to BGSBU Interacts!</h2>
                        <p>Hello {name},</p>
                        <p>Great news! Your account has been <strong>approved by our admin team</strong>.</p>
                        <p>You can now log in and start exploring the platform:</p>
                        <ul style="margin: 20px 0;">
                            <li>Connect with other students and alumni</li>
                            <li>Browse job opportunities and internships</li>
                            <li>Seek mentorship from experienced professionals</li>
                            <li>Share your experiences and help others</li>
                        </ul>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="http://localhost:5000/login" style="background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">Login Now</a>
                        </div>
                        <p>If you have any questions, feel free to reach out to our support team.</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Admin Team</strong></p>
                    </div>
                </body>
            </html>
            """
            return EmailService._send_email(recipient_email, subject, body)
        except Exception as e:
            print(f"Error sending account approved email: {str(e)}")
            return False

    @staticmethod
    def send_job_approved_email(recipient_email: str, name: str, job_title: str, company: str) -> bool:
        """Send job posting approval confirmation email to alumni.

        Args:
            recipient_email (str): The recipient's email address.
            name (str): The recipient's display name for the greeting.
            job_title (str): The title of the approved job.
            company (str): The company name.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Job Posting Approved!"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #28a745;">Job Posting Approved!</h2>
                        <p>Hello {name},</p>
                        <p>Excellent news! Your job posting has been <strong>approved and is now live</strong>.</p>
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                            <p><strong>Job Title:</strong> {job_title}</p>
                            <p><strong>Company:</strong> {company}</p>
                        </div>
                        <p>Your job is now visible to all students and alumni on the platform. You can expect applications to start coming in soon!</p>
                        <p>You can manage your job posting and view applications from your dashboard.</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Team</strong></p>
                    </div>
                </body>
            </html>
            """
            return EmailService._send_email(recipient_email, subject, body)
        except Exception as e:
            print(f"Error sending job approved email: {str(e)}")
            return False

    @staticmethod
    def send_transformation_approved_email(recipient_email: str, name: str) -> bool:
        """Send account transformation approval email (student to alumni conversion).

        Args:
            recipient_email (str): The recipient's email address.
            name (str): The recipient's display name for the greeting.

        Returns:
            bool: True if the email was sent successfully; False otherwise.
        """
        try:
            subject = "BGSBU Interacts - Account Transformation Approved!"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #28a745;">Congratulations!</h2>
                        <p>Hello {name},</p>
                        <p>Congratulations on your graduation! Your account has been <strong>successfully converted from Student to Alumni</strong>.</p>
                        <p>As an alumnus, you now have access to exclusive features:</p>
                        <ul style="margin: 20px 0;">
                            <li>Post job opportunities and internships</li>
                            <li>Mentor current students and guide their careers</li>
                            <li>Connect with fellow alumni</li>
                            <li>Share your professional experiences</li>
                            <li>Access alumni-only resources and groups</li>
                        </ul>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="http://localhost:5000/dashboard" style="background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">Go to Dashboard</a>
                        </div>
                        <p>Welcome to the BGSBU alumni community!</p>
                        <p>Best regards,<br><strong>BGSBU Interacts Team</strong></p>
                    </div>
                </body>
            </html>
            """
            return EmailService._send_email(recipient_email, subject, body)
        except Exception as e:
            print(f"Error sending transformation approved email: {str(e)}")
            return False


# =============================================================================
# OTP Service
# =============================================================================

class OTPService:
    """Handle OTP generation, hashing, and expiration validation.

    Generates cryptographically secure numeric OTPs and URL-safe reset
    tokens, hashes OTPs with SHA-256 for secure database storage, and
    provides expiration checking with timezone-aware datetime handling.
    """

    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """Generate a cryptographically secure numeric OTP.

        Uses secrets.choice() over string.digits for unbiased random
        selection.

        Args:
            length (int): Number of digits in the OTP (default: 6).

        Returns:
            str: A numeric OTP string of the specified length.
        """
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def generate_reset_token(length: int = 32) -> str:
        """Generate a secure URL-safe password reset token.

        Args:
            length (int): Byte length of the random token (default: 32).

        Returns:
            str: A URL-safe base64-encoded token string.
        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def is_otp_expired(created_at, expiry_minutes: int = 10) -> bool:
        """Check if an OTP has exceeded its validity period.

        Handles both datetime objects and ISO-formatted strings (common
        when reading from a database). Also normalizes timezone-aware and
        timezone-naive datetimes for consistent comparison.

        Args:
            created_at (datetime or str or None): The OTP creation time.
            expiry_minutes (int): Validity duration in minutes (default: 10).

        Returns:
            bool: True if the OTP has expired or created_at is invalid;
                  False if still valid.
        """
        if not created_at:
            return True

        # Handle both datetime and string formats from database
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return True

        # Ensure we're comparing timezone-aware or naive datetimes consistently
        now = datetime.now()
        if created_at.tzinfo is not None and now.tzinfo is None:
            created_at = created_at.replace(tzinfo=None)

        expiry_time = created_at + timedelta(minutes=expiry_minutes)
        return now > expiry_time

    @staticmethod
    def is_reset_token_expired(expires_at, expiry_minutes: int = 30) -> bool:
        """Check if a password reset token has exceeded its validity period.

        Handles both datetime objects and ISO-formatted strings. Normalises
        timezone awareness for consistent comparison with datetime.now().

        Args:
            expires_at (datetime or str or None): The token expiration time.
            expiry_minutes (int): Validity duration in minutes (default: 30).

        Returns:
            bool: True if the token has expired or expires_at is invalid;
                  False if still valid.
        """
        if not expires_at:
            return True

        # Handle both datetime and string formats from database
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return True

        # Ensure we're comparing timezone-aware or naive datetimes consistently
        now = datetime.now()
        if expires_at.tzinfo is not None and now.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=None)

        return now > expires_at

    @staticmethod
    def hash_otp(otp: str) -> str:
        """Hash an OTP using SHA-256 for secure storage.

        OTPs should never be stored in plain text. This method produces a
        one-way hash suitable for comparison during verification.

        Args:
            otp (str): The OTP string to hash.

        Returns:
            str or None: The hex-encoded SHA-256 digest, or None if otp
            is empty/falsy.
        """
        if not otp:
            return None
        return hashlib.sha256(otp.encode()).hexdigest()

    @staticmethod
    def verify_otp(stored_hash: str, otp_input: str) -> bool:
        """Verify a user-supplied OTP against a stored SHA-256 hash.

        Args:
            stored_hash (str): The previously stored SHA-256 hex digest.
            otp_input (str): The OTP string provided by the user.

        Returns:
            bool: True if the hashed input matches the stored hash; False
                  otherwise (including if either argument is empty).
        """
        if not stored_hash or not otp_input:
            return False
        return hashlib.sha256(otp_input.encode()).hexdigest() == stored_hash
