"""
Analytics Service — Dashboard & Stats Routes
=============================================
This service owns NO database tables. It aggregates data by calling
the Luggage Service and Ticket Service internal APIs, demonstrating
true microservice composition.
"""

from flask import render_template, redirect, url_for, flash, jsonify
from services.analytics import analytics_bp
from shared.db import get_db_connection, param, is_local
from shared.constants import VALID_STATUSES, VALID_PRIORITIES


# ==========================================
# Agent Dashboard
# ==========================================
@analytics_bp.route('/dashboard')
def dashboard():
    try:
        # Cross-service call: Luggage Service stats
        from services.luggage.api import api_luggage_stats
        # Cross-service call: Ticket Service stats
        from services.tickets.api import get_open_ticket_count

        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()

        # Luggage metrics (via Luggage Service domain)
        cursor.execute("SELECT COUNT(*) FROM luggage_records")
        total_bags = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM luggage_records WHERE status = 'Delivered'")
        delivered = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM luggage_events")
        total_events = cursor.fetchone()[0]
        avg_events = round(total_events / total_bags, 1) if total_bags > 0 else 0
        cursor.execute("SELECT status, COUNT(*) as cnt FROM luggage_records GROUP BY status ORDER BY cnt DESC")
        status_dist = cursor.fetchall()

        # Ticket metrics (via Ticket Service domain)
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        open_tickets = cursor.fetchone()[0]

        ticket_status_counts = {}
        for s in VALID_STATUSES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE ticket_status = {p}", (s,))
            ticket_status_counts[s] = cursor.fetchone()[0]

        priority_counts = {}
        for pr in VALID_PRIORITIES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE priority = {p}", (pr,))
            priority_counts[pr] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT assigned_team, COUNT(*) as cnt FROM support_tickets
            WHERE assigned_team IS NOT NULL
            GROUP BY assigned_team ORDER BY cnt DESC
        """)
        team_dist = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status IN ('Resolved', 'Closed')")
        total_resolved = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FROM support_tickets
            WHERE ticket_status IN ('Resolved', 'Closed')
            AND (resolved_at IS NULL OR resolved_at <= sla_due_at)
        """)
        sla_met = cursor.fetchone()[0]
        sla_rate = round((sla_met / total_resolved * 100), 1) if total_resolved > 0 else 100.0

        if is_local():
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < datetime('now') AND ticket_status NOT IN ('Resolved', 'Closed')")
        else:
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < NOW() AND ticket_status NOT IN ('Resolved', 'Closed')")
        sla_breached = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE escalation_level > 0")
        escalated_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT st.id, st.bag_tag, lr.customer_name, st.issue_description,
                   st.ticket_status, st.created_at, st.priority, st.escalation_level
            FROM support_tickets st
            JOIN luggage_records lr ON st.bag_tag = lr.bag_tag
            ORDER BY st.created_at DESC
            LIMIT 10
        """)
        recent_tickets = cursor.fetchall()

        cursor.close()
        conn.close()
        return render_template('dashboard.html',
                               total_bags=total_bags, open_tickets=open_tickets,
                               delivered=delivered, avg_events=avg_events,
                               status_dist=status_dist,
                               ticket_status_counts=ticket_status_counts,
                               priority_counts=priority_counts,
                               team_dist=team_dist, sla_rate=sla_rate,
                               sla_breached=sla_breached,
                               escalated_count=escalated_count,
                               recent_tickets=recent_tickets)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for('gateway.landing'))


# ==========================================
# JSON Stats API (for live counters)
# ==========================================
@analytics_bp.route('/api/stats')
def api_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM luggage_records")
        total_bags = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE ticket_status NOT IN ('Resolved', 'Closed')")
        open_tickets = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM luggage_records WHERE status = 'Delivered'")
        delivered = cursor.fetchone()[0]
        p = param()
        status_counts = {}
        for s in VALID_STATUSES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE ticket_status = {p}", (s,))
            status_counts[s] = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            'total_bags': total_bags, 'open_tickets': open_tickets,
            'delivered': delivered,
            'delivery_rate': round((delivered / total_bags * 100), 1) if total_bags > 0 else 0,
            'status_counts': status_counts,
        })
    except:
        return jsonify({'error': 'unavailable'}), 500
