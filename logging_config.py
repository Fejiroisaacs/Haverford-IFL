import logging
import json
import queue
import threading
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any
import random
from firebase_admin import db as firebase_db

# Configure logging to console (for Koyeb)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

# Check if we're in production (Koyeb sets this env var)
IS_PRODUCTION = os.getenv('KOYEB_PUBLIC_DOMAIN') is not None or os.getenv('ENVIRONMENT') == 'production'

# Background queue for async Firebase writes
log_queue = queue.Queue(maxsize=1000)
SAMPLE_RATE = 0.2  # Sample 20% of requests for detailed logs
CLEANUP_DAYS = 30  # Delete logs older than 30 days

class FirebaseLogger:
    """Handles Firebase logging with background processing"""

    def __init__(self):
        self.db_ref = None
        self.running = True
        self.last_cleanup = datetime.now()
        if IS_PRODUCTION:
            self._start_worker()
            logger.info("Firebase logger background worker started (PRODUCTION MODE)")
        else:
            logger.info("Firebase logging DISABLED (LOCAL DEVELOPMENT MODE)")

    def _start_worker(self):
        """Start background thread for processing log queue"""
        worker = threading.Thread(target=self._process_queue, daemon=True)
        worker.start()
        logger.info("Firebase logger background worker started")

    def _process_queue(self):
        """Process log entries from queue in background"""
        while self.running:
            try:
                # Get log entry with timeout
                log_entry = log_queue.get(timeout=1)
                self._write_to_firebase(log_entry)
                log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing log queue: {e}")

        logger.info("Firebase logger worker stopped")

    def _write_to_firebase(self, log_entry: Dict[str, Any]):
        """Write log entry to Firebase (only in production)"""
        if not IS_PRODUCTION:
            return  # Skip Firebase writes in local development

        try:
            if self.db_ref is None:
                self.db_ref = firebase_db.reference('/analytics')

            log_type = log_entry.pop('log_type', 'request')

            if log_type == 'counter':
                # Aggregate counter (increment)
                counter_path = log_entry.get('path')
                increment = log_entry.get('increment', 1)
                ref = self.db_ref.child(counter_path)
                current = ref.get() or 0
                ref.set(current + increment)

            elif log_type == 'detailed':
                # Detailed log entry (sampled requests)
                date_key = datetime.now().strftime('%Y-%m-%d')
                self.db_ref.child(f'detailed_logs/{date_key}').push(log_entry)

            elif log_type == 'error':
                # Error tracking
                self.db_ref.child('errors').push(log_entry)

            # Periodic cleanup
            # self._cleanup_old_logs()

        except Exception as e:
            logger.error(f"Failed to write to Firebase: {e}")

    def _cleanup_old_logs(self):
        """Remove logs older than CLEANUP_DAYS"""
        try:
            now = datetime.now()
            # Only run cleanup once per day
            if (now - self.last_cleanup).days < 1:
                return

            self.last_cleanup = now
            cutoff_date = (now - timedelta(days=CLEANUP_DAYS)).strftime('%Y-%m-%d')

            if self.db_ref is None:
                return

            # Get all detailed log dates
            detailed_ref = self.db_ref.child('detailed_logs')
            logs = detailed_ref.get() or {}

            for date_key in logs.keys():
                if date_key < cutoff_date:
                    detailed_ref.child(date_key).delete()
                    logger.info(f"Cleaned up logs from {date_key}")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def stop(self):
        """Stop the background worker"""
        self.running = False

# Global logger instance
firebase_logger = FirebaseLogger()

def log_request(request_data: Dict[str, Any]):
    """
    Queue a request for logging

    Args:
        request_data: Dictionary with request information
    """
    try:
        route = request_data.get('route', '')
        method = request_data.get('method', '')
        status_code = request_data.get('status_code', 0)
        response_time = request_data.get('response_time_ms', 0)
        ip = request_data.get('ip', 'unknown')

        # Skip static files
        if '/static' in route:
            return

        # Console logging (always, both dev and production)
        env_tag = "[DEV]" if not IS_PRODUCTION else ""
        log_msg = f"{env_tag} {method} {route} | {ip} | {response_time}ms | {status_code}".strip()

        if status_code >= 500:
            logger.error(log_msg)
        elif status_code >= 400:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Firebase: Only log in production (skip in local dev)
        if IS_PRODUCTION:
            # Always update aggregate counters
            _log_aggregate_counters(request_data)

            # Sample detailed logs (20% of requests)
            if random.random() < SAMPLE_RATE:
                _log_detailed(request_data)

            # Always log errors
            if status_code >= 400:
                _log_error(request_data)

    except Exception as e:
        logger.error(f"Error in log_request: {e}")

