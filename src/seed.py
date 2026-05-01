import os
import json
import random
import uuid
import datetime
import sqlite3
from datetime import timedelta

try:
    import psycopg2
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    pass

REGION = "us-east-1"
SECRET_NAME_PREFIX = "luggage-db-credentials"

def get_db_credentials():
    print("Fetching DB Credentials from AWS Secrets Manager...")
    client = boto3.client('secretsmanager', region_name=REGION)
    
    # We find the exact secret name that starts with luggage-db-credentials
    paginator = client.get_paginator('list_secrets')
    secret_arn = None
    for page in paginator.paginate():
        for secret in page['SecretList']:
            if secret['Name'].startswith(SECRET_NAME_PREFIX):
                secret_arn = secret['ARN']
                break
        if secret_arn:
            break
            
    if not secret_arn:
        raise Exception(f"Could not find secret starting with {SECRET_NAME_PREFIX} in {REGION}")

    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except ClientError as e:
        print(f"Error fetching secret: {e}")
        raise e

    secret_dict = json.loads(response['SecretString'])
    return secret_dict


# ==========================================
# Shared Data Definitions
# ==========================================
STATUSES = ['Checked In', 'Loaded', 'In Transit', 'Arrived', 'Delivered']
FIRST_NAMES = ['Alice', 'Bob', 'Charlie', 'Diana', 'Ethan', 'Fiona', 'George', 'Hannah']
LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis']
LOCATIONS = [
    'JFK Terminal 4', 'LAX Terminal B', 'ORD Concourse K', 'ATL South Terminal',
    'DFW Gate C12', 'MIA Carousel 7', 'SFO International', 'DEN Baggage Hub',
    'SEA North Satellite', 'BOS Terminal E', 'EWR Terminal C', 'IAD Dulles Main'
]
TICKET_ISSUES = [
    "Bag arrived with visible damage to handle and zipper. Passenger requesting compensation.",
    "Luggage missing from carousel after Flight UA-482. Passenger filed claim at counter.",
    "Wrong bag delivered to passenger. Tag mismatch — investigating cross-routing error.",
    "Delayed luggage — bag stuck at transfer hub for 6+ hours. Passenger flight departed.",
    "Luggage lock broken during security screening. TSA notice attached.",
    "Bag tag partially torn — scanner unable to read. Manual routing required.",
    "Passenger reports items missing from checked luggage after arrival.",
    "Oversized luggage rejected at gate. Needs manual re-routing to cargo hold.",
    "Bag rerouted to wrong destination. Currently at MIA instead of JFK.",
    "Weight discrepancy flagged — bag 12kg heavier than check-in record.",
    "Fragile items damaged during transit. Insurance claim initiated.",
    "Bag not loaded onto connecting flight due to tight layover window.",
    "Priority tag missing — First Class passenger bag treated as economy.",
    "Luggage carousel jam caused 45-min delay. Multiple passengers affected.",
    "Customs hold — bag flagged for secondary inspection at destination."
]
AGENTS = ['Agent Smith', 'Agent Jones', 'Agent Park', 'Agent Chen', 'Agent Rivera']
TEAMS = ['Baggage Handling', 'Customer Relations', 'Routing & Transfer', 'Security & Compliance']
CATEGORIES = ['Damage', 'Lost', 'Delayed', 'Misrouted', 'Security', 'Other']
PRIORITIES = ['P1', 'P2', 'P3', 'P4']
SLA_HOURS = {'P1': 1, 'P2': 4, 'P3': 24, 'P4': 72}


