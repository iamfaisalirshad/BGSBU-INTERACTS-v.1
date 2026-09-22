"""
Admin Routes Module
===================
Provides the administrative backend for managing the entire platform:
- Dashboard with aggregated platform stats (users, connections, jobs, etc.)
- User CRUD (approve, toggle active, delete, profile edit)
- Job approval workflow (pending jobs, approve/reject)
- Job application management (admin-level status updates)
- Mentorship management (view, accept, reject, complete mentorships)
- Protocol & system settings management
- Dashboard drill-down lists (users, students, alumni, connections, pending approvals)
"""

from flask import Blueprint, render_template, request, session, jsonify, flash, redirect, url_for, current_app
from werkzeug.utils import secure_filename
import os
from db import Database
from utils.decorators import admin_required
from utils.auth_utils import allowed_file
from constants import STUDENT_YEARS, ALL_DEPARTMENTS, DEGREE_SEMESTERS
from utils.audit_logger import AuditLogger

admin_bp = Blueprint('admin', __name__)


# ==================== ADMIN DASHBOARD ====================

@admin_bp.route('/admin')
@admin_required
def admin_dashboard():
    """Render the main admin dashboard with aggregate platform statistics.

    Computes:
    - Total users, students, alumni, pending approvals
    - Accepted connections, active jobs, pending job posts
    - Total messages, ongoing mentorships
    - Also fetches recent users (last 20), pending approval list,
      and department/role distribution for charts.

    Returns:
        Rendered admin.html template with all stats as template vars.
    """
    stats = {}
    for key, query in [
        ('total_users', "SELECT COUNT(*) as c FROM users WHERE role!='admin'"),
        ('total_students', "SELECT COUNT(*) as c FROM users WHERE role='student'"),
        ('total_alumni', "SELECT COUNT(*) as c FROM users WHERE role='alumni'"),
        ('pending_approvals', "SELECT COUNT(*) as c FROM users WHERE is_approved=0"),
        ('total_connections', "SELECT COUNT(*) as c FROM connections WHERE status='accepted'"),
        ('total_jobs', "SELECT COUNT(*) as c FROM jobs WHERE is_active=1 AND is_approved=1"),
        ('pending_applications', "SELECT COUNT(*) as c FROM job_applications WHERE status='applied'"),
        ('pending_job_posts', "SELECT COUNT(*) as c FROM jobs WHERE is_active=1 AND is_approved=0"),
        ('total_messages', "SELECT COUNT(*) as c FROM messages"),
        ('total_mentorships', "SELECT COUNT(*) as c FROM mentorship WHERE status IN ('accepted','active')"),
        ('total_groups', "SELECT COUNT(*) as c FROM mentorship_groups"),
        ('total_transformation_requests', "SELECT COUNT(*) as c FROM users u INNER JOIN student_profiles sp ON u.id=sp.user_id WHERE u.role='student' AND sp.student_year=0"),
    ]:
        stats[key] = Database.execute_query(query, fetch_one=True)['c']
    recent_activity = Database.execute_query("""
        (SELECT 'registration' as type, id as ref_id, name, NULL as detail1, NULL as detail2, created_at, profile_pic FROM users WHERE role!='admin')
        UNION ALL
        (SELECT 'connection' as type, c.id, u1.name, u2.name, NULL, c.created_at, NULL FROM connections c JOIN users u1 ON c.requester_id=u1.id JOIN users u2 ON c.recipient_id=u2.id WHERE c.status='accepted')
        UNION ALL
        (SELECT 'job' as type, id, title, company, NULL, created_at, NULL FROM jobs WHERE is_active=1)
        ORDER BY created_at DESC LIMIT 20
    """, fetch_all=True)
    pending_users = Database.execute_query(
        """SELECT id, name, email, role, created_at
        FROM users WHERE is_approved=0 ORDER BY created_at DESC""", fetch_all=True)
    dept_stats = Database.execute_query(
        """SELECT COALESCE(department, 'General') as department, COUNT(*) as count, role FROM users
        WHERE role!='admin' GROUP BY COALESCE(department, 'General'), role ORDER BY count DESC""", fetch_all=True)
    return render_template('admin.html', **stats, recent_activity=recent_activity,
        pending_users=pending_users, dept_stats=dept_stats)


# ==================== JOB APPLICATION MANAGEMENT ====================

@admin_bp.route('/admin/job-applications')
@admin_required
def admin_job_applications():
    """View all job applications across the platform (admin overview).

    Includes job title, company, applicant info, and current status.

    Returns:
        Rendered admin_job_applications.html template.
    """
    applications = Database.execute_query(
        """SELECT a.id as application_id, a.status, a.applied_at,
            j.title as job_title, j.company as job_company,
            u.id as user_id, u.name as applicant_name, u.email as applicant_email,
            u.department as applicant_department
            FROM job_applications a
            INNER JOIN jobs j ON a.job_id=j.id
            INNER JOIN users u ON a.user_id=u.id
            ORDER BY a.applied_at DESC""",
        fetch_all=True)
    return render_template('admin_job_applications.html', applications=applications)


@admin_bp.route('/api/admin/update-application-status', methods=['POST'])
@admin_required
def admin_update_application_status():
    """Admin override: update any job application's status.

    Valid statuses: reviewed, accepted, rejected. Notifies the applicant.

    Returns:
        JSON success/message or 400/404/500 error.
    """
    application_id = request.json.get('application_id')
    status = request.json.get('status')
    if status not in ['reviewed', 'accepted', 'rejected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    try:
        app_data = Database.execute_query(
            """SELECT a.user_id, a.job_id, j.title FROM job_applications a
            INNER JOIN jobs j ON a.job_id=j.id WHERE a.id=%s""",
            (application_id,), fetch_one=True)
        if not app_data:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        Database.execute_query(
            "UPDATE job_applications SET status=%s WHERE id=%s",
            (status, application_id), commit=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'application_update', %s, %s, %s)",
            (app_data['user_id'], 'Application Status Update', f"Your application for '{app_data['title']}' has been {status}.", "/jobs"), commit=True)
        return jsonify({'success': True, 'message': f'Application {status}'} )
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== JOB APPROVAL WORKFLOW ====================