def _log_aggregate_counters(request_data: Dict[str, Any]):
    """Update aggregate counters for analytics"""
    try:
        route = request_data.get('route', '')

        # Daily request counter
        date_key = datetime.now().strftime('%Y-%m-%d')
        log_queue.put({
            'log_type': 'counter',
            'path': f'daily_stats/{date_key}/total_requests',
            'increment': 1
        })

        # Route-specific counters
        if route.startswith('/players/') and len(route) > 9:
            player_name = route.replace('/players/', '').split('?')[0]
            log_queue.put({
                'log_type': 'counter',
                'path': f'player_views/{player_name}',
                'increment': 1
            })

        elif route.startswith('/teams/') and len(route) > 7:
            parts = route.replace('/teams/', '').split('/')
            
            # Case 1: /teams/<team_name>
            if len(parts) == 1:
                team_name = parts[0].split('?')[0]
                log_queue.put({
                    'log_type': 'counter',
                    'path': f'team_views/{team_name}',
                    'increment': 1
                })

            # Case 2: /teams/<team_name>/<match_id>
            elif len(parts) == 2:
                team_name = parts[0]
                match_id = parts[1].split('?')[0]
                log_queue.put({
                    'log_type': 'counter',
                    'path': f'match_views/{team_name}/{match_id}',
                    'increment': 1
                })


        elif route == '/players':
            log_queue.put({
                'log_type': 'counter',
                'path': 'page_views/players',
                'increment': 1
            })

        elif route == '/teams':
            log_queue.put({
                'log_type': 'counter',
                'path': 'page_views/teams',
                'increment': 1
            })

        elif route == '/matches':
            log_queue.put({
                'log_type': 'counter',
                'path': 'page_views/matches',
                'increment': 1
            })

        elif route.startswith('/player_search'):
            log_queue.put({
                'log_type': 'counter',
                'path': 'page_views/player_search',
                'increment': 1
            })
        elif route.startswith('/api/match-preview'):
            params = request_data.get('query_params', {})

            team1 = params.get('team1', 'unknown')
            team2 = params.get('team2', 'unknown')
            matchday = params.get('matchday', 'unknown')

            log_queue.put({
                'log_type': 'counter',
                'path': f'match_preview_views/{team1}/{team1}-{team2}-{matchday}',
                'increment': 1
            })

        else:
            # Aggregate all other page visits (home, statistics, hall-of-fame, archives, gallery, contact, etc.)
            # Exclude static files, API endpoints, and health checks
            if not route.startswith('/static') and not route.startswith('/api/') and route != '/health':
                log_queue.put({
                    'log_type': 'counter',
                    'path': 'page_views/other_page_visits',
                    'increment': 1
                })

    except Exception as e:
        logger.error(f"Error logging counters: {e}")

def _log_detailed(request_data: Dict[str, Any]):
    """Log detailed request information (sampled)"""
    try:
        log_entry = {
            'log_type': 'detailed',
            'timestamp': datetime.now().isoformat(),
            'route': request_data.get('route'),
            'method': request_data.get('method'),
            'status_code': request_data.get('status_code'),
            'response_time_ms': request_data.get('response_time_ms'),
            'ip': request_data.get('ip'),
            'user_agent': request_data.get('user_agent', '')[:200],  # Truncate
            'query_params': request_data.get('query_params', {})
        }
        log_queue.put(log_entry)

    except Exception as e:
        logger.error(f"Error logging detailed: {e}")

def _log_error(request_data: Dict[str, Any]):
    """Log error-specific information"""
    try:
        error_entry = {
            'log_type': 'error',
            'timestamp': datetime.now().isoformat(),
            'route': request_data.get('route'),
            'method': request_data.get('method'),
            'status_code': request_data.get('status_code'),
            'ip': request_data.get('ip'),
            'user_agent': request_data.get('user_agent', '')[:200],
            'error_details': request_data.get('error_details', '')
        }
        log_queue.put(error_entry)

    except Exception as e:
        logger.error(f"Error logging error: {e}")

def get_analytics_summary():
    """
    Retrieve analytics summary from Firebase (only in production)

    Returns:
        Dict with analytics data
    """
    if not IS_PRODUCTION:
        logger.info("Analytics not available in local development mode")
        return {}

    try:
        db_ref = firebase_db.reference('/analytics')

        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')

        return {
            'daily_stats': db_ref.child('daily_stats').get() or {},
            'player_views': db_ref.child('player_views').order_by_value().limit_to_last(10).get() or {},
            'team_views': db_ref.child('team_views').order_by_value().limit_to_last(10).get() or {},
            'page_views': db_ref.child('page_views').get() or {},
            'error_count': len(db_ref.child('errors').get() or {})
        }

    except Exception as e:
        logger.error(f"Error retrieving analytics: {e}")
        return {}