# ==========================================
# Local SQLite Seeder
# ==========================================
def seed_local():
    print("Running LOCAL SQLite seed...")
    db_path = 'local_luggage.db'

    # Remove stale database so we start fresh
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"  Removed stale {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    # ---- Schema ----
    print("Creating tables...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            booking_reference TEXT NOT NULL,
            status TEXT NOT NULL,
            last_updated TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag TEXT NOT NULL REFERENCES luggage_records(bag_tag),
            event_status TEXT NOT NULL,
            location TEXT NOT NULL,
            event_time TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag TEXT NOT NULL REFERENCES luggage_records(bag_tag),
            issue_description TEXT,
            ticket_status TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            priority TEXT DEFAULT 'P3',
            sla_due_at TIMESTAMP,
            assigned_team TEXT,
            assigned_agent TEXT,
            escalation_level INTEGER DEFAULT 0,
            category TEXT,
            subcategory TEXT,
            contact_method TEXT DEFAULT 'Counter',
            resolution_notes TEXT,
            resolved_at TIMESTAMP,
            closed_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id),
            activity_type TEXT NOT NULL,
            author TEXT DEFAULT 'System',
            content TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            created_at TIMESTAMP NOT NULL
        )
    """)

    # ---- Seed Luggage Records ----
    print("Seeding 50 luggage records...")
    all_bag_tags = []

    for i in range(50):
        bag_tag = f"BAG-{uuid.uuid4().hex[:8].upper()}"
        customer = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        booking = f"BKG-{random.randint(10000, 99999)}"
        status = random.choice(STATUSES)
        updated_at = (datetime.datetime.now() - timedelta(minutes=random.randint(1, 1440))).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT INTO luggage_records (bag_tag, customer_name, booking_reference, status, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (bag_tag, customer, booking, status, updated_at))

        all_bag_tags.append(bag_tag)

        # Generate chronological journey events for this bag
        status_idx = STATUSES.index(status)
        num_events = status_idx + 1
        event_base_time = datetime.datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S') - timedelta(hours=num_events * 2)
        for j in range(num_events):
            event_time = (event_base_time + timedelta(hours=j * 2, minutes=random.randint(0, 30))).strftime('%Y-%m-%d %H:%M:%S')
            event_location = random.choice(LOCATIONS)
            cursor.execute("""
                INSERT INTO luggage_events (bag_tag, event_status, location, event_time)
                VALUES (?, ?, ?, ?)
            """, (bag_tag, STATUSES[j], event_location, event_time))

    # ---- Seed Support Tickets ----
    print("Seeding 15 support tickets...")
    ticket_bags = random.sample(all_bag_tags, 15)

    for idx, bag_tag in enumerate(ticket_bags):
        ticket_status = random.choice(['New', 'In Progress', 'In Progress', 'Resolved', 'Closed'])
        created_at = datetime.datetime.now() - timedelta(hours=random.randint(1, 72))
        priority = random.choice(PRIORITIES)
        sla_due = created_at + timedelta(hours=SLA_HOURS[priority])
        team = random.choice(TEAMS)
        agent = random.choice(AGENTS)
        category = random.choice(CATEGORIES)
        escalation = random.choice([0, 0, 0, 1])

        if ticket_status == 'Resolved':
            resolved_at = (created_at + timedelta(hours=random.randint(1, SLA_HOURS[priority]))).strftime('%Y-%m-%d %H:%M:%S')
            closed_at = None
        elif ticket_status == 'Closed':
            resolved_at = (created_at + timedelta(hours=random.randint(1, SLA_HOURS[priority] + 1))).strftime('%Y-%m-%d %H:%M:%S')
            closed_at = (datetime.datetime.strptime(resolved_at, '%Y-%m-%d %H:%M:%S') + timedelta(hours=random.randint(0, 4))).strftime('%Y-%m-%d %H:%M:%S')
        else:
            resolved_at = None
            closed_at = None

        created_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
        sla_str = sla_due.strftime('%Y-%m-%d %H:%M:%S')
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT INTO support_tickets 
            (bag_tag, issue_description, ticket_status, created_at, priority, sla_due_at,
             assigned_team, assigned_agent, category, escalation_level, contact_method,
             resolved_at, closed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Phone', ?, ?, ?)
        """, (bag_tag, TICKET_ISSUES[idx], ticket_status, created_str, priority, sla_str,
              team, agent, category, escalation, resolved_at, closed_at, now_str))

        new_ticket_id = cursor.lastrowid

        # Log initial activity
        cursor.execute("""
            INSERT INTO ticket_activity (ticket_id, activity_type, author, content, created_at)
            VALUES (?, 'system', 'System', 'Ticket created.', ?)
        """, (new_ticket_id, created_str))

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Local SQLite database seeded successfully at {db_path}")
    print("  50 luggage records, journey events, 15 support tickets with activity logs.")