@admin_bp.route('/admin/approved-jobs')
@admin_required
def admin_approved_jobs():
    """View all approved/published jobs.

    Returns:
        Rendered admin_approved_jobs.html template.
    """
    jobs = Database.execute_query(
        """SELECT j.id as job_id, j.title, j.company, j.location, j.job_type,
            j.salary_min, j.salary_max, j.requirements, j.created_at, j.posted_by,
            u.name as poster_name, u.email as poster_email, u.department as poster_department
            FROM jobs j
            INNER JOIN users u ON j.posted_by=u.id
            WHERE j.is_approved=1 AND j.is_active=1
            ORDER BY j.created_at DESC""",
        fetch_all=True)
    return render_template('admin_approved_jobs.html', jobs=jobs)


@admin_bp.route('/admin/pending-jobs')
@admin_required
def admin_pending_jobs():
    """View all jobs awaiting admin approval.

    Shows job details and poster info for pending review.

    Returns:
        Rendered admin_pending_jobs.html template.
    """
    jobs = Database.execute_query(
        """SELECT j.id as job_id, j.title, j.company, j.location, j.job_type,
            j.salary_min, j.salary_max, j.requirements, j.created_at, u.id as poster_id, u.name as poster_name,
            u.email as poster_email, u.department as poster_department
            FROM jobs j
            INNER JOIN users u ON j.posted_by=u.id
            WHERE j.is_approved=0 AND j.is_active=1
            ORDER BY j.created_at DESC""",
        fetch_all=True)
    return render_template('admin_pending_jobs.html', jobs=jobs)


@admin_bp.route('/api/admin/update-job-approval', methods=['POST'])
@admin_required
def admin_update_job_approval():
    """Approve or reject a pending job posting.

    Sets both is_approved and is_active accordingly. Notifies the poster.

    Returns:
        JSON success/message or 400/404/500 error.
    """
    job_id = request.json.get('job_id')
    status = request.json.get('status')
    if status not in ['approved', 'rejected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    try:
        job = Database.execute_query("SELECT posted_by, title, company FROM jobs WHERE id=%s", (job_id,), fetch_one=True)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found'}), 404
        
        is_approved = 1 if status == 'approved' else 0
        is_active = 1 if status == 'approved' else 0
        Database.execute_query("UPDATE jobs SET is_approved=%s, is_active=%s WHERE id=%s",
            (is_approved, is_active, job_id), commit=True)
        
        message = f"Your job '{job['title']}' has been {status}."
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'job_approval', %s, %s, %s)",
            (job['posted_by'], 'Job Approval Update', message, "/jobs"), commit=True)
        
        # Send approval email if approved
        if status == 'approved':
            poster = Database.execute_query("SELECT name, email FROM users WHERE id=%s", (job['posted_by'],), fetch_one=True)
            if poster:
                from utils.email_service import EmailService
                EmailService.send_job_approved_email(poster['email'], poster['name'], job['title'], job['company'])
        
        return jsonify({'success': True, 'message': f'Job {status}'} )
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== USER MANAGEMENT ====================

