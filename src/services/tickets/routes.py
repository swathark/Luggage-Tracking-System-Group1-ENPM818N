"""
Ticket Service — UI Routes
============================
Handles all ticket-domain web pages and actions.
Owns: support_tickets, ticket_activity tables exclusively.
Cross-domain data (customer names) fetched via Luggage Service internal API.
"""

import json
import datetime
from flask import render_template, request, redirect, url_for, flash

try:
    import boto3
except ImportError:
    pass

from services.tickets import tickets_bp
from shared.db import get_db_connection, param, is_local, now_sql, log_activity
from shared.constants import (
    VALID_STATUSES, VALID_PRIORITIES, PRIORITY_LABELS, SLA_HOURS,
    TEAMS, AGENTS, CATEGORIES, CONTACT_METHODS, STATE_TRANSITIONS,
    TEAM_ASSIGNMENT_MAP, REGION,
)


def _publish_sns_event(bag_tag, issue):
    """Fan out ticket event to serverless pipeline (production only)."""
    if is_local():
        return
    try:
        sns = boto3.client('sns', region_name=REGION)
        topics = sns.list_topics()['Topics']
        target_arn = next((t['TopicArn'] for t in topics if 'luggage-support-tickets-topic' in t['TopicArn']), None)
        if target_arn:
            sns.publish(TopicArn=target_arn, Message=json.dumps({'bag_tag': bag_tag, 'issue_description': issue}))
    except Exception as e:
        print(f"SNS Broadcast skipped/isolated due to: {e}")


# ==========================================
# Ticket Center (All Tickets)
# ==========================================
@tickets_bp.route('/tickets')
def tickets():
    try:
        status_filter = request.args.get('status', 'all')
        priority_filter = request.args.get('priority', 'all')
        team_filter = request.args.get('team', 'all')
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []
        p = param()

        if status_filter in VALID_STATUSES:
            conditions.append(f"st.ticket_status = {p}")
            params.append(status_filter)
        if priority_filter in VALID_PRIORITIES:
            conditions.append(f"st.priority = {p}")
            params.append(priority_filter)
        if team_filter != 'all' and team_filter in TEAMS:
            conditions.append(f"st.assigned_team = {p}")
            params.append(team_filter)

        where_clause = " AND ".join(conditions)
        if where_clause:
            where_clause = "WHERE " + where_clause

        # Cross-service JOIN kept for list performance; documented as an optimization
        cursor.execute(f"""
            SELECT st.id, st.bag_tag, lr.customer_name, st.issue_description,
                   st.ticket_status, st.created_at, st.priority, st.assigned_team,
                   st.escalation_level, st.sla_due_at, st.category
            FROM support_tickets st
            JOIN luggage_records lr ON st.bag_tag = lr.bag_tag
            {where_clause}
            ORDER BY
                CASE st.priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 WHEN 'P4' THEN 4 END,
                st.created_at DESC
        """, tuple(params))
        all_tickets = cursor.fetchall()

        status_counts = {}
        for s in VALID_STATUSES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE ticket_status = {p}", (s,))
            status_counts[s] = cursor.fetchone()[0]
        total_count = sum(status_counts.values())
        active_count = total_count - status_counts.get('Resolved', 0) - status_counts.get('Closed', 0)

        priority_counts = {}
        for pr in VALID_PRIORITIES:
            cursor.execute(f"SELECT COUNT(*) FROM support_tickets WHERE priority = {p}", (pr,))
            priority_counts[pr] = cursor.fetchone()[0]

        if is_local():
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < datetime('now') AND ticket_status NOT IN ('Resolved', 'Closed')")
        else:
            cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE sla_due_at < NOW() AND ticket_status NOT IN ('Resolved', 'Closed')")
        sla_breached = cursor.fetchone()[0]

        cursor.close()
        conn.close()
        return render_template('tickets.html',
                               tickets=all_tickets, status_filter=status_filter,
                               priority_filter=priority_filter, team_filter=team_filter,
                               status_counts=status_counts, priority_counts=priority_counts,
                               total_count=total_count, active_count=active_count,
                               sla_breached=sla_breached)
    except Exception as e:
        import traceback; traceback.print_exc()
        flash(f"Error loading tickets: {str(e)}")
        return redirect(url_for('gateway.landing'))


