# BGSBU:INTERACTS — Alumni & Student Connection Platform

A web platform for the students, alumni, and administrators of **Baba Ghulam Shah Badshah University (BGSBU), Rajouri** to connect, network, and manage professional relationships.

> **Note:** This is a shareable demo version with test accounts only. No real student data is included.

---

## Features

### Authentication
- User registration with email **OTP verification**
- Secure login / logout with **bcrypt** password hashing
- Password change and password reset (email OTP)
- Role-based access control (Student / Alumni / Admin)

### User Profiles
- Role-specific profiles for students and alumni
- Profile photo upload (validated and processed with Pillow)
- Academic details (department, batch, semester), skills, and work experience

### Directory & Connections
- Searchable alumni directory with filters (name, department, role, batch)
- Connection requests — send, accept, reject, remove
- View full profiles of connected users only

### Chat
- Real-time messaging between connected users (AJAX polling)
- Message requests / permission control
- Conversation and message deletion
- Chat file uploads

### Jobs
- Alumni post job openings (optional admin approval)
- Students browse and apply for jobs
- Application tracking, job history, and post management

### Mentorship
- Alumni register as mentors; students request mentorship
- Mentorship dashboard, sessions with scheduling and reminders
- Mentorship groups with members, announcements, chat, and tasks
- Shared resources and analytics for both mentors and mentees

### Notifications
- Notifications for connections, messages, job applications, and mentorship events
- Unread counts and mark-as-read support

### Administration
- User management: approve, activate/deactivate, delete, edit profiles
- Job moderation and application status management
- Mentorship oversight and mentor verification
- Message and conversation moderation
- Session overview, system protocols, and audit logs

---

## Technology Stack

| Layer      | Technology                                        |
|------------|---------------------------------------------------|
| Language   | Python 3.8+                                       |
| Backend    | Flask 3.0 (MVC, application factory, blueprints)  |
| Database   | MySQL 8.0+ / MariaDB 10.4+                        |
| Frontend   | HTML5, CSS3, Bootstrap 5.3 (dark theme), JavaScript (AJAX) |
| Templating | Jinja2                                            |
| Auth       | Flask-Bcrypt, OTP email verification              |
| Email      | Brevo (Sendinblue) API with SMTP fallback         |
| Drivers    | mysql-connector-python 8.2.0                      |

Dependencies are listed in [`requirements.txt`](requirements.txt).

---

## Requirements

| Software | Version                    |
|----------|----------------------------|
| Python   | 3.8+                       |
| MySQL    | 8.0+ (MariaDB 10.4+)       |
| pip      | bundled with Python        |

---

## Setup & Installation