@admin_bp.route('/admin/users')
@admin_required
def all_users():
    """View all users with search and role filter.

    Query params: ?search=<term>&role=student|alumni

    Returns:
        Rendered admin_users.html template.
    """
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    conditions = []
    params = []
    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if role_filter:
        conditions.append("role = %s")
        params.append(role_filter)
    where = " AND ".join(conditions) if conditions else "1=1"
    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.role, u.department,
        u.profile_pic,
        COALESCE(sp.passing_year, ap.passing_year) as passing_year, sp.joining_year,
        sp.student_year, sp.batch_year, sp.currently_studying,
        ap.company, ap.current_job_title,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        u.is_approved, u.is_active, u.is_mentor, u.mentor_verified, u.created_at
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where} ORDER BY u.created_at DESC""",
        params, fetch_all=True)

    role_counts = Database.execute_query(
        "SELECT role, COUNT(*) as count FROM users GROUP BY role", fetch_all=True)
    role_count_map = {r['role']: r['count'] for r in role_counts}
    total_all = sum(role_count_map.values())
    total_students = role_count_map.get('student', 0)
    total_alumni = role_count_map.get('alumni', 0)
    total_admins = role_count_map.get('admin', 0)

    return render_template('admin_users.html', users=users, search=search, role_filter=role_filter,
        total_all=total_all, total_students=total_students, total_alumni=total_alumni, total_admins=total_admins)


@admin_bp.route('/api/admin/approve-user', methods=['POST'])
@admin_required
def approve_user():
    """Approve a user account that is pending approval.

    Sets is_approved=1 and sends a notification to the user.

    Returns:
        JSON success/message or 500 error.
    """
    user_id = request.json.get('user_id')
    try:
        user = Database.execute_query("SELECT name, email FROM users WHERE id=%s", (user_id,), fetch_one=True)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        Database.execute_query("UPDATE users SET is_approved=1 WHERE id=%s", (user_id,), commit=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message) VALUES (%s, 'account_approved', 'Account Approved', 'Your account has been approved!')",
            (user_id,), commit=True)
        
        # Send approval email
        from utils.email_service import EmailService
        EmailService.send_account_approved_email(user['email'], user['name'])
        
        return jsonify({'success': True, 'message': 'User approved'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/admin/toggle-active', methods=['POST'])
@admin_required
def toggle_active():
    """Toggle a user's active/inactive status (soft disable).

    Inactive users cannot log in or interact with the platform.

    Returns:
        JSON with new is_active state or 500 error.
    """
    user_id = request.json.get('user_id')
    try:
        user = Database.execute_query("SELECT is_active FROM users WHERE id=%s", (user_id,), fetch_one=True)
        new_status = 0 if user['is_active'] else 1
        Database.execute_query("UPDATE users SET is_active=%s WHERE id=%s", (new_status, user_id), commit=True)
        return jsonify({'success': True, 'is_active': new_status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/admin/delete-user', methods=['POST'])
@admin_required
def delete_user():
    """Permanently delete a non-admin user from the database.

    WARNING: This cascading delete removes all associated data.

    Returns:
        JSON success/message or 500 error.
    """
    user_id = request.json.get('user_id')
    try:
        Database.execute_query("DELETE FROM users WHERE id=%s AND role!='admin'", (user_id,), commit=True)
        return jsonify({'success': True, 'message': 'User deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN PROFILE MANAGEMENT ====================

@admin_bp.route('/admin/profile/<int:user_id>')
@admin_required
def admin_view_profile(user_id):
    """View and manage a user's profile with admin-level access.

    Displays all user fields, with admin controls for editing.

    Args:
        user_id: The user to view.

    Returns:
        Rendered admin_profile_view.html template.
    """
    user = Database.execute_query("SELECT * FROM users WHERE id=%s", (user_id,), fetch_one=True)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.all_users'))

    # Merge role-specific profile data (safe merge: never overwrite user id/user_id)
    if user['role'] == 'student':
        sp = Database.execute_query(
            "SELECT * FROM student_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if sp:
            for k, v in sp.items():
                if k not in ('id', 'user_id'):
                    user[k] = v
    elif user['role'] == 'alumni':
        ap = Database.execute_query(
            "SELECT * FROM alumni_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if ap:
            for k, v in ap.items():
                if k not in ('id', 'user_id'):
                    user[k] = v
    skills = Database.execute_query(
        "SELECT skill FROM user_skills WHERE user_id=%s", (user_id,), fetch_all=True)
    user['skills'] = ', '.join(s['skill'] for s in (skills or []))
    work_exp = Database.execute_query(
        "SELECT * FROM work_experiences WHERE user_id=%s ORDER BY start_date DESC", (user_id,), fetch_all=True)
    user['job_history'] = '\n'.join(
        f"{w.get('job_title','')} at {w.get('company','')} ({w.get('start_date','')} - {w.get('end_date','') or 'Present'})"
        for w in (work_exp or []) if w.get('job_title') or w.get('company'))
    user['work_experiences'] = work_exp or []

    return render_template('admin_profile_view.html', user=user, departments=ALL_DEPARTMENTS, 
                         student_years=STUDENT_YEARS, degree_semesters=DEGREE_SEMESTERS)


@admin_bp.route('/admin/profile/<int:user_id>/edit', methods=['POST'])
@admin_required
def admin_edit_user_profile(user_id):
    """Admin edit user profile with special override permissions.

    Allows changing name, email, role, department, student/alumni fields,
    profile picture, and admin flags (is_active, is_approved, is_mentor).
    Only updates non-empty fields to avoid overwriting data with blanks.

    Args:
        user_id: The user to edit.

    Returns:
        JSON success/message or 400/500 error.
    """
    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        department = request.form.get('department', '').strip()
        phone = request.form.get('phone', '').strip()
        bio = request.form.get('bio', '').strip()
        role = request.form.get('role', '').strip()

        # Validate required fields
        if not name or not email:
            return jsonify({'success': False, 'message': 'Name and email are required'}), 400

        # Student-specific fields
        student_year = request.form.get('student_year')
        currently_studying = request.form.get('currently_studying') == 'on'
        degree_completed = request.form.get('degree_completed') == '1' if request.form.get('degree_completed') else False
        if degree_completed:
            student_year = '0'
            currently_studying = False
        batch_year = request.form.get('batch_year')

        # Alumni-specific fields
        current_job_title = request.form.get('current_job_title', '').strip()
        company = request.form.get('current_company', '').strip()  # form still sends as current_company for backwards compat
        job_start_date = request.form.get('job_start_date')
        job_history = request.form.get('job_history', '').strip()

        # New fields
        roll_number = request.form.get('roll_number', '').strip()
        joining_year = request.form.get('joining_year')
        skills = request.form.get('skills', '').strip()
        is_active = request.form.get('is_active') == '1'
        is_approved = request.form.get('is_approved') == '1'
        is_mentor = request.form.get('is_mentor') == '1'

        # Admin notes
        admin_notes = request.form.get('admin_notes', '').strip()

        # Handle profile picture upload
        profile_pic_filename = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename and allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
                filename = secure_filename(f"{user_id}_{file.filename}")
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                profile_pic_filename = filename

        # Build update query for core user fields only
        updates = []
        params = []

        updates.append("name=%s"); params.append(name)
        updates.append("email=%s"); params.append(email)
        if role:
            updates.append("role=%s"); params.append(role)
        updates.append("department=%s"); params.append(department if department else None)
        updates.append("phone=%s"); params.append(phone if phone else None)
        updates.append("bio=%s"); params.append(bio if bio else None)
        updates.append("interests=%s"); params.append(request.form.get('interests', '').strip())
        updates.append("admin_notes=%s"); params.append(admin_notes if admin_notes else None)

        # Boolean toggles
        updates.append("is_active=%s"); params.append(1 if is_active else 0)
        updates.append("is_approved=%s"); params.append(1 if is_approved else 0)
        updates.append("is_mentor=%s"); params.append(1 if is_mentor else 0)

        if profile_pic_filename:
            updates.append("profile_pic=%s"); params.append(profile_pic_filename)

        if updates:
            params.append(user_id)
            query = f"UPDATE users SET {', '.join(updates)} WHERE id=%s"
            Database.execute_query(query, params, commit=True)

        # Update role-specific profile tables
        current_role = role or Database.execute_query("SELECT role FROM users WHERE id=%s", (user_id,), fetch_one=True)['role']
        if current_role == 'student':
            def safe_int(val):
                try: return int(val) if val else None
                except: return None
            Database.execute_query(
                """INSERT INTO student_profiles (user_id, roll_number, joining_year, student_year, batch_year, currently_studying)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE roll_number=%s, joining_year=%s, student_year=%s, batch_year=%s, currently_studying=%s""",
                (user_id, roll_number, safe_int(joining_year), safe_int(student_year), safe_int(batch_year),
                 1 if currently_studying else 0,
                 roll_number, safe_int(joining_year), safe_int(student_year), safe_int(batch_year), 1 if currently_studying else 0),
                commit=True)
            if safe_int(student_year) == 0:
                admins = Database.execute_query("SELECT id FROM users WHERE role='admin'", fetch_all=True)
                if admins:
                    for a in admins:
                        Database.execute_query(
                            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'graduation_request', 'Degree Completion Request', %s, %s)",
                            (a['id'], f'{name} has marked Degree Completed and requests alumni conversion.', url_for('admin.admin_transformation_requests', _external=True)),
                            commit=True)
        elif current_role == 'alumni':
            Database.execute_query(
                """INSERT INTO alumni_profiles (user_id, roll_number, company, current_job_title, job_start_date)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE roll_number=%s, company=%s, current_job_title=%s, job_start_date=%s""",
                (user_id, roll_number, company, current_job_title, job_start_date,
                 roll_number, company, current_job_title, job_start_date),
                commit=True)

        # Update skills: replace all
        Database.execute_query("DELETE FROM user_skills WHERE user_id=%s", (user_id,), commit=True)
        if skills:
            for s in [s.strip() for s in skills.split(',') if s.strip()]:
                Database.execute_query(
                    "INSERT INTO user_skills (user_id, skill) VALUES (%s, %s) ON DUPLICATE KEY UPDATE skill=skill",
                    (user_id, s), commit=True)

        # Update work_experiences for alumni
        if current_role == 'alumni':
            Database.execute_query("DELETE FROM work_experiences WHERE user_id=%s", (user_id,), commit=True)
            import re
            job_fields = {k: v for k, v in request.form.items() if k.startswith('job_title_')}
            for field_name, job_title in job_fields.items():
                m = re.match(r'job_title_(\d+)', field_name)
                if not m: continue
                idx = m.group(1)
                comp = request.form.get(f'company_{idx}', '').strip()
                role = request.form.get(f'role_{idx}', '').strip()
                start_date = request.form.get(f'start_date_{idx}', '').strip()
                end_date = request.form.get(f'end_date_{idx}', '').strip()
                is_current = request.form.get(f'is_current_{idx}') == '1'
                if job_title.strip() or comp.strip():
                    Database.execute_query(
                        "INSERT INTO work_experiences (user_id, job_title, company, role, start_date, end_date, is_current) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (user_id, job_title.strip(), comp, role, start_date or None, end_date or None, 1 if is_current else 0),
                        commit=True)

        return jsonify({'success': True, 'message': 'User profile updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ENHANCED USER MANAGEMENT ====================

@admin_bp.route('/admin/manage-users')
@admin_required
def manage_users():
    """Enhanced user management page with role + department filtering.

    Query params: ?search=<term>&role=student|alumni&dept=<department>

    Returns:
        Rendered admin_manage_users.html template.
    """
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    dept_filter = request.args.get('dept', '')

    conditions = ["role != 'admin'"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if role_filter:
        conditions.append("role = %s")
        params.append(role_filter)
    if dept_filter:
        conditions.append("department = %s")
        params.append(dept_filter)

    where = " AND ".join(conditions)
    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.role, u.department,
            u.profile_pic,
            COALESCE(sp.passing_year, ap.passing_year) as passing_year, sp.joining_year,
            sp.student_year, sp.batch_year,
            ap.company, ap.current_job_title,
            COALESCE(sp.roll_number, ap.roll_number) as roll_number,
            u.is_approved, u.is_active, u.created_at
            FROM users u
            LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
            LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
            WHERE {where} ORDER BY u.created_at DESC""",
        params, fetch_all=True)

    return render_template('admin_manage_users.html', users=users, search=search, 
                         role_filter=role_filter, dept_filter=dept_filter, 
                         departments=ALL_DEPARTMENTS)


