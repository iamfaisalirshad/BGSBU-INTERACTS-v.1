"""
Authentication utilities for BGSBU Interacts

Provides password hashing and verification (via Flask-Bcrypt), email and
input validation, password strength checks, and file upload filtering.
"""

import re
from datetime import datetime
from flask_bcrypt import Bcrypt

# Allowed email domains for registration
# Only users with emails from these domains may register
ALLOWED_EMAIL_DOMAINS = [
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
    'bgsbu.ac.in', 'students.bgsbu.ac.in', 'alumni.bgsbu.ac.in',
    'edu.in', 'ac.in', 'rediffmail.com', 'aol.com'
]

bcrypt = Bcrypt()


# =============================================================================
# Password Hashing
# =============================================================================

def hash_password(password):
    """Hash a plaintext password using Flask-Bcrypt.

    Wraps bcrypt.generate_password_hash() and decodes the byte result to a
    UTF-8 string suitable for database storage.

    Args:
        password (str): The plaintext password to hash.

    Returns:
        str: The bcrypt hash as a UTF-8 string.
    """
    return bcrypt.generate_password_hash(password).decode('utf-8')


def check_password(hashed, password):
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        hashed (str): The previously stored bcrypt hash string.
        password (str): The plaintext password to verify.

    Returns:
        bool: True if the password matches the hash; False otherwise.
    """
    return bcrypt.check_password_hash(hashed, password)


# =============================================================================
# Input Validation
# =============================================================================

def validate_email(email):
    """Validate email format, structure, and allowed domains.

    Checks that the email matches a standard format regex and that its
    domain is in the ALLOWED_EMAIL_DOMAINS whitelist.

    Args:
        email (str): The email address to validate.

    Returns:
        bool: True if the email passes all checks; False otherwise.
    """
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    # Extract domain (part after the last @) and check against whitelist
    domain = email.rsplit('@', 1)[-1].lower()
    return domain in ALLOWED_EMAIL_DOMAINS


def validate_password_strength(password):
    """Validate password strength against security requirements.

    Requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character (!@#$%^&*)

    Args:
        password (str): The password candidate to validate.

    Returns:
        tuple: (is_valid, message) where:
            - is_valid (bool): True if all requirements are met.
            - message (str): Human-readable result or concatenated errors.
    """
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character (!@#$%^&*)")

    if errors:
        return False, " ".join(errors)
    return True, "Password is strong"


def validate_name(name):
    """Validate a user's display name.

    Enforces length constraints (2-100 characters) and restricts characters
    to letters, spaces, dots, hyphens, and apostrophes.

    Args:
        name (str): The name string to validate.

    Returns:
        tuple: (is_valid, message) where:
            - is_valid (bool): True if the name passes all checks.
            - message (str): Human-readable result or error description.
    """
    if not name or len(name) < 2:
        return False, "Name must be at least 2 characters"
    if len(name) > 100:
        return False, "Name must not exceed 100 characters"
    if not re.match(r'^[a-zA-Z\s\.\-\']+$', name):
        return False, "Name contains invalid characters"
    return True, "Name is valid"


def validate_phone(phone):
    """Validate a phone number (optional field).

    Empty/null values are accepted. Non-empty values must be 10-15
    characters consisting of digits, +, -, parentheses, and spaces.

    Args:
        phone (str or None): The phone number to validate.

    Returns:
        tuple: (is_valid, message) where:
            - is_valid (bool): True if valid or empty.
            - message (str): Human-readable result or error description.
    """
    if not phone:
        return True, "Phone is optional"
    phone = phone.strip()
    if not re.match(r'^[0-9\+\-\(\)\s]{10,15}$', phone):
        return False, "Phone must be 10-15 digits"
    return True, "Phone is valid"


def validate_academic_years(joining_year, passing_year):
    """Validate academic session joining and passing years.

    Ensures both years are present, within reasonable ranges, and that the
    passing year is not before the joining year.

    Args:
        joining_year (str or int): The year the user joined.
        passing_year (str or int): The year the user passed/graduated.

    Returns:
        tuple: (is_valid, message) where:
            - is_valid (bool): True if both years are valid.
            - message (str): Human-readable result or error description.

    Raises:
        ValueError: Caught internally; returns failure tuple if years are
                    not valid integers.
    """
    try:
        joining = int(joining_year) if joining_year else None
        passing = int(passing_year) if passing_year else None

        if not joining or not passing:
            return False, "Both joining and passing years are required"

        current_year = datetime.now().year
        if joining < 1990 or joining > current_year + 1:
            return False, f"Joining year must be between 1990 and {current_year + 1}"

        if passing < joining or passing < 1990 or passing > current_year + 10:
            return False, f"Passing year must be after joining year and within reasonable range"

        return True, "Academic years are valid"
    except ValueError:
        return False, "Years must be valid numbers"


# =============================================================================
# File Upload Helpers
# =============================================================================

def allowed_file(filename, allowed_extensions):
    """Check whether a filename has an allowed extension for uploads.

    Verifies the file has a dot-separated extension and that the extension
    (case-insensitive) is present in the allowed set.

    Args:
        filename (str): The name of the uploaded file.
        allowed_extensions (set or list): Collection of allowed extension
            strings (e.g. {'png', 'jpg', 'pdf'}).

    Returns:
        bool: True if the file extension is allowed; False otherwise.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
