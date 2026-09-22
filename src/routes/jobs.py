"""
Jobs Routes Module
==================
Handles job posting, browsing, and application workflows:
- Job listing page with filtering (type, search)
- Job posting (alumni only, requires admin approval)
- Job application (students apply with cover letter)
- My postings dashboard (alumni view their job stats)
- Individual job detail page
- Application management (view/update status by alumni)
- Job toggle (activate/deactivate)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import Database
from utils.decorators import login_required, alumni_required
from utils.protocols import is_protocol_enabled, protocol_disabled_response, check_application_limit_for_student, check_applications_per_job

jobs_bp = Blueprint('jobs', __name__)


# ==================== JOB LISTING & BROWSING ====================

@jobs_bp.route('/jobs')
@login_required
def jobs_page():
    """Display paginated, filterable job listings.

    Supports query params:
    - ?type=job|internship (filter by job type)
    - ?search=<term> (search in title/company/description)

    Also computes which jobs the current user has already applied to.

    Returns:
        Rendered jobs.html template with job list and applied-job IDs.
    """
    # Admins cannot access jobs - redirect to admin panel
    if session.get('role') == 'admin':
        flash('Admins do not use job boards. Use Admin Panel to manage users.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    if not is_protocol_enabled('jobs'):
        flash('Jobs are currently disabled by admin.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    job_type = request.args.get('type', '')
    search = request.args.get('search', '')
    conditions = ["j.is_active = 1"]
    params = []
    if job_type:
        conditions.append("j.job_type = %s")
        params.append(job_type)
    if search:
        conditions.append("(j.title LIKE %s OR j.company LIKE %s OR j.description LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where = " AND ".join(conditions)
    jobs = Database.execute_query(
        f"""SELECT j.*, u.name as poster_name, u.profile_pic as poster_pic,
        (SELECT COUNT(*) FROM job_applications WHERE job_id=j.id) as application_count
        FROM jobs j INNER JOIN users u ON j.posted_by=u.id WHERE {where} AND j.is_approved=1 ORDER BY j.created_at DESC""",
        params, fetch_all=True)
    applied_jobs = Database.execute_query(
        "SELECT job_id FROM job_applications WHERE user_id=%s", (session['user_id'],), fetch_all=True)
    applied_job_ids = [a['job_id'] for a in applied_jobs]
    return render_template('jobs.html', jobs=jobs, applied_job_ids=applied_job_ids, current_type=job_type, search=search)


# ==================== JOB POSTING (Alumni only) ====================

@jobs_bp.route('/jobs/post', methods=['GET', 'POST'])
@login_required
@alumni_required
def post_job():
    """Allow alumni to post a new job or internship.

    GET: Display the posting form.
    POST: Validate required fields (title, company, description) and insert
    a new job record with is_approved=0 (pending admin review).

    Returns:
        GET -> Rendered post_job.html form.
        POST -> Redirect to jobs page with flash message.
    """
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        company = request.form.get('company', '').strip()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        job_type = request.form.get('job_type', 'job')
        salary = request.form.get('salary', '').strip()
        requirements = request.form.get('requirements', '').strip()
        deadline = request.form.get('deadline', '') or None
        if not title or not company or not description:
            flash('Title, Company, and Description required.', 'danger')
            return render_template('post_job.html')
        try:
            Database.execute_query(
                """INSERT INTO jobs (title, company, description, location, job_type, salary_min, requirements, posted_by, is_approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)""",
                (title, company, description, location, job_type, salary, requirements, session['user_id']), commit=True)
            flash('Job posted and is pending admin approval.', 'success')
            return redirect(url_for('jobs.jobs_page'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    return render_template('post_job.html')


# ==================== JOB APPLICATIONS ====================

@jobs_bp.route('/api/apply-job', methods=['POST'])
@login_required
def apply_job():
    """Submit a job application (cover letter) for the current user.

    Validates:
    - Applications protocol is enabled
    - User hasn't already applied to this job

    On success, notifies the job poster via the notifications system.

    Returns:
        JSON with success/message, or 400/500 on error.
    """
    if not is_protocol_enabled('applications'):
        return protocol_disabled_response('applications')

    job_id = request.json.get('job_id')
    cover_letter = request.json.get('cover_letter', '')
    uid = session['user_id']
    if not job_id:
        return jsonify({'success': False, 'message': 'Job ID required'}), 400
    job = Database.execute_query("SELECT id, posted_by FROM jobs WHERE id=%s", (job_id,), fetch_one=True)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    if job['posted_by'] == uid:
        return jsonify({'success': False, 'message': 'Cannot apply to your own job'}), 400
    existing = Database.execute_query("SELECT id FROM job_applications WHERE job_id=%s AND user_id=%s", (job_id, uid), fetch_one=True)
    if existing:
        return jsonify({'success': False, 'message': 'Already applied'}), 400
    # Enforce application protocol limits
    ok, msg = check_application_limit_for_student(uid)
    if not ok:
        return jsonify({'success': False, 'message': msg}), 429
    ok, msg = check_applications_per_job(job_id)
    if not ok:
        return jsonify({'success': False, 'message': msg}), 429
    try:
        Database.execute_query("INSERT INTO job_applications (job_id, user_id, cover_letter) VALUES (%s, %s, %s)",
            (job_id, uid, cover_letter), commit=True)
        job = Database.execute_query("SELECT posted_by, title FROM jobs WHERE id=%s", (job_id,), fetch_one=True)
        user = Database.execute_query("SELECT name FROM users WHERE id=%s", (uid,), fetch_one=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'job_application', %s, %s, %s)",
            (job['posted_by'], 'New Job Application', f"{user['name']} applied for {job['title']}", "/jobs/my-postings"), commit=True)
        return jsonify({'success': True, 'message': 'Application submitted!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== MY POSTINGS (Alumni dashboard) ====================

@jobs_bp.route('/jobs/my-postings')
@login_required
@alumni_required
def my_postings():
    """Display alumni's own job postings with aggregated statistics.

    Computes:
    - Total applications received across all postings
    - Pending applications count
    - Active job count
    - Approved job count

    Returns:
        Rendered my_postings.html with jobs list and stats.
    """
    user_id = session['user_id']
    jobs = Database.execute_query(
        """SELECT j.*, (SELECT COUNT(*) FROM job_applications WHERE job_id=j.id) as application_count
        FROM jobs j WHERE j.posted_by=%s ORDER BY j.created_at DESC""", (user_id,), fetch_all=True)
    # Calculate statistics
    total_applications = Database.execute_query(
        "SELECT COUNT(*) as count FROM job_applications a INNER JOIN jobs j ON a.job_id=j.id WHERE j.posted_by=%s",
        (user_id,), fetch_one=True)['count']
    pending_applications = Database.execute_query(
        "SELECT COUNT(*) as count FROM job_applications a INNER JOIN jobs j ON a.job_id=j.id WHERE j.posted_by=%s AND a.status='pending'",
        (user_id,), fetch_one=True)['count']
    active_jobs = Database.execute_query(
        "SELECT COUNT(*) as count FROM jobs WHERE posted_by=%s AND is_active=1",
        (user_id,), fetch_one=True)['count']
    approved_jobs = Database.execute_query(
        "SELECT COUNT(*) as count FROM jobs WHERE posted_by=%s AND is_approved=1",
        (user_id,), fetch_one=True)['count']
    return render_template('my_postings.html', jobs=jobs, total_applications=total_applications,
        pending_applications=pending_applications, active_jobs=active_jobs, approved_jobs=approved_jobs)


# ==================== JOB DETAIL & APPLICATION MANAGEMENT ====================

@jobs_bp.route('/jobs/<int:job_id>')
@login_required
def view_job(job_id):
    """View a single job's full details.

    Also checks whether the current user has already applied.

    Args:
        job_id: The job's primary key.

    Returns:
        Rendered job_detail.html template, or redirect with flash if not found.
    """
    if session.get('role') == 'admin':
        flash('Admins do not use job boards.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))
    job = Database.execute_query(
        """SELECT j.*, u.name as poster_name, u.email as poster_email, u.profile_pic as poster_pic,
        (SELECT COUNT(*) FROM job_applications WHERE job_id=j.id) as application_count
        FROM jobs j INNER JOIN users u ON j.posted_by=u.id WHERE j.id=%s""",
        (job_id,), fetch_one=True)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('jobs.jobs_page'))
    has_applied = Database.execute_query(
        "SELECT id FROM job_applications WHERE job_id=%s AND user_id=%s",
        (job_id, session['user_id']), fetch_one=True)
    return render_template('job_detail.html', job=job, has_applied=has_applied)


@jobs_bp.route('/jobs/<int:job_id>/applications')
@login_required
@alumni_required
def view_applications(job_id):
    """View all applications received for a specific job posting.

    Only the job poster (alumni) can access this.

    Args:
        job_id: The job's primary key.

    Returns:
        Rendered applications.html with job info and applicant list.
    """
    job = Database.execute_query("SELECT * FROM jobs WHERE id=%s AND posted_by=%s", (job_id, session['user_id']), fetch_one=True)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('jobs.my_postings'))
    applications = Database.execute_query(
        """SELECT a.*, u.name, u.email, u.phone, u.department,
        GROUP_CONCAT(DISTINCT us.skill SEPARATOR ', ') as skills, u.profile_pic
        FROM job_applications a INNER JOIN users u ON a.user_id=u.id
        LEFT JOIN user_skills us ON u.id = us.user_id
        WHERE a.job_id=%s GROUP BY a.id ORDER BY a.applied_at DESC""",
        (job_id,), fetch_all=True)
    return render_template('applications.html', job=job, applications=applications)


@jobs_bp.route('/api/update-application', methods=['POST'])
@login_required
@alumni_required
def update_application():
    """Update the status of a job application (reviewed/accepted/rejected).

    Only the job poster can update; notifies the applicant of the change.

    Returns:
        JSON with success/message, or 400/403/500 on error.
    """
    app_id = request.json.get('application_id')
    status = request.json.get('status')
    if status not in ['reviewed', 'accepted', 'rejected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    try:
        app_data = Database.execute_query(
            """SELECT a.*, j.title, j.posted_by FROM job_applications a
            INNER JOIN jobs j ON a.job_id=j.id WHERE a.id=%s""", (app_id,), fetch_one=True)
        if not app_data or app_data['posted_by'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        Database.execute_query("UPDATE job_applications SET status=%s WHERE id=%s", (status, app_id), commit=True)
        Database.execute_query(
            "INSERT INTO notifications (user_id, type, title, message, action_url) VALUES (%s, 'application_update', %s, %s, %s)",
            (app_data['user_id'], 'Application Status Update', f"Your application for '{app_data['title']}' has been {status}", "/jobs"), commit=True)
        return jsonify({'success': True, 'message': f'Application {status}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== JOB TOGGLE ====================

@jobs_bp.route('/api/toggle-job', methods=['POST'])
@login_required
@alumni_required
def toggle_job():
    """Toggle a job's active/inactive status (soft disable).

    Only the job poster can toggle. Used to close listings without deleting.

    Returns:
        JSON with new is_active state, or 404/500 on error.
    """
    job_id = request.json.get('job_id')
    try:
        job = Database.execute_query("SELECT is_active FROM jobs WHERE id=%s AND posted_by=%s",
            (job_id, session['user_id']), fetch_one=True)
        if not job:
            return jsonify({'success': False, 'message': 'Not found'}), 404
        new_status = 0 if job['is_active'] else 1
        Database.execute_query("UPDATE jobs SET is_active=%s WHERE id=%s", (new_status, job_id), commit=True)
        return jsonify({'success': True, 'is_active': new_status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
