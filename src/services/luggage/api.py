"""
Luggage Service — Internal API Endpoints
=========================================
JSON endpoints consumed by other microservices (Ticket Service, Analytics Service).
In a production ECS/EKS deployment, these would be called via service discovery DNS.
In this Blueprint architecture, they are called as internal function imports.
"""

from flask import jsonify
from services.luggage import luggage_bp
from shared.db import get_db_connection, param, is_local


@luggage_bp.route('/api/luggage/health')
def api_health():
    """Health check for the Luggage microservice."""
    return jsonify({'service': 'luggage', 'status': 'healthy'}), 200


@luggage_bp.route('/api/luggage/<bag_tag>')
def api_get_bag(bag_tag):
    """Return a single luggage record as JSON. Used by Ticket Service."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"""
            SELECT bag_tag, customer_name, booking_reference, status, last_updated
            FROM luggage_records WHERE bag_tag = {p}
        """, (bag_tag,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        return jsonify({
            'bag_tag': row[0],
            'customer_name': row[1],
            'booking_reference': row[2],
            'status': row[3],
            'last_updated': str(row[4]),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@luggage_bp.route('/api/luggage/batch')
def api_get_bags_batch():
    """Return multiple luggage records by comma-separated tags. Used by Ticket Service for list views."""
    from flask import request
    tags = request.args.get('tags', '').split(',')
    tags = [t.strip() for t in tags if t.strip()]
    if not tags:
        return jsonify({})
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ', '.join([param()] * len(tags))
        cursor.execute(f"""
            SELECT bag_tag, customer_name FROM luggage_records
            WHERE bag_tag IN ({placeholders})
        """, tuple(tags))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = {row[0]: row[1] for row in rows}
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@luggage_bp.route('/api/luggage/all-tags')
def api_all_tags():
    """Return all bag tags and customer names. Used by Ticket Service create form."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT bag_tag, customer_name FROM luggage_records ORDER BY bag_tag")
        bags = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{'bag_tag': b[0], 'customer_name': b[1]} for b in bags])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@luggage_bp.route('/api/luggage/stats')
def api_luggage_stats():
    """Return aggregated luggage metrics. Used by Analytics Service."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM luggage_records")
        total_bags = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM luggage_records WHERE status = 'Delivered'")
        delivered = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM luggage_events")
        total_events = cursor.fetchone()[0]
        avg_events = round(total_events / total_bags, 1) if total_bags > 0 else 0

        cursor.execute("""
            SELECT status, COUNT(*) as cnt FROM luggage_records GROUP BY status ORDER BY cnt DESC
        """)
        status_dist = [{'status': row[0], 'count': row[1]} for row in cursor.fetchall()]

        cursor.close()
        conn.close()
        return jsonify({
            'total_bags': total_bags,
            'delivered': delivered,
            'avg_events': avg_events,
            'delivery_rate': round((delivered / total_bags * 100), 1) if total_bags > 0 else 0,
            'status_distribution': status_dist,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_bag_record(bag_tag):
    """Internal function for same-process service calls (avoids HTTP overhead)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    p = param()
    cursor.execute(f"""
        SELECT bag_tag, customer_name, booking_reference, status, last_updated
        FROM luggage_records WHERE bag_tag = {p}
    """, (bag_tag,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def get_customer_names_batch(bag_tags):
    """Internal function: return dict of {bag_tag: customer_name} for a list of tags."""
    if not bag_tags:
        return {}
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ', '.join([param()] * len(bag_tags))
    cursor.execute(f"""
        SELECT bag_tag, customer_name FROM luggage_records
        WHERE bag_tag IN ({placeholders})
    """, tuple(bag_tags))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[0]: row[1] for row in rows}
