# ==========================================
# Shared Constants — Luggage Tracking Microservices
# Single source of truth for all service-level constants.
# ==========================================

REGION = "us-east-1"
SECRET_NAME_PREFIX = "luggage-db-credentials"

VALID_STATUSES = ['New', 'In Progress', 'On Hold', 'Resolved', 'Closed']
VALID_PRIORITIES = ['P1', 'P2', 'P3', 'P4']
PRIORITY_LABELS = {'P1': 'Critical', 'P2': 'High', 'P3': 'Medium', 'P4': 'Low'}
SLA_HOURS = {'P1': 1, 'P2': 4, 'P3': 24, 'P4': 72}
TEAMS = ['Baggage Handling', 'Customer Relations', 'Routing & Transfer', 'Security & Compliance', 'Management Escalation']
AGENTS = ['Agent Smith', 'Agent Jones', 'Agent Park', 'Agent Chen', 'Agent Rivera']
CATEGORIES = ['Damage', 'Lost', 'Delayed', 'Misrouted', 'Security', 'Other']
CONTACT_METHODS = ['Phone', 'Email', 'Counter', 'App']

# Valid state transitions for ticket lifecycle
STATE_TRANSITIONS = {
    'New':         ['In Progress', 'On Hold', 'Closed'],
    'In Progress': ['On Hold', 'Resolved', 'Closed'],
    'On Hold':     ['New', 'In Progress', 'Closed'],
    'Resolved':    ['Closed', 'In Progress'],
    'Closed':      ['New'],  # Reopen
}

# Auto-assignment map: category -> team
TEAM_ASSIGNMENT_MAP = {
    'Damage': 'Baggage Handling',
    'Lost': 'Routing & Transfer',
    'Delayed': 'Routing & Transfer',
    'Misrouted': 'Routing & Transfer',
    'Security': 'Security & Compliance',
    'Other': 'Customer Relations',
}
