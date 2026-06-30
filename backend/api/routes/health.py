from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__)

@health_bp.route('/status', methods=['GET'])
def health_status():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'healthy',
        'service': 'day-trading-bot-api',
        'version': '1.0.0'
    }), 200
