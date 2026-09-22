"""
Dashboard Routes
=================
Serves the main user dashboard and all "view more" card endpoints.
All routes require authentication (@login_required) and redirect
admins to the admin panel.

The dashboard aggregates: user profile summary, connections count,
pending requests, recommended users, notifications, and platform
statistics (total alumni, jobs, mentors).
"""

from flask import Blueprint, render_template, session, redirect, url_for, request
from db import Database
from utils.decorators import login_required

dashboard_bp = Blueprint('dashboard', __name__)


# ==================== MAIN DASHBOARD ====================

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Render the main dashboard for the logged-in user.

    Fetches:
        - Full user record
        - Accepted connections count
        - Pending connection requests count
        - Up to 5 recommended users based on matching department/skills
          (excluding existing connections and self)
        - Latest 10 notifications
        - Platform-wide stats: total alumni, jobs, mentors
        - User's job application count and connection count

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard.html with all context.
    """
    # Admins should not access dashboard - redirect to admin panel
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    user = Database.execute_query("SELECT * FROM users WHERE id = %s", (user_id,), fetch_one=True)
    # Merge role-specific profile data for template access (safe merge)
    if user:
        if user['role'] == 'student':
            sp = Database.execute_query("SELECT * FROM student_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
            if sp:
                for k, v in sp.items():
                    if k not in ('id', 'user_id'):
                        user[k] = v
        elif user['role'] == 'alumni':
            ap = Database.execute_query("SELECT * FROM alumni_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
            if ap:
                for k, v in ap.items():
                    if k not in ('id', 'user_id'):
                        user[k] = v
        skills = Database.execute_query("SELECT skill FROM user_skills WHERE user_id=%s", (user_id,), fetch_all=True)
        user['skills'] = ', '.join(s['skill'] for s in (skills or []))
    connections_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM connections WHERE (requester_id=%s OR recipient_id=%s) AND status='accepted'",
        (user_id, user_id), fetch_one=True)['count']
    pending_requests = Database.execute_query(
        "SELECT COUNT(*) as count FROM connections WHERE recipient_id=%s AND status='pending'",
        (user_id,), fetch_one=True)['count']
    # Fetch user skills from user_skills table
    user_skill_rows = Database.execute_query(
        "SELECT skill FROM user_skills WHERE user_id=%s", (user_id,), fetch_all=True)
    skill_list = [s['skill'] for s in (user_skill_rows or [])]
    # Recommend based on similar skills
    skill_conditions = []
    skill_params = []
    for skill in skill_list[:5]:
        skill_conditions.append("us.skill LIKE %s")
        skill_params.append(f"%{skill}%")
    skill_where = ""
    skill_join = ""
    if skill_conditions:
        skill_where = f"OR ({' OR '.join(skill_conditions)})"
        skill_join = "LEFT JOIN user_skills us ON u.id = us.user_id"
    query = f"""SELECT DISTINCT u.id, u.name, u.role, u.department, u.profile_pic, u.bio,
        sp.joining_year, sp.passing_year, sp.student_year, sp.batch_year,
        ap.company, ap.current_job_title
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        {skill_join}
        WHERE u.id != %s AND u.is_active = 1 AND u.is_approved = 1 AND u.role != 'admin'
        AND u.id NOT IN (SELECT CASE WHEN requester_id=%s THEN recipient_id ELSE requester_id END
        FROM connections WHERE requester_id=%s OR recipient_id=%s)
        AND (u.department = %s {skill_where}) ORDER BY RAND() LIMIT 6"""
    params = [user_id, user_id, user_id, user_id, user.get('department', '')] + skill_params
    recommended = Database.execute_query(query, params, fetch_all=True)
    notifications = Database.execute_query(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 10",
        (user_id,), fetch_all=True)
    total_alumni = Database.execute_query(
        "SELECT COUNT(*) as count FROM users WHERE role='alumni' AND is_active=1", fetch_one=True)['count']
    total_jobs = Database.execute_query(
        "SELECT COUNT(*) as count FROM jobs WHERE is_active=1 AND is_approved=1", fetch_one=True)['count']
    total_mentors = Database.execute_query(
        "SELECT COUNT(*) as count FROM users WHERE is_mentor=1 AND is_active=1", fetch_one=True)['count']
    total_users = Database.execute_query(
        "SELECT COUNT(*) as count FROM users WHERE role!='admin' AND is_active=1 AND is_approved=1", fetch_one=True)['count']
    total_students = Database.execute_query(
        "SELECT COUNT(*) as count FROM users WHERE role='student' AND is_active=1 AND is_approved=1", fetch_one=True)['count']
    user_applied_jobs = Database.execute_query(
        "SELECT COUNT(*) as count FROM job_applications WHERE user_id=%s", (user_id,), fetch_one=True)['count']
    return render_template('dashboard.html', user=user, connections_count=connections_count,
        pending_requests=pending_requests, recommended=recommended, notifications=notifications,
        total_alumni=total_alumni, total_jobs=total_jobs, total_mentors=total_mentors,
        total_users=total_users, total_students=total_students, user_applied_jobs=user_applied_jobs)


# ==================== DASHBOARD FUNCTIONAL ENDPOINTS ====================

@dashboard_bp.route('/dashboard/alumni')
@login_required
def dashboard_view_alumni():
    """
    Display all alumni (accessed from dashboard card).

    Supports optional search by name, email, or department.

    Query Params:
        search (str, optional): Keyword to filter alumni by name/email/department.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_alumni_view.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    search = request.args.get('search', '')

    conditions = ["role = 'alumni' AND is_active = 1"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR u.department LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(conditions)

    alumni = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.department, u.profile_pic,
        sp.joining_year, COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        ap.company, ap.current_job_title,
        ap.roll_number
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where_clause} ORDER BY u.name ASC""",
        params, fetch_all=True)

    total_count = len(alumni)

    return render_template('dashboard_alumni_view.html',
        alumni=alumni, search=search, total_count=total_count)


@dashboard_bp.route('/dashboard/connections-view')
@login_required
def dashboard_connections_view():
    """
    Display paginated list of accepted connections (from dashboard card).

    Query Params:
        page (int, optional): Page number for pagination (default: 1).

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_connections_view.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    connections = Database.execute_query(
        """SELECT CASE WHEN requester_id=%s THEN recipient_id ELSE requester_id END as connected_user_id,
            CASE WHEN requester_id=%s THEN u2.id ELSE u1.id END as user_id,
            CASE WHEN requester_id=%s THEN u2.name ELSE u1.name END as name,
            CASE WHEN requester_id=%s THEN u2.email ELSE u1.email END as email,
            CASE WHEN requester_id=%s THEN u2.department ELSE u1.department END as department,
            CASE WHEN requester_id=%s THEN u2.profile_pic ELSE u1.profile_pic END as profile_pic,
            CASE WHEN requester_id=%s THEN u2.role ELSE u1.role END as role,
            c.created_at
        FROM connections c
        LEFT JOIN users u1 ON c.requester_id = u1.id
        LEFT JOIN users u2 ON c.recipient_id = u2.id
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted'
        ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
        [user_id]*9 + [per_page, offset], fetch_all=True)

    total_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM connections WHERE (requester_id=%s OR recipient_id=%s) AND status='accepted'",
        (user_id, user_id), fetch_one=True)['count']

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('dashboard_connections_view.html',
        connections=connections, page=page, total_pages=total_pages, total_count=total_count)


@dashboard_bp.route('/dashboard/pending-requests')
@login_required
def dashboard_pending_requests():
    """
    Display paginated list of pending connection requests received by the user.

    Query Params:
        page (int, optional): Page number for pagination (default: 1).

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_pending_requests.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    requests = Database.execute_query(
        """SELECT c.id, u.id as user_id, u.name, u.email, u.department, u.profile_pic, c.created_at
        FROM connections c
        INNER JOIN users u ON c.requester_id = u.id
        WHERE c.recipient_id=%s AND c.status='pending'
        ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
        (user_id, per_page, offset), fetch_all=True)

    total_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM connections WHERE recipient_id=%s AND status='pending'",
        (user_id,), fetch_one=True)['count']

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('dashboard_pending_requests.html',
        requests=requests, page=page, total_pages=total_pages, total_count=total_count)


@dashboard_bp.route('/dashboard/jobs-view')
@login_required
def dashboard_jobs_view():
    """
    Display paginated list of active, approved jobs (from dashboard card).

    Supports optional search by title/company and filter by job_type.

    Query Params:
        search   (str, optional): Keyword to filter jobs by title or company.
        job_type (str, optional): Filter by job type (e.g. full-time, internship).
        page     (int, optional): Page number for pagination (default: 1).

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_jobs_view.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    search = request.args.get('search', '')
    job_type_filter = request.args.get('job_type', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    conditions = ["is_active = 1 AND is_approved = 1"]
    params = []

    if search:
        conditions.append("(title LIKE %s OR company LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if job_type_filter:
        conditions.append("job_type = %s")
        params.append(job_type_filter)

    where_clause = " AND ".join(conditions)
    offset = (page - 1) * per_page

    jobs = Database.execute_query(
        f"""SELECT id, title, company, location, job_type, salary_min, salary_max,
        CONCAT(COALESCE(salary_min, ''), IF(salary_min IS NOT NULL AND salary_max IS NOT NULL, ' - ', ''), COALESCE(salary_max, '')) as salary,
        description, posted_by, created_at
        FROM jobs WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        params + [per_page, offset], fetch_all=True)

    total_count = Database.execute_query(
        f"SELECT COUNT(*) as count FROM jobs WHERE {where_clause}",
        params, fetch_one=True)['count']

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('dashboard_jobs_view.html',
        jobs=jobs, search=search, job_type_filter=job_type_filter,
        page=page, total_pages=total_pages, total_count=total_count)


@dashboard_bp.route('/dashboard/notifications')
@login_required
def dashboard_notifications():
    """
    Display all notifications for the logged-in user on a dedicated page.

    Only students and alumni can access this view;
    admins are redirected to their admin dashboard.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_notifications.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']

    notifications = Database.execute_query(
        """SELECT n.*, u.name as sender_name, u.profile_pic as sender_pic
        FROM notifications n
        LEFT JOIN users u ON n.related_user_id = u.id
        WHERE n.user_id = %s AND n.type != 'new_message'
        ORDER BY n.created_at DESC""",
        (user_id,), fetch_all=True)

    total_count = len(notifications)

    return render_template('dashboard_notifications.html',
        notifications=notifications, total_count=total_count)


@dashboard_bp.route('/dashboard/mentors')
@login_required
def dashboard_mentors():
    """
    Display all available mentors (from dashboard card).

    Mentors are users with is_mentor=1. Supports optional search by name or bio.
    Excludes the current user from results.

    Query Params:
        search (str, optional): Keyword to filter mentors by name or bio.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_mentors_view.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    search = request.args.get('search', '')

    conditions = ["u.is_mentor = 1 AND u.is_active = 1 AND u.id != %s"]
    params = [user_id]

    if search:
        conditions.append("(u.name LIKE %s OR u.bio LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(conditions)

    mentors = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.department, ap.company, u.bio, u.profile_pic,
        sp.joining_year, COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where_clause} ORDER BY u.name ASC""",
        params, fetch_all=True)

    total_count = len(mentors)

    return render_template('dashboard_mentors_view.html',
        mentors=mentors, search=search, total_count=total_count)


@dashboard_bp.route('/dashboard/applied-jobs')
@login_required
def dashboard_applied_jobs():
    """
    Display paginated list of jobs the current user has applied to.

    Query Params:
        page (int, optional): Page number for pagination (default: 1).

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders dashboard_applied_jobs.html.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    applications = Database.execute_query(
        """SELECT a.id, a.status, a.applied_at,
            j.id as job_id, j.title, j.company, j.location, j.job_type,
            CONCAT(COALESCE(j.salary_min, ''), IF(j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL, ' - ', ''), COALESCE(j.salary_max, '')) as salary
        FROM job_applications a
        INNER JOIN jobs j ON a.job_id = j.id
        WHERE a.user_id = %s
        ORDER BY a.applied_at DESC LIMIT %s OFFSET %s""",
        (user_id, per_page, offset), fetch_all=True)

    total_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM job_applications WHERE user_id = %s",
        (user_id,), fetch_one=True)['count']

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('dashboard_applied_jobs.html',
        applications=applications, page=page, total_pages=total_pages, total_count=total_count)



@dashboard_bp.route('/dashboard/all-users')
@login_required
def dashboard_all_users():
    """
    Display all users (students and alumni) with search and role filter.

    Non-admin version of the admin panel's all_users functionality.
    Supports optional search by name, email, department, roll number, or batch year.

    Query Params:
        search (str, optional): Keyword to filter users.
        role (str, optional): Filter by role (student or alumni).

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders a list of all active, approved users.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    
    conditions = ["role != 'admin' AND is_active = 1 AND is_approved = 1"]
    params = []
    
    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR u.department LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    
    if role_filter:
        conditions.append("u.role = %s")
        params.append(role_filter)
    
    where_clause = " AND ".join(conditions)
    
    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.role, u.department, u.profile_pic,
        COALESCE(sp.passing_year, ap.passing_year) as passing_year, sp.joining_year,
        sp.student_year, sp.batch_year, sp.currently_studying,
        ap.company, ap.current_job_title,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        u.created_at
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where_clause} ORDER BY u.created_at DESC""",
        params, fetch_all=True)

    total_count = len(users)

    return render_template('dashboard_all_users_view.html',
        users=users, search=search, role_filter=role_filter, total_count=total_count)


@dashboard_bp.route('/dashboard/total-students')
@login_required
def dashboard_total_students():
    """
    Display all registered students (for alumni panel view).

    Shows all active, approved student accounts with optional search.

    Query Params:
        search (str, optional): Keyword to filter students by name, email, or department.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders a list of all students.
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    search = request.args.get('search', '')

    conditions = ["u.role = 'student' AND u.is_active = 1 AND u.is_approved = 1"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR u.department LIKE %s OR COALESCE(sp.roll_number) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(conditions)

    students = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.department, u.profile_pic,
        sp.joining_year, sp.passing_year, sp.student_year, sp.batch_year, sp.roll_number,
        sp.currently_studying
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        WHERE {where_clause} ORDER BY u.name ASC""",
        params, fetch_all=True)

    total_count = len(students)

    return render_template('dashboard_total_students_view.html',
        students=students, search=search, total_count=total_count)
