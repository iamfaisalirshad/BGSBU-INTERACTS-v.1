"""
Mentorship Routes Module
========================
Comprehensive mentorship subsystem covering the full lifecycle:
- Mentorship requests & response (CRUD)
- Mentorship sessions (schedule, complete, rate)
- Goal & task tracking (create, update, submit, feedback)
- Resource sharing (alumni-shared materials)
- Group mentorship (create, join, message, announce)
- Verified mentor badges (admin)
- Mentorship dashboard (aggregated stats & progress)
"""

from datetime import datetime
from flask import Blueprint, render_template, request, session, flash, jsonify, redirect, url_for
from db import Database
from utils.decorators import login_required, admin_required
from utils.protocols import is_protocol_enabled, protocol_disabled_response, check_mentor_capacity, is_verified_mentor_required

mentorship_bp = Blueprint('mentorship', __name__)


# ==================== MENTORSHIP PAGE (Hub) ====================

@mentorship_bp.route('/mentorship')
@login_required
def mentorship_page():
    """Render the main mentorship hub page.

    Depending on the user's role (student vs. alumni), shows:
    - A list of available mentors (all verified/is_mentor users)
    - The user's outgoing requests (if student)
    - Incoming requests (if alumni/mentor)
    - Active/accepted mentorships with session counts.

    Admins are redirected away.

    Returns:
        Rendered mentorship.html template with all context.
    """
    # Admins cannot access mentorship - redirect to admin panel
    if session.get('role') == 'admin':
        flash('Admins do not participate in mentorship. Use Admin Panel to manage users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    if not is_protocol_enabled('mentorship'):
        flash('Mentorship is currently disabled by admin.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    uid = session['user_id']
    role = session['role']
    mentors = Database.execute_query(
        """SELECT u.id, u.name, u.department, ap.company,
               (SELECT GROUP_CONCAT(DISTINCT skill SEPARATOR ', ') FROM user_skills WHERE user_id=u.id) as skills,
               u.profile_pic, u.bio,
               COALESCE(sp.passing_year, ap.passing_year) as passing_year, sp.joining_year, u.mentor_verified
        FROM users u
        LEFT JOIN alumni_profiles ap ON u.id=ap.user_id
        LEFT JOIN student_profiles sp ON u.id=sp.user_id
        WHERE u.is_mentor=1 AND u.is_active=1 AND u.id!=%s
        ORDER BY u.name ASC""", (uid,), fetch_all=True)
    my_requests = []
    mentor_requests = []
    active_mentorships = []

    # Get active/accepted mentorships for all users
    active_mentorships = Database.execute_query(
        """SELECT m.*, 
                   u_mentor.name as mentor_name, u_mentor.profile_pic as mentor_pic,
                   u_mentee.name as mentee_name, u_mentee.profile_pic as mentee_pic
            FROM mentorship m
            INNER JOIN users u_mentor ON m.mentor_id = u_mentor.id
            INNER JOIN users u_mentee ON m.mentee_id = u_mentee.id
            WHERE (m.mentor_id = %s OR m.mentee_id = %s)
            AND m.status IN ('accepted', 'active')
            ORDER BY m.created_at DESC""",
        (uid, uid), fetch_all=True)

    # Count sessions for each mentorship
    for m in active_mentorships:
        m['session_count'] = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_sessions WHERE mentorship_id=%s",
            (m['id'],), fetch_one=True)['c']

    if role == 'student':
        my_requests = Database.execute_query(
            """SELECT m.*, u.name as mentor_name, u.department, ap.company, u.profile_pic
            FROM mentorship m INNER JOIN users u ON m.mentor_id=u.id LEFT JOIN alumni_profiles ap ON u.id=ap.user_id WHERE m.mentee_id=%s ORDER BY m.created_at DESC""",
            (uid,), fetch_all=True)
    else:
        mentor_requests = Database.execute_query(
            """SELECT m.*, u.name as mentee_name, u.department, u.profile_pic,
                   (SELECT GROUP_CONCAT(DISTINCT skill SEPARATOR ', ') FROM user_skills WHERE user_id=u.id) as skills
            FROM mentorship m INNER JOIN users u ON m.mentee_id=u.id WHERE m.mentor_id=%s ORDER BY m.created_at DESC""",
            (uid,), fetch_all=True)
    mentor_status = {}
    for r in Database.execute_query(
            "SELECT id, mentor_id, status FROM mentorship WHERE mentee_id=%s", (uid,), fetch_all=True):
        mentor_status[r['mentor_id']] = r
    mentor_row = Database.execute_query("SELECT is_mentor FROM users WHERE id=%s", (uid,), fetch_one=True)
    is_mentor = mentor_row['is_mentor'] if mentor_row else False
    return render_template('mentorship.html', mentors=mentors, my_requests=my_requests,
        mentor_requests=mentor_requests, mentor_status=mentor_status, is_mentor=is_mentor,
        active_mentorships=active_mentorships)


# ==================== MENTORSHIP REQUESTS ====================

@mentorship_bp.route('/api/request-mentorship', methods=['POST'])
@login_required
def request_mentorship():
    """Send a mentorship request from a student to a mentor.

    Validates:
    - Mentorship protocol enabled
    - Cannot request self as mentor
    - No duplicate active request

    On success, notifies the mentor.

    Returns:
        JSON success/message or 400/500 error.
    """
    if not is_protocol_enabled('mentorship'):
        return protocol_disabled_response('mentorship')
    uid = session['user_id']
    if session.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Only students can request mentorship'}), 403
    mentor_id = request.json.get('mentor_id')
    reason = request.json.get('reason', '').strip()
    interests = request.json.get('interests', '').strip()
    goals = request.json.get('goals', '').strip()
    message = request.json.get('message', '').strip()
    if not mentor_id:
        return jsonify({'success': False, 'message': 'Mentor ID required'}), 400
    try:
        mentor_id = int(mentor_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid mentor ID'}), 400
    mentor_exists = Database.execute_query("SELECT id FROM users WHERE id=%s", (mentor_id,), fetch_one=True)
    if not mentor_exists:
        return jsonify({'success': False, 'message': 'Mentor not found'}), 404
    if mentor_id == uid:
        return jsonify({'success': False, 'message': 'Cannot mentor yourself'}), 400
    mentor = Database.execute_query("SELECT id, is_mentor, mentor_verified FROM users WHERE id=%s", (mentor_id,), fetch_one=True)
    if not mentor or not mentor['is_mentor']:
        return jsonify({'success': False, 'message': 'User is not a mentor'}), 400
    # Enforce verified mentor protocol
    if is_verified_mentor_required() and not mentor.get('mentor_verified'):
        return jsonify({'success': False, 'message': 'This mentor is not yet verified by admin'}), 403
    # Enforce mentor capacity protocol
    ok, msg = check_mentor_capacity(mentor_id)
    if not ok:
        return jsonify({'success': False, 'message': msg}), 429
    existing = Database.execute_query("SELECT id, status FROM mentorship WHERE mentor_id=%s AND mentee_id=%s",
        (mentor_id, uid), fetch_one=True)
    if existing:
        if existing['status'] == 'rejected':
            Database.execute_query("DELETE FROM mentorship WHERE id=%s", (existing['id'],), commit=True)
        else:
            return jsonify({'success': False, 'message': 'Mentorship already exists with this mentor'}), 400
    try:
        Database.execute_query("INSERT INTO mentorship (mentor_id, mentee_id, reason, interests, goals, message) VALUES (%s, %s, %s, %s, %s, %s)",
            (mentor_id, uid, reason, interests, goals, message), commit=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (uid,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'mentorship_request', %s, %s, %s)",
            (mentor_id, 'New Mentorship Request', f"{user['name']} requested mentorship", "/mentorship"), commit=True)
        return jsonify({'success': True, 'message': 'Mentorship request sent!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/create-task', methods=['POST'])
@login_required
def create_group_task():
    """Create a task for a group and assign to a specific member (mentor only).

    Inserts into mentorship_tasks with type='group' and group_id set.
    Only the group mentor can create tasks.

    Returns:
        JSON success/message or 403/400/500 error.
    """
    group_id = request.json.get('group_id')
    title = request.json.get('title', '').strip()
    description = request.json.get('description', '').strip()
    assigned_to = request.json.get('assigned_to')
    deadline = request.json.get('deadline')

    if not group_id or not title:
        return jsonify({'success': False, 'message': 'Group ID and title are required'}), 400

    is_mentor = Database.execute_query(
        "SELECT id FROM mentorship_groups WHERE id=%s AND mentor_id=%s",
        (group_id, session['user_id']), fetch_one=True)
    if not is_mentor:
        return jsonify({'success': False, 'message': 'Only mentors can create group tasks'}), 403

    try:
        task_id = Database.execute_query(
            """INSERT INTO mentorship_tasks (group_id, created_by, assigned_to, title, description, deadline, type)
               VALUES (%s, %s, %s, %s, %s, %s, 'group')""",
            (group_id, session['user_id'], assigned_to, title, description, deadline), commit=True)

        if assigned_to:
            user = Database.execute_query("SELECT name FROM users WHERE id=%s", (session['user_id'],), fetch_one=True)
            group = Database.execute_query("SELECT name FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
            Database.execute_query(
                "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'group_task', %s, %s, %s)",
                (assigned_to, 'New Group Task', f"{user['name']} assigned a task in {group['name']}: {title}", f"/mentorship/groups/{group_id}"), commit=True)

        return jsonify({'success': True, 'task_id': task_id, 'message': 'Task created!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== GROUP MENTORSHIP ====================

@mentorship_bp.route('/mentorship/groups')
@login_required
def mentorship_groups():
    """Display the group mentorship listing page.

    Shows:
    - Groups I created (alumni only)
    - Groups I've joined
    - Available groups to join (excluding already joined or owned)

    Returns:
        Rendered mentorship_groups.html template.
    """
    if session.get('role') == 'admin':
        flash('Admins do not participate in mentorship.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    uid = session['user_id']
    role = session['role']

    my_groups = []
    if role == 'alumni':
        my_groups = Database.execute_query(
            """SELECT g.*, 
               (SELECT COUNT(*) FROM mentorship_group_members WHERE group_id=g.id AND status='approved') as member_count
               FROM mentorship_groups g WHERE g.mentor_id=%s ORDER BY g.created_at DESC""",
            (uid,), fetch_all=True)

    joined_groups = Database.execute_query(
        """SELECT g.*, u.name as mentor_name, u.profile_pic as mentor_pic,
           (SELECT COUNT(*) FROM mentorship_group_members WHERE group_id=g.id AND status='approved') as member_count
           FROM mentorship_groups g
           INNER JOIN mentorship_group_members m ON g.id=m.group_id AND m.user_id=%s AND m.status='approved'
           INNER JOIN users u ON g.mentor_id=u.id
           ORDER BY g.name ASC""",
        (uid,), fetch_all=True)

    available_groups = Database.execute_query(
        """SELECT g.*, u.name as mentor_name, u.profile_pic as mentor_pic,
           (SELECT COUNT(*) FROM mentorship_group_members WHERE group_id=g.id AND status='approved') as member_count,
           (SELECT status FROM mentorship_group_members WHERE group_id=g.id AND user_id=%s) as my_status
           FROM mentorship_groups g
           INNER JOIN users u ON g.mentor_id=u.id
           WHERE g.is_active=1 AND g.mentor_id!=%s
           AND g.id NOT IN (SELECT group_id FROM mentorship_group_members WHERE user_id=%s AND status='approved')
           ORDER BY g.created_at DESC""",
        (uid, uid, uid), fetch_all=True)

    return render_template('mentorship_groups.html', my_groups=my_groups, 
                          joined_groups=joined_groups, available_groups=available_groups)


@mentorship_bp.route('/api/mentorship/groups/create', methods=['POST'])
@login_required
def create_group():
    """Create a new mentorship group (alumni only).

    The creator is automatically added as an approved member.
    Requires name; description, domain, max_members are optional.

    Returns:
        JSON with group_id or 403/400/500 error.
    """
    if session['role'] != 'alumni':
        return jsonify({'success': False, 'message': 'Only alumni can create groups'}), 403

    name = request.json.get('name', '').strip()
    description = request.json.get('description', '').strip()
    domain = request.json.get('domain', '').strip()
    max_members = request.json.get('max_members', 20)

    if not name:
        return jsonify({'success': False, 'message': 'Group name is required'}), 400

    try:
        group_id = Database.execute_query(
            "INSERT INTO mentorship_groups (mentor_id, name, description, domain, max_members) VALUES (%s, %s, %s, %s, %s)",
            (session['user_id'], name, description, domain, max_members), commit=True)
        Database.execute_query(
            "INSERT INTO mentorship_group_members (group_id, user_id, status) VALUES (%s, %s, 'approved')",
            (group_id, session['user_id']), commit=True)
        return jsonify({'success': True, 'message': 'Group created!', 'group_id': group_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/join', methods=['POST'])
@login_required
def join_group():
    """Request to join a mentorship group.

    If the user already has a pending/approved membership, returns an error.
    Notifies the group mentor of the join request.

    Returns:
        JSON success/message or 400/500 error.
    """
    group_id = request.json.get('group_id')
    if not group_id:
        return jsonify({'success': False, 'message': 'Group ID required'}), 400
    try:
        group = Database.execute_query("SELECT id FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        if not group:
            return jsonify({'success': False, 'message': 'Group not found'}), 404
        existing = Database.execute_query(
            "SELECT id, status FROM mentorship_group_members WHERE group_id=%s AND user_id=%s",
            (group_id, session['user_id']), fetch_one=True)
        if existing:
            return jsonify({'success': False, 'message': f'Already {existing["status"]}'}), 400

        Database.execute_query(
            "INSERT INTO mentorship_group_members (group_id, user_id) VALUES (%s, %s)",
            (group_id, session['user_id']), commit=True)

        group = Database.execute_query("SELECT mentor_id, name FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (session['user_id'],), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'group_join', %s, %s, %s)",
            (group['mentor_id'], 'Group Join Request', f"{user['name']} wants to join {group['name']}", "/mentorship/groups"), commit=True)

        return jsonify({'success': True, 'message': 'Join request sent!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/members', methods=['GET'])
@login_required
def group_members():
    """List all members (and pending requests) for a group.

    Accepts ?group_id query parameter. Returns user details and
    membership status.

    Returns:
        JSON with members array.
    """
    group_id = request.args.get('group_id', type=int)
    members = Database.execute_query(
        """SELECT m.*, u.name, u.email, u.profile_pic, u.role
           FROM mentorship_group_members m
           INNER JOIN users u ON m.user_id=u.id
           WHERE m.group_id=%s
           ORDER BY m.status ASC, m.joined_at DESC""",
        (group_id,), fetch_all=True)
    return jsonify({'success': True, 'members': members})


@mentorship_bp.route('/api/mentorship/groups/approve-member', methods=['POST'])
@login_required
def approve_group_member():
    """Approve or reject a pending group membership request.

    Only the group mentor can take this action. Notifies the applicant.

    Returns:
        JSON success/message or 403/500 error.
    """
    membership_id = request.json.get('membership_id')
    action = request.json.get('action')
    status = 'approved' if action == 'approve' else 'rejected'

    membership = Database.execute_query(
        """SELECT m.*, g.mentor_id, g.name as group_name FROM mentorship_group_members m
           INNER JOIN mentorship_groups g ON m.group_id=g.id
           WHERE m.id=%s""",
        (membership_id,), fetch_one=True)

    if not membership or membership['mentor_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    Database.execute_query(
        "UPDATE mentorship_group_members SET status=%s WHERE id=%s",
        (status, membership_id), commit=True)

    user = Database.execute_query("SELECT name FROM users WHERE id=%s", (session['user_id'],), fetch_one=True)
    Database.execute_query(
        "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'group_membership', %s, %s, %s)",
        (membership['user_id'], 'Group Membership', f"You were {status} to {membership['group_name']}", "/mentorship/groups"), commit=True)

    return jsonify({'success': True, 'message': f'Member {status}'})


@mentorship_bp.route('/mentorship/groups/<int:group_id>')
@login_required
def group_detail(group_id):
    """Render the detailed view of a mentorship group.

    Shows messages, announcements, members (including pending for mentor),
    resources, tasks, etc. Only approved members and the mentor can access.

    Args:
        group_id: The group to view.

    Returns:
        Rendered mentorship_group_detail.html, or redirect if not permitted.
    """
    group = Database.execute_query(
        """SELECT g.*, u.name as mentor_name, u.profile_pic as mentor_pic, u.email as mentor_email
           FROM mentorship_groups g
           INNER JOIN users u ON g.mentor_id=u.id
           WHERE g.id=%s""",
        (group_id,), fetch_one=True)
    if not group:
        flash('Group not found', 'danger')
        return redirect(url_for('mentorship.mentorship_groups'))

    uid = session['user_id']
    is_mentor = group['mentor_id'] == uid
    is_member = Database.execute_query(
        "SELECT id FROM mentorship_group_members WHERE group_id=%s AND user_id=%s AND status='approved'",
        (group_id, uid), fetch_one=True)

    if not is_mentor and not is_member:
        flash('You are not a member of this group', 'warning')
        return redirect(url_for('mentorship.mentorship_groups'))

    messages = Database.execute_query(
        """SELECT m.*, u.name as user_name, u.profile_pic as user_pic
           FROM mentorship_group_messages m
           INNER JOIN users u ON m.user_id=u.id
           WHERE m.group_id=%s ORDER BY m.created_at ASC""",
        (group_id,), fetch_all=True)

    announcements = Database.execute_query(
        """SELECT a.*, u.name as user_name
           FROM mentorship_group_announcements a
           INNER JOIN users u ON a.user_id=u.id
           WHERE a.group_id=%s ORDER BY a.created_at DESC""",
        (group_id,), fetch_all=True)

    members = Database.execute_query(
        """SELECT m.*, u.name, u.profile_pic, u.role
           FROM mentorship_group_members m
           INNER JOIN users u ON m.user_id=u.id
           WHERE m.group_id=%s AND m.status='approved'""",
        (group_id,), fetch_all=True)

    pending_members = []
    if is_mentor:
        pending_members = Database.execute_query(
            """SELECT m.*, u.name, u.email, u.profile_pic, u.role
               FROM mentorship_group_members m
               INNER JOIN users u ON m.user_id=u.id
               WHERE m.group_id=%s AND m.status='pending'""",
            (group_id,), fetch_all=True)

    resources = Database.execute_query(
        "SELECT * FROM mentorship_resources WHERE group_id=%s OR (mentor_id=%s AND group_id IS NULL AND is_public=1) ORDER BY created_at DESC",
        (group_id, uid), fetch_all=True)

    tasks = Database.execute_query(
        """SELECT t.*, u.name as assigned_name
           FROM mentorship_tasks t
           LEFT JOIN users u ON t.assigned_to=u.id
           WHERE t.group_id=%s ORDER BY t.created_at DESC""",
        (group_id,), fetch_all=True)

    return render_template('mentorship_group_detail.html', group=group, messages=messages,
                          announcements=announcements, members=members, pending_members=pending_members,
                          resources=resources, tasks=tasks, is_mentor=is_mentor, is_member=is_member)


@mentorship_bp.route('/api/mentorship/groups/send-message', methods=['POST'])
@login_required
def send_group_message():
    """Post a message to a mentorship group chat.

    Only approved members and the mentor can send messages.

    Returns:
        JSON success/message or 400/403/500 error.
    """
    group_id = request.json.get('group_id')
    content = request.json.get('content', '').strip()

    if not content:
        return jsonify({'success': False, 'message': 'Message is required'}), 400

    is_member = Database.execute_query(
        "SELECT id FROM mentorship_group_members WHERE group_id=%s AND user_id=%s AND status='approved'",
        (group_id, session['user_id']), fetch_one=True)
    is_mentor = Database.execute_query(
        "SELECT id FROM mentorship_groups WHERE id=%s AND mentor_id=%s",
        (group_id, session['user_id']), fetch_one=True)

    if not is_member and not is_mentor:
        return jsonify({'success': False, 'message': 'Not a member'}), 403

    try:
        Database.execute_query(
            "INSERT INTO mentorship_group_messages (group_id, user_id, content) VALUES (%s, %s, %s)",
            (group_id, session['user_id'], content), commit=True)
        return jsonify({'success': True, 'message': 'Message sent'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/delete-message', methods=['POST'])
@login_required
def delete_group_message():
    """Delete a message from a mentorship group chat.

    Only the message sender or the group mentor can delete.

    Returns:
        JSON success/message or 403/404/500 error.
    """
    message_id = request.json.get('message_id')
    if not message_id:
        return jsonify({'success': False, 'message': 'Message ID required'}), 400

    try:
        msg = Database.execute_query(
            "SELECT * FROM mentorship_group_messages WHERE id=%s", (message_id,), fetch_one=True)
        if not msg:
            return jsonify({'success': False, 'message': 'Message not found'}), 404

        uid = session['user_id']
        is_mentor = Database.execute_query(
            "SELECT id FROM mentorship_groups WHERE id=%s AND mentor_id=%s",
            (msg['group_id'], uid), fetch_one=True)

        if msg['user_id'] != uid and not is_mentor:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        Database.execute_query("DELETE FROM mentorship_group_messages WHERE id=%s", (message_id,), commit=True)
        return jsonify({'success': True, 'message': 'Message deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== MENTORSHIP DETAIL PAGE ====================

@mentorship_bp.route('/mentorship/detail/<int:mentorship_id>')
@login_required
def mentorship_detail(mentorship_id):
    mentorship = Database.execute_query(
        """SELECT m.*,
                   u_mentor.name as mentor_name, u_mentor.email as mentor_email,
                   u_mentor.profile_pic as mentor_pic, u_mentor.mentor_verified as mentor_verified,
                   u_mentee.name as mentee_name, u_mentee.email as mentee_email,
                   u_mentee.profile_pic as mentee_pic
            FROM mentorship m
            INNER JOIN users u_mentor ON m.mentor_id = u_mentor.id
            INNER JOIN users u_mentee ON m.mentee_id = u_mentee.id
            WHERE m.id=%s""", (mentorship_id,), fetch_one=True)
    if not mentorship:
        flash('Mentorship not found', 'danger')
        return redirect(url_for('mentorship.mentorship_page'))
    uid = session['user_id']
    if uid != mentorship['mentor_id'] and uid != mentorship['mentee_id']:
        flash('Access denied', 'danger')
        return redirect(url_for('mentorship.mentorship_page'))
    is_mentor = uid == mentorship['mentor_id']
    sessions = Database.execute_query(
        "SELECT * FROM mentorship_sessions WHERE mentorship_id=%s ORDER BY session_date DESC",
        (mentorship_id,), fetch_all=True)
    next_meeting = Database.execute_query(
        "SELECT session_date FROM mentorship_sessions WHERE mentorship_id=%s AND session_date > NOW() ORDER BY session_date ASC LIMIT 1",
        (mentorship_id,), fetch_one=True)
    mentorship['next_meeting'] = next_meeting['session_date'] if next_meeting else None
    tasks = Database.execute_query(
        """SELECT t.*, u.name as assigned_name FROM mentorship_tasks t
           LEFT JOIN users u ON t.assigned_to=u.id
           WHERE t.mentorship_id=%s ORDER BY t.created_at DESC""",
        (mentorship_id,), fetch_all=True)
    resources = Database.execute_query(
        "SELECT * FROM mentorship_resources WHERE mentorship_id=%s ORDER BY created_at DESC",
        (mentorship_id,), fetch_all=True)
    return render_template('mentorship_detail.html', mentorship=mentorship,
        is_mentor=is_mentor, sessions=sessions, tasks=tasks, resources=resources)


# ==================== MENTORSHIP DASHBOARD ====================

@mentorship_bp.route('/mentorship/dashboard')
@login_required
def mentorship_dashboard():
    uid = session['user_id']
    active_mentorships = Database.execute_query(
        """SELECT m.*,
                   u_mentor.name as mentor_name, u_mentor.profile_pic as mentor_pic,
                   u_mentor.mentor_verified as mentor_verified,
                   u_mentee.name as mentee_name, u_mentee.profile_pic as mentee_pic
            FROM mentorship m
            INNER JOIN users u_mentor ON m.mentor_id = u_mentor.id
            INNER JOIN users u_mentee ON m.mentee_id = u_mentee.id
            WHERE (m.mentor_id=%s OR m.mentee_id=%s) AND m.status IN ('accepted','active')
            ORDER BY m.created_at DESC""", (uid, uid), fetch_all=True)
    for m in active_mentorships:
        m['session_count'] = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_sessions WHERE mentorship_id=%s",
            (m['id'],), fetch_one=True)['c']
        m['task_count'] = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_tasks WHERE mentorship_id=%s AND status='completed'",
            (m['id'],), fetch_one=True)['c']
        m['total_tasks'] = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_tasks WHERE mentorship_id=%s",
            (m['id'],), fetch_one=True)['c']
        m['progress_pct'] = int((m['task_count'] / m['total_tasks'] * 100)) if m['total_tasks'] > 0 else 0
    group_count = Database.execute_query(
        "SELECT COUNT(*) as c FROM mentorship_group_members WHERE user_id=%s AND status='approved'",
        (uid,), fetch_one=True)['c']
    resource_count = Database.execute_query(
        "SELECT COUNT(*) as c FROM mentorship_resources WHERE mentor_id=%s",
        (uid,), fetch_one=True)['c']
    total_sessions = sum(m['session_count'] for m in active_mentorships)
    all_tasks = Database.execute_query(
        "SELECT t.status FROM mentorship_tasks t INNER JOIN mentorship m ON t.mentorship_id=m.id WHERE (m.mentor_id=%s OR m.mentee_id=%s)",
        (uid, uid), fetch_all=True)
    overall_total = len(all_tasks)
    overall_done = sum(1 for t in all_tasks if t['status'] == 'completed')
    overall_progress_pct = int((overall_done / overall_total * 100)) if overall_total > 0 else 0
    goal_count = Database.execute_query(
        "SELECT COUNT(*) as c FROM mentorship WHERE (mentor_id=%s OR mentee_id=%s) AND goals IS NOT NULL AND goals!=''",
        (uid, uid), fetch_one=True)['c']
    completed_goal_count = Database.execute_query(
        "SELECT COUNT(*) as c FROM mentorship WHERE (mentor_id=%s OR mentee_id=%s) AND status='completed'",
        (uid, uid), fetch_one=True)['c']
    return render_template('mentorship_dashboard.html', active_mentorships=active_mentorships,
        group_count=group_count, resource_count=resource_count, total_sessions=total_sessions,
        overall_progress_pct=overall_progress_pct, overall_done=overall_done,
        overall_total=overall_total, completed_goal_count=completed_goal_count, goal_count=goal_count)


# ==================== MENTORSHIP RESOURCES ====================

@mentorship_bp.route('/mentorship/resources')
@login_required
def mentorship_resources():
    uid = session['user_id']
    my_resources = Database.execute_query(
        """SELECT r.*, u.name as mentor_name FROM mentorship_resources r
           INNER JOIN users u ON r.mentor_id=u.id
           WHERE r.mentor_id=%s ORDER BY r.created_at DESC""", (uid,), fetch_all=True)
    public_resources = Database.execute_query(
        """SELECT r.*, u.name as mentor_name FROM mentorship_resources r
           INNER JOIN users u ON r.mentor_id=u.id
           WHERE r.is_public=1 AND r.mentor_id!=%s ORDER BY r.created_at DESC""", (uid,), fetch_all=True)
    return render_template('mentorship_resources.html', my_resources=my_resources,
        public_resources=public_resources)


# ==================== TOGGLE MENTOR STATUS ====================

@mentorship_bp.route('/api/toggle-mentor', methods=['POST'])
@login_required
def toggle_mentor():
    if session.get('role') != 'alumni':
        return jsonify({'success': False, 'message': 'Only alumni can toggle mentor status'}), 403
    try:
        user = Database.execute_query("SELECT is_mentor FROM users WHERE id=%s",
            (session['user_id'],), fetch_one=True)
        new = 0 if user['is_mentor'] else 1
        Database.execute_query("UPDATE users SET is_mentor=%s WHERE id=%s",
            (new, session['user_id']), commit=True)
        return jsonify({'success': True, 'message': 'Mentor status updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== RESPOND TO MENTORSHIP REQUEST ====================

@mentorship_bp.route('/api/respond-mentorship', methods=['POST'])
@login_required
def respond_mentorship():
    mentorship_id = request.json.get('mentorship_id')
    action = request.json.get('action')
    if action not in ['accept', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    try:
        mentorship = Database.execute_query(
            "SELECT * FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
        if not mentorship:
            return jsonify({'success': False, 'message': 'Not found'}), 404
        if mentorship['mentor_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        if action == 'accept':
            Database.execute_query("UPDATE mentorship SET status='accepted', accepted_at=NOW() WHERE id=%s",
                (mentorship_id,), commit=True)
            Database.execute_query(
                "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'mentorship_accepted', %s, %s, %s)",
                (mentorship['mentee_id'], 'Mentorship Accepted', 'Your mentorship request was accepted!', '/mentorship'), commit=True)
        else:
            Database.execute_query("UPDATE mentorship SET status='rejected' WHERE id=%s",
                (mentorship_id,), commit=True)
        return jsonify({'success': True, 'message': f'Request {action}ed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== SCHEDULE SESSION ====================

@mentorship_bp.route('/api/mentorship/<int:mentorship_id>/schedule-session', methods=['POST'])
@login_required
def schedule_session(mentorship_id):
    mentorship = Database.execute_query("SELECT * FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
    if not mentorship or (mentorship['mentor_id'] != session['user_id'] and mentorship['mentee_id'] != session['user_id']):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    session_date = request.json.get('session_date')
    if not session_date:
        return jsonify({'success': False, 'message': 'Session date is required'}), 400
    duration = request.json.get('duration')
    notes = request.json.get('notes', '')
    meeting_link = request.json.get('meeting_link', '')
    try:
        Database.execute_query(
            "INSERT INTO mentorship_sessions (mentorship_id, session_date, duration_minutes, notes, meeting_link) VALUES (%s, %s, %s, %s, %s)",
            (mentorship_id, session_date, duration, notes, meeting_link), commit=True)
        return jsonify({'success': True, 'message': 'Session scheduled!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADD GUIDANCE ====================

@mentorship_bp.route('/api/mentorship/<int:mentorship_id>/add-guidance', methods=['POST'])
@login_required
def add_guidance(mentorship_id):
    mentorship = Database.execute_query("SELECT * FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
    if not mentorship or (mentorship['mentor_id'] != session['user_id'] and mentorship['mentee_id'] != session['user_id']):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    content = request.json.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'message': 'Content is required'}), 400
    try:
        existing = Database.execute_query("SELECT guidance_notes FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
        new_notes = (existing['guidance_notes'] + '\n\n---\n' + content) if existing['guidance_notes'] else content
        Database.execute_query("UPDATE mentorship SET guidance_notes=%s WHERE id=%s",
            (new_notes, mentorship_id), commit=True)
        return jsonify({'success': True, 'message': 'Guidance shared!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADD GOALS ====================

@mentorship_bp.route('/api/mentorship/<int:mentorship_id>/add-goals', methods=['POST'])
@login_required
def add_goals(mentorship_id):
    mentorship = Database.execute_query("SELECT * FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
    if not mentorship or (mentorship['mentor_id'] != session['user_id'] and mentorship['mentee_id'] != session['user_id']):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    topic = request.json.get('topic', '').strip()
    goals = request.json.get('goals', '').strip()
    if not goals:
        return jsonify({'success': False, 'message': 'Goals are required'}), 400
    try:
        if topic:
            Database.execute_query("UPDATE mentorship SET topic=%s WHERE id=%s", (topic, mentorship_id), commit=True)
        if goals:
            Database.execute_query("UPDATE mentorship SET goals=%s WHERE id=%s", (goals, mentorship_id), commit=True)
        return jsonify({'success': True, 'message': 'Goals updated!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== RATE SESSION ====================

@mentorship_bp.route('/api/mentorship/<int:session_id>/rate-session', methods=['POST'])
@login_required
def rate_session(session_id):
    rating = request.json.get('rating')
    feedback = request.json.get('feedback', '').strip()
    if not rating or rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Invalid rating'}), 400
    try:
        session_data = Database.execute_query(
            """SELECT ms.*, m.mentor_id, m.mentee_id FROM mentorship_sessions ms
               INNER JOIN mentorship m ON ms.mentorship_id=m.id WHERE ms.id=%s""",
            (session_id,), fetch_one=True)
        if not session_data:
            return jsonify({'success': False, 'message': 'Session not found'}), 404
        uid = session['user_id']
        if uid == session_data['mentor_id']:
            Database.execute_query("UPDATE mentorship_sessions SET feedback_from_mentor=%s, rating=%s WHERE id=%s",
                (feedback, rating, session_id), commit=True)
        elif uid == session_data['mentee_id']:
            Database.execute_query("UPDATE mentorship_sessions SET feedback_from_mentee=%s, rating=%s WHERE id=%s",
                (feedback, rating, session_id), commit=True)
        else:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return jsonify({'success': True, 'message': 'Rating submitted!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== CREATE RESOURCE ====================

@mentorship_bp.route('/api/mentorship/resources/create', methods=['POST'])
@login_required
def create_resource():
    if session['role'] != 'alumni':
        return jsonify({'success': False, 'message': 'Only alumni can share resources'}), 403
    title = request.json.get('title', '').strip()
    description = request.json.get('description', '').strip()
    resource_type = request.json.get('resource_type', 'link')
    url = request.json.get('url', '').strip()
    domain = request.json.get('domain', '').strip()
    is_public = request.json.get('is_public', False)
    if not title:
        return jsonify({'success': False, 'message': 'Title is required'}), 400
    try:
        Database.execute_query(
            "INSERT INTO mentorship_resources (mentor_id, title, description, resource_type, url, domain, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (session['user_id'], title, description, resource_type, url, domain, 1 if is_public else 0), commit=True)
        return jsonify({'success': True, 'message': 'Resource shared!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/announce', methods=['POST'])
@login_required
def group_announce():
    """Post an announcement to a group (mentor only).

    Requires both title and content.

    Returns:
        JSON success/message or 400/403/500 error.
    """
    group_id = request.json.get('group_id')
    title = request.json.get('title', '').strip()
    content = request.json.get('content', '').strip()

    if not title or not content:
        return jsonify({'success': False, 'message': 'Title and content required'}), 400

    is_mentor = Database.execute_query(
        "SELECT id FROM mentorship_groups WHERE id=%s AND mentor_id=%s",
        (group_id, session['user_id']), fetch_one=True)
    if not is_mentor:
        return jsonify({'success': False, 'message': 'Only mentors can announce'}), 403

    try:
        Database.execute_query(
            "INSERT INTO mentorship_group_announcements (group_id, user_id, title, content) VALUES (%s, %s, %s, %s)",
            (group_id, session['user_id'], title, content), commit=True)
        return jsonify({'success': True, 'message': 'Announcement posted!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== VERIFIED MENTOR BADGE SYSTEM ====================

@mentorship_bp.route('/api/admin/mentor/verify', methods=['POST'])
@admin_required
def admin_verify_mentor():
    """Admin endpoint to verify an alumni mentor and assign verified badge.

    Only admins can verify mentors. Sets mentor_verified=1 for the user.

    Returns:
        JSON success/message or 403/404/500 error.
    """
    if session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    mentor_id = request.json.get('mentor_id')
    action = request.json.get('action')  # 'verify' or 'unverify'
    
    mentor = Database.execute_query("SELECT id, name, email FROM users WHERE id=%s AND role='alumni'", (mentor_id,), fetch_one=True)
    if not mentor:
        return jsonify({'success': False, 'message': 'Mentor not found'}), 404
    
    try:
        if action == 'verify':
            Database.execute_query(
                "UPDATE users SET mentor_verified=1 WHERE id=%s",
                (mentor_id,), commit=True)
            Database.execute_query(
                "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'mentor_verified', %s, %s, %s)",
                (mentor_id, 'Mentor Verified ✓', 'Congratulations! You have been verified as a professional mentor', '/mentorship'), commit=True)
            return jsonify({'success': True, 'message': f'Mentor {mentor["name"]} verified!'})
        else:
            Database.execute_query(
                "UPDATE users SET mentor_verified=0 WHERE id=%s",
                (mentor_id,), commit=True)
            return jsonify({'success': True, 'message': f'Verification removed from {mentor["name"]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/analytics/personal', methods=['GET'])
@login_required
def get_personal_analytics():
    """Get comprehensive personal mentorship analytics for the logged-in user.

    Calculates:
    - Total mentorships (as mentor and mentee)
    - Active sessions
    - Task completion rates
    - Goal progress
    - Group participation
    - Session ratings
    - Activity metrics

    Returns:
        JSON with detailed analytics data.
    """
    uid = session['user_id']
    role = session['role']
    
    try:
        # Mentorship counts
        as_mentor = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship WHERE mentor_id=%s AND status IN ('accepted', 'active')",
            (uid,), fetch_one=True)['c']
        as_mentee = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship WHERE mentee_id=%s AND status IN ('accepted', 'active')",
            (uid,), fetch_one=True)['c']
        
        # Session analytics
        total_sessions = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_sessions ms 
               INNER JOIN mentorship m ON ms.mentorship_id=m.id
               WHERE m.mentor_id=%s OR m.mentee_id=%s""",
            (uid, uid), fetch_one=True)['c']
        
        completed_sessions = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_sessions ms
               INNER JOIN mentorship m ON ms.mentorship_id=m.id
               WHERE (m.mentor_id=%s OR m.mentee_id=%s) AND ms.session_date <= NOW()""",
            (uid, uid), fetch_one=True)['c']
        
        upcoming_sessions = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_sessions ms
               INNER JOIN mentorship m ON ms.mentorship_id=m.id
               WHERE (m.mentor_id=%s OR m.mentee_id=%s) AND ms.session_date > NOW()""",
            (uid, uid), fetch_one=True)['c']
        
        # Task analytics
        total_tasks = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_tasks t
               INNER JOIN mentorship m ON t.mentorship_id=m.id
               WHERE m.mentor_id=%s OR m.mentee_id=%s""",
            (uid, uid), fetch_one=True)['c']
        
        completed_tasks = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_tasks t
               INNER JOIN mentorship m ON t.mentorship_id=m.id
               WHERE (m.mentor_id=%s OR m.mentee_id=%s) AND t.status='completed'""",
            (uid, uid), fetch_one=True)['c']
        
        task_completion_rate = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
        
        # Group participation
        group_count = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_group_members WHERE user_id=%s AND status='approved'",
            (uid,), fetch_one=True)['c']
        
        group_messages = Database.execute_query(
            """SELECT COUNT(*) as c FROM mentorship_group_messages
               WHERE user_id=%s""",
            (uid,), fetch_one=True)['c']
        
        # Resource sharing
        resource_count = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_resources WHERE mentor_id=%s",
            (uid,), fetch_one=True)['c']
        
        # Session ratings
        avg_rating = Database.execute_query(
            """SELECT AVG(rating) as avg FROM mentorship_sessions ms
               INNER JOIN mentorship m ON ms.mentorship_id=m.id
               WHERE (m.mentor_id=%s OR m.mentee_id=%s) AND rating IS NOT NULL""",
            (uid, uid), fetch_one=True)
        avg_rating = round(avg_rating['avg'], 2) if avg_rating['avg'] else 0
        
        # Goal progress
        goals_set = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship WHERE (mentor_id=%s OR mentee_id=%s) AND goals IS NOT NULL AND goals!=''",
            (uid, uid), fetch_one=True)['c']
        
        # Recent activity
        recent_sessions = Database.execute_query(
            """SELECT ms.session_date FROM mentorship_sessions ms
               INNER JOIN mentorship m ON ms.mentorship_id=m.id
               WHERE m.mentor_id=%s OR m.mentee_id=%s
               ORDER BY ms.session_date DESC LIMIT 5""",
            (uid, uid), fetch_all=True)
        
        last_activity = recent_sessions[0]['session_date'] if recent_sessions else None
        
        return jsonify({
            'success': True,
            'analytics': {
                'mentorships': {
                    'as_mentor': as_mentor,
                    'as_mentee': as_mentee,
                    'total': as_mentor + as_mentee
                },
                'sessions': {
                    'total': total_sessions,
                    'completed': completed_sessions,
                    'upcoming': upcoming_sessions,
                    'avg_rating': avg_rating
                },
                'tasks': {
                    'total': total_tasks,
                    'completed': completed_tasks,
                    'completion_rate': task_completion_rate
                },
                'groups': {
                    'count': group_count,
                    'messages': group_messages
                },
                'resources': {
                    'shared': resource_count
                },
                'goals': {
                    'set': goals_set
                },
                'last_activity': last_activity.isoformat() if last_activity else None
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/<int:mentorship_id>/analytics', methods=['GET'])
@login_required
def get_mentorship_analytics(mentorship_id):
    """Get detailed analytics for a specific mentorship relationship.

    Shows progress, sessions, tasks, goals, and interaction metrics.

    Returns:
        JSON with mentorship-specific analytics or 403/404 error.
    """
    mentorship = Database.execute_query(
        "SELECT * FROM mentorship WHERE id=%s", (mentorship_id,), fetch_one=True)
    
    if not mentorship:
        return jsonify({'success': False, 'message': 'Mentorship not found'}), 404
    
    uid = session['user_id']
    if uid not in [mentorship['mentor_id'], mentorship['mentee_id']]:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Session data
        sessions = Database.execute_query(
            "SELECT * FROM mentorship_sessions WHERE mentorship_id=%s ORDER BY session_date DESC",
            (mentorship_id,), fetch_all=True)
        
        # Task progress
        tasks = Database.execute_query(
            "SELECT * FROM mentorship_tasks WHERE mentorship_id=%s ORDER BY created_at DESC",
            (mentorship_id,), fetch_all=True)
        
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t['status'] == 'completed')
        task_completion_rate = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
        
        # Session ratings
        ratings = [s['rating'] for s in sessions if s.get('rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        # Activity score (0-100)
        activity_score = min(100, (
            (completed_tasks / max(total_tasks, 1)) * 40 +
            (len(sessions) / max(10, 1)) * 40 +
            (avg_rating / 5) * 20
        ))
        
        return jsonify({
            'success': True,
            'analytics': {
                'duration': {
                    'started': mentorship['created_at'].isoformat() if mentorship['created_at'] else None,
                    'accepted': mentorship['accepted_at'].isoformat() if mentorship.get('accepted_at') else None
                },
                'sessions': {
                    'total': len(sessions),
                    'completed': sum(1 for s in sessions if s['session_date'] <= Database.execute_query("SELECT NOW()", fetch_one=True).get('NOW()')),
                    'avg_rating': round(avg_rating, 2)
                },
                'tasks': {
                    'total': total_tasks,
                    'completed': completed_tasks,
                    'completion_rate': task_completion_rate
                },
                'activity_score': round(activity_score, 1),
                'goals': mentorship.get('goals', ''),
                'topic': mentorship.get('topic', '')
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/session/<int:session_id>/add-reminder', methods=['POST'])
@login_required
def add_session_reminder(session_id):
    """Add or update a reminder for a mentorship session.

    Reminder can be set for before session (1 day, 1 hour, 30 min, etc.)

    Returns:
        JSON success/message or 403/404/500 error.
    """
    reminder_before = request.json.get('reminder_before')  # minutes before session
    
    sess = Database.execute_query(
        """SELECT ms.*, m.mentor_id, m.mentee_id FROM mentorship_sessions ms
           INNER JOIN mentorship m ON ms.mentorship_id=m.id WHERE ms.id=%s""",
        (session_id,), fetch_one=True)
    
    if not sess:
        return jsonify({'success': False, 'message': 'Session not found'}), 404
    
    uid = session['user_id']
    if uid not in [sess['mentor_id'], sess['mentee_id']]:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        Database.execute_query(
            "UPDATE mentorship_sessions SET reminder_before=%s WHERE id=%s",
            (reminder_before, session_id), commit=True)
        return jsonify({'success': True, 'message': 'Reminder set!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/analytics/<int:group_id>', methods=['GET'])
@login_required
def get_group_analytics(group_id):
    """Get analytics for a mentorship group.

    Shows member count, message activity, task completion, participation levels.

    Returns:
        JSON with group analytics or 403/404 error.
    """
    group = Database.execute_query(
        "SELECT * FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
    
    if not group:
        return jsonify({'success': False, 'message': 'Group not found'}), 404
    
    uid = session['user_id']
    is_mentor = group['mentor_id'] == uid
    is_member = Database.execute_query(
        "SELECT id FROM mentorship_group_members WHERE group_id=%s AND user_id=%s AND status='approved'",
        (group_id, uid), fetch_one=True)
    
    if not is_mentor and not is_member:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Member stats
        total_members = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_group_members WHERE group_id=%s AND status='approved'",
            (group_id,), fetch_one=True)['c']
        
        pending_members = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_group_members WHERE group_id=%s AND status='pending'",
            (group_id,), fetch_one=True)['c']
        
        # Activity stats
        total_messages = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_group_messages WHERE group_id=%s",
            (group_id,), fetch_one=True)['c']
        
        total_announcements = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_group_announcements WHERE group_id=%s",
            (group_id,), fetch_one=True)['c']
        
        # Task stats
        total_tasks = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_tasks WHERE group_id=%s",
            (group_id,), fetch_one=True)['c']
        
        completed_tasks = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_tasks WHERE group_id=%s AND status='completed'",
            (group_id,), fetch_one=True)['c']
        
        task_completion_rate = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
        
        # Resource stats
        resources_shared = Database.execute_query(
            "SELECT COUNT(*) as c FROM mentorship_resources WHERE group_id=%s",
            (group_id,), fetch_one=True)['c']
        
        # Member participation (most active members)
        member_activity = Database.execute_query(
            """SELECT u.id, u.name, u.profile_pic,
                      COUNT(m.id) as message_count,
                      COUNT(t.id) as task_count
               FROM users u
               LEFT JOIN mentorship_group_messages m ON u.id=m.user_id AND m.group_id=%s
               LEFT JOIN mentorship_tasks t ON u.id=t.assigned_to AND t.group_id=%s
               WHERE u.id IN (SELECT user_id FROM mentorship_group_members WHERE group_id=%s AND status='approved')
               GROUP BY u.id
               ORDER BY (COUNT(m.id) + COUNT(t.id)) DESC
               LIMIT 10""",
            (group_id, group_id, group_id), fetch_all=True)
        
        return jsonify({
            'success': True,
            'analytics': {
                'members': {
                    'active': total_members,
                    'pending': pending_members
                },
                'activity': {
                    'messages': total_messages,
                    'announcements': total_announcements
                },
                'tasks': {
                    'total': total_tasks,
                    'completed': completed_tasks,
                    'completion_rate': task_completion_rate
                },
                'resources': resources_shared,
                'participation': [
                    {
                        'name': m['name'],
                        'profile_pic': m['profile_pic'],
                        'messages': m['message_count'],
                        'tasks_assigned': m['task_count']
                    } for m in member_activity
                ]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== MY GROUPS (for add-to-group modal) ====================

@mentorship_bp.route('/api/mentorship/my-groups')
@login_required
def my_groups_api():
    uid = session['user_id']
    groups = Database.execute_query(
        """SELECT g.*,
           (SELECT COUNT(*) FROM mentorship_group_members WHERE group_id=g.id AND status='approved') as member_count
           FROM mentorship_groups g
           WHERE g.mentor_id=%s AND g.is_active=1
           ORDER BY g.name ASC""",
        (uid,), fetch_all=True)
    return jsonify({'success': True, 'groups': groups})


# ==================== MY MENTEES (for adding to groups) ====================

@mentorship_bp.route('/api/mentorship/my-mentees')
@login_required
def my_mentees():
    uid = session['user_id']
    mentees = Database.execute_query(
        """SELECT u.id, u.name, u.email, u.profile_pic, u.department, m.id as mentorship_id, m.topic
           FROM mentorship m
           INNER JOIN users u ON m.mentee_id = u.id
           WHERE m.mentor_id = %s AND m.status IN ('accepted', 'active')
           ORDER BY u.name ASC""",
        (uid,), fetch_all=True)
    return jsonify({'success': True, 'mentees': mentees})


# ==================== ADD MEMBER TO GROUP (direct, approved) ====================

@mentorship_bp.route('/api/mentorship/groups/search-students', methods=['GET'])
@login_required
def search_students():
    """Search for students to add to a group (mentor only).

    Query params: q=<search term>, group_id=<group id>.
    Excludes users already in the group.

    Returns:
        JSON with users array.
    """
    q = request.args.get('q', '').strip()
    group_id = request.args.get('group_id', type=int)
    if len(q) < 2 or not group_id:
        return jsonify({'success': False, 'message': 'Query too short'}), 400
    group = Database.execute_query("SELECT mentor_id FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
    if not group or group['mentor_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    users = Database.execute_query(
        """SELECT id, name, email FROM users
           WHERE role='student' AND is_active=1 AND is_approved=1
           AND (name LIKE %s OR email LIKE %s)
           AND id NOT IN (SELECT user_id FROM mentorship_group_members WHERE group_id=%s)
           LIMIT 20""",
        (f"%{q}%", f"%{q}%", group_id), fetch_all=True)
    return jsonify({'success': True, 'users': users})


@mentorship_bp.route('/api/mentorship/groups/add-member', methods=['POST'])
@login_required
def add_group_member():
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    if not group_id or not user_id:
        return jsonify({'success': False, 'message': 'Group and user required'}), 400
    try:
        group = Database.execute_query("SELECT * FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        if not group or group['mentor_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        existing = Database.execute_query(
            "SELECT id, status FROM mentorship_group_members WHERE group_id=%s AND user_id=%s",
            (group_id, user_id), fetch_one=True)
        if existing:
            if existing['status'] == 'approved':
                return jsonify({'success': False, 'message': 'Already a member'}), 400
            Database.execute_query("UPDATE mentorship_group_members SET status='approved' WHERE id=%s",
                (existing['id'],), commit=True)
        else:
            Database.execute_query(
                "INSERT INTO mentorship_group_members (group_id, user_id, status) VALUES (%s, %s, 'approved')",
                (group_id, user_id), commit=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (user_id,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'group_added', %s, %s, %s)",
            (user_id, 'Added to Group', f"You were added to {group['name']}", f"/mentorship/groups/{group_id}"), commit=True)
        return jsonify({'success': True, 'message': f'{user["name"]} added to {group["name"]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/leave', methods=['POST'])
@login_required
def leave_group():
    """Let a member leave a group on their own.

    Removes their membership record. Prevents the mentor from leaving.

    Returns:
        JSON success/message or 400/500 error.
    """
    group_id = request.json.get('group_id')
    if not group_id:
        return jsonify({'success': False, 'message': 'Group ID required'}), 400
    try:
        uid = session['user_id']
        group = Database.execute_query("SELECT mentor_id FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        if not group:
            return jsonify({'success': False, 'message': 'Group not found'}), 404
        if group['mentor_id'] == uid:
            return jsonify({'success': False, 'message': 'Mentor cannot leave. Delete the group instead.'}), 400
        member = Database.execute_query(
            "SELECT id FROM mentorship_group_members WHERE group_id=%s AND user_id=%s AND status='approved'",
            (group_id, uid), fetch_one=True)
        if not member:
            return jsonify({'success': False, 'message': 'Not a member of this group'}), 404
        Database.execute_query("DELETE FROM mentorship_group_members WHERE id=%s", (member['id'],), commit=True)
        return jsonify({'success': True, 'message': 'You have left the group'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/remove-member', methods=['POST'])
@login_required
def remove_group_member():
    group_id = request.json.get('group_id')
    user_id = request.json.get('user_id')
    if not group_id or not user_id:
        return jsonify({'success': False, 'message': 'Group and user required'}), 400
    try:
        group = Database.execute_query("SELECT * FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        if not group or group['mentor_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        if int(user_id) == group['mentor_id']:
            return jsonify({'success': False, 'message': 'Cannot remove the group mentor'}), 400
        member = Database.execute_query(
            "SELECT id FROM mentorship_group_members WHERE group_id=%s AND user_id=%s AND status='approved'",
            (group_id, user_id), fetch_one=True)
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'}), 404
        Database.execute_query("DELETE FROM mentorship_group_members WHERE id=%s", (member['id'],), commit=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (user_id,), fetch_one=True)
        return jsonify({'success': True, 'message': f'{user["name"]} removed from {group["name"]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@mentorship_bp.route('/api/mentorship/groups/delete', methods=['POST'])
@login_required
def delete_group():
    group_id = request.json.get('group_id')
    if not group_id:
        return jsonify({'success': False, 'message': 'Group ID required'}), 400
    try:
        group = Database.execute_query("SELECT * FROM mentorship_groups WHERE id=%s", (group_id,), fetch_one=True)
        if not group or group['mentor_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        Database.execute_query("DELETE FROM mentorship_group_members WHERE group_id=%s", (group_id,), commit=True)
        Database.execute_query("DELETE FROM mentorship_group_messages WHERE group_id=%s", (group_id,), commit=True)
        Database.execute_query("DELETE FROM mentorship_group_announcements WHERE group_id=%s", (group_id,), commit=True)
        Database.execute_query("DELETE FROM mentorship_tasks WHERE group_id=%s", (group_id,), commit=True)
        Database.execute_query("UPDATE mentorship_resources SET group_id=NULL WHERE group_id=%s", (group_id,), commit=True)
        Database.execute_query("DELETE FROM mentorship_groups WHERE id=%s", (group_id,), commit=True)
        return jsonify({'success': True, 'message': f'Group "{group["name"]}" deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
