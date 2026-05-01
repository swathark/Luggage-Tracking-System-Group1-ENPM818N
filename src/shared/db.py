"""
Shared Database Layer — Luggage Tracking Microservices

Provides a unified database connection factory and helper utilities
consumed by all microservices. Supports both local SQLite (LOCAL_MODE=1)
and production PostgreSQL via AWS Secrets Manager.
"""

import os
import json
import sqlite3

try:
    import boto3
    import psycopg2
    import psycopg2.extras
    from botocore.exceptions import ClientError
except ImportError:
    pass

from shared.constants import REGION, SECRET_NAME_PREFIX

# Cache credentials to avoid pounding Secrets Manager API limits internally
_cached_creds = None


def get_db_credentials():
    """Fetch database credentials from AWS Secrets Manager."""
    global _cached_creds
    if _cached_creds:
        return _cached_creds

    client = boto3.client('secretsmanager', region_name=REGION)
    paginator = client.get_paginator('list_secrets')
    secret_arn = None

    # Locate secret ARN programmatically to avoid hardcoding ARNs in Code
    for page in paginator.paginate():
        for secret in page['SecretList']:
            if secret['Name'].startswith(SECRET_NAME_PREFIX):
                secret_arn = secret['ARN']
                break
        if secret_arn:
            break

    if not secret_arn:
        return None

    try:
        response = client.get_secret_value(SecretId=secret_arn)
        _cached_creds = json.loads(response['SecretString'])
        return _cached_creds
    except ClientError as e:
        print(f"Error fetching DB Secret from AWS: {e}")
        return None


def get_db_connection():
    """Return a database connection (SQLite locally, PostgreSQL in production)."""
    if is_local():
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_luggage.db')
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    creds = get_db_credentials()
    if not creds:
        raise Exception("Database credentials not found. Ensure IAM roles and Secrets exist.")

    return psycopg2.connect(
        host=creds['host'],
        port=creds['port'],
        database=creds['dbname'],
        user=creds['username'],
        password=creds['password'],
        cursor_factory=psycopg2.extras.DictCursor
    )


def is_local():
    """Check if the application is running in local offline mode."""
    return os.environ.get('LOCAL_MODE') == '1'


def param(idx=1):
    """Return parameter placeholder based on DB driver."""
    return '?' if is_local() else '%s'


def now_sql():
    """Return current timestamp expression for the active DB."""
    return "datetime('now')" if is_local() else "NOW()"


def log_activity(cursor, ticket_id, activity_type, content, author='System', old_value=None, new_value=None):
    """Insert an activity log entry for a ticket."""
    if is_local():
        cursor.execute("""
            INSERT INTO ticket_activity (ticket_id, activity_type, author, content, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (ticket_id, activity_type, author, content, old_value, new_value))
    else:
        cursor.execute("""
            INSERT INTO ticket_activity (ticket_id, activity_type, author, content, old_value, new_value, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (ticket_id, activity_type, author, content, old_value, new_value))