# ==========================================
# Ticket Detail
# ==========================================
@tickets_bp.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()

        cursor.execute(f"""
            SELECT st.id, st.bag_tag, st.issue_description, st.ticket_status, st.created_at,
                   lr.customer_name, lr.booking_reference, lr.status, lr.last_updated,
                   st.priority, st.sla_due_at, st.assigned_team, st.assigned_agent,
                   st.escalation_level, st.category, st.subcategory, st.contact_method,
                   st.resolution_notes, st.resolved_at, st.closed_at, st.updated_at
            FROM support_tickets st
            JOIN luggage_records lr ON st.bag_tag = lr.bag_tag
            WHERE st.id = {p}
        """, (ticket_id,))
        ticket = cursor.fetchone()

        if not ticket:
            flash("Ticket not found.")
            return redirect(url_for('tickets.tickets'))

        cursor.execute(f"""
            SELECT id, activity_type, author, content, old_value, new_value, created_at
            FROM ticket_activity WHERE ticket_id = {p} ORDER BY created_at DESC
        """, (ticket_id,))
        activities = cursor.fetchall()

        cursor.close()
        conn.close()
        return render_template('ticket_detail.html', ticket=ticket, activities=activities)
    except Exception as e:
        flash(f"Error loading ticket: {str(e)}")
        return redirect(url_for('tickets.tickets'))


# ==========================================
# Create Ticket (Standalone)
# ==========================================
@tickets_bp.route('/ticket/create', methods=['GET', 'POST'])
def create_ticket():
    if request.method == 'GET':
        try:
            # Cross-service call: get bag list from Luggage Service
            from services.luggage.api import get_customer_names_batch
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT bag_tag, customer_name FROM luggage_records ORDER BY bag_tag")
            bags = cursor.fetchall()
            cursor.close()
            conn.close()
            return render_template('new_ticket.html', bags=bags)
        except Exception as e:
            flash(f"Error loading bag list: {str(e)}")
            return redirect(url_for('tickets.tickets'))

    bag_tag = request.form.get('bag_tag', '').strip()
    issue = request.form.get('issue_description', '').strip()
    priority = request.form.get('priority', 'P3')
    category = request.form.get('category', 'Other')
    contact_method = request.form.get('contact_method', 'Counter')

    if not bag_tag or not issue:
        flash("Bag Tag and Issue Description are required.")
        return redirect(url_for('tickets.create_ticket'))
    if priority not in VALID_PRIORITIES:
        priority = 'P3'
    if category not in CATEGORIES:
        category = 'Other'

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()

        cursor.execute(f"SELECT bag_tag FROM luggage_records WHERE bag_tag = {p}", (bag_tag,))
        if not cursor.fetchone():
            flash("Invalid Bag Tag — not found in the system.")
            cursor.close(); conn.close()
            return redirect(url_for('tickets.create_ticket'))

        assigned_team = TEAM_ASSIGNMENT_MAP.get(category, 'Customer Relations')
        assigned_agent = AGENTS[hash(bag_tag) % len(AGENTS)]

        if is_local():
            sla_due = (datetime.datetime.now() + datetime.timedelta(hours=SLA_HOURS[priority])).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO support_tickets
                (bag_tag, issue_description, ticket_status, priority, sla_due_at,
                 assigned_team, assigned_agent, category, contact_method, created_at, updated_at)
                VALUES (?, ?, 'New', ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (bag_tag, issue, priority, sla_due, assigned_team, assigned_agent, category, contact_method))
        else:
            cursor.execute("""
                INSERT INTO support_tickets
                (bag_tag, issue_description, ticket_status, priority, sla_due_at,
                 assigned_team, assigned_agent, category, contact_method, created_at, updated_at)
                VALUES (%s, %s, 'New', %s, NOW() + INTERVAL '%s hours',
                 %s, %s, %s, %s, NOW(), NOW())
            """, (bag_tag, issue, priority, SLA_HOURS[priority], assigned_team, assigned_agent, category, contact_method))

        conn.commit()
        if is_local():
            cursor.execute("SELECT last_insert_rowid()")
        else:
            cursor.execute("SELECT currval(pg_get_serial_sequence('support_tickets', 'id'))")
        new_id = cursor.fetchone()[0]

        log_activity(cursor, new_id, 'system',
                    f'Ticket created. Priority: {priority} ({PRIORITY_LABELS[priority]}). Category: {category}. Assigned to {assigned_team} / {assigned_agent}.',
                    author='System')
        conn.commit()
        cursor.close()
        conn.close()

        _publish_sns_event(bag_tag, issue)

        flash("Support ticket created and auto-assigned!")
        return redirect(url_for('tickets.ticket_detail', ticket_id=new_id))
    except Exception as e:
        flash(f"Error creating ticket: {str(e)}")
        return redirect(url_for('tickets.create_ticket'))


