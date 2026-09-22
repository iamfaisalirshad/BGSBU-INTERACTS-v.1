"""
Security utilities for BGSBU Interacts

Provides rate limiting, CSRF protection, input sanitization,
password strength validation, IP address extraction, and
security-related decorators for Flask routes.
"""

from functools import wraps
from flask import request, jsonify, session
from datetime import datetime, timedelta
from collections import defaultdict
import secrets
import re


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter for login attempts and API endpoints.

    Tracks request counts per identifier (e.g. IP address or email) and
    enforces lockout periods once the maximum number of attempts is exceeded.
    Uses an in-memory dictionary; data is lost on server restart.
    """

    def __init__(self):
        """Initialize the rate limiter with default thresholds.

        Sets up:
            attempts (defaultdict): Maps identifier -> list of datetime
                timestamps for each recorded attempt.
            max_attempts (int): Maximum allowed attempts before lockout.
            lockout_time (int): Lockout duration in minutes.
        """
        self.attempts = defaultdict(list)
        self.max_attempts = 5
        self.lockout_time = 15  # minutes

    def is_rate_limited(self, identifier):
        """Check if identifier (IP/email) is currently rate limited.

        Prunes expired attempts older than the lockout window, then checks
        whether the remaining count exceeds the threshold.

        Args:
            identifier (str): Unique key -- typically a client IP address or
                an email address.

        Returns:
            bool: True if the identifier has exceeded max_attempts within
                  the lockout_time window; False otherwise.
        """
        now = datetime.now()

        # Prune attempts that have fallen outside the lockout window
        self.attempts[identifier] = [
            attempt_time for attempt_time in self.attempts[identifier]
            if (now - attempt_time).total_seconds() < (self.lockout_time * 60)
        ]

        # Threshold check
        if len(self.attempts[identifier]) >= self.max_attempts:
            return True
        return False

    def record_attempt(self, identifier):
        """Record an attempt timestamp for the given identifier.

        Args:
            identifier (str): The identifier to record the attempt for.
        """
        self.attempts[identifier].append(datetime.now())

    def clear_attempts(self, identifier):
        """Clear all recorded attempts for an identifier (e.g. on successful login).

        Args:
            identifier (str): The identifier whose attempts should be cleared.
        """
        self.attempts.pop(identifier, None)

    def get_remaining_time(self, identifier):
        """Get remaining lockout time in seconds for the given identifier.

        Computes the time until the oldest surviving attempt expires from the
        lockout window.

        Args:
            identifier (str): The identifier to check.

        Returns:
            int: Remaining lockout time in seconds, or 0 if not rate limited.
        """
        if not self.is_rate_limited(identifier):
            return 0

        now = datetime.now()
        attempts = self.attempts.get(identifier, [])
        if not attempts:
            return 0

        # Find the oldest attempt and compute how long until it leaves the window
        oldest_attempt = min(attempts)
        locked_until = oldest_attempt + timedelta(minutes=self.lockout_time)
        remaining = (locked_until - now).total_seconds()
        return max(0, int(remaining))


# Global rate limiter instance shared across the application
rate_limiter = RateLimiter()


# =============================================================================
# CSRF Protection
# =============================================================================

class CSRFProtection:
    """CSRF token generation and validation.

    Provides static methods to generate cryptographically secure tokens,
    store them in the Flask session, and validate incoming tokens against
    the stored value (including age checks).
    """

    TOKEN_SIZE = 32  # 32 bytes = 256 bits of entropy
    TOKEN_TIMEOUT = 3600  # Token valid for 1 hour (in seconds)

    @staticmethod
    def generate_token():
        """Generate a new cryptographically secure CSRF token.

        Uses secrets.token_urlsafe() for URL-safe random bytes.

        Returns:
            str: A URL-safe base64-encoded random token.
        """
        return secrets.token_urlsafe(CSRFProtection.TOKEN_SIZE)

    @staticmethod
    def get_token_from_session():
        """Retrieve the current CSRF token from the Flask session.

        If no token exists yet, generates a new one along with a timestamp
        and persists both to the session.

        Returns:
            str: The CSRF token stored in the session.
        """
        if '_csrf_token' not in session:
            session['_csrf_token'] = CSRFProtection.generate_token()
            session['_csrf_token_time'] = datetime.now().isoformat()
        return session['_csrf_token']

    @staticmethod
    def validate_token(token):
        """Validate a submitted CSRF token against the session.

        Checks both the token value match and the token age against the
        configured timeout.

        Args:
            token (str): The token submitted by the client.

        Returns:
            bool: True if the token is valid and not expired; False otherwise.
        """
        if '_csrf_token' not in session:
            return False

        # Value comparison -- must match exactly
        if token != session.get('_csrf_token'):
            return False

        # Age check -- reject tokens older than TOKEN_TIMEOUT
        token_time_str = session.get('_csrf_token_time')
        if token_time_str:
            try:
                token_time = datetime.fromisoformat(token_time_str)
                if (datetime.now() - token_time).total_seconds() > CSRFProtection.TOKEN_TIMEOUT:
                    return False
            except:
                return False

        return True


# =============================================================================
# Input Sanitization
# =============================================================================

def validate_input_sanitization(data):
    """Sanitize user input to prevent XSS and injection attacks.

    Strips dangerous patterns such as <script> tags, javascript: URIs, and
    inline event handlers (onclick, onerror, etc.) from string inputs.
    This is a basic sanitization layer; contextual output escaping should
    still be applied at the template layer.

    Args:
        data: Input data -- only strings are sanitized; other types pass
            through unchanged.

    Returns:
        str or any: The sanitized string if input was a string, or the
        original value unchanged.
    """
    if isinstance(data, str):
        # Remove potentially dangerous characters but allow common ones
        # This is basic; real sanitization depends on context
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',  # Script tags
            r'javascript:',                  # JavaScript protocol
            r'on\w+\s*=',                    # Event handlers (onclick, etc.)
        ]

        for pattern in dangerous_patterns:
            data = re.sub(pattern, '', data, flags=re.IGNORECASE)

    return data


# =============================================================================
# Helper Utilities
# =============================================================================

def get_client_ip(request):
    """Get client IP address, handling proxies.

    Checks Cloudflare (CF-Connecting-IP) and standard proxy
    (X-Forwarded-For) headers before falling back to the direct remote
    address.

    Args:
        request: The Flask request object.

    Returns:
        str: The client IP address string.
    """
    if request.environ.get('HTTP_CF_CONNECTING_IP'):
        return request.environ['HTTP_CF_CONNECTING_IP']
    elif request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0]
    else:
        return request.remote_addr


def rate_limit_decorator(max_attempts=5, lockout_minutes=15):
    """Decorator factory to apply rate limiting to specific Flask endpoints.

    Uses the global rate_limiter to track attempts keyed by
    ``client_ip:endpoint``. If the limit is exceeded, returns a 429 response
    with the remaining lockout time. On a successful 200 response, clears
    the attempt history.

    Args:
        max_attempts (int): Maximum requests before lockout (default: 5).
        lockout_minutes (int): Lockout duration in minutes (default: 15).

    Returns:
        function: The decorator to apply to a Flask route function.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = get_client_ip(request)
            identifier = f"{client_ip}:{request.endpoint}"

            if rate_limiter.is_rate_limited(identifier):
                remaining = rate_limiter.get_remaining_time(identifier)
                return jsonify({
                    'success': False,
                    'message': f'Too many attempts. Try again in {remaining} seconds.'
                }), 429

            try:
                result = f(*args, **kwargs)
                # Only clear on success (assume successful operations don't return error status)
                if isinstance(result, tuple) and len(result) > 1 and result[1] == 200:
                    rate_limiter.clear_attempts(identifier)
                return result
            except Exception as e:
                rate_limiter.record_attempt(identifier)
                raise e

        return decorated_function
    return decorator


def validate_email_format(email):
    """Validate email format.

    Uses a regex that checks for a local part, @ symbol, domain, and TLD
    with at least two alpha characters.

    Args:
        email (str): The email address to validate.

    Returns:
        bool: True if the email matches the expected pattern; False otherwise.
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def check_duplicate_email(email, db, exclude_user_id=None):
    """Check if email already exists in database.

    Optionally excludes a specific user ID, allowing the email owner to
    keep their own email without triggering a duplicate warning.

    Args:
        email (str): The email address to check.
        db: Database wrapper with an execute_query method.
        exclude_user_id (int, optional): If provided, the user ID to
            exclude from the duplicate check.

    Returns:
        bool: True if a user with the given email (other than the excluded
              user) already exists; False otherwise.
    """
    query = "SELECT id FROM users WHERE email = %s"
    params = (email,)

    if exclude_user_id:
        query += " AND id != %s"
        params = (email, exclude_user_id)

    result = db.execute_query(query, params, fetch_one=True)
    return result is not None
