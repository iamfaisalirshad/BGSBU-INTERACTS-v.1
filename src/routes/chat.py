"""
Chat Routes Module
==================
Handles all direct messaging between connected users:
- Chat page rendering with connection list
- Fetching/displaying message history between two users
- Sending new messages (with protocol enforcement & quotas)
- File uploads for chat attachments
"""

import os
import json
import uuid
from flask import Blueprint, render_template, request, session, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from db import Database
from config import Config
from utils.decorators import login_required
from utils.protocols import is_protocol_enabled, get_messaging_quota, require_connection_for_messaging, protocol_disabled_response

chat_bp = Blueprint('chat', __name__)


# ==================== CHAT PAGE ====================

@chat_bp.route('/chat')
@login_required
def chat_page():
    """Render the chat interface with user's connections and last messages.

    Builds a sidebar of accepted connections along with their last message,
    timestamp, and unread count. Admins are redirected away (no chat access).

    Returns:
        Rendered chat.html template with connections and optional selected user.
    """
    # Admins cannot chat - redirect to admin panel
    if session.get('role') == 'admin':
        flash('Admins do not have messaging. Use Admin Panel to manage users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    uid = session['user_id']
    connections = Database.execute_query(
        """SELECT u.id, u.name, u.profile_pic, u.role, u.department,
        (SELECT content FROM messages WHERE is_deleted=0 AND ((sender_id=u.id AND receiver_id=%s)
        OR (sender_id=%s AND receiver_id=u.id)) ORDER BY created_at DESC LIMIT 1) as last_message,
        (SELECT created_at FROM messages WHERE is_deleted=0 AND ((sender_id=u.id AND receiver_id=%s)
        OR (sender_id=%s AND receiver_id=u.id)) ORDER BY created_at DESC LIMIT 1) as last_time,
        (SELECT COUNT(*) FROM messages WHERE sender_id=u.id AND receiver_id=%s AND is_read=0 AND is_deleted=0) as unread
        FROM users u INNER JOIN connections c ON (c.requester_id=u.id OR c.recipient_id=u.id)
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted' AND u.id!=%s AND u.is_active=1
        ORDER BY last_time DESC""",
        (uid, uid, uid, uid, uid, uid, uid, uid), fetch_all=True)
    # Also fetch accepted message request conversations (non-connection chats)
    req_convs = Database.execute_query(
        """SELECT u.id, u.name, u.profile_pic, u.role, u.department,
        (SELECT content FROM messages WHERE is_deleted=0 AND ((sender_id=u.id AND receiver_id=%s)
        OR (sender_id=%s AND receiver_id=u.id)) ORDER BY created_at DESC LIMIT 1) as last_message,
        (SELECT created_at FROM messages WHERE is_deleted=0 AND ((sender_id=u.id AND receiver_id=%s)
        OR (sender_id=%s AND receiver_id=u.id)) ORDER BY created_at DESC LIMIT 1) as last_time,
        (SELECT COUNT(*) FROM messages WHERE sender_id=u.id AND receiver_id=%s AND is_read=0 AND is_deleted=0) as unread
        FROM users u INNER JOIN message_requests mr ON
        ((mr.sender_id=u.id AND mr.recipient_id=%s) OR (mr.recipient_id=u.id AND mr.sender_id=%s))
        WHERE mr.status='accepted' AND u.id!=%s AND u.is_active=1
        AND u.id NOT IN (SELECT CASE WHEN c.requester_id=%s THEN c.recipient_id ELSE c.requester_id END
                         FROM connections c WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted')
        ORDER BY last_time DESC""",
        (uid, uid, uid, uid, uid, uid, uid, uid, uid, uid, uid), fetch_all=True)
    all_conversations = connections + req_convs
    selected_user_id = request.args.get('user', type=int)
    request_mode = request.args.get('request') == '1'
    request_target = None
    if request_mode and selected_user_id:
        # Don't show request mode if already connected or accepted request exists
        existing = Database.execute_query(
            """SELECT 1 FROM connections WHERE ((requester_id=%s AND recipient_id=%s)
            OR (requester_id=%s AND recipient_id=%s)) AND status='accepted'
            UNION SELECT 1 FROM message_requests WHERE ((sender_id=%s AND recipient_id=%s)
            OR (sender_id=%s AND recipient_id=%s)) AND status='accepted'""",
            (uid, selected_user_id, selected_user_id, uid,
             uid, selected_user_id, selected_user_id, uid), fetch_one=True)
        if not existing:
            request_target = Database.execute_query(
                "SELECT id, name, profile_pic FROM users WHERE id=%s AND is_active=1",
                (selected_user_id,), fetch_one=True)
            if not request_target:
                request_mode = False
        else:
            request_mode = False
    return render_template('chat.html', connections=all_conversations, selected_user_id=selected_user_id,
                         request_convs=req_convs, request_mode=request_mode, request_target=request_target)


# ==================== MESSAGE CRUD ====================

@chat_bp.route('/api/messages/<int:other_user_id>', methods=['GET'])
@login_required
def get_messages(other_user_id):
    """Fetch all messages between the current user and another user.

    Marks unread incoming messages as read, then retrieves the full
    conversation thread ordered chronologically.

    Args:
        other_user_id: ID of the other user in the conversation.

    Returns:
        JSON object with 'success' flag and 'messages' array (each message
        includes sender info, timestamps, and parsed attachments).
    """
    uid = session['user_id']
    conn = Database.execute_query(
        """SELECT id FROM connections WHERE ((requester_id=%s AND recipient_id=%s)
        OR (requester_id=%s AND recipient_id=%s)) AND status='accepted'""",
        (uid, other_user_id, other_user_id, uid), fetch_one=True)
    if not conn:
        # Also check accepted message requests
        mr = Database.execute_query(
            """SELECT id FROM message_requests WHERE ((sender_id=%s AND recipient_id=%s)
            OR (sender_id=%s AND recipient_id=%s)) AND status='accepted'""",
            (uid, other_user_id, other_user_id, uid), fetch_one=True)
        if not mr:
            return jsonify({'success': False, 'message': 'Not connected'}), 403
    Database.execute_query(
        "UPDATE messages SET is_read=1 WHERE sender_id=%s AND receiver_id=%s AND is_read=0",
        (other_user_id, uid), commit=True)
    messages = Database.execute_query(
        """SELECT m.*, u.name as sender_name, u.profile_pic as sender_pic FROM messages m
        INNER JOIN users u ON m.sender_id=u.id
        WHERE m.is_deleted=0 AND ((m.sender_id=%s AND m.receiver_id=%s) OR (m.sender_id=%s AND m.receiver_id=%s))
        ORDER BY m.created_at ASC""",
        (uid, other_user_id, other_user_id, uid), fetch_all=True)
    for msg in messages:
        msg['created_at'] = msg['created_at'].strftime('%Y-%m-%d %H:%M:%S') if msg['created_at'] else ''
        if msg.get('attachments'):
            try:
                msg['attachments'] = json.loads(msg['attachments'])
            except (json.JSONDecodeError, TypeError):
                msg['attachments'] = None
    unread_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = 0 AND is_deleted = 0",
        (uid,), fetch_one=True
    )['count']
    return jsonify({'success': True, 'messages': messages, 'unread_count': unread_count})


