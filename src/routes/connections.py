"""
Connection Management Routes
=============================
Handles the social graph between users: viewing connections,
sending/accepting/rejecting connection requests, and removing
connections. All routes require authentication (@login_required)
and are disabled for admin users.

Endpoints:
    /connections                - Renders the connections management page (HTML)
    /api/send-request           - Send a new connection request (JSON)
    /api/respond-request        - Accept or reject a pending request (JSON)
    /api/remove-connection      - Remove an existing connection (JSON)
"""

from flask import Blueprint, render_template, request, session, flash, jsonify, redirect, url_for
from db import Database
from utils.decorators import login_required
from utils.protocols import is_protocol_enabled, protocol_disabled_response, check_connection_limit, check_total_connections

connections_bp = Blueprint('connections', __name__)


# ==================== CONNECTIONS PAGE ====================

@connections_bp.route('/connections')
@login_required
def connections_page():
    """
    Render the connections management page for the logged-in user.

    Fetches all connection categories:
        - accepted (all)
        - accepted_students
        - accepted_alumni
        - pending_received (incoming requests)
        - pending_sent (outgoing requests)

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders connections.html with all connection data.
    """
    # Admins cannot access connections - redirect to admin panel
    if session.get('role') == 'admin':
        flash('Admins do not have personal connections. Use Admin Panel to manage users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    uid = session['user_id']
    accepted = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.department, ap.company, u.profile_pic,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills,
        sp.joining_year, COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        c.id as connection_id, c.created_at FROM users u
        INNER JOIN connections c ON (c.requester_id=u.id OR c.recipient_id=u.id)
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        LEFT JOIN user_skills us ON u.id = us.user_id
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted' AND u.id!=%s AND u.is_active=1
        GROUP BY u.id ORDER BY c.updated_at DESC""", (uid, uid, uid), fetch_all=True)
    accepted_students = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.department, ap.company, u.profile_pic,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills,
        sp.joining_year, COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        c.id as connection_id, c.created_at FROM users u
        INNER JOIN connections c ON (c.requester_id=u.id OR c.recipient_id=u.id)
        LEFT JOIN student_profiles sp ON u.id = sp.user_id
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id
        LEFT JOIN user_skills us ON u.id = us.user_id
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted' AND u.id!=%s AND u.is_active=1 AND u.role='student'
        GROUP BY u.id ORDER BY c.updated_at DESC""", (uid, uid, uid), fetch_all=True)
    accepted_alumni = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.department, ap.company, u.profile_pic,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills,
        sp.joining_year, COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        c.id as connection_id, c.created_at FROM users u
        INNER JOIN connections c ON (c.requester_id=u.id OR c.recipient_id=u.id)
        LEFT JOIN student_profiles sp ON u.id = sp.user_id
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id
        LEFT JOIN user_skills us ON u.id = us.user_id
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted' AND u.id!=%s AND u.is_active=1 AND u.role='alumni'
        GROUP BY u.id ORDER BY c.updated_at DESC""", (uid, uid, uid), fetch_all=True)
    pending_received = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.department, ap.company, u.profile_pic,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills,
        ap.roll_number,
        c.id as connection_id, c.created_at FROM users u
        INNER JOIN connections c ON c.requester_id=u.id
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id
        LEFT JOIN user_skills us ON u.id = us.user_id
        WHERE c.recipient_id=%s AND c.status='pending' AND u.is_active=1
        GROUP BY u.id ORDER BY c.created_at DESC""", (uid,), fetch_all=True)
    pending_sent = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.department, ap.company, u.profile_pic,
        ap.roll_number,
        c.id as connection_id, c.created_at FROM users u
        INNER JOIN connections c ON c.recipient_id=u.id
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id
        WHERE c.requester_id=%s AND c.status='pending' AND u.is_active=1
        GROUP BY u.id ORDER BY c.created_at DESC""", (uid,), fetch_all=True)
    return render_template('connections.html', accepted=accepted, accepted_students=accepted_students, accepted_alumni=accepted_alumni, pending_received=pending_received, pending_sent=pending_sent)


# ==================== CONNECTION ACTIONS ====================

@connections_bp.route('/api/send-request', methods=['POST'])
@login_required
def send_request():
    """
    Send a connection request to another user.

    Validates:
        - User is not admin
        - Connections protocol is enabled
        - Cannot send request to self
        - No existing connection (pending/accepted) between the two users

    On success, creates a pending connection record and sends a
    notification to the recipient.

    Request Body (JSON):
        receiver_id (int): The ID of the user to connect with.

    Returns:
        JSON: {'success': True/False, 'message': str}
    """
    # Admins cannot send connection requests
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins cannot send connection requests'}), 403

    receiver_id = request.json.get('receiver_id')
    sender_id = session['user_id']
    if not receiver_id:
        return jsonify({'success': False, 'message': 'Recipient required'}), 400
    try:
        receiver_id = int(receiver_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid recipient'}), 400
    if receiver_id == sender_id:
        return jsonify({'success': False, 'message': 'Cannot connect with yourself'}), 400
    recipient = Database.execute_query("SELECT id FROM users WHERE id=%s AND is_active=1", (receiver_id,), fetch_one=True)
    if not recipient:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    # Enforce connection protocol limits
    ok, msg = check_connection_limit(sender_id)
    if not ok:
        return jsonify({'success': False, 'message': msg}), 429
    ok, msg = check_total_connections(sender_id)
    if not ok:
        return jsonify({'success': False, 'message': msg}), 429
    existing = Database.execute_query(
        """SELECT id, status FROM connections WHERE (requester_id=%s AND recipient_id=%s)
        OR (requester_id=%s AND recipient_id=%s)""",
        (sender_id, receiver_id, receiver_id, sender_id), fetch_one=True)
    if existing:
        return jsonify({'success': False, 'message': f'Connection already {existing["status"]}'}), 400
    try:
        Database.execute_query(
            "INSERT INTO connections (requester_id, recipient_id, status) VALUES (%s, %s, 'pending')",
            (sender_id, receiver_id), commit=True)
        sender = Database.execute_query("SELECT name FROM users WHERE id=%s", (sender_id,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'connection_request', %s, %s, %s)",
            (receiver_id, 'New Connection Request', f"{sender['name']} sent you a connection request", f"/profile/{sender_id}"), commit=True)
        return jsonify({'success': True, 'message': 'Connection request sent!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@connections_bp.route('/api/respond-request', methods=['POST'])
@login_required
def respond_request():
    """
    Accept or reject a pending incoming connection request.

    Only the recipient (recipient_id) can respond. Validates that
    the connection exists and is in 'pending' status.

    Request Body (JSON):
        connection_id (int): The ID of the connection record.
        action        (str): 'accept' or 'reject'.

    Returns:
        JSON: {'success': True/False, 'message': str}
    """
    # Admins cannot respond to connection requests
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins cannot respond to connection requests'}), 403

    connection_id = request.json.get('connection_id')
    action = request.json.get('action')
    if action not in ['accept', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    status = 'accepted' if action == 'accept' else 'rejected'
    try:
        conn = Database.execute_query(
            "SELECT * FROM connections WHERE id=%s AND recipient_id=%s AND status='pending'",
            (connection_id, session['user_id']), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        Database.execute_query("UPDATE connections SET status=%s WHERE id=%s", (status, connection_id), commit=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (session['user_id'],), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'connection_response', %s, %s, %s)",
            (conn['requester_id'], 'Connection Request Update', f"{user['name']} {status} your connection request",
            f"/profile/{session['user_id']}"), commit=True)
        return jsonify({'success': True, 'message': f'Request {status}!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@connections_bp.route('/api/accept-connection-request', methods=['POST'])
@login_required
def accept_connection_request():
    """Accept a pending connection request from a user (by sender_id)."""
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins cannot respond to connection requests'}), 403
    sender_id = request.json.get('sender_id')
    user_id = session['user_id']
    if not sender_id:
        return jsonify({'success': False, 'message': 'Sender ID required'}), 400
    try:
        conn = Database.execute_query(
            "SELECT * FROM connections WHERE requester_id=%s AND recipient_id=%s AND status='pending'",
            (sender_id, user_id), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        Database.execute_query("UPDATE connections SET status='accepted' WHERE id=%s", (conn['id'],), commit=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (user_id,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url, related_user_id) VALUES (%s, 'connection_accepted', %s, %s, %s, %s)",
            (sender_id, 'Connection Accepted', f"{user['name']} accepted your connection request",
             f"/profile/{user_id}", user_id), commit=True)
        return jsonify({'success': True, 'message': 'Connection request accepted!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@connections_bp.route('/api/reject-connection-request', methods=['POST'])
@login_required
def reject_connection_request():
    """Reject a pending connection request from a user (by sender_id)."""
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins cannot respond to connection requests'}), 403
    sender_id = request.json.get('sender_id')
    user_id = session['user_id']
    if not sender_id:
        return jsonify({'success': False, 'message': 'Sender ID required'}), 400
    try:
        conn = Database.execute_query(
            "SELECT * FROM connections WHERE requester_id=%s AND recipient_id=%s AND status='pending'",
            (sender_id, user_id), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        Database.execute_query("UPDATE connections SET status='rejected' WHERE id=%s", (conn['id'],), commit=True)
        return jsonify({'success': True, 'message': 'Connection request declined'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@connections_bp.route('/api/remove-connection', methods=['POST'])
@login_required
def remove_connection():
    """
    Remove an existing accepted connection.

    Either party (requester or recipient) can remove the connection.
    Deletes the connection record entirely from the database.

    Request Body (JSON):
        connection_id (int): The ID of the connection record to delete.

    Returns:
        JSON: {'success': True/False, 'message': str}
    """
    # Admins cannot remove connections
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins do not have connections'}), 403

    connection_id = request.json.get('connection_id')
    uid = session['user_id']
    if not connection_id:
        return jsonify({'success': False, 'message': 'Connection ID required'}), 400
    try:
        conn = Database.execute_query(
            "SELECT id FROM connections WHERE id=%s AND (requester_id=%s OR recipient_id=%s)",
            (connection_id, uid, uid), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404
        Database.execute_query("DELETE FROM connections WHERE id=%s", (connection_id,), commit=True)
        return jsonify({'success': True, 'message': 'Connection removed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@connections_bp.route('/api/remove-connection-with-user', methods=['POST'])
@login_required
def remove_connection_with_user():
    """Remove an accepted connection by the other user's ID.

    Either party can remove. Looks up the connection between the
    current user and the specified user, then deletes it.

    Request Body (JSON):
        user_id (int): The ID of the connected user to disconnect from.

    Returns:
        JSON: {'success': True/False, 'message': str}
    """
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins do not have connections'}), 403

    other_id = request.json.get('user_id')
    uid = session['user_id']
    if not other_id:
        return jsonify({'success': False, 'message': 'User ID required'}), 400
    try:
        conn = Database.execute_query(
            """SELECT id FROM connections WHERE (requester_id=%s AND recipient_id=%s)
            OR (requester_id=%s AND recipient_id=%s)""",
            (uid, other_id, other_id, uid), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404
        Database.execute_query("DELETE FROM connections WHERE id=%s", (conn['id'],), commit=True)
        return jsonify({'success': True, 'message': 'Connection removed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
