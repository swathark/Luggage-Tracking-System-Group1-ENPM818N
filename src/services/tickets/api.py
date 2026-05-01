"""
Ticket Service — Internal API Endpoints
========================================
JSON endpoints consumed by other microservices (Luggage Service, Analytics Service).
"""

from flask import jsonify
from services.tickets import tickets_bp
from shared.db import get_db_connection, param, is_local
from shared.constants import VALID_STATUSES, VALID_PRIORITIES


@tickets_bp.route('/api/tickets/health')
def api_health():
    """Health check for the Ticket microservice."""
    return jsonify({'service': 'tickets', 'status': 'healthy'}), 200


@tickets_bp.route('/api/tickets/open-count')
def api_open_count():
    """Return the count of active (non-closed/resolved) tickets. Used by sidebar badge."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({'open_count': count})
    except:
        return jsonify({'open_count': 0})


@tickets_bp.route('/api/tickets/by-bag/<bag_tag>')
def api_tickets_by_bag(bag_tag):
    """Return tickets for a specific bag tag. Used by Luggage Service bag detail."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"""
            SELECT id, issue_description, ticket_status, priority, created_at, assigned_team, category
            FROM support_tickets WHERE bag_tag = {p} ORDER BY created_at DESC
        """, (bag_tag,))
        tickets = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{
            'id': t[0], 'issue_description': t[1], 'ticket_status': t[2],
            'priority': t[3], 'created_at': str(t[4]),
            'assigned_team': t[5], 'category': t[6]
        } for t in tickets])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@tickets_bp.route('/api/tickets/stats')
def api_ticket_stats():
    """Return aggregated ticket metrics. Used by Analytics Service."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()

        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        open_tickets = cursor.fetchone()[0]

        # Status counts
        status_counts = {}
        for s in VALID_STATUSES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE ticket_status = {p}", (s,))
            status_counts[s] = cursor.fetchone()[0]

        # Priority counts
        priority_counts = {}
        for pr in VALID_PRIORITIES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE priority = {p}", (pr,))
            priority_counts[pr] = cursor.fetchone()[0]

        # Team distribution
        cursor.execute("""
            SELECT assigned_team, COUNT(*) as cnt FROM support_tickets
            WHERE assigned_team IS NOT NULL
            GROUP BY assigned_team ORDER BY cnt DESC
        """)
        team_dist = [{'team': row[0], 'count': row[1]} for row in cursor.fetchall()]

        # SLA metrics
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status IN ('Resolved', 'Closed')")
        total_resolved = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM support_tickets
            WHERE ticket_status IN ('Resolved', 'Closed')
            AND (resolved_at IS NULL OR resolved_at <= sla_due_at)
        """)
        sla_met = cursor.fetchone()[0]
        sla_rate = round((sla_met / total_resolved * 100), 1) if total_resolved > 0 else 100.0

        # SLA breaches
        if is_local():
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < datetime('now') AND ticket_status NOT IN ('Resolved', 'Closed')")
        else:
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < NOW() AND ticket_status NOT IN ('Resolved', 'Closed')")
        sla_breached = cursor.fetchone()[0]

        # Escalation count
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE escalation_level > 0")
        escalated_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()
        return jsonify({
            'open_tickets': open_tickets,
            'status_counts': status_counts,
            'priority_counts': priority_counts,
            'team_distribution': team_dist,
            'sla_rate': sla_rate,
            'sla_breached': sla_breached,
            'escalated_count': escalated_count,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@tickets_bp.route('/api/tickets/recent')
def api_recent_tickets():
    """Return 10 most recent tickets with customer names. Used by Analytics Service."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # NOTE: This is the one remaining cross-domain JOIN kept for performance.
        # In a true distributed deployment, this would call the Luggage Service API.
        cursor.execute("""
            SELECT st.id, st.bag_tag, lr.customer_name, st.issue_description,
                   st.ticket_status, st.created_at, st.priority, st.escalation_level
            FROM support_tickets st
            JOIN luggage_records lr ON st.bag_tag = lr.bag_tag
            ORDER BY st.created_at DESC
            LIMIT 10
        """)
        tickets = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{
            'id': t[0], 'bag_tag': t[1], 'customer_name': t[2],
            'issue_description': t[3], 'ticket_status': t[4],
            'created_at': str(t[5]), 'priority': t[6], 'escalation_level': t[7]
        } for t in tickets])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# Internal helper functions (same-process calls)
# ==========================================
def get_tickets_for_bag(bag_tag):
    """Internal function called by Luggage Service to get tickets for a bag."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = param()
    cursor.execute(f"""
        SELECT id, issue_description, ticket_status, priority, created_at, assigned_team, category
        FROM support_tickets WHERE bag_tag = {p} ORDER BY created_at DESC
    """, (bag_tag,))
    tickets = cursor.fetchall()
    cursor.close()
    conn.close()
    return tickets


def get_open_ticket_count():
    """Internal function for sidebar badge count."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count
    except:
        return 0
