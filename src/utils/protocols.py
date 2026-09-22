"""
Protocols Utility
=================
Provides helper functions that check system protocol settings before
allowing platform features. All feature routes call these helpers to
enforce admin-configured rules in real time.
"""

from db import Database
from flask import jsonify


def get_protocol(protocol_type):
    """Fetch a single protocol row by type. Returns None if not found."""
    return Database.execute_query(
        "SELECT * FROM system_protocols WHERE protocol_type = %s",
        (protocol_type,), fetch_one=True)


def is_protocol_enabled(protocol_type):
    """Return True if the given protocol exists and is enabled."""
    row = get_protocol(protocol_type)
    return row is not None and row['is_enabled'] == 1


def protocol_disabled_response(protocol_type):
    """Standard JSON 403 response when a protocol is disabled."""
    return jsonify({
        'success': False,
        'message': f'{protocol_type.capitalize()} is currently disabled by admin.'
    }), 403


# ==================== MESSAGING ====================

def get_messaging_quota(user_id):
    """Return messaging quota info for a user, or None if unlimited."""
    row = get_protocol('messaging')
    if not row or not row['is_enabled'] or not row['max_messages_per_day']:
        return None
    sent_today = Database.execute_query(
        "SELECT COUNT(*) as c FROM messages WHERE sender_id=%s AND DATE(created_at)=CURDATE()",
        (user_id,), fetch_one=True)['c']
    limit = row['max_messages_per_day']
    return {'limit': limit, 'used': sent_today, 'remaining': max(0, limit - sent_today)}


def require_connection_for_messaging():
    """Return True if messaging requires a connection between users."""
    row = get_protocol('messaging')
    if row and row.get('require_connection_for_messaging') is not None:
        return row['require_connection_for_messaging'] == 1
    return True   # default: require connection


# ==================== CONNECTIONS ====================

def check_connection_limit(user_id):
    """Return (ok, message) — ok=False if daily connection request limit exceeded."""
    row = get_protocol('connections')
    if not row or not row.get('max_connections_per_day'):
        return True, None
    sent_today = Database.execute_query(
        "SELECT COUNT(*) as c FROM connections WHERE requester_id=%s AND DATE(created_at)=CURDATE()",
        (user_id,), fetch_one=True)['c']
    limit = row['max_connections_per_day']
    if sent_today >= limit:
        return False, f'Daily connection request limit of {limit} reached.'
    return True, None


def check_total_connections(user_id):
    """Return (ok, message) — ok=False if total connection cap is exceeded."""
    row = get_protocol('connections')
    if not row or not row.get('max_total_connections'):
        return True, None
    total = Database.execute_query(
        "SELECT COUNT(*) as c FROM connections WHERE (requester_id=%s OR recipient_id=%s) AND status='accepted'",
        (user_id, user_id), fetch_one=True)['c']
    limit = row['max_total_connections']
    if total >= limit:
        return False, f'Maximum connection limit of {limit} reached.'
    return True, None


# ==================== JOBS ====================

def check_job_post_limit(alumni_id):
    """Return (ok, message) — ok=False if alumni has hit their active job post cap."""
    row = get_protocol('jobs')
    if not row or not row.get('max_jobs_per_alumni'):
        return True, None
    active = Database.execute_query(
        "SELECT COUNT(*) as c FROM jobs WHERE posted_by=%s AND is_active=1",
        (alumni_id,), fetch_one=True)['c']
    limit = row['max_jobs_per_alumni']
    if active >= limit:
        return False, f'You can have at most {limit} active job post(s) at once.'
    return True, None


def check_application_limit_for_student(student_id):
    """Return (ok, message) — ok=False if student hit total application cap."""
    row = get_protocol('jobs')
    if not row or not row.get('max_applications_per_student'):
        return True, None
    total = Database.execute_query(
        "SELECT COUNT(*) as c FROM job_applications WHERE user_id=%s",
        (student_id,), fetch_one=True)['c']
    limit = row['max_applications_per_student']
    if total >= limit:
        return False, f'You have reached the maximum of {limit} job application(s).'
    return True, None


def is_admin_approval_required_for_jobs():
    """Return True if new job posts must be approved by admin before going live."""
    row = get_protocol('jobs')
    if row and row.get('require_admin_approval') is not None:
        return row['require_admin_approval'] == 1
    return True   # default: require approval


# ==================== MENTORSHIP ====================

def check_mentor_capacity(mentor_id):
    """Return (ok, message) — ok=False if mentor has hit their active mentorship cap."""
    row = get_protocol('mentorship')
    if not row or not row.get('max_mentorships_per_mentor'):
        return True, None
    active = Database.execute_query(
        "SELECT COUNT(*) as c FROM mentorship WHERE mentor_id=%s AND status IN ('accepted','active')",
        (mentor_id,), fetch_one=True)['c']
    limit = row['max_mentorships_per_mentor']
    if active >= limit:
        return False, f'This mentor has reached their maximum of {limit} active mentorship(s).'
    return True, None


def is_verified_mentor_required():
    """Return True if only admin-verified mentors can accept requests."""
    row = get_protocol('mentorship')
    if row and row.get('require_verified_mentor') is not None:
        return row['require_verified_mentor'] == 1
    return False   # default: any alumni with is_mentor=True can mentor


# ==================== APPLICATIONS ====================

def check_applications_per_job(job_id):
    """Return (ok, message) — ok=False if a job has hit its application cap."""
    row = get_protocol('applications')
    if not row or not row.get('max_applications_per_job'):
        return True, None
    count = Database.execute_query(
        "SELECT COUNT(*) as c FROM job_applications WHERE job_id=%s",
        (job_id,), fetch_one=True)['c']
    limit = row['max_applications_per_job']
    if count >= limit:
        return False, f'This job has reached the maximum of {limit} application(s).'
    return True, None