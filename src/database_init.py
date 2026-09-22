"""
BGSBU Interacts - Database Initialization & Seed Script
========================================================
Creates the database schema from a SQL file, verifies the resulting
structure, and optionally populates test data.

Usage:
    python database_init.py                          # Full init
    python database_init.py --verify                 # Verify only
    python database_init.py --test-data              # Init + test data
    python database_init.py --sql-file custom.sql    # Init from custom file
"""

import mysql.connector
from mysql.connector import Error
from config import Config
import os
import sys


class DatabaseInitializer:
    """
    Handles all aspects of database setup: connecting to MySQL,
    executing schema-definition SQL, verifying the created tables,
    seeding test users, and creating the default admin account.
    """

    def __init__(self):
        # Load connection parameters from the application configuration
        self.host = Config.MYSQL_HOST
        self.user = Config.MYSQL_USER
        self.password = Config.MYSQL_PASSWORD
        self.database = Config.MYSQL_DB
        self.port = Config.MYSQL_PORT
        # Schema version tag used for diagnostic output
        self.schema_version = "4.0"

    # ==================== CONNECTION HELPERS ====================

    def connect(self):
        """
        Open a raw connection to the MySQL server (without selecting a
        specific database). The caller is responsible for closing the
        connection.

        Returns:
            mysql.connector.connection: An open MySQL connection.

        Exits the process if the connection fails.
        """
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                port=self.port,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            return connection
        except Error as e:
            print(f"\u274c Connection error: {e}")
            sys.exit(1)

    # ==================== SQL FILE HANDLING ====================

    def load_sql_file(self, filename):
        """
        Read the complete contents of a SQL file into a string.

        Args:
            filename (str): Path to the .sql file.

        Returns:
            str: Full file content.

        Exits the process if the file is not found.
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"\u274c File not found: {filename}")
            sys.exit(1)

    # ==================== SQL EXECUTION ====================

    def execute_sql(self, sql_content):
        """
        Execute a multi-statement SQL string against the MySQL server.
        Statements are split on ``;\\n`` and executed individually so
        that errors can be reported per-statement.

        Args:
            sql_content (str): One or more SQL statements.

        Exits the process on unrecoverable execution errors.
        """
        connection = self.connect()

        try:
            # Normalise line endings then split on ";\n" to handle both Unix
            # and Windows (CRLF) line endings in the SQL dump file.
            sql_content = sql_content.replace('\r\n', '\n').replace('\r', '\n')
            statements = sql_content.split(';\n')

            for statement in statements:
                statement = statement.strip()
                # Skip empty statements and SQL comments
                if statement and not statement.startswith('--'):
                    try:
                        cursor = connection.cursor()
                        cursor.execute(statement)
                        # Consume any result sets so the cursor can be reused
                        if cursor.description:
                            cursor.fetchall()
                        connection.commit()
                        cursor.close()
                    except Error as e:
                        # Ignore "already exists" errors to make the script
                        # idempotent for repeated runs
                        if 'already exists' not in str(e).lower():
                            print(f"\u26a0\ufe0f  Statement error: {e}")
                            print(f"Statement: {statement[:100]}...")
                        if cursor:
                            cursor.close()

            print("\u2713 SQL statements executed successfully")
        except Error as e:
            print(f"\u274c Execution error: {e}")
            sys.exit(1)
        finally:
            connection.close()

    # ==================== FULL INITIALIZATION ====================

    def initialize_database(self, sql_file='bgsbu_interacts_demo.sql'):
        """
        High-level entry point: load a SQL schema file and execute it
        against the MySQL server to create the database and all tables.

        Args:
            sql_file (str): Path to the schema SQL file (default: bgsbu_interacts_demo.sql).
        """
        print("\n" + "=" * 60)
        print("BGSBU INTERACTS - Database Initialization")
        print("=" * 60)

        print(f"\n\U0001f4cb Database Configuration:")
        print(f"   Host: {self.host}:{self.port}")
        print(f"   Database: {self.database}")
        print(f"   Schema Version: {self.schema_version}")

        print(f"\n\U0001f4d6 Loading SQL file: {sql_file}...")
        sql_content = self.load_sql_file(sql_file)

        print("\U0001f504 Creating database structure...")
        self.execute_sql(sql_content)

        print("\n\u2705 Database initialization completed!")
        print("=" * 60)

    # ==================== VERIFICATION ====================

    def verify_database(self):
        """
        Inspect the database and report the list of tables, row counts,
        and any missing required tables.

        Returns:
            bool: True if all required tables exist, False otherwise.
        """
        connection = self.connect()
        cursor = connection.cursor(dictionary=True)

        try:
            # Select the target database
            cursor.execute(f"USE {self.database}")

            # Count all tables in the database
            cursor.execute("""
            SELECT COUNT(*) as count FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = %s
            """, (self.database,))

            result = cursor.fetchone()
            table_count = result['count'] if result else 0

            # Retrieve individual table names and approximate row counts
            cursor.execute("""
            SELECT TABLE_NAME, TABLE_ROWS 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = %s 
            ORDER BY TABLE_NAME
            """, (self.database,))

            tables = cursor.fetchall()

            print(f"\n\U0001f4ca Database Verification:")
            print(f"   Total Tables: {table_count}")
            print(f"   Tables Found:")
            for table in tables:
                rows = table['TABLE_ROWS'] if table['TABLE_ROWS'] else 0
                print(f"      \u2022 {table['TABLE_NAME']:<30} ({rows} rows)")

            # Core tables that the application expects
            required_tables = [
                'users', 'connections', 'messages', 'notifications',
                'jobs', 'job_applications',
                'mentorship', 'mentorship_sessions',
                'mentorship_groups', 'mentorship_group_members',
                'mentorship_group_messages', 'mentorship_group_announcements',
                'mentorship_tasks', 'mentorship_resources',
                'audit_logs', 'system_settings', 'system_protocols'
            ]

            existing_tables = [t['TABLE_NAME'] for t in tables]
            missing = [t for t in required_tables if t not in existing_tables]

            if missing:
                print(f"\n   \u26a0\ufe0f  Missing tables: {', '.join(missing)}")
                return False

            print(f"\n   \u2705 All required tables present!")
            return True

        except Error as e:
            print(f"\u274c Verification error: {e}")
            return False
        finally:
            cursor.close()
            connection.close()

    # ==================== TEST DATA SEEDING ====================

    def create_test_data(self):
        """
        Insert sample student and alumni accounts for development and
        testing. Uses bcrypt to hash passwords before storage.

        Credentials created:
            - student@test.com / Student@123  (role: student)
            - alumni@test.com  / Alumni@123   (role: alumni)
        """
        print("\n\U0001f9ea Creating test data...")

        # Attempt to import the application's hash function, falling
        # back to Flask-Bcrypt or raw bcrypt if that is unavailable
        try:
            from utils.auth_utils import hash_password
        except ImportError:
            try:
                from flask_bcrypt import Bcrypt
                bcrypt = Bcrypt()
                hash_password = lambda p: bcrypt.generate_password_hash(p).decode('utf-8')
            except ImportError:
                import bcrypt as _bcrypt
                hash_password = lambda p: _bcrypt.hashpw(p.encode(), _bcrypt.gensalt(12)).decode()

        connection = self.connect()
        cursor = connection.cursor()

        try:
            cursor.execute(f"USE {self.database}")

            # Insert a test student user
            test_password = hash_password("Student@123")
            cursor.execute("""
            INSERT INTO users (role, name, email, password, department, is_active, is_approved, email_verified_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, NOW())
            ON DUPLICATE KEY UPDATE email=email
            """, ('student', 'Test Student', 'student@test.com', test_password, 'Computer Science & Engineering'))
            student_id = cursor.lastrowid
            if student_id:
                cursor.execute("""
                INSERT INTO student_profiles (user_id, roll_number, joining_year, currently_studying)
                VALUES (%s, '2024CS001', 2024, 1)
                ON DUPLICATE KEY UPDATE user_id=user_id
                """, (student_id,))

            # Insert a test alumni user with company and skills
            test_password = hash_password("Alumni@123")
            cursor.execute("""
            INSERT INTO users (role, name, email, password, department, is_mentor, is_active, is_approved, email_verified_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, TRUE, NOW())
            ON DUPLICATE KEY UPDATE email=email
            """, ('alumni', 'Test Alumni', 'alumni@test.com', test_password, 'Computer Science & Engineering'))
            alumni_id = cursor.lastrowid
            if alumni_id:
                cursor.execute("""
                INSERT INTO alumni_profiles (user_id, company)
                VALUES (%s, 'Google')
                ON DUPLICATE KEY UPDATE user_id=user_id
                """, (alumni_id,))
                for skill in ['Python', 'Java', 'Machine Learning']:
                    cursor.execute("""
                    INSERT INTO user_skills (user_id, skill) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE skill=skill
                    """, (alumni_id, skill))

            connection.commit()
            print("   \u2713 Test data created")
            print("   \u2713 Student: student@test.com / Student@123")
            print("   \u2713 Alumni: alumni@test.com / Alumni@123")

        except Error as e:
            print(f"   \u26a0\ufe0f  Test data error (non-critical): {e}")
        finally:
            cursor.close()
            connection.close()

    # ==================== ADMIN ACCOUNT ====================

    def create_admin_account(self):
        """
        Ensure a default administrator account exists in the database.
        If the admin email from Config already has a user record this
        method is a no-op.
        """
        print("\n\U0001f464 Creating admin account...")

        # Attempt to import the application's hash function, falling
        # back to Flask-Bcrypt or raw bcrypt if that is unavailable
        try:
            from utils.auth_utils import hash_password
        except ImportError:
            try:
                from flask_bcrypt import Bcrypt
                bcrypt = Bcrypt()
                hash_password = lambda p: bcrypt.generate_password_hash(p).decode('utf-8')
            except ImportError:
                import bcrypt as _bcrypt
                hash_password = lambda p: _bcrypt.hashpw(p.encode(), _bcrypt.gensalt(12)).decode()

        connection = self.connect()
        cursor = connection.cursor()

        try:
            cursor.execute(f"USE {self.database}")

            admin_email = Config.ADMIN_EMAIL
            admin_password_plain = Config.ADMIN_PASSWORD

            # Skip creation if the admin already exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
            existing = cursor.fetchone()

            if existing:
                print("   \u2705 Admin account already exists")
                return

            # Hash the plain-text password and insert the admin record
            admin_password = hash_password(admin_password_plain)
            cursor.execute("""
            INSERT INTO users (role, name, email, password, phone, is_active, is_approved, email_verified_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, ('admin', 'Administrator', admin_email, admin_password, '+91-0000000000', True, True))

            connection.commit()
            print("   \u2705 Admin account created")

        except Error as e:
            if 'Duplicate entry' not in str(e):
                print(f"   \u26a0\ufe0f  Admin account error: {e}")
        finally:
            cursor.close()
            connection.close()


# ==================== CLI ENTRY POINT ====================

def main():
    """
    CLI entry point. Parses command-line arguments and orchestrates
    database initialisation, verification, test-data seeding, and
    admin-account creation.
    """
    import argparse

    parser = argparse.ArgumentParser(description='Initialize BGSBU Interacts Database')
    parser.add_argument('--verify', action='store_true', help='Verify database only')
    parser.add_argument('--test-data', action='store_true', help='Create test data')
    parser.add_argument('--sql-file', default='database.sql', help='SQL file to load')

    args = parser.parse_args()

    initializer = DatabaseInitializer()

    if args.verify:
        initializer.verify_database()
    else:
        initializer.initialize_database(args.sql_file)
        initializer.verify_database()

        # The admin account is *always* bootstrapped, even when no
        # --test-data flag is supplied
        initializer.create_admin_account()

        if args.test_data:
            initializer.create_test_data()


if __name__ == '__main__':
    main()
