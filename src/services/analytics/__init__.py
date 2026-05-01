"""
Analytics Microservice
======================
Owns: No tables (pure aggregation service)
Responsibility: Dashboard, KPI metrics, stats API
Composes data by calling Luggage and Ticket Service APIs.
"""

from flask import Blueprint

analytics_bp = Blueprint('analytics', __name__)

from services.analytics import routes  # noqa: E402, F401