# ==========================================
# Remote PostgreSQL Seeder (AWS)
# ==========================================
def seed_db():
    try:
        creds = get_db_credentials()
    except Exception as e:
        print("Failed to get credentials. Have you run 'terraform apply'?")
        return
        
    print(f"Connecting to database {creds['dbname']} at {creds['host']}...")
    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['dbname'],
            user=creds['username'],
            password=creds['password']
        )
    except Exception as e:
        print("\nERROR: Could not connect to DB.")
        print("Note: Because our RDS is securely enclosed in Private Subnets with publicly_accessible=false, ")
        print("you cannot bridge directly from your local laptop without a VPN, Session Manager port forward,")
        print("or by executing this script directly on a Bastion/Jump EC2 Host deployed in the VPC.")
        return

    conn.autocommit = True
    cursor = conn.cursor()

    print("Creating layout schemas (tables)...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_records (
            id SERIAL PRIMARY KEY,
            bag_tag VARCHAR(50) UNIQUE NOT NULL,
            customer_name VARCHAR(100) NOT NULL,
            booking_reference VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL,
            last_updated TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
            issue_description TEXT,
            ticket_status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            priority VARCHAR(10) DEFAULT 'P3',
            sla_due_at TIMESTAMP,
            assigned_team VARCHAR(50),
            assigned_agent VARCHAR(100),
            escalation_level INTEGER DEFAULT 0,
            category VARCHAR(50),
            subcategory VARCHAR(50),
            contact_method VARCHAR(20) DEFAULT 'Counter',
            resolution_notes TEXT,
            resolved_at TIMESTAMP,
            closed_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_activity (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER REFERENCES support_tickets(id),
            activity_type VARCHAR(20) NOT NULL,
            author VARCHAR(100) DEFAULT 'System',
            content TEXT NOT NULL,
            old_value VARCHAR(100),
            new_value VARCHAR(100),
            created_at TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_events (
            id SERIAL PRIMARY KEY,
            bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
            event_status VARCHAR(50) NOT NULL,
            location VARCHAR(100) NOT NULL,
            event_time TIMESTAMP NOT NULL
        )
    """)

    print("Injecting 50 rows of dummy luggage data into Postgres...")
    all_bag_tags = []

    for i in range(50):
        bag_tag = f"BAG-{uuid.uuid4().hex[:8].upper()}"
        customer = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        booking = f"BKG-{random.randint(10000, 99999)}"
        status = random.choice(STATUSES)
        updated_at = datetime.datetime.now() - timedelta(minutes=random.randint(1, 1440))

        cursor.execute("""
            INSERT INTO luggage_records (bag_tag, customer_name, booking_reference, status, last_updated)
            VALUES (%s, %s, %s, %s, %s)
        """, (bag_tag, customer, booking, status, updated_at))

        all_bag_tags.append(bag_tag)

        # Generate chronological journey events for this bag
        status_idx = STATUSES.index(status)
        num_events = status_idx + 1
        event_base_time = updated_at - timedelta(hours=num_events * 2)
        for j in range(num_events):
            event_time = event_base_time + timedelta(hours=j * 2, minutes=random.randint(0, 30))
            event_location = random.choice(LOCATIONS)
            cursor.execute("""
                INSERT INTO luggage_events (bag_tag, event_status, location, event_time)
                VALUES (%s, %s, %s, %s)
            """, (bag_tag, STATUSES[j], event_location, event_time))

    # Pre-seed support tickets so Dashboard and Ticket Center have data
    print("Injecting 15 pre-seeded support tickets...")
    ticket_bags = random.sample(all_bag_tags, 15)
    for idx, bag_tag in enumerate(ticket_bags):
        ticket_status = random.choice(['New', 'In Progress', 'In Progress', 'Resolved', 'Closed'])
        created_at = datetime.datetime.now() - timedelta(hours=random.randint(1, 72))
        priority = random.choice(PRIORITIES)
        sla_due = created_at + timedelta(hours=SLA_HOURS[priority])
        team = random.choice(TEAMS)
        agent = random.choice(AGENTS)
        category = random.choice(CATEGORIES)
        escalation = random.choice([0, 0, 0, 1])

        if ticket_status == 'Resolved':
            resolved_at = created_at + timedelta(hours=random.randint(1, SLA_HOURS[priority]))
            closed_at = None
        elif ticket_status == 'Closed':
            resolved_at = created_at + timedelta(hours=random.randint(1, SLA_HOURS[priority] + 1))
            closed_at = resolved_at + timedelta(hours=random.randint(0, 4))
        else:
            resolved_at = None
            closed_at = None

        cursor.execute("""
            INSERT INTO support_tickets 
            (bag_tag, issue_description, ticket_status, created_at, priority, sla_due_at, assigned_team, assigned_agent, category, escalation_level, contact_method, resolved_at, closed_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Phone', %s, %s, %s)
            RETURNING id
        """, (bag_tag, TICKET_ISSUES[idx], ticket_status, created_at, priority, sla_due, team, agent, category, escalation, resolved_at, closed_at, datetime.datetime.now()))
        
        new_ticket_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO ticket_activity (ticket_id, activity_type, author, content, created_at)
            VALUES (%s, 'system', 'System', 'Ticket created.', %s)
        """, (new_ticket_id, created_at))

    print("Mock data successfully seeded. UI is ready for query visualizations.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    if os.environ.get('LOCAL_MODE') == '1':
        seed_local()
    else:
        seed_db()
