"""
Luggage Service — UI Routes
============================
Handles all luggage-domain web pages: search, results, bag detail, registration.
This service owns the luggage_records and luggage_events tables exclusively.
Cross-domain data (tickets) is fetched via the Ticket Service internal API.
"""

import uuid
from flask import render_template, request, redirect, url_for, flash
from services.luggage import luggage_bp
from shared.db import get_db_connection, param, is_local, now_sql


# ==========================================
# Search Page
# ==========================================
@luggage_bp.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            flash("Please enter a Bag Tag or Booking Reference ID")
            return redirect(url_for('luggage.search'))
        return redirect(url_for('luggage.results', search_query=query))
    return render_template('search.html')


# ==========================================
# Search Results (Sortable + Clickable)
# ==========================================
@luggage_bp.route('/results/<search_query>')
def results(search_query):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query_pattern = f"%{search_query}%"
        p = param()

        if is_local():
            cursor.execute(f"""
                SELECT bag_tag, customer_name, booking_reference, status, last_updated
                FROM luggage_records
                WHERE bag_tag = {p} OR booking_reference = {p} OR customer_name LIKE {p}
            """, (search_query, search_query, query_pattern))
        else:
            cursor.execute(f"""
                SELECT bag_tag, customer_name, booking_reference, status, last_updated
                FROM luggage_records
                WHERE bag_tag = {p} OR booking_reference = {p} OR customer_name ILIKE {p}
            """, (search_query, search_query, query_pattern))

        records = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('results.html', records=records, search_query=search_query)
    except Exception as e:
        flash(f"System Offline / Database error: {str(e)}")
        return redirect(url_for('luggage.search'))


# ==========================================
# Individual Bag Detail
# ==========================================
@luggage_bp.route('/bag/<bag_tag>')
def bag_detail(bag_tag):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()

        # Query from OUR domain: luggage_records
        cursor.execute(f"""
            SELECT bag_tag, customer_name, booking_reference, status, last_updated
            FROM luggage_records WHERE bag_tag = {p}
        """, (bag_tag,))
        record = cursor.fetchone()

        if not record:
            flash("Bag not found in the system.")
            return redirect(url_for('luggage.search'))

        # Query from OUR domain: luggage_events
        cursor.execute(f"""
            SELECT event_status, location, event_time
            FROM luggage_events WHERE bag_tag = {p} ORDER BY event_time ASC
        """, (bag_tag,))
        events = cursor.fetchall()

        cursor.close()
        conn.close()

        # Cross-service call: fetch tickets from the Ticket Service API
        from services.tickets.api import get_tickets_for_bag
        tickets = get_tickets_for_bag(bag_tag)

        return render_template('bag_detail.html', record=record, events=events, tickets=tickets)
    except Exception as e:
        flash(f"Error loading bag details: {str(e)}")
        return redirect(url_for('luggage.search'))


# ==========================================
# Register New Bag
# ==========================================
@luggage_bp.route('/bag/new', methods=['GET', 'POST'])
def new_bag():
    if request.method == 'POST':
        try:
            customer_name = request.form.get('customer_name', '').strip()
            booking_reference = request.form.get('booking_reference', '').strip()
            initial_location = request.form.get('initial_location', '').strip()

            if not customer_name or not booking_reference or not initial_location:
                flash("All fields are required to register a new bag.")
                return redirect(url_for('luggage.new_bag'))

            bag_tag = f"BAG-{uuid.uuid4().hex[:8].upper()}"

            conn = get_db_connection()
            cursor = conn.cursor()
            p = param()
            now = now_sql()

            if is_local():
                cursor.execute(f"""
                    INSERT INTO luggage_records (bag_tag, customer_name, booking_reference, status, last_updated)
                    VALUES ({p}, {p}, {p}, 'Checked In', {now})
                """, (bag_tag, customer_name, booking_reference))

                cursor.execute(f"""
                    INSERT INTO luggage_events (bag_tag, event_status, location, event_time)
                    VALUES ({p}, 'Checked In', {p}, {now})
                """, (bag_tag, initial_location))
            else:
                cursor.execute(f"""
                    INSERT INTO luggage_records (bag_tag, customer_name, booking_reference, status, last_updated)
                    VALUES ({p}, {p}, {p}, 'Checked In', {now})
                """, (bag_tag, customer_name, booking_reference))

                cursor.execute(f"""
                    INSERT INTO luggage_events (bag_tag, event_status, location, event_time)
                    VALUES ({p}, 'Checked In', {p}, {now})
                """, (bag_tag, initial_location))

            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Success! Luggage registered with ID: {bag_tag}")
            return redirect(url_for('luggage.bag_detail', bag_tag=bag_tag))

        except Exception as e:
            flash(f"Error registering luggage: {str(e)}")
            return redirect(url_for('luggage.new_bag'))

    return render_template('new_bag.html')