### 1. Install Python and MySQL
- **Python** — download from [python.org](https://www.python.org/downloads/) and check **Add to PATH** during installation.
- **MySQL** — install [XAMPP](https://www.apachefriends.org/) (includes Apache + MySQL/MariaDB). Open the XAMPP Control Panel and **Start** both `Apache` and `MySQL`.

### 2. Open a terminal in the project folder
```bash
cd BGSBU_INTERACTS_SHAREABLE
```

### 3. Create and activate a virtual environment
```bash
python -m venv .venv
```
**Windows:**
```bash
.venv\Scripts\activate
```
**Linux / macOS:**
```bash
source .venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Create the database
1. Open your browser and go to `http://localhost/phpmyadmin`
2. Click **New** → database name `bgsbu_interacts`
3. Collation: `utf8mb4_general_ci` → **Create**

### 6. Import the schema and demo data
Use the provided demo SQL file (contains the full schema plus test accounts only):

**Option A — phpMyAdmin**
1. Select the `bgsbu_interacts` database
2. Click **Import** → **Choose File** → select `bgsbu_interacts_demo.sql`
3. Scroll down and click **Import**

**Option B — MySQL CLI**
```bash
mysql -u root -p bgsbu_interacts < bgsbu_interacts_demo.sql
```

### 7. Configure the environment
Copy the template and fill in your values (or keep XAMPP defaults):
```bash
copy .env.example .env
```
The `.env` file at the project root controls database credentials, mail settings, and the secret key. The default configuration targets a local XAMPP setup:
```
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DB=bgsbu_interacts
```

> **Important:** The `.env` file contains credentials and must never be committed to version control or shared.

### 8. Run the application
```bash
python app.py
```
Open your browser and go to: **http://localhost:5000**

---

## Demo Accounts

> These are **test-only** accounts with fabricated credentials for demonstration purposes.

| Role    | Email                | Password      |
|---------|----------------------|---------------|
| **Admin**  | `admin@demo.com`    | `Admin@123`   |
| **Alumni**  | `alumni@test.com`   | `Alumni@123`  |
| **Student** | `student@test.com`  | `Student@123` |

- Admin panel: **http://localhost:5000/admin**
- Full reference of test credentials is kept in [`passwords.md`](passwords.md).

---

## Project Structure

```
BGSBU_INTERACTS_SHAREABLE/
│
├── app.py                     # Entry point — run this
├── requirements.txt           # Python dependencies
├── .env.example               # Template for environment configuration
├── bgsbu_interacts_demo.sql   # Database schema + demo test accounts
├── passwords.md               # Demo/test account credentials
├── LICENSE                    # Restricted-use license
├── README.md
│
└── src/
    ├── app.py                 # Flask application factory
    ├── config.py              # Application configuration (env-driven)
    ├── constants.py           # Shared constants (departments, semesters)
    ├── db.py                  # MySQL connection pool
    ├── database_init.py       # Database initialization helper
    │
    ├── routes/                # Backend route blueprints
    │   ├── auth.py            # Register, login, OTP, password reset
    │   ├── dashboard.py       # Role-aware dashboards
    │   ├── profile.py         # Profile view & edit
    │   ├── directory.py       # Alumni directory & search
    │   ├── connections.py     # Connection requests & management
    │   ├── chat.py            # Messaging & message requests
    │   ├── jobs.py            # Job board, posting & applications
    │   ├── mentorship.py      # Mentorship program, groups, resources
    │   ├── admin.py           # Admin dashboard & management APIs
    │   └── notifications.py   # Notifications & unread counts
    │
    ├── templates/             # Jinja2 HTML templates
    ├── static/                # Frontend assets (CSS, JS, images)
    │   ├── css/
    │   ├── js/
    │   └── images/
    ├── utils/                 # Helper modules
    │   ├── auth_utils.py
    │   ├── security.py
    │   ├── email_service.py
    │   ├── protocols.py
    │   ├── decorators.py
    │   └── audit_logger.py
    └── uploads/               # User-uploaded files
```

---

## Security Notes

- Passwords are hashed with **bcrypt** before storage.
- Forms are protected against **CSRF** attacks.
- All user inputs are validated; database queries use parameterized statements to prevent SQL injection.
- Sensitive endpoints are rate-limited to deter brute-force attempts.
- Administrative actions are recorded in an **audit log**.
- Sessions use HTTP-only, SameSite cookies with a configurable lifetime.

---

## Troubleshooting

**No database connection message on startup**
- Make sure MySQL is running in XAMPP.
- Verify the credentials in `.env` match your MySQL setup.

**"Module not found" errors**
- Activate the virtual environment and run: `pip install -r requirements.txt`

**Port 5000 already in use**
- Edit the port in `app.py` (e.g., `port=5001`) and update `BASE_URL` in `.env`.

**Tables missing / import errors**
- Re-import `bgsbu_interacts_demo.sql` via phpMyAdmin into the `bgsbu_interacts` database.

---

## License

This project is licensed under a **Restricted-Use License** held by **Syed Faisal Irshad**. Any unauthorized use, distribution, or misattribution is strictly prohibited. See [`LICENSE`](LICENSE) for full details.

---

## Project Team

Developed as a group project during Industrial Training by students of the Department of Computer Science & Engineering, BGSBU.

> Contact the project owner for any inquiries.
