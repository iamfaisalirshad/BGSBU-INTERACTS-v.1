from flask import Blueprint, jsonify, session, request
from db import Database
from utils.decorators import login_required

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


def _portal_url(role, notif):
    """
    Compute a portal-correct URL for a notification so that clicking it
    navigates within the user's current portal (student, alumni, or admin).

    Students and alumni share the same route space (/profile, /chat, /jobs, etc.).
    Admin has a separate route space (/admin/...).
    """
    action_url = notif.get('action_url') or ''
    ntype = notif.get('type') or ''
    related_user_id = notif.get('related_user_id')
    related_job_id = notif.get('related_job_id')
    related_mentorship_id = notif.get('related_mentorship_id')

    if role == 'admin':
        # Map notification types to admin portal routes
        admin_routes = {
            'account_approved':       '/admin/manage-users',
            'application_update':     f'/admin/applications',
            'job_approval':           f'/admin/pending-jobs',
            'job_application':        f'/admin/applications',
            'mentorship_request':     '/admin/mentorships',
            'mentorship_accepted':    '/admin/mentorships',
            'mentor_verified':        '/admin/mentorships',
            'group_join':             '/admin/groups',
            'group_membership':       '/admin/groups',
            'group_added':            '/admin/groups',
            'group_task':             '/admin/groups',
            'graduation_request':     '/admin/transformation-requests',
        }
        # If the type has a known admin route, use it
        if ntype in admin_routes:
            route = admin_routes[ntype]
            # For entity-specific pages, embed the id as a query param
            if related_job_id and '{job_id}' in route:
                route = route.format(job_id=related_job_id)
            return route
        # Fallback: try to keep the action_url if it points to /admin/ (full URL or path)
        if '/admin/' in action_url:
            from urllib.parse import urlparse
            parsed = urlparse(action_url)
            return parsed.path or action_url
        # Last resort: admin dashboard
        return '/admin/dashboard'

    # Student / Alumni — use the stored action_url directly
    # These roles share the same route space (/profile, /chat, /jobs, etc.)
    if action_url:
        return action_url

    # Fallback by type if action_url is empty
    student_routes = {
        'account_approved':       '/dashboard',
        'connection_request':     f'/profile/{related_user_id}' if related_user_id else '/connections',
        'connection_accepted':    f'/profile/{related_user_id}' if related_user_id else '/connections',
        'connection_response':    f'/profile/{related_user_id}' if related_user_id else '/connections',
        'new_message':            '/chat',
        'message_request':        '/chat?tab=requests',
        'message_request_accepted': '/chat',
        'job_application':        f'/jobs/{related_job_id}' if related_job_id else '/jobs',
        'application_update':     f'/jobs/{related_job_id}' if related_job_id else '/jobs',
        'job_approval':           '/jobs',
        'mentorship_request':     '/mentorship',
        'mentorship_accepted':    '/mentorship',
        'mentor_verified':        '/mentorship',
        'group_join':             '/mentorship',
        'group_membership':       '/mentorship',
        'group_added':            '/mentorship',
        'group_task':             '/mentorship',
    }
    return student_routes.get(ntype, '/dashboard')


@notifications_bp.route('', methods=['GET'])
@login_required
def get_notifications():
    user_id = session['user_id']
    role = session.get('role', 'student')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    notifications = Database.execute_query("""
        SELECT n.*, u.name as sender_name, u.profile_pic as sender_pic
        FROM notifications n
        LEFT JOIN users u ON n.related_user_id = u.id
        WHERE n.user_id = %s AND n.type != 'new_message'
        ORDER BY n.created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset), fetch_all=True)

    for n in notifications:
        n['portal_url'] = _portal_url(role, n)

    return jsonify({'success': True, 'notifications': notifications})


@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
def unread_count():
    user_id = session['user_id']
    count = Database.execute_query(
        "SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0 AND type != 'new_message'",
        (user_id,), fetch_one=True
    )['count']
    return jsonify({'success': True, 'count': count})


@notifications_bp.route('/mark-read', methods=['POST'])
@login_required
def mark_read():
    user_id = session['user_id']
    data = request.get_json() or {}
    notification_id = data.get('notification_id')
    next_url = (data.get('next_url') or '').strip()

    if notification_id:
        Database.execute_query(
            "UPDATE notifications SET is_read = 1, read_at = NOW() WHERE id = %s AND user_id = %s",
            (notification_id, user_id), commit=True
        )
    else:
        Database.execute_query(
            "UPDATE notifications SET is_read = 1, read_at = NOW() WHERE user_id = %s AND is_read = 0",
            (user_id,), commit=True
        )

    if next_url:
        return jsonify({'success': True, 'redirect': next_url})
    return jsonify({'success': True})


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    user_id = session['user_id']
    Database.execute_query(
        "UPDATE notifications SET is_read = 1, read_at = NOW() WHERE user_id = %s AND is_read = 0",
        (user_id,), commit=True
    )
    return jsonify({'success': True})