# ==========================================
# Create Ticket (from Bag Detail)
# ==========================================
@tickets_bp.route('/ticket/new/<bag_tag>', methods=['POST'])
def new_ticket(bag_tag):
    issue = request.form.get('issue_description')
    priority = request.form.get('priority', 'P3')
    category = request.form.get('category', 'Other')
    contact_method = request.form.get('contact_method', 'Counter')

    if priority not in VALID_PRIORITIES:
        priority = 'P3'
    if category not in CATEGORIES:
        category = 'Other'

    if issue:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            p = param()

            assigned_team = TEAM_ASSIGNMENT_MAP.get(category, 'Customer Relations')
            assigned_agent = AGENTS[hash(bag_tag) % len(AGENTS)]

            if is_local():
                sla_due = (datetime.datetime.now() + datetime.timedelta(hours=SLA_HOURS[priority])).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO support_tickets
                    (bag_tag, issue_description, ticket_status, priority, sla_due_at,
                     assigned_team, assigned_agent, category, contact_method, created_at, updated_at)
                    VALUES (?, ?, 'New', ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (bag_tag, issue, priority, sla_due, assigned_team, assigned_agent, category, contact_method))
            else:
                cursor.execute("""
                    INSERT INTO support_tickets
                    (bag_tag, issue_description, ticket_status, priority, sla_due_at,
                     assigned_team, assigned_agent, category, contact_method, created_at, updated_at)
                    VALUES (%s, %s, 'New', %s, NOW() + INTERVAL '%s hours',
                     %s, %s, %s, %s, NOW(), NOW())
                """, (bag_tag, issue, priority, SLA_HOURS[priority], assigned_team, assigned_agent, category, contact_method))

            conn.commit()
            if is_local():
                cursor.execute("SELECT last_insert_rowid()")
            else:
                cursor.execute("SELECT currval(pg_get_serial_sequence('support_tickets', 'id'))")
            new_id = cursor.fetchone()[0]

            log_activity(cursor, new_id, 'system',
                        f'Ticket created. Priority: {priority} ({PRIORITY_LABELS[priority]}). Category: {category}. Assigned to {assigned_team} / {assigned_agent}.',
                        author='System')
            conn.commit()
            cursor.close()
            conn.close()

            _publish_sns_event(bag_tag, issue)

            flash("Support ticket created and auto-assigned!")
            return redirect(url_for('tickets.ticket_detail', ticket_id=new_id))
        except Exception as e:
            flash(f"Error creating platform ticket: {str(e)}")

    return redirect(url_for('luggage.bag_detail', bag_tag=bag_tag))


