"""
API Gateway — Luggage Tracking Microservices
=============================================
Thin gateway that registers all microservice Blueprints, global template
filters, context processors, and serves the landing page + health check.

Architecture:
  ┌─────────────────────────────────────────────┐
  │  API Gateway (this file)                     │
  │  ├── Luggage Service   (services.luggage)    │
  │  ├── Ticket Service    (services.tickets)    │
  │  └── Analytics Service (services.analytics)  │
  └─────────────────────────────────────────────┘
"""

import os
import datetime
from flask import Flask, Blueprint, render_template, flash

# ==========================================
# Initialize Flask Application
# ==========================================
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==========================================
# Register Microservice Blueprints
# ==========================================
from services.luggage import luggage_bp
from services.tickets import tickets_bp
from services.analytics import analytics_bp

app.register_blueprint(luggage_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(analytics_bp)

# ==========================================
# Gateway Blueprint (landing + health)
# ==========================================
gateway_bp = Blueprint('gateway', __name__)


@gateway_bp.route('/health')
def health_check():
    """
    Required functionality: Used by our public Application Load Balancer to ensure
    the web EC2 instances are actively serving traffic!
    """
    return "OK", 200


@gateway_bp.route('/')
def landing():
    """Landing page — aggregates stats from Luggage and Ticket services."""
    try:
        from shared.db import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM luggage_records")
        total_bags = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        open_tickets = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM luggage_records WHERE status = 'Delivered'")
        delivered = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        delivery_rate = round((delivered / total_bags * 100), 1) if total_bags > 0 else 0
        return render_template('landing.html',
                               total_bags=total_bags, open_tickets=open_tickets,
                               delivered=delivered, delivery_rate=delivery_rate)
    except Exception as e:
        return render_template('landing.html', total_bags=0, open_tickets=0, delivered=0, delivery_rate=0)


app.register_blueprint(gateway_bp)

# ==========================================
# Global Template Context & Filters
# ==========================================
from shared.constants import (
    VALID_STATUSES, VALID_PRIORITIES, PRIORITY_LABELS, TEAMS,
    AGENTS, CATEGORIES, CONTACT_METHODS, STATE_TRANSITIONS, SLA_HOURS,
)
from services.tickets.api import get_open_ticket_count


@app.context_processor
def inject_globals():
    """Make constants and open ticket count available to all templates."""
    return {
        'open_ticket_count': get_open_ticket_count(),
        'VALID_STATUSES': VALID_STATUSES,
        'VALID_PRIORITIES': VALID_PRIORITIES,
        'PRIORITY_LABELS': PRIORITY_LABELS,
        'TEAMS': TEAMS,
        'AGENTS': AGENTS,
        'CATEGORIES': CATEGORIES,
        'CONTACT_METHODS': CONTACT_METHODS,
        'STATE_TRANSITIONS': STATE_TRANSITIONS,
        'SLA_HOURS': SLA_HOURS,
    }


@app.template_filter('timeago')
def timeago_filter(dt):
    """Convert a datetime to a relative 'time ago' string."""
    if not dt:
        return 'N/A'
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt
    now = datetime.datetime.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return 'just now'
    if seconds < 60:
        return f'{seconds}s ago'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    days = hours // 24
    if days < 30:
        return f'{days}d ago'
    months = days // 30
    return f'{months}mo ago'


@app.template_filter('sla_remaining')
def sla_remaining_filter(sla_due_at):
    """Return SLA remaining time or overdue status."""
    if not sla_due_at:
        return {'text': 'No SLA', 'status': 'none', 'seconds': 0}
    if isinstance(sla_due_at, str):
        try:
            sla_due_at = datetime.datetime.fromisoformat(sla_due_at)
        except (ValueError, TypeError):
            return {'text': 'Invalid', 'status': 'none', 'seconds': 0}
    now = datetime.datetime.now()
    diff = sla_due_at - now
    total_seconds = int(diff.total_seconds())
    if total_seconds <= 0:
        overdue = abs(total_seconds)
        hours = overdue // 3600
        mins = (overdue % 3600) // 60
        return {'text': f'Overdue by {hours}h {mins}m', 'status': 'breached', 'seconds': total_seconds}
    hours = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    status = 'ok' if hours >= 2 else 'warning' if hours >= 1 else 'critical'
    return {'text': f'{hours}h {mins}m remaining', 'status': status, 'seconds': total_seconds}


# ==========================================
# Entry Point
# ==========================================
if __name__ == '__main__':
    if os.environ.get('LOCAL_MODE') == '1':
        print("Running in LOCAL OFFLINE MODE on port 5000")
        print("Microservices: Luggage, Tickets, Analytics — registered as Blueprints")
        app.run(host='127.0.0.1', port=5000, debug=True)
    else:
        # Binds to 0.0.0.0 universally for ALB routing to container/EC2 boundary
        app.run(host='0.0.0.0', port=80, debug=False)