@chat_bp.route('/api/messages/unread-count', methods=['GET'])
@login_required
def unread_messages_count():
    """Return the current count of unread chat messages for the active user."""
    user_id = session['user_id']
    count = Database.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = 0 AND is_deleted = 0",
        (user_id,), fetch_one=True
    )['count']
    return jsonify({'success': True, 'count': count})


@chat_bp.route('/api/send-message', methods=['POST'])
@login_required
def send_message():
    """Send a new message from the current user to a receiver.

    Enforces:
    - Non-empty message or attachments
    - Messaging protocol enabled
    - Connection requirement (optional, via protocol settings)
    - Daily message quota (optional, via protocol settings)

    Returns:
        JSON with success flag, or 400/403/429/500 on failure.
    """
    uid = session['user_id']
    receiver_id = request.json.get('receiver_id')
    message = request.json.get('message', '').strip()
    attachments = request.json.get('attachments')

    if not message and not attachments:
        return jsonify({'success': False, 'message': 'Empty message'}), 400

    if not is_protocol_enabled('messaging'):
        return protocol_disabled_response('messaging')

    if require_connection_for_messaging():
        conn = Database.execute_query(
            """SELECT id FROM connections WHERE ((requester_id=%s AND recipient_id=%s)
            OR (requester_id=%s AND recipient_id=%s)) AND status='accepted'""",
            (uid, receiver_id, receiver_id, uid), fetch_one=True)
        if not conn:
            mr = Database.execute_query(
                """SELECT id FROM message_requests WHERE ((sender_id=%s AND recipient_id=%s)
                OR (sender_id=%s AND recipient_id=%s)) AND status='accepted'""",
                (uid, receiver_id, receiver_id, uid), fetch_one=True)
            if not mr:
                return jsonify({'success': False, 'message': 'Not connected'}), 403

    # Check if the user has exceeded their daily message limit
    quota = get_messaging_quota(uid)
    if quota and quota['remaining'] <= 0:
        return jsonify({'success': False, 'message': f'Daily message limit ({quota["limit"]}) reached.'}), 429

    try:
        attachments_json = json.dumps(attachments) if attachments else None
        msg_id = Database.execute_query(
            "INSERT INTO messages (sender_id, receiver_id, content, attachments) VALUES (%s, %s, %s, %s)",
            (uid, receiver_id, message, attachments_json), commit=True)
        return jsonify({'success': True, 'message_id': msg_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== MESSAGE REQUESTS ====================

@chat_bp.route('/api/message-request/send', methods=['POST'])
@login_required
def send_message_request():
    """Send a message request to a non-connected user.

    Creates a pending record in message_requests. The recipient can
    accept or reject it. Only allowed when no active connection exists.
    A brief introductory message is encouraged.

    Returns:
        JSON success/message or 400/403/409/500 error.
    """
    uid = session['user_id']
    receiver_id = request.json.get('receiver_id')
    message = request.json.get('message', '').strip()

    if not receiver_id:
        return jsonify({'success': False, 'message': 'Recipient required'}), 400
    if uid == receiver_id:
        return jsonify({'success': False, 'message': 'Cannot send request to yourself'}), 400

    # Block if already connected
    conn = Database.execute_query(
        """SELECT id FROM connections WHERE ((requester_id=%s AND recipient_id=%s)
        OR (requester_id=%s AND recipient_id=%s)) AND status='accepted'""",
        (uid, receiver_id, receiver_id, uid), fetch_one=True)
    if conn:
        return jsonify({'success': False, 'message': 'Already connected'}), 409

    # Block if request already exists
    existing = Database.execute_query(
        """SELECT * FROM message_requests WHERE (sender_id=%s AND recipient_id=%s)
        OR (sender_id=%s AND recipient_id=%s)""",
        (uid, receiver_id, receiver_id, uid), fetch_one=True)
    if existing:
        if existing['status'] == 'pending':
            return jsonify({'success': False, 'message': 'Request already sent'}), 409
        if existing['status'] == 'accepted':
            return jsonify({'success': False, 'message': 'Already connected via request'}), 409
        # Rejected — allow re-send by updating
        Database.execute_query(
            "UPDATE message_requests SET status='pending', message=%s, responded_at=NULL WHERE id=%s",
            (message, existing['id']), commit=True)
        return jsonify({'success': True, 'message': 'Message request sent!'})

    try:
        Database.execute_query(
            "INSERT INTO message_requests (sender_id, recipient_id, message) VALUES (%s, %s, %s)",
            (uid, receiver_id, message), commit=True)
        sender = Database.execute_query("SELECT name FROM users WHERE id=%s", (uid,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'message_request', %s, %s, %s)",
            (receiver_id, 'Message Request', f"Message request from {sender['name']}",
             f"/chat?tab=requests"), commit=True)
        return jsonify({'success': True, 'message': 'Message request sent!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/message-request/accept', methods=['POST'])
@login_required
def accept_message_request():
    """Accept a pending message request, enabling chat between the two users.

    Returns:
        JSON success/message or 400/404 error.
    """
    uid = session['user_id']
    sender_id = request.json.get('sender_id')
    if not sender_id:
        return jsonify({'success': False, 'message': 'Sender ID required'}), 400

    mr = Database.execute_query(
        "SELECT * FROM message_requests WHERE sender_id=%s AND recipient_id=%s AND status='pending'",
        (sender_id, uid), fetch_one=True)
    if not mr:
        return jsonify({'success': False, 'message': 'No pending request found'}), 404

    try:
        Database.execute_query(
            "UPDATE message_requests SET status='accepted', responded_at=NOW() WHERE id=%s",
            (mr['id'],), commit=True)
        sender = Database.execute_query("SELECT name FROM users WHERE id=%s", (uid,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'message_request', %s, %s, %s)",
            (sender_id, 'Message Request Accepted', f"{sender['name']} accepted your message request",
             f"/chat?user={uid}"), commit=True)
        return jsonify({'success': True, 'message': 'Request accepted. You can now chat!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/message-request/reject', methods=['POST'])
@login_required
def reject_message_request():
    """Reject a pending message request.

    Returns:
        JSON success/message or 400/404 error.
    """
    uid = session['user_id']
    sender_id = request.json.get('sender_id')
    if not sender_id:
        return jsonify({'success': False, 'message': 'Sender ID required'}), 400

    mr = Database.execute_query(
        "SELECT * FROM message_requests WHERE sender_id=%s AND recipient_id=%s AND status='pending'",
        (sender_id, uid), fetch_one=True)
    if not mr:
        return jsonify({'success': False, 'message': 'No pending request found'}), 404

    try:
        Database.execute_query(
            "UPDATE message_requests SET status='rejected', responded_at=NOW() WHERE id=%s",
            (mr['id'],), commit=True)
        return jsonify({'success': True, 'message': 'Request declined.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/message-requests', methods=['GET'])
@login_required
def get_message_requests():
    """Fetch all message requests for the current user.

    Returns both pending received requests and sent request statuses.

    Returns:
        JSON object with 'received' (pending requests sent TO the user)
        and 'sent' (user's outgoing requests) arrays.
    """
    uid = session['user_id']
    received = Database.execute_query(
        """SELECT mr.*, u.name as sender_name, u.profile_pic as sender_pic, u.department as sender_dept
        FROM message_requests mr INNER JOIN users u ON mr.sender_id=u.id
        WHERE mr.recipient_id=%s AND mr.status='pending'
        ORDER BY mr.created_at DESC""",
        (uid,), fetch_all=True)
    sent = Database.execute_query(
        """SELECT mr.*, u.name as recipient_name, u.profile_pic as recipient_pic
        FROM message_requests mr INNER JOIN users u ON mr.recipient_id=u.id
        WHERE mr.sender_id=%s ORDER BY mr.created_at DESC""",
        (uid,), fetch_all=True)
    return jsonify({'received': received, 'sent': sent})


# ==================== UNREAD COUNT / FILE UPLOAD ====================

@chat_bp.route('/api/unread-count', methods=['GET'])
@login_required
def unread_count():
    """Return the total unread message count for the current user.

    Used by the frontend to display a badge on the chat icon.

    Returns:
        JSON with a 'count' integer.
    """
    count = Database.execute_query(
        "SELECT COUNT(*) as count FROM messages WHERE receiver_id=%s AND is_read=0 AND is_deleted=0",
        (session['user_id'],), fetch_one=True)['count']
    return jsonify({'count': count})


@chat_bp.route('/api/messages/delete', methods=['POST'])
@login_required
def delete_message():
    """Delete a direct message.

    Either the sender or receiver can delete the message.

    Returns:
        JSON success/message or 403/404/500 error.
    """
    message_id = request.json.get('message_id')
    if not message_id:
        return jsonify({'success': False, 'message': 'Message ID required'}), 400

    try:
        msg = Database.execute_query(
            "SELECT * FROM messages WHERE id=%s", (message_id,), fetch_one=True)
        if not msg:
            return jsonify({'success': False, 'message': 'Message not found'}), 404

        if msg['sender_id'] != session['user_id'] and msg['receiver_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        Database.execute_query("DELETE FROM messages WHERE id=%s", (message_id,), commit=True)
        return jsonify({'success': True, 'message': 'Message deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/conversation/delete', methods=['POST'])
@login_required
def delete_conversation():
    """Delete the entire conversation between the current user and another user.

    Both parties can delete the conversation. Removes all messages
    exchanged between the two users.

    Returns:
        JSON success/message or 400/500 error.
    """
    other_user_id = request.json.get('user_id')
    if not other_user_id:
        return jsonify({'success': False, 'message': 'User ID required'}), 400

    try:
        uid = session['user_id']
        Database.execute_query(
            """UPDATE messages SET is_deleted=1
               WHERE (sender_id=%s AND receiver_id=%s)
                  OR (sender_id=%s AND receiver_id=%s)""",
            (uid, other_user_id, other_user_id, uid), commit=True)
        return jsonify({'success': True, 'message': 'Conversation deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/upload-chat-file', methods=['POST'])
@login_required
def upload_chat_file():
    """Handle file uploads for chat attachments.

    Validates:
    - A file was provided
    - Extension is in the allowed list (from Config)
    - Saves to uploads/chat/ with a UUID prefix to avoid collisions.

    Returns:
        JSON with file URL, display name, and type, or 400 on error.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({'success': False, 'message': 'File type not allowed'}), 400
    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
    chat_dir = os.path.join(Config.UPLOAD_FOLDER, 'chat')
    os.makedirs(chat_dir, exist_ok=True)
    file.save(os.path.join(chat_dir, filename))
    file_url = f'/uploads/chat/{filename}'
    return jsonify({'success': True, 'url': file_url, 'name': file.filename, 'type': ext})