@admin_bp.route('/api/admin/update-job-history', methods=['POST'])
@admin_required
def update_job_history():
    """Append a job history entry for an alumni user (admin).

    Formats the entry as "Title at Company (start - end)" and appends
    it to the existing job_history text field.

    Returns:
        JSON success/message or 500 error.
    """
    try:
        user_id = request.json.get('user_id')
        job_title = request.json.get('job_title', '').strip()
        company = request.json.get('company', '').strip()
        start_date = request.json.get('start_date')
        end_date = request.json.get('end_date')
        is_current = request.json.get('is_current', False)

        # Insert into work_experiences table
        Database.execute_query(
            """INSERT INTO work_experiences (user_id, job_title, company, start_date, end_date, is_current)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, job_title, company, start_date, end_date, 1 if is_current else 0), commit=True)

        # Also update alumni_profiles with latest company
        Database.execute_query(
            "INSERT INTO alumni_profiles (user_id, company, current_job_title) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE company=%s, current_job_title=%s",
            (user_id, company, job_title, company, job_title), commit=True)

        return jsonify({'success': True, 'message': 'Job history updated'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/admin/update-student-status', methods=['POST'])
@admin_required
def update_student_status():
    """Update a student's year and studying status (admin).

    Returns:
        JSON success/message or 500 error.
    """
    try:
        user_id = request.json.get('user_id')
        student_year = request.json.get('student_year')
        currently_studying = request.json.get('currently_studying', True)
        batch_year = request.json.get('batch_year')

        Database.execute_query(
            """INSERT INTO student_profiles (user_id, student_year, currently_studying, batch_year)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE student_year=%s, currently_studying=%s, batch_year=%s""",
            (user_id, student_year, 1 if currently_studying else 0, batch_year,
             student_year, 1 if currently_studying else 0, batch_year), commit=True)

        return jsonify({'success': True, 'message': 'Student status updated'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== PROTOCOL & SYSTEM SETTINGS ====================

@admin_bp.route('/admin/protocols')
@admin_required
def manage_protocols():
    """View and manage system protocol settings.

    Protocols control feature toggles (messaging, jobs, mentorship)
    and their constraints (quotas, connection requirements, etc.).

    Returns:
        Rendered admin_protocols.html template.
    """
    # Ensure all protocol types exist in the database
    protocol_types = ['messaging', 'connections', 'jobs', 'mentorship', 'applications']
    for ptype in protocol_types:
        existing = Database.execute_query(
            "SELECT id FROM system_protocols WHERE protocol_type=%s",
            (ptype,), fetch_one=True)
        if not existing:
            Database.execute_query(
                "INSERT INTO system_protocols (protocol_type, is_enabled, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
                (ptype, 1), commit=True)
    
    protocols = Database.execute_query(
        "SELECT * FROM system_protocols ORDER BY protocol_type",
        fetch_all=True)
    return render_template('admin_protocols.html', protocols=protocols)


@admin_bp.route('/api/admin/update-setting', methods=['POST'])
@admin_required
def update_setting():
    """Update or create a system setting (key-value store).

    Upserts into the system_settings table.

    Returns:
        JSON success/message or 500 error.
    """
    setting_key = request.json.get('setting_key')
    setting_value = request.json.get('setting_value')
    try:
        existing = Database.execute_query(
            "SELECT id FROM system_settings WHERE setting_key=%s",
            (setting_key,), fetch_one=True)
        if existing:
            Database.execute_query(
                "UPDATE system_settings SET setting_value=%s WHERE setting_key=%s",
                (setting_value, setting_key), commit=True)
        else:
            Database.execute_query(
                "INSERT INTO system_settings (setting_key, setting_value, data_type) VALUES (%s, %s, 'string')",
                (setting_key, setting_value), commit=True)
        return jsonify({'success': True, 'message': 'Setting updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/admin/update-protocol', methods=['POST'])
@admin_required
def update_protocol():
    """Update system protocol settings (enable/disable, quotas, etc.).

    Handles all protocol types: messaging, connections, jobs, mentorship, applications.
    Only updates columns that exist in the table; ignores unknown fields gracefully.

    Returns:
        JSON success/message or 500 error.
    """
    try:
        data = request.json or {}
        protocol_type = data.get('protocol_type')
        if not protocol_type:
            return jsonify({'success': False, 'message': 'protocol_type required'}), 400

        # Ensure the protocol row exists (upsert)
        existing = Database.execute_query(
            "SELECT id FROM system_protocols WHERE protocol_type=%s",
            (protocol_type,), fetch_one=True)
        if not existing:
            Database.execute_query(
                "INSERT INTO system_protocols (protocol_type, is_enabled, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
                (protocol_type, data.get('is_enabled', 1)), commit=True)

        # Map of all supported fields → DB column names
        field_map = {
            'is_enabled':                       'is_enabled',
            'max_messages_per_day':             'max_messages_per_day',
            'message_retention_days':           'message_retention_days',
            'require_connection_for_messaging': 'require_connection_for_messaging',
            'auto_delete_messages':             'auto_delete_messages',
            'max_connections_per_day':          'max_connections_per_day',
            'max_total_connections':            'max_total_connections',
            'max_jobs_per_alumni':              'max_jobs_per_alumni',
            'max_applications_per_student':     'max_applications_per_student',
            'require_admin_approval':           'require_admin_approval',
            'max_mentorships_per_mentor':       'max_mentorships_per_mentor',
            'max_sessions_per_mentorship':      'max_sessions_per_mentorship',
            'require_verified_mentor':          'require_verified_mentor',
            'max_applications_per_job':         'max_applications_per_job',
            'application_review_days':          'application_review_days',
        }

        # Build SET clause only for fields present in request
        set_clauses = ['updated_at=NOW()', 'updated_by=%s']
        values = [session['user_id']]
        for key, col in field_map.items():
            if key in data:
                set_clauses.insert(0, f'{col}=%s')
                values.insert(0, data[key])

        if len(set_clauses) <= 2:
            # If no fields to update besides updated_at and updated_by
            values.append(protocol_type)
            Database.execute_query(
                f"UPDATE system_protocols SET updated_at=NOW(), updated_by=%s WHERE protocol_type=%s",
                (session['user_id'], protocol_type), commit=True)
        else:
            values.append(protocol_type)
            try:
                Database.execute_query(
                    f"UPDATE system_protocols SET {', '.join(set_clauses)} WHERE protocol_type=%s",
                    tuple(values), commit=True)
            except Exception as ex:
                # Column might not exist yet — fallback: only update core fields
                is_enabled = data.get('is_enabled', 1)
                Database.execute_query(
                    "UPDATE system_protocols SET is_enabled=%s, updated_by=%s, updated_at=NOW() WHERE protocol_type=%s",
                    (is_enabled, session['user_id'], protocol_type), commit=True)

        label = protocol_type.capitalize()
        return jsonify({'success': True, 'message': f'{label} protocol updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500



# ==================== ADMIN MENTORSHIP MANAGEMENT ====================

@admin_bp.route('/admin/mentorship')
@admin_required
def admin_mentorship_management():
    """View all mentorships in the system (paginated, admin view).

    Shows mentor/mentee info, session counts, and average ratings.

    Query params: ?page=<page_number> (default 1, 20 per page).

    Returns:
        Rendered admin_mentorship.html template.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    mentorships = Database.execute_query(
        """SELECT m.*, 
                   u_mentor.name as mentor_name, u_mentor.email as mentor_email, u_mentor.profile_pic as mentor_pic,
                   u_mentee.name as mentee_name, u_mentee.email as mentee_email, u_mentee.profile_pic as mentee_pic,
                   COUNT(DISTINCT ms.id) as session_count,
                   AVG(ms.rating) as avg_rating
            FROM mentorship m
            INNER JOIN users u_mentor ON m.mentor_id = u_mentor.id
            INNER JOIN users u_mentee ON m.mentee_id = u_mentee.id
            LEFT JOIN mentorship_sessions ms ON m.id = ms.mentorship_id
            GROUP BY m.id
            ORDER BY m.created_at DESC LIMIT %s OFFSET %s""",
        (per_page, offset), fetch_all=True)

    total = Database.execute_query(
        "SELECT COUNT(*) as count FROM mentorship",
        fetch_one=True)['count']

    return render_template('admin_mentorship.html', mentorships=mentorships,
                         total_pages=(total + per_page - 1) // per_page, current_page=page)


@admin_bp.route('/admin/mentorship/<int:mentorship_id>')
@admin_required
def admin_view_mentorship(mentorship_id):
    """View detailed info about a specific mentorship (admin).

    Shows mentorship metadata plus all sessions with ratings.

    Args:
        mentorship_id: The mentorship to view.

    Returns:
        Rendered admin_mentorship_detail.html, or redirect if not found.
    """
    mentorship = Database.execute_query(
        """SELECT m.*, 
                   u_mentor.name as mentor_name, u_mentor.email as mentor_email, u_mentor.profile_pic as mentor_pic,
                   u_mentee.name as mentee_name, u_mentee.email as mentee_email, u_mentee.profile_pic as mentee_pic
            FROM mentorship m
            INNER JOIN users u_mentor ON m.mentor_id = u_mentor.id
            INNER JOIN users u_mentee ON m.mentee_id = u_mentee.id
            WHERE m.id = %s""", (mentorship_id,), fetch_one=True)

    if not mentorship:
        flash('Mentorship not found', 'danger')
        return redirect(url_for('admin.admin_mentorship_management'))

    sessions = Database.execute_query(
        """SELECT * FROM mentorship_sessions 
           WHERE mentorship_id = %s 
           ORDER BY session_date DESC""",
        (mentorship_id,), fetch_all=True)

    return render_template('admin_mentorship_detail.html', mentorship=mentorship, sessions=sessions)


@admin_bp.route('/api/admin/mentorship-action', methods=['POST'])
@admin_required
def admin_mentorship_action():
    """Perform admin actions on a mentorship (accept, reject, complete).

    Overrides normal participant-only controls. Notifications are handled
    at the application level as needed.

    Returns:
        JSON with new status or 400/404/500 error.
    """
    mentorship_id = request.json.get('mentorship_id')
    action = request.json.get('action')

    if action not in ['accept', 'reject', 'complete']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

    try:
        mentorship = Database.execute_query(
            "SELECT * FROM mentorship WHERE id=%s",
            (mentorship_id,), fetch_one=True)

        if not mentorship:
            return jsonify({'success': False, 'message': 'Mentorship not found'}), 404

        if action == 'accept':
            new_status = 'accepted'
            Database.execute_query(
                "UPDATE mentorship SET status=%s, accepted_at=NOW() WHERE id=%s",
                (new_status, mentorship_id), commit=True)
        elif action == 'reject':
            new_status = 'rejected'
            Database.execute_query(
                "UPDATE mentorship SET status=%s WHERE id=%s",
                (new_status, mentorship_id), commit=True)
        elif action == 'complete':
            new_status = 'completed'
            Database.execute_query(
                "UPDATE mentorship SET status=%s, completed_at=NOW() WHERE id=%s",
                (new_status, mentorship_id), commit=True)

        return jsonify({'success': True, 'message': f'Mentorship {action}ed', 'status': new_status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== DASHBOARD DRILL-DOWN LISTS ====================

@admin_bp.route('/admin/dashboard/users-list')
@admin_required
def dashboard_users_list():
    """View all non-admin users (drill-down from dashboard card).

    Supports search and role filter.

    Returns:
        Rendered admin_dashboard_list.html template.
    """
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')

    conditions = ["role != 'admin'"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR COALESCE(sp.roll_number, ap.roll_number) LIKE %s OR CAST(COALESCE(sp.passing_year, ap.passing_year) AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    if role_filter:
        conditions.append("role = %s")
        params.append(role_filter)

    where_clause = " AND ".join(conditions)

    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.role, u.department,
        u.profile_pic,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        sp.joining_year, sp.student_year, sp.batch_year,
        ap.company, ap.current_job_title,
        u.is_approved, u.is_active, u.created_at 
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where_clause} ORDER BY u.created_at DESC""",
        params, fetch_all=True)
    
    total_count = len(users)
    
    return render_template('admin_dashboard_list.html', 
        users=users, title="All Users", search=search, role_filter=role_filter,
        total_count=total_count, list_type='users')


@admin_bp.route('/admin/dashboard/students-list')
@admin_required
def dashboard_students_list():
    """View all registered students (drill-down from dashboard).

    Supports search by name/email.

    Returns:
        Rendered admin_dashboard_list.html template.
    """
    search = request.args.get('search', '')

    conditions = ["role = 'student'"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR sp.roll_number LIKE %s OR CAST(sp.passing_year AS CHAR) LIKE %s OR CAST(sp.joining_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(conditions)

    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.department, u.profile_pic,
        sp.roll_number, sp.passing_year, sp.joining_year, sp.student_year, sp.batch_year,
        u.is_approved, u.is_active, u.created_at 
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id
        WHERE {where_clause} ORDER BY u.created_at DESC""",
        params, fetch_all=True)
    
    total_count = len(users)
    
    return render_template('admin_dashboard_list.html', 
        users=users, title="Students", search=search,
        total_count=total_count, list_type='students')


@admin_bp.route('/admin/dashboard/alumni-list')
@admin_required
def dashboard_alumni_list():
    """View all registered alumni (drill-down from dashboard).

    Supports search by name/email.

    Returns:
        Rendered admin_dashboard_list.html template.
    """
    search = request.args.get('search', '')

    conditions = ["role = 'alumni'"]
    params = []

    if search:
        conditions.append("(u.name LIKE %s OR u.email LIKE %s OR ap.roll_number LIKE %s OR CAST(ap.passing_year AS CHAR) LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(conditions)

    users = Database.execute_query(
        f"""SELECT u.id, u.name, u.email, u.phone, u.department, u.profile_pic,
        ap.company, ap.current_job_title, ap.roll_number, ap.passing_year,
        u.is_approved, u.is_active, u.created_at
        FROM users u
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE {where_clause} ORDER BY u.created_at DESC""",
        params, fetch_all=True)

    total_count = len(users)

    return render_template('admin_dashboard_list.html', 
        users=users, title="Alumni", search=search,
        total_count=total_count, list_type='alumni')


@admin_bp.route('/admin/dashboard/connections-list')
@admin_required
def dashboard_connections_list():
    """View all accepted connections between users.

    Returns:
        Rendered admin_dashboard_connections.html template.
    """
    connections = Database.execute_query(
        """SELECT c.id, c.requester_id, c.recipient_id, c.created_at,
            u1.name as requester_name, u1.email as requester_email,
            u2.name as recipient_name, u2.email as recipient_email
        FROM connections c
        INNER JOIN users u1 ON c.requester_id = u1.id
        INNER JOIN users u2 ON c.recipient_id = u2.id
        WHERE c.status = 'accepted'
        ORDER BY c.created_at DESC""",
        fetch_all=True)

    total_count = len(connections)

    return render_template('admin_dashboard_connections.html',
        connections=connections, total_count=total_count)


@admin_bp.route('/admin/dashboard/pending-approvals')
@admin_required
def dashboard_pending_approvals():
    """View all users pending account approval.

    Drill-down from the dashboard pending approvals card.

    Returns:
        Rendered admin_dashboard_pending_approvals.html template.
    """
    users = Database.execute_query(
        """SELECT u.id, u.name, u.email, u.phone, u.profile_pic, u.role, u.department,
        COALESCE(sp.passing_year, ap.passing_year) as passing_year,
        COALESCE(sp.roll_number, ap.roll_number) as roll_number,
        sp.joining_year, sp.student_year, sp.batch_year,
        ap.company, ap.current_job_title,
        u.is_active, u.created_at
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id AND u.role = 'student'
        LEFT JOIN alumni_profiles ap ON u.id = ap.user_id AND u.role = 'alumni'
        WHERE u.is_approved = 0 ORDER BY u.created_at DESC""",
        fetch_all=True)

    total_count = len(users)

    return render_template('admin_dashboard_pending_approvals.html',
        users=users, total_count=total_count)


# ==================== ADMIN OVERSIGHT: GROUPS ====================

@admin_bp.route('/admin/groups')
@admin_required
def admin_groups_oversight():
    """View all mentorship groups across the platform (admin oversight).

    Shows group name, description, mentor name, member count, and
    creation date for every group in the system.

    Returns:
        Rendered admin_groups_oversight.html template.
    """
    groups = Database.execute_query(
        """SELECT g.id, g.name, g.description, g.created_at,
                  u.id as mentor_id, u.name as mentor_name, u.email as mentor_email,
                  (SELECT COUNT(*) FROM mentorship_group_members gm WHERE gm.group_id=g.id) as member_count,
                  (SELECT COUNT(*) FROM mentorship_group_messages gm WHERE gm.group_id=g.id) as message_count
           FROM mentorship_groups g
           INNER JOIN users u ON g.mentor_id=u.id
           ORDER BY g.created_at DESC""",
        fetch_all=True)
    return render_template('admin_groups_oversight.html', groups=groups)


@admin_bp.route('/admin/groups/<int:group_id>')
@admin_required
def admin_group_detail(group_id):
    """View detailed info about a specific group (admin oversight).

    Shows all members and all messages in the group.

    Args:
        group_id: The group to inspect.

    Returns:
        Rendered admin_group_detail.html template.
    """
    group = Database.execute_query(
        """SELECT g.*, u.name as mentor_name, u.email as mentor_email
           FROM mentorship_groups g
           INNER JOIN users u ON g.mentor_id=u.id
           WHERE g.id=%s""",
        (group_id,), fetch_one=True)
    if not group:
        flash('Group not found', 'danger')
        return redirect(url_for('admin.admin_groups_oversight'))

    members = Database.execute_query(
        """SELECT u.id, u.name, u.email, u.role, u.profile_pic, gm.joined_at
           FROM mentorship_group_members gm
           INNER JOIN users u ON gm.user_id=u.id
           WHERE gm.group_id=%s ORDER BY gm.joined_at DESC""",
        (group_id,), fetch_all=True)

    messages = Database.execute_query(
        """SELECT gm.id, gm.content, gm.created_at, u.id as sender_id, u.name as sender_name,
                  u.email as sender_email, u.profile_pic as sender_pic
           FROM mentorship_group_messages gm
           INNER JOIN users u ON gm.user_id=u.id
           WHERE gm.group_id=%s ORDER BY gm.created_at DESC""",
        (group_id,), fetch_all=True)

    return render_template('admin_group_detail.html', group=group, members=members, messages=messages)


# ==================== ADMIN OVERSIGHT: MESSAGES ====================

@admin_bp.route('/admin/messages')
@admin_required
def admin_messages_oversight():
    """View all direct messages across the platform (admin oversight).

    Shows sender, receiver, message preview, and timestamp.
    Paginated, 50 per page.

    Returns:
        Rendered admin_messages_oversight.html template.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    messages = Database.execute_query(
        """SELECT m.id, m.content, m.created_at, m.attachments,
                  u_s.name as sender_name, u_s.email as sender_email, u_s.id as sender_id,
                  u_r.name as receiver_name, u_r.email as receiver_email, u_r.id as receiver_id
           FROM messages m
           INNER JOIN users u_s ON m.sender_id=u_s.id
           INNER JOIN users u_r ON m.receiver_id=u_r.id
           ORDER BY m.created_at DESC LIMIT %s OFFSET %s""",
        (per_page, offset), fetch_all=True)

    total_count = Database.execute_query(
        "SELECT COUNT(*) as count FROM messages", fetch_one=True)['count']
    total_pages = (total_count + per_page - 1) // per_page

    return render_template('admin_messages_oversight.html',
        messages=messages, page=page, total_pages=total_pages, total_count=total_count)


# ==================== ADMIN DELETE MESSAGE ====================

@admin_bp.route('/api/admin/delete-message', methods=['POST'])
@admin_required
def admin_delete_message():
    """Admin override: permanently delete any direct message.

    Returns:
        JSON success/message or 404/500 error.
    """
    message_id = request.json.get('message_id')
    if not message_id:
        return jsonify({'success': False, 'message': 'Message ID required'}), 400
    try:
        msg = Database.execute_query("SELECT id FROM messages WHERE id=%s", (message_id,), fetch_one=True)
        if not msg:
            return jsonify({'success': False, 'message': 'Message not found'}), 404
        Database.execute_query("DELETE FROM messages WHERE id=%s", (message_id,), commit=True)
        return jsonify({'success': True, 'message': 'Message deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN OVERSIGHT: SESSIONS ====================

@admin_bp.route('/admin/sessions')
@admin_required
def admin_sessions_oversight():
    """View all mentorship sessions across the platform (admin oversight).

    Shows session date, mentor/mentee names, meeting link, duration,
    notes, feedback, and rating.

    Returns:
        Rendered admin_sessions_oversight.html template.
    """
    sessions = Database.execute_query(
        """SELECT ms.*, m.mentor_id, m.mentee_id,
                  u_mentor.name as mentor_name,
                  u_mentee.name as mentee_name
           FROM mentorship_sessions ms
           INNER JOIN mentorship m ON ms.mentorship_id=m.id
           INNER JOIN users u_mentor ON m.mentor_id=u_mentor.id
           INNER JOIN users u_mentee ON m.mentee_id=u_mentee.id
           ORDER BY ms.session_date DESC""",
        fetch_all=True)
    return render_template('admin_sessions_oversight.html', sessions=sessions)


# ==================== ADMIN REMOVE CONNECTION ====================

@admin_bp.route('/api/admin/remove-connection', methods=['POST'])
@admin_required
def admin_remove_connection():
    """Admin override: permanently delete any connection.
    Returns JSON success/message or 404/500 error.
    """
    connection_id = request.json.get('connection_id')
    if not connection_id:
        return jsonify({'success': False, 'message': 'Connection ID required'}), 400
    try:
        conn = Database.execute_query("SELECT id FROM connections WHERE id=%s", (connection_id,), fetch_one=True)
        if not conn:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404
        Database.execute_query("DELETE FROM connections WHERE id=%s", (connection_id,), commit=True)
        return jsonify({'success': True, 'message': 'Connection removed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== PROFILE TRANSFORMATION REQUESTS ====================

@admin_bp.route('/admin/transformation-requests')
@admin_required
def admin_transformation_requests():
    """Show students who marked Degree Completed, pending alumni conversion."""
    students = Database.execute_query(
        """SELECT u.id, u.name, u.email, u.department, u.phone, u.is_approved, u.is_active,
                  sp.roll_number, sp.joining_year, sp.passing_year, sp.student_year
           FROM users u
           INNER JOIN student_profiles sp ON u.id = sp.user_id
           WHERE u.role = 'student' AND sp.student_year = 0
           ORDER BY u.name""",
        fetch_all=True)
    return render_template('admin_transformation_requests.html', students=students)


@admin_bp.route('/api/admin/approve-transformation', methods=['POST'])
@admin_required
def admin_approve_transformation():
    """Convert a student with Degree Completed to alumni status."""
    user_id = request.json.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID required'}), 400
    try:
        user = Database.execute_query("SELECT * FROM users WHERE id=%s AND role='student'", (user_id,), fetch_one=True)
        if not user:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        sp = Database.execute_query("SELECT * FROM student_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if not sp:
            return jsonify({'success': False, 'message': 'Student profile not found'}), 404
        Database.execute_query(
            """INSERT INTO alumni_profiles (user_id, roll_number, passing_year)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE roll_number=%s, passing_year=%s""",
            (user_id, sp['roll_number'], sp['passing_year'],
             sp['roll_number'], sp['passing_year']), commit=True)
        Database.execute_query("DELETE FROM student_profiles WHERE user_id=%s", (user_id,), commit=True)
        Database.execute_query("UPDATE users SET role='alumni' WHERE id=%s", (user_id,), commit=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message) VALUES (%s, 'account_approved', 'Profile Converted', 'Your profile has been converted to alumni status. Welcome to the alumni community!')",
            (user_id,), commit=True)
        
        # Send transformation approval email
        from utils.email_service import EmailService
        EmailService.send_transformation_approved_email(user['email'], user['name'])
        
        AuditLogger.log_event('profile_conversion', user_id=user_id, details=f"Student {user_id} converted to alumni by admin")
        return jsonify({'success': True, 'message': 'Student converted to alumni successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
