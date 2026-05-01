"""
Ticket Microservice
===================
Owns: support_tickets, ticket_activity tables
Responsibility: Ticket lifecycle, SLA management, escalation, work notes
"""

from flask import Blueprint

tickets_bp = Blueprint('tickets', __name__)

from services.tickets import routes, api  # noqa: E402, F401
