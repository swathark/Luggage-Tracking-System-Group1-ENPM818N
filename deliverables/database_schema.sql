-- ==========================================
-- Luggage Tracking System Relational Schema
-- Target Engine: PostgreSQL 16.x
-- ==========================================

-- Table: luggage_records
-- Purpose: Holds absolute state profiles for physical baggage assets
CREATE TABLE IF NOT EXISTS luggage_records (
    id SERIAL PRIMARY KEY,
    bag_tag VARCHAR(50) UNIQUE NOT NULL,       -- Example: BAG-A1B2C3D4
    customer_name VARCHAR(100) NOT NULL,
    booking_reference VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,               -- e.g. 'Checked In', 'Loaded', 'In Transit', 'Arrived', 'Delivered'
    last_updated TIMESTAMP NOT NULL
);

-- Table: luggage_events
-- Purpose: Chronological journey timeline per bag (one-to-many from luggage_records)
CREATE TABLE IF NOT EXISTS luggage_events (
    id SERIAL PRIMARY KEY,
    bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
    event_status VARCHAR(50) NOT NULL,         -- e.g. 'Checked In', 'Loaded'
    location VARCHAR(100) NOT NULL,            -- e.g. 'JFK Terminal 4', 'LAX Terminal B'
    event_time TIMESTAMP NOT NULL
);

-- Table: support_tickets
-- Purpose: ITSM-grade Tier-1 CS escalation tracking with SLA, priority, team assignment
CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    bag_tag VARCHAR(50) REFERENCES luggage_records(bag_tag),
    issue_description TEXT,
    ticket_status VARCHAR(50) NOT NULL,        -- 'New', 'In Progress', 'On Hold', 'Resolved', 'Closed'
    created_at TIMESTAMP NOT NULL,
    priority VARCHAR(10) DEFAULT 'P3',         -- P1 (Critical), P2 (High), P3 (Medium), P4 (Low)
    sla_due_at TIMESTAMP,                      -- Computed from priority: P1=1h, P2=4h, P3=24h, P4=72h
    assigned_team VARCHAR(50),                 -- e.g. 'Baggage Handling', 'Routing & Transfer'
    assigned_agent VARCHAR(100),               -- e.g. 'Agent Smith'
    escalation_level INTEGER DEFAULT 0,        -- 0=Normal, 1=Escalated, 2=Management
    category VARCHAR(50),                      -- 'Damage', 'Lost', 'Delayed', 'Misrouted', 'Security', 'Other'
    subcategory VARCHAR(50),
    contact_method VARCHAR(20) DEFAULT 'Counter', -- 'Phone', 'Email', 'Counter', 'App'
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Table: ticket_activity
-- Purpose: Audit trail and work notes for each support ticket action
CREATE TABLE IF NOT EXISTS ticket_activity (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER REFERENCES support_tickets(id),
    activity_type VARCHAR(20) NOT NULL,        -- 'system', 'state_change', 'assignment', 'escalation', 'work_note'
    author VARCHAR(100) DEFAULT 'System',
    content TEXT NOT NULL,                     -- Description of the activity
    old_value VARCHAR(100),                    -- Previous value (for state changes)
    new_value VARCHAR(100),                    -- New value (for state changes)
    created_at TIMESTAMP NOT NULL
);

-- Indexing Strategies
CREATE INDEX idx_luggage_records_bag_tag ON luggage_records(bag_tag);
CREATE INDEX idx_luggage_events_bag_tag ON luggage_events(bag_tag);
CREATE INDEX idx_support_tickets_bag_tag ON support_tickets(bag_tag);
CREATE INDEX idx_support_tickets_status ON support_tickets(ticket_status);
CREATE INDEX idx_support_tickets_priority ON support_tickets(priority);
CREATE INDEX idx_ticket_activity_ticket_id ON ticket_activity(ticket_id);
