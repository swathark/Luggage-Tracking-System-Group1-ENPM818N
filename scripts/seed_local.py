import sqlite3
import random
import uuid
import datetime
from datetime import timedelta
import os

DB_PATH = 'local_luggage.db'

def seed_db():
    print(f"Connecting to local SQLite database at ./{DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Creating layout schemas (tables)...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag VARCHAR(50) UNIQUE NOT NULL,
            customer_name VARCHAR(100) NOT NULL,
            booking_reference VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL,
            last_updated TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
            issue_description TEXT,
            ticket_status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS luggage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
            event_status VARCHAR(50) NOT NULL,
            location VARCHAR(100) NOT NULL,
            event_time TIMESTAMP NOT NULL
        )
    """)

    # Check if there are already records
    cursor.execute("SELECT COUNT(*) FROM luggage_records")
    if cursor.fetchone()[0] > 0:
        print("Database is already seeded. Exiting.")
        conn.close()
        return

    print("Injecting 50 rows of dummy luggage data into SQLite...")
    statuses = ['Checked In', 'Loaded', 'In Transit', 'Arrived', 'Delivered']
    first_names = ['Alice', 'Bob', 'Charlie', 'Diana', 'Ethan', 'Fiona', 'George', 'Hannah']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis']
    locations = [
        'JFK Terminal 4', 'LAX Terminal B', 'ORD Concourse K', 'ATL South Terminal',
        'DFW Gate C12', 'MIA Carousel 7', 'SFO International', 'DEN Baggage Hub',
        'SEA North Satellite', 'BOS Terminal E', 'EWR Terminal C', 'IAD Dulles Main'
    ]

    all_bag_tags = []

    for i in range(50):
        bag_tag = f"BAG-{uuid.uuid4().hex[:8].upper()}"
        customer = f"{random.choice(first_names)} {random.choice(last_names)}"
        booking = f"BKG-{random.randint(10000, 99999)}"
        status = random.choice(statuses)
        updated_at = datetime.datetime.now() - timedelta(minutes=random.randint(1, 1440))

        cursor.execute("""
            INSERT INTO luggage_records (bag_tag, customer_name, booking_reference, status, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (bag_tag, customer, booking, status, updated_at))

        all_bag_tags.append(bag_tag)

        # Generate chronological journey events for this bag
        status_idx = statuses.index(status)
        num_events = status_idx + 1
        event_base_time = updated_at - timedelta(hours=num_events * 2)
        for j in range(num_events):
            event_time = event_base_time + timedelta(hours=j * 2, minutes=random.randint(0, 30))
            event_location = random.choice(locations)
            cursor.execute("""
                INSERT INTO luggage_events (bag_tag, event_status, location, event_time)
                VALUES (?, ?, ?, ?)
            """, (bag_tag, statuses[j], event_location, event_time))

    # Pre-seed support tickets so Dashboard and Ticket Center have data
    print("Injecting 15 pre-seeded support tickets...")
    ticket_issues = [
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

    ticket_bags = random.sample(all_bag_tags, 15)
    for idx, bag_tag in enumerate(ticket_bags):
        ticket_status = random.choice(['Open', 'Open', 'Open', 'Closed', 'Closed'])
        created_at = datetime.datetime.now() - timedelta(hours=random.randint(1, 72))
        cursor.execute("""
            INSERT INTO support_tickets (bag_tag, issue_description, ticket_status, created_at)
            VALUES (?, ?, ?, ?)
        """, (bag_tag, ticket_issues[idx], ticket_status, created_at))

    conn.commit()
    print("Mock data successfully seeded. UI is ready for query visualizations.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    seed_db()