# ==========================================
# Update Status
# ==========================================
@tickets_bp.route('/ticket/update-status/<int:ticket_id>', methods=['POST'])
def update_ticket_status(ticket_id):
    new_status = request.form.get('new_status')
    if new_status not in VALID_STATUSES:
        flash("Invalid status.")
        return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT ticket_status FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            flash("Ticket not found."); return redirect(url_for('tickets.tickets'))
        old_status = row[0]
        allowed = STATE_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            flash(f"Cannot transition from '{old_status}' to '{new_status}'.")
            return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
        agent = AGENTS[ticket_id % len(AGENTS)]
        updates = [f"ticket_status = {p}", f"updated_at = {now_sql()}"]
        params = [new_status]
        if new_status == 'Resolved':
            updates.append(f"resolved_at = {now_sql()}")
        elif new_status == 'Closed':
            updates.append(f"closed_at = {now_sql()}")
        update_sql = ", ".join(updates)
        params.append(ticket_id)
        cursor.execute(f"UPDATE support_tickets SET {update_sql} WHERE id = {p}", tuple(params))
        log_activity(cursor, ticket_id, 'state_change',
                     f'Status changed from {old_status} to {new_status}.', author=agent, old_value=old_status, new_value=new_status)
        conn.commit(); cursor.close(); conn.close()
        flash(f"Ticket status updated to '{new_status}'.")
    except Exception as e:
        flash(f"Error updating ticket: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Update Priority
# ==========================================
@tickets_bp.route('/ticket/update-priority/<int:ticket_id>', methods=['POST'])
def update_ticket_priority(ticket_id):
    new_priority = request.form.get('new_priority')
    if new_priority not in VALID_PRIORITIES:
        flash("Invalid priority."); return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT priority, created_at FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            flash("Ticket not found."); return redirect(url_for('tickets.tickets'))
        old_priority = row[0]
        if is_local():
            try:
                created_dt = datetime.datetime.fromisoformat(str(row[1]))
            except:
                created_dt = datetime.datetime.now()
            new_sla = (created_dt + datetime.timedelta(hours=SLA_HOURS[new_priority])).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(f"UPDATE support_tickets SET priority = {p}, sla_due_at = {p}, updated_at = datetime('now') WHERE id = {p}",
                          (new_priority, new_sla, ticket_id))
        else:
            cursor.execute(f"UPDATE support_tickets SET priority = %s, sla_due_at = created_at + INTERVAL '%s hours', updated_at = NOW() WHERE id = %s",
                          (new_priority, SLA_HOURS[new_priority], ticket_id))
        agent = AGENTS[ticket_id % len(AGENTS)]
        log_activity(cursor, ticket_id, 'state_change',
                     f'Priority changed from {old_priority} ({PRIORITY_LABELS.get(old_priority, "")}) to {new_priority} ({PRIORITY_LABELS[new_priority]}).',
                     author=agent, old_value=old_priority, new_value=new_priority)
        conn.commit(); cursor.close(); conn.close()
        flash(f"Priority updated to {new_priority} ({PRIORITY_LABELS[new_priority]}).")
    except Exception as e:
        flash(f"Error updating priority: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Assign Team/Agent
# ==========================================
@tickets_bp.route('/ticket/assign/<int:ticket_id>', methods=['POST'])
def assign_ticket(ticket_id):
    new_team = request.form.get('assigned_team')
    new_agent = request.form.get('assigned_agent')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT assigned_team, assigned_agent FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            flash("Ticket not found."); return redirect(url_for('tickets.tickets'))
        old_team, old_agent = row[0], row[1]
        cursor.execute(f"UPDATE support_tickets SET assigned_team = {p}, assigned_agent = {p}, updated_at = {now_sql()} WHERE id = {p}",
                      (new_team, new_agent, ticket_id))
        agent = AGENTS[ticket_id % len(AGENTS)]
        changes = []
        if old_team != new_team:
            changes.append(f'Team: {old_team or "Unassigned"} -> {new_team}')
        if old_agent != new_agent:
            changes.append(f'Agent: {old_agent or "Unassigned"} -> {new_agent}')
        if changes:
            log_activity(cursor, ticket_id, 'assignment', 'Assignment updated. ' + '. '.join(changes),
                        author=agent, old_value=old_team, new_value=new_team)
        conn.commit(); cursor.close(); conn.close()
        flash("Assignment updated.")
    except Exception as e:
        flash(f"Error updating assignment: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Escalate
# ==========================================
@tickets_bp.route('/ticket/escalate/<int:ticket_id>', methods=['POST'])
def escalate_ticket(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT escalation_level, priority FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            flash("Ticket not found."); return redirect(url_for('tickets.tickets'))
        old_level = row[0] or 0
        current_priority = row[1]
        new_level = min(old_level + 1, 2)
        updates = [f"escalation_level = {p}", f"updated_at = {now_sql()}"]
        params = [new_level]
        new_priority = current_priority
        if new_level >= 1 and current_priority in ('P3', 'P4'):
            new_priority = 'P2'; updates.append(f"priority = {p}"); params.append(new_priority)
        elif new_level >= 2 and current_priority != 'P1':
            new_priority = 'P1'; updates.append(f"priority = {p}"); params.append(new_priority)
        if new_level >= 2:
            updates.append(f"assigned_team = {p}"); params.append('Management Escalation')
        update_sql = ", ".join(updates)
        params.append(ticket_id)
        cursor.execute(f"UPDATE support_tickets SET {update_sql} WHERE id = {p}", tuple(params))
        level_labels = {0: 'Normal', 1: 'Escalated', 2: 'Management'}
        agent = AGENTS[ticket_id % len(AGENTS)]
        content = f'Ticket escalated from {level_labels[old_level]} to {level_labels[new_level]}.'
        if new_priority != current_priority:
            content += f' Priority auto-bumped to {new_priority}.'
        if new_level >= 2:
            content += ' Reassigned to Management Escalation.'
        log_activity(cursor, ticket_id, 'escalation', content, author=agent, old_value=str(old_level), new_value=str(new_level))
        conn.commit(); cursor.close(); conn.close()
        flash(f"Ticket escalated to {level_labels[new_level]} level.")
    except Exception as e:
        flash(f"Error escalating ticket: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Add Work Note
# ==========================================
@tickets_bp.route('/ticket/<int:ticket_id>/note', methods=['POST'])
def add_work_note(ticket_id):
    content = request.form.get('note_content', '').strip()
    author = request.form.get('author', 'Agent Smith')
    if not content:
        flash("Work note cannot be empty."); return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT id FROM support_tickets WHERE id = {p}", (ticket_id,))
        if not cursor.fetchone():
            flash("Ticket not found."); return redirect(url_for('tickets.tickets'))
        log_activity(cursor, ticket_id, 'work_note', content, author=author)
        cursor.execute(f"UPDATE support_tickets SET updated_at = {now_sql()} WHERE id = {p}", (ticket_id,))
        conn.commit(); cursor.close(); conn.close()
        flash("Work note added.")
    except Exception as e:
        flash(f"Error adding work note: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Close Ticket
# ==========================================
@tickets_bp.route('/ticket/close/<int:ticket_id>', methods=['POST'])
def close_ticket(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT ticket_status FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        old_status = row[0] if row else 'Unknown'
        cursor.execute(f"UPDATE support_tickets SET ticket_status = 'Closed', closed_at = {now_sql()}, updated_at = {now_sql()} WHERE id = {p}", (ticket_id,))
        agent = AGENTS[ticket_id % len(AGENTS)]
        log_activity(cursor, ticket_id, 'state_change', f'Status changed from {old_status} to Closed.', author=agent, old_value=old_status, new_value='Closed')
        conn.commit()
        cursor.execute(f"SELECT bag_tag FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        cursor.close(); conn.close()
        flash("Ticket closed.")
        referrer = request.form.get('redirect_to', '')
        if referrer == 'tickets':
            return redirect(url_for('tickets.tickets'))
        elif row:
            return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
        return redirect(url_for('tickets.tickets'))
    except Exception as e:
        flash(f"Error managing ticket: {str(e)}")
        return redirect(url_for('tickets.tickets'))


# ==========================================
# Resolve Ticket
# ==========================================
@tickets_bp.route('/ticket/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    resolution_notes = request.form.get('resolution_notes', '').strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        cursor.execute(f"SELECT ticket_status FROM support_tickets WHERE id = {p}", (ticket_id,))
        row = cursor.fetchone()
        old_status = row[0] if row else 'Unknown'
        cursor.execute(f"UPDATE support_tickets SET ticket_status = 'Resolved', resolution_notes = {p}, resolved_at = {now_sql()}, updated_at = {now_sql()} WHERE id = {p}",
                      (resolution_notes, ticket_id))
        agent = AGENTS[ticket_id % len(AGENTS)]
        content = f'Status changed from {old_status} to Resolved.'
        if resolution_notes:
            content += f' Resolution: {resolution_notes}'
        log_activity(cursor, ticket_id, 'state_change', content, author=agent, old_value=old_status, new_value='Resolved')
        conn.commit(); cursor.close(); conn.close()
        flash("Ticket resolved.")
    except Exception as e:
        flash(f"Error resolving ticket: {str(e)}")
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ==========================================
# Bulk Actions
# ==========================================
@tickets_bp.route('/tickets/bulk-action', methods=['POST'])
def bulk_ticket_action():
    action = request.form.get('bulk_action')
    ticket_ids = request.form.getlist('ticket_ids')
    if not ticket_ids:
        flash("No tickets selected."); return redirect(url_for('tickets.tickets'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        p = param()
        count = 0
        for tid_str in ticket_ids:
            tid = int(tid_str)
            if action == 'close':
                cursor.execute(f"SELECT ticket_status FROM support_tickets WHERE id = {p}", (tid,))
                row = cursor.fetchone()
                old_status = row[0] if row else 'Unknown'
                cursor.execute(f"UPDATE support_tickets SET ticket_status = 'Closed', closed_at = {now_sql()}, updated_at = {now_sql()} WHERE id = {p}", (tid,))
                log_activity(cursor, tid, 'state_change', f'Bulk close: {old_status} -> Closed.', author='System')
                count += 1
            elif action == 'assign':
                team = request.form.get('bulk_team', 'Customer Relations')
                cursor.execute(f"UPDATE support_tickets SET assigned_team = {p}, updated_at = {now_sql()} WHERE id = {p}", (team, tid))
                log_activity(cursor, tid, 'assignment', f'Bulk assignment to {team}.', author='System')
                count += 1
            elif action == 'priority':
                new_pri = request.form.get('bulk_priority', 'P3')
                if new_pri in VALID_PRIORITIES:
                    cursor.execute(f"UPDATE support_tickets SET priority = {p}, updated_at = {now_sql()} WHERE id = {p}", (new_pri, tid))
                    log_activity(cursor, tid, 'state_change', f'Bulk priority change to {new_pri}.', author='System')
                    count += 1
        conn.commit(); cursor.close(); conn.close()
        flash(f"Bulk action '{action}' applied to {count} tickets.")
    except Exception as e:
        flash(f"Error in bulk action: {str(e)}")
    return redirect(url_for('tickets.tickets'))
