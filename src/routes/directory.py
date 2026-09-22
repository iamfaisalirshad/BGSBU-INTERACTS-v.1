"""
Alumni Directory Routes
========================
Provides an interactive searchable directory of alumni/students with AJAX
search and filter capabilities. All routes require authentication.
Admins are redirected away from these pages.

Endpoints:
    /directory               - Renders the directory page (HTML)
    /api/search-alumni       - JSON endpoint for filtered directory search
    /api/departments         - JSON endpoint listing all distinct departments
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from db import Database
from utils.decorators import login_required

directory_bp = Blueprint('directory', __name__)


# ==================== DIRECTORY PAGE ====================

@directory_bp.route('/directory')
@login_required
def alumni_directory():
    """
    Render the alumni/student directory page.

    This is a client-side searchable directory. The actual data
    is fetched via GET /api/search-alumni on the frontend.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise renders directory.html.
    """
    # Admins cannot access directory - redirect to admin panel
    if session.get('role') == 'admin':
        flash('Admins cannot access directory. Use Admin Panel to manage users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))
    return render_template('directory.html')


# ==================== SEARCH API ====================

@directory_bp.route('/api/search-alumni', methods=['GET'])
@login_required
def search_alumni():
    """
    AJAX endpoint for filtered, paginated directory search.

    Supports filtering by:
        - q (keyword):    Searches name and email
        - department:     Exact department match
        - company:        Partial company name match
        - skill:          Partial skills match
        - role:           Exact role match (student/alumni)

    Query Params:
        q          (str, optional): General search keyword.
        department (str, optional): Department filter.
        company    (str, optional): Company name filter.
        skill      (str, optional): Skill keyword filter.
        role       (str, optional): Role filter.
        page       (int, optional): Page number (default: 1, 12 per page).

    Returns:
        JSON with keys:
            users        (list): Matching user records.
            total        (int):  Total matching count.
            page         (int):  Current page number.
            per_page     (int):  Results per page.
            total_pages  (int):  Total pages available.
            departments  (list): All distinct departments (for filter dropdown).
    """
    query = request.args.get('q', '').strip()
    department = request.args.get('department', '').strip()
    company = request.args.get('company', '').strip()
    skill = request.args.get('skill', '').strip()
    role_filter = request.args.get('role', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 12
    offset = (page - 1) * per_page
    conditions = ["u.is_active = 1", "u.is_approved = 1", "u.role != 'admin'"]
    params = []
    base_joins = " LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student' LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni' LEFT JOIN user_skills us ON u.id = us.user_id"
    extra_joins = ""
    if query:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"])
    if department:
        conditions.append("u.department = %s")
        params.append(department)
    if company:
        conditions.append("ap.company LIKE %s")
        params.append(f"%{company}%")
    if skill:
        conditions.append("us.skill LIKE %s")
        params.append(f"%{skill}%")
    if role_filter:
        conditions.append("u.role = %s")
        params.append(role_filter)
    where = " AND ".join(conditions)
    all_joins = base_joins + extra_joins
    total = Database.execute_query(f"SELECT COUNT(DISTINCT u.id) as total FROM users u {all_joins} WHERE {where}", params, fetch_one=True)['total']
    data_query = f"""SELECT DISTINCT u.id, u.name, u.email, u.role, u.department,
        COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills,
        sp.joining_year, sp.student_year, sp.batch_year,
        ap.company, ap.current_job_title,
        u.profile_pic, u.bio, u.is_mentor
        FROM users u
        {base_joins}
        {extra_joins}
        WHERE {where}
        GROUP BY u.id ORDER BY u.name ASC LIMIT %s OFFSET %s"""
    params.extend([per_page, offset])
    users = Database.execute_query(data_query, params, fetch_all=True)
    departments = Database.execute_query(
        "SELECT DISTINCT department FROM users WHERE department IS NOT NULL AND department != '' ORDER BY department",
        fetch_all=True)
    return jsonify({'users': users, 'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'departments': [d['department'] for d in departments]})


# ==================== DATA API ====================

@directory_bp.route('/api/departments', methods=['GET'])
@login_required
def get_departments():
    """
    AJAX endpoint returning all distinct departments in the users table.

    Used by the directory frontend to populate the department filter dropdown.

    Returns:
        JSON array of department name strings.
    """
    depts = Database.execute_query(
        "SELECT DISTINCT department FROM users WHERE department IS NOT NULL AND department != '' ORDER BY department",
        fetch_all=True)
    return jsonify([d['department'] for d in depts])
