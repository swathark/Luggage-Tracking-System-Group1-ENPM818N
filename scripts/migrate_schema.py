"""
Schema migration for Luggage Tracker v2.0
Adds: priority, SLA, team assignment, escalation, categories, work notes table.
Safe to re-run — each ALTER TABLE is wrapped in try/except.
"""
import sqlite3
import datetime
import random

DB_PATH = 'local_luggage.db'

AGENTS = ['Agent Smith', 'Agent Jones', 'Agent Park', 'Agent Chen', 'Agent Rivera']
TEAMS = ['Baggage Handling', 'Customer Relations', 'Routing & Transfer', 'Security & Compliance', 'Management Escalation']
CATEGORIES = ['Damage', 'Lost', 'Delayed', 'Misrouted', 'Security', 'Other']
PRIORITIES = ['P1', 'P2', 'P3', 'P4']
SLA_HOURS = {'P1': 1, 'P2': 4, 'P3': 24, 'P4': 72}

def add_column(cursor, table, column, col_type, default=None):
    """Safely add a column — silently skips if it already exists."""
    try:
        if default is not None:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT '{default}'")
        else:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        print(f"  [OK] Added {table}.{column}")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print(f"  [SKIP] {table}.{column} already exists, skipping")
        else:
            raise

def run_migration():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── 1. Add new columns to support_tickets ──
    print("\n[1/4] Adding new columns to support_tickets...")
    add_column(cursor, 'support_tickets', 'priority', 'VARCHAR(10)', 'P3')
    add_column(cursor, 'support_tickets', 'sla_due_at', 'TIMESTAMP', None)
    add_column(cursor, 'support_tickets', 'assigned_team', 'VARCHAR(50)', None)
    add_column(cursor, 'support_tickets', 'assigned_agent', 'VARCHAR(100)', None)
    add_column(cursor, 'support_tickets', 'escalation_level', 'INTEGER', '0')
    add_column(cursor, 'support_tickets', 'category', 'VARCHAR(50)', None)
    add_column(cursor, 'support_tickets', 'subcategory', 'VARCHAR(50)', None)
    add_column(cursor, 'support_tickets', 'contact_method', 'VARCHAR(20)', 'Counter')
    add_column(cursor, 'support_tickets', 'resolution_notes', 'TEXT', None)
    add_column(cursor, 'support_tickets', 'resolved_at', 'TIMESTAMP', None)
    add_column(cursor, 'support_tickets', 'closed_at', 'TIMESTAMP', None)
    add_column(cursor, 'support_tickets', 'updated_at', 'TIMESTAMP', None)

    # ── 2. Create ticket_activity table ──
    print("\n[2/4] Creating ticket_activity table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER REFERENCES support_tickets(id),
            activity_type VARCHAR(20) NOT NULL,
            author VARCHAR(100) DEFAULT 'System',
            content TEXT NOT NULL,
            old_value VARCHAR(100),
            new_value VARCHAR(100),
            created_at TIMESTAMP NOT NULL
        )
    """)
    print("  [OK] ticket_activity table ready")

    # ── 3. Migrate existing ticket states ──
    print("\n[3/4] Migrating existing ticket states...")
    # Convert 'Open' to 'New' for freshly migrated tickets
    cursor.execute("UPDATE support_tickets SET ticket_status = 'New' WHERE ticket_status = 'Open'")
    migrated = cursor.rowcount
    print(f"  [OK] Migrated {migrated} 'Open' tickets to 'New'")

    # ── 4. Backfill new fields on existing tickets ──
    print("\n[4/4] Backfilling priority, team, SLA, and category data...")
    cursor.execute("SELECT id, created_at, ticket_status FROM support_tickets")
    tickets = cursor.fetchall()

    for tid, created_at_str, status in tickets:
        priority = random.choice(PRIORITIES)
        team = random.choice(TEAMS[:-1])  # Exclude Management for normal tickets
        agent = random.choice(AGENTS)
        category = random.choice(CATEGORIES)
        contact = random.choice(['Phone', 'Email', 'Counter', 'App'])
        escalation = random.choice([0, 0, 0, 1])  # Mostly non-escalated

        # Compute SLA due
        try:
            created_dt = datetime.datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            created_dt = datetime.datetime.now() - datetime.timedelta(hours=random.randint(1, 48))
        sla_due = created_dt + datetime.timedelta(hours=SLA_HOURS[priority])

        # Spread tickets across states
        if status == 'Closed':
            new_status = random.choice(['Resolved', 'Closed'])
            resolved_at = created_dt + datetime.timedelta(hours=random.randint(1, SLA_HOURS[priority] + 2))
            closed_at = resolved_at + datetime.timedelta(hours=random.randint(0, 4)) if new_status == 'Closed' else None
        else:
            new_status = random.choice(['New', 'In Progress', 'In Progress', 'On Hold'])
            resolved_at = None
            closed_at = None

        cursor.execute("""
            UPDATE support_tickets
            SET priority = ?, sla_due_at = ?, assigned_team = ?, assigned_agent = ?,
                escalation_level = ?, category = ?, contact_method = ?,
                ticket_status = ?, resolved_at = ?, closed_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (priority, sla_due, team, agent, escalation, category, contact,
              new_status, resolved_at, closed_at, datetime.datetime.now(), tid))

        # Insert a creation activity entry
        cursor.execute("""
            INSERT OR IGNORE INTO ticket_activity (ticket_id, activity_type, author, content, created_at)
            VALUES (?, 'system', 'System', 'Ticket created.', ?)
        """, (tid, created_dt))

        # Add a sample work note on some tickets
        if random.random() > 0.4:
            notes = [
                "Contacted passenger via phone. Awaiting callback.",
                "Checked carousel CCTV footage. Bag was loaded on wrong cart.",
                "Coordinated with ground crew at destination airport.",
                "Passenger confirmed bag description. Initiating trace.",
                "Escalated to routing team for cross-airport investigation.",
                "TSA clearance obtained. Bag released from security hold.",
                "Filed insurance claim documentation for passenger.",
                "Replacement bag offered and accepted by passenger.",
            ]
            note_time = created_dt + datetime.timedelta(minutes=random.randint(15, 120))
            cursor.execute("""
                INSERT INTO ticket_activity (ticket_id, activity_type, author, content, created_at)
                VALUES (?, 'work_note', ?, ?, ?)
            """, (tid, random.choice(AGENTS), random.choice(notes), note_time))

    conn.commit()
    print(f"\n[DONE] Migration complete. {len(tickets)} tickets updated.")
    cursor.close()
    conn.close()

if __name__ == '__main__':
    run_migration()
