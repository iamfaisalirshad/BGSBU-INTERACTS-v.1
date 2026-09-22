"""
Profile Routes
===============
Handles user profile viewing and editing. All routes require
authentication (@login_required). Admins are redirected to the
admin panel since their profiles are managed separately.

Endpoints:
    /profile/<int:user_id>  - View another user's profile
    /profile/edit           - Edit own profile
    /my-profile             - Convenience redirect to own profile
"""

import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from db import Database
from utils.decorators import login_required
from utils.auth_utils import allowed_file
from utils.audit_logger import AuditLogger
from constants import ALL_DEPARTMENTS, DEGREE_SEMESTERS

profile_bp = Blueprint('profile', __name__)


# ==================== PROFILE VIEWING ====================

@profile_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    """
    View a user's public profile.

    Fetches full user record, determines the connection status between
    the viewing user and the profile owner (none/pending/accepted/received),
    and lists up to 6 mutual connections.

    Args:
        user_id (int): The ID of the user whose profile is being viewed.

    Returns:
        Redirect to admin dashboard if user is admin,
        redirect to dashboard if user not found,
        otherwise renders profile.html.
    """
    user = Database.execute_query("SELECT * FROM users WHERE id=%s", (user_id,), fetch_one=True)
    # Admins can view profiles but bypass the is_active check for themselves
    if session.get('role') != 'admin' and (not user or not user['is_active']):
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Fetch role-specific profile data (safe merge: never overwrite user id/user_id)
    profile_data = dict(user)
    if user['role'] == 'student':
        sp = Database.execute_query(
            "SELECT * FROM student_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if sp:
            for k, v in sp.items():
                if k not in ('id', 'user_id'):
                    profile_data[k] = v
    elif user['role'] == 'alumni':
        ap = Database.execute_query(
            "SELECT * FROM alumni_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if ap:
            for k, v in ap.items():
                if k not in ('id', 'user_id'):
                    profile_data[k] = v
    skills = Database.execute_query(
        "SELECT skill FROM user_skills WHERE user_id=%s", (user_id,), fetch_all=True)
    profile_data['skills'] = ', '.join(s['skill'] for s in skills) if skills else ''
    work_exp = Database.execute_query(
        "SELECT * FROM work_experiences WHERE user_id=%s ORDER BY start_date DESC", (user_id,), fetch_all=True)
    profile_data['work_experiences'] = work_exp or []
    profile_data['job_history'] = '\n'.join(
        f"{w.get('job_title','')} at {w.get('company','')} ({w.get('start_date','')} - {w.get('end_date','') or 'Present'})"
        for w in (work_exp or []) if w.get('job_title') or w.get('company'))
    profile_data['company'] = (work_exp or [{}])[0].get('company', '') if work_exp else ''

    connection_status = None
    msg_req_status = None
    if user_id != session['user_id']:
        conn = Database.execute_query(
            """SELECT * FROM connections WHERE (requester_id=%s AND recipient_id=%s)
            OR (requester_id=%s AND recipient_id=%s)
            ORDER BY FIELD(status,'accepted','pending','rejected','blocked') LIMIT 1""",
            (session['user_id'], user_id, user_id, session['user_id']), fetch_one=True)
        if conn:
            connection_status = conn['status']
            if conn['status'] == 'pending' and conn['recipient_id'] == session['user_id']:
                connection_status = 'received'
        # Check message request status (only for non-connected profiles)
        if not connection_status or connection_status not in ('accepted',):
            mr = Database.execute_query(
                """SELECT * FROM message_requests WHERE (sender_id=%s AND recipient_id=%s)
                OR (sender_id=%s AND recipient_id=%s)
                ORDER BY FIELD(status,'accepted','pending','rejected') LIMIT 1""",
                (session['user_id'], user_id, user_id, session['user_id']), fetch_one=True)
            if mr:
                msg_req_status = mr['status']
                if mr['status'] == 'pending' and mr['recipient_id'] == session['user_id']:
                    msg_req_status = 'received_request'

    connections = Database.execute_query(
        """SELECT u.id, u.name, u.role, u.profile_pic
        FROM users u INNER JOIN connections c ON (c.requester_id=u.id OR c.recipient_id=u.id)
        WHERE (c.requester_id=%s OR c.recipient_id=%s) AND c.status='accepted' AND u.id!=%s LIMIT 6""",
        (user_id, user_id, user_id), fetch_all=True)

    return render_template('profile.html', user=profile_data, profile_data=profile_data,
                         connection_status=connection_status, msg_req_status=msg_req_status,
                         connections=connections,
                         is_own_profile=(user_id == session['user_id']))


# ==================== PROFILE EDITING ====================

@profile_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """
    Edit the logged-in user's own profile.

    GET:  Render edit form pre-filled with current user data.
    POST: Validate and update common fields (name, phone, bio, department,
          roll_number, skills, company, job_history, academic years, student_year).
          Optionally upload a new profile picture (UUID-based filename for
          uniqueness). Logs the update via AuditLogger.

    Returns:
        Redirect to admin dashboard if user is admin,
        redirect to dashboard if user not found,
        otherwise renders edit_profile.html (GET) or
        redirects to view_profile on successful update (POST).
    """
    # Admins cannot edit their own profile
    if session.get('role') == 'admin':
        flash('Admins cannot edit their own profile. Use Admin Panel to manage other users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    user_id = session['user_id']
    user_role = session.get('role')

    # Get user data
    user = Database.execute_query("SELECT * FROM users WHERE id=%s", (user_id,), fetch_one=True)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Profile data is now in user dictionary
    profile_data = user

    if request.method == 'POST':
        # Common fields
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        bio = request.form.get('bio', '').strip()
        profile_pic_name = None

        # Handle profile picture upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename and allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                profile_pic_name = filename

        try:
            department = request.form.get('department', '').strip()
            roll_number = request.form.get('roll_number', '').strip()
            skills_str = request.form.get('skills', '').strip()
            interests = request.form.get('interests', '').strip()
            internships = request.form.get('internships', '').strip()
            projects = request.form.get('projects', '').strip()

            joining_year = request.form.get('joining_year', '').strip()
            passing_year = request.form.get('passing_year', '').strip()
            student_year = request.form.get('student_year', '').strip()
            degree_completed = request.form.get('degree_completed') == '1'
            currently_studying = request.form.get('currently_studying') == '1'

            jy = int(joining_year) if joining_year else None
            py = int(passing_year) if passing_year else None
            sy = int(student_year) if student_year else None
            if degree_completed:
                sy = 0
                currently_studying = False

            # Update common user fields
            update_query = "UPDATE users SET name=%s, phone=%s, bio=%s, department=%s, interests=%s"
            update_params = [name, phone, bio, department, interests]

            if profile_pic_name:
                update_query += ", profile_pic=%s"
                update_params.append(profile_pic_name)

            update_query += " WHERE id=%s"
            update_params.append(user_id)
            Database.execute_query(update_query, tuple(update_params), commit=True)

            # Update role-specific profile
            if user_role == 'student':
                Database.execute_query(
                    "INSERT INTO student_profiles (user_id, roll_number, joining_year, passing_year, student_year, currently_studying, internships, projects) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE roll_number=%s, joining_year=%s, passing_year=%s, student_year=%s, currently_studying=%s, internships=%s, projects=%s",
                    (user_id, roll_number, jy, py, sy, 1 if currently_studying else 0, internships, projects,
                     roll_number, jy, py, sy, 1 if currently_studying else 0, internships, projects), commit=True)
                if sy == 0:
                    admins = Database.execute_query("SELECT id FROM users WHERE role='admin'", fetch_all=True)
                    if admins:
                        for a in admins:
                            Database.execute_query(
                                "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'graduation_request', 'Degree Completion Request', %s, %s)",
                                (a['id'], f'{name} has marked Degree Completed and requests alumni conversion.', url_for('admin.admin_transformation_requests', _external=True)),
                                commit=True)
            elif user_role == 'alumni':
                # Save structured work experiences
                Database.execute_query("DELETE FROM work_experiences WHERE user_id=%s", (user_id,), commit=True)
                import re
                job_fields = {k: v for k, v in request.form.items() if k.startswith('job_title_')}
                for field_name, job_title in job_fields.items():
                    m = re.match(r'job_title_(\d+)', field_name)
                    if not m: continue
                    idx = m.group(1)
                    company = request.form.get(f'company_{idx}', '').strip()
                    role = request.form.get(f'role_{idx}', '').strip()
                    start_date = request.form.get(f'start_date_{idx}', '').strip()
                    end_date = request.form.get(f'end_date_{idx}', '').strip()
                    is_current = request.form.get(f'is_current_{idx}') == '1'
                    if job_title.strip() or company.strip():
                        Database.execute_query(
                            "INSERT INTO work_experiences (user_id, job_title, company, role, start_date, end_date, is_current) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (user_id, job_title.strip(), company, role, start_date or None, end_date or None, 1 if is_current else 0),
                            commit=True)

            # Update skills: delete existing, insert new
            Database.execute_query("DELETE FROM user_skills WHERE user_id=%s", (user_id,), commit=True)
            if skills_str:
                skills_list = [s.strip() for s in skills_str.split(',') if s.strip()]
                for skill in skills_list:
                    Database.execute_query(
                        "INSERT INTO user_skills (user_id, skill) VALUES (%s, %s) ON DUPLICATE KEY UPDATE skill=skill",
                        (user_id, skill), commit=True)

            session['user_name'] = name
            AuditLogger.log_event(AuditLogger.EVENT_PROFILE_UPDATE, user_id=user_id)
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile.view_profile', user_id=user_id))
        except Exception as e:
            flash(f'Error updating profile: {str(e)}', 'danger')

    # Build profile_data with role-specific fields for the template
    profile_data = dict(user)
    if user_role == 'student':
        sp = Database.execute_query(
            "SELECT * FROM student_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if sp:
            for k, v in sp.items():
                if k not in ('id', 'user_id'):
                    profile_data[k] = v
    elif user_role == 'alumni':
        ap = Database.execute_query(
            "SELECT * FROM alumni_profiles WHERE user_id=%s", (user_id,), fetch_one=True)
        if ap:
            for k, v in ap.items():
                if k not in ('id', 'user_id'):
                    profile_data[k] = v
    skills = Database.execute_query(
        "SELECT skill FROM user_skills WHERE user_id=%s", (user_id,), fetch_all=True)
    profile_data['skills'] = ', '.join(s['skill'] for s in skills) if skills else ''

    return render_template('edit_profile.html', user=profile_data, profile_data=profile_data,
                         user_role=user_role, departments=ALL_DEPARTMENTS, degree_semesters=DEGREE_SEMESTERS)


# ==================== ACCOUNT DELETION ====================

@profile_bp.route('/api/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    """
    Permanently delete the logged-in user's account and all associated data.

    CASCADE foreign keys ensure that connections, messages, mentorships,
    job applications, group memberships, etc. are removed automatically.
    References with ON DELETE SET NULL are nullified. Also removes the
    user's profile picture from disk if it exists.

    Admin users cannot delete themselves via this endpoint (use admin panel).

    Returns:
        JSON with success status and message.
    """
    if session.get('role') == 'admin':
        return jsonify({'success': False, 'message': 'Admins cannot delete their own account. Use Admin Panel.'}), 403

    user_id = session['user_id']

    try:
        user = Database.execute_query(
            "SELECT profile_pic FROM users WHERE id=%s AND is_active=1",
            (user_id,), fetch_one=True)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Remove profile picture from disk
        if user['profile_pic'] and user['profile_pic'] != 'default.svg':
            pic_path = os.path.join(current_app.config['UPLOAD_FOLDER'], user['profile_pic'])
            if os.path.exists(pic_path):
                os.remove(pic_path)

        # Log BEFORE delete so user_id still references a valid FK row
        AuditLogger.log_event(AuditLogger.EVENT_ACCOUNT_DELETED, user_id=user_id,
                              details=f"User {user_id} deleted their own account")

        # Delete user — CASCADE handles all related records
        Database.execute_query("DELETE FROM users WHERE id=%s", (user_id,), commit=True)

        # Clear session
        session.clear()

        return jsonify({'success': True, 'message': 'Account permanently deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== REDIRECT ROUTES ====================

@profile_bp.route('/my-profile')
@login_required
def my_profile():
    """
    Convenience redirect to the logged-in user's own profile page.

    Returns:
        Redirect to admin dashboard if user is admin,
        otherwise redirects to profile.view_profile with the user's own ID.
    """
    # Admins go to admin dashboard instead
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    return redirect(url_for('profile.view_profile', user_id=session['user_id']))
