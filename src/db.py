"""
BGSBU Interacts - Database Access Layer
=========================================
Provides a singleton-style MySQL connection pool and a high-level
query execution helper. All database interactions in the application
go through the Database class exported here.
"""

import mysql.connector
from mysql.connector import pooling, Error
from config import Config


class Database:
    """
    Thread-safe MySQL database access via a connection pool.

    Usage:
        Database.initialize_pool()
        user = Database.execute_query("SELECT * FROM users WHERE id = %s", (1,), fetch_one=True)
        Database.execute_query("UPDATE users SET name = %s WHERE id = %s", ("New", 1), commit=True)
    """

    # Class-level connection pool shared by all callers
    _pool = None

    # ==================== POOL LIFECYCLE ====================

    @classmethod
    def initialize_pool(cls):
        """
        Create the MySQL connection pool.

        The pool holds up to 10 persistent connections and is configured
        with UTF-8 MB4 support for full Unicode (including emoji).
        Call once at application startup.
        """
        try:
            cls._pool = pooling.MySQLConnectionPool(
                pool_name="bgsbu_pool",
                pool_size=10,
                pool_reset_session=True,
                host=Config.MYSQL_HOST,
                user=Config.MYSQL_USER,
                password=Config.MYSQL_PASSWORD,
                database=Config.MYSQL_DB,
                port=Config.MYSQL_PORT,
                autocommit=False,           # Manual commit/rollback control
                charset='utf8mb4',
                collation='utf8mb4_general_ci'
            )
            print("Database connection pool created successfully")
        except Error as e:
            print(f"Error creating connection pool: {e}")
            raise e

    @classmethod
    def get_connection(cls):
        """
        Borrow a connection from the pool, lazily initialising the pool
        if it has not been created yet.

        Returns:
            mysql.connector.connection: A pooled database connection.
        """
        if cls._pool is None:
            cls.initialize_pool()
        try:
            return cls._pool.get_connection()
        except Error as e:
            print(f"Error getting connection: {e}")
            raise e

    # ==================== QUERY EXECUTION ====================

    @classmethod
    def execute_query(cls, query, params=None, fetch_one=False, fetch_all=False, commit=False):
        """
        Execute a parameterised SQL query and optionally fetch results
        and/or commit the transaction.

        Args:
            query (str):        SQL statement with %s placeholders.
            params (tuple):     Values to bind to placeholders.
            fetch_one (bool):   If True, return a single row dict.
            fetch_all (bool):   If True, return a list of row dicts.
            commit (bool):      If True, commit the transaction and
                                return the last inserted row ID.

        Returns:
            dict | list[dict] | int | None:
                - A single row as a dict when fetch_one is True.
                - A list of row dicts when fetch_all is True.
                - The last inserted ID when commit is True.
                - None otherwise.

        Raises:
            mysql.connector.Error: On database errors (the caller should
                                   handle or propagate).
        """
        connection = None
        cursor = None
        try:
            connection = cls.get_connection()
            # Use dictionary cursor so rows are returned as dicts keyed by column name
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params or ())

            result = None
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()

            if commit:
                connection.commit()
                result = cursor.lastrowid

            return result

        except Error as e:
            # Roll back any uncommitted changes on failure when the
            # caller intended to commit
            if connection and commit:
                connection.rollback()
            print(f"Database error: {e}")
            raise e

        finally:
            # Always release the cursor and return the connection to the pool
            if cursor:
                cursor.close()
            if connection:
                connection.close()


