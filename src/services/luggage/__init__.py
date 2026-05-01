"""
Luggage Microservice
====================
Owns: luggage_records, luggage_events tables
Responsibility: Bag CRUD, search, event timeline, luggage data APIs
"""

from flask import Blueprint

luggage_bp = Blueprint('luggage', __name__)

from services.luggage import routes, api  # noqa: E402, F401
