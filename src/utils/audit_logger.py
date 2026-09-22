"""
Audit logging system for tracking security-relevant events
Logs are stored in the audit_logs table for admin review
"""

from db import Database
from datetime import datetime
from utils.security import get_client_ip
from flask import session, request


class AuditLogger:
    """Log security-relevant events to database"""
    
    # Event types
    EVENT_LOGIN_SUCCESS = 'LOGIN_SUCCESS'
    EVENT_LOGIN_FAILED = 'LOGIN_FAILED'
    EVENT_LOGOUT = 'LOGOUT'
    EVENT_REGISTRATION = 'REGISTRATION'
    EVENT_PASSWORD_RESET = 'PASSWORD_RESET'
    EVENT_PASSWORD_CHANGE = 'PASSWORD_CHANGE'
    EVENT_EMAIL_VERIFIED = 'EMAIL_VERIFIED'
    EVENT_ACCOUNT_APPROVAL = 'ACCOUNT_APPROVAL'
    EVENT_ACCOUNT_REJECTED = 'ACCOUNT_REJECTED'
    EVENT_ACCOUNT_DEACTIVATED = 'ACCOUNT_DEACTIVATED'
    EVENT_ACCOUNT_ACTIVATED = 'ACCOUNT_ACTIVATED'
    EVENT_ACCOUNT_DELETED = 'ACCOUNT_DELETED'
    EVENT_PERMISSION_DENIED = 'PERMISSION_DENIED'
    EVENT_RATE_LIMIT_EXCEEDED = 'RATE_LIMIT_EXCEEDED'
    EVENT_CSRF_VIOLATION = 'CSRF_VIOLATION'
    EVENT_SESSION_EXPIRED = 'SESSION_EXPIRED'
    EVENT_PROFILE_UPDATE = 'PROFILE_UPDATE'
    EVENT_DATA_EXPORT = 'DATA_EXPORT'
    
    @staticmethod
    def log_event(event_type, user_id=None, details=None, ip_address=None):
        """
        Log a security event to the database
        
        Args:
            event_type: Type of event (use EVENT_* constants)
            user_id: ID of user involved (optional)
            details: Additional event details (string)
            ip_address: Client IP (auto-detected if not provided)
        """
        try:
            if ip_address is None:
                ip_address = get_client_ip(request) if request else 'unknown'
            
            current_user_id = user_id or session.get('user_id')
            
            # Insert audit log (table is created by database.sql schema)
            insert_sql = """
            INSERT INTO audit_logs (event_type, user_id, ip_address, details)
            VALUES (%s, %s, %s, %s)
            """
            Database.execute_query(insert_sql, (event_type, current_user_id, ip_address, details), commit=True)
            
        except Exception as e:
            # Don't raise exception - just log to stdout
            print(f"Audit logging error: {e}")
    
    @staticmethod
    def log_login_attempt(email, success, ip_address=None, details=None):
        """Log a login attempt"""
        event_type = AuditLogger.EVENT_LOGIN_SUCCESS if success else AuditLogger.EVENT_LOGIN_FAILED
        log_details = f"Email: {email}"
        if details:
            log_details += f" | {details}"
        
        AuditLogger.log_event(event_type, details=log_details, ip_address=ip_address)
    
    @staticmethod
    def log_password_change(user_id, ip_address=None):
        """Log a password change"""
        AuditLogger.log_event(AuditLogger.EVENT_PASSWORD_CHANGE, user_id=user_id, ip_address=ip_address)
    
    @staticmethod
    def log_account_approval(approved_user_id, approver_user_id, approved=True):
        """Log account approval/rejection"""
        event_type = AuditLogger.EVENT_ACCOUNT_APPROVAL if approved else AuditLogger.EVENT_ACCOUNT_REJECTED
        details = f"Approved by admin ID {approver_user_id}"
        AuditLogger.log_event(event_type, user_id=approved_user_id, details=details)
    
    @staticmethod
    def log_rate_limit_exceeded(identifier, endpoint, ip_address=None):
        """Log rate limit exceeded"""
        details = f"Endpoint: {endpoint} | Identifier: {identifier}"
        AuditLogger.log_event(AuditLogger.EVENT_RATE_LIMIT_EXCEEDED, details=details, ip_address=ip_address)
    
    @staticmethod
    def log_csrf_violation(ip_address=None, endpoint=None):
        """Log CSRF token validation failure"""
        details = f"Endpoint: {endpoint}" if endpoint else None
        AuditLogger.log_event(AuditLogger.EVENT_CSRF_VIOLATION, details=details, ip_address=ip_address)
    
    @staticmethod
    def get_audit_logs(user_id=None, event_type=None, limit=100, offset=0):
        """
        Retrieve audit logs (admin only)
        
        Args:
            user_id: Filter by user (optional)
            event_type: Filter by event type (optional)
            limit: Number of records to return
            offset: Pagination offset
        
        Returns:
            List of audit log records
        """
        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        
        if user_id:
            sql += " AND user_id = %s"
            params.append(user_id)
        
        if event_type:
            sql += " AND event_type = %s"
            params.append(event_type)
        
        sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        try:
            return Database.execute_query(sql, tuple(params), fetch_all=True)
        except:
            return []
    
    @staticmethod
    def get_failed_login_attempts(ip_address, minutes=15):
        """Get failed login attempts from IP in last N minutes"""
        sql = """
        SELECT COUNT(*) as count 
        FROM audit_logs 
        WHERE event_type = %s 
        AND ip_address = %s 
        AND created_at > DATE_SUB(NOW(), INTERVAL %s MINUTE)
        """
        result = Database.execute_query(
            sql, 
            (AuditLogger.EVENT_LOGIN_FAILED, ip_address, minutes),
            fetch_one=True
        )
        return result['count'] if result else 0
    
    @staticmethod
    def cleanup_old_logs(days=90):
        """Delete audit logs older than N days (admin maintenance)"""
        sql = """
        DELETE FROM audit_logs 
        WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        try:
            Database.execute_query(sql, (days,), commit=True)
            return True
        except:
            return False
