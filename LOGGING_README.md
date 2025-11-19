# Logging System Documentation

## Overview

This application uses a two-tier logging system optimized for Koyeb deployment:

1. **Console Logging** - All requests logged to stdout (viewable in Koyeb dashboard)
2. **Firebase Analytics** - Aggregate metrics and sampled detailed logs stored in Firebase (**PRODUCTION ONLY**)

## Environment Detection

The system automatically detects whether it's running in production or local development:

- **Production** (Koyeb): Full logging to console + Firebase analytics
- **Local Development**: Console logging only, Firebase writes are DISABLED

This prevents test data from polluting your production analytics.

**Detection Logic:**
- Checks for `KOYEB_PUBLIC_DOMAIN` environment variable (auto-set by Koyeb)
- OR checks for `ENVIRONMENT=production` environment variable

## System Components

### 1. `logging_config.py`
- Configures logging format and handlers
- Manages background queue for async Firebase writes
- Handles aggregate counters and cleanup

### 2. `middleware.py`
- `RequestLoggingMiddleware` - Captures all HTTP requests
- Tracks response times, status codes, IPs, user agents
- Non-blocking Firebase writes (<1ms overhead per request)

### 3. `app.py` Integration
- Middleware automatically tracks all routes
- No changes needed to existing route handlers

## What Gets Logged

### Console (100% of requests)
Every request is logged to stdout in this format:

**Local Development:**
```
2025-11-10 14:56:13 | INFO | [DEV] GET /players | 192.168.1.xxx | 203ms | 200
2025-11-10 14:56:14 | WARNING | [DEV] GET /invalid | 192.168.1.xxx | 45ms | 404
```

**Production (Koyeb):**
```
2025-11-10 14:48:25 | INFO | GET /players | 192.168.1.xxx | 203ms | 200
2025-11-10 14:48:26 | WARNING | GET /invalid | 192.168.1.xxx | 45ms | 404
```

Note the `[DEV]` tag in local development mode.

**View in Koyeb:**
- Go to your Koyeb app dashboard
- Click "Logs" tab
- See real-time request logs

### Firebase Analytics Structure

** Production Only** - Firebase writes are automatically disabled in local development.

```
/analytics
  /daily_stats
    /2025-11-10
      total_requests: 487
    /2025-11-11
      total_requests: 523

  /player_views
    /John%20Doe: 45
    /Jane%20Smith: 32
    /Mike%20Johnson: 28

  /team_views
    /TeamA: 67
    /TeamB: 54

  /page_views
    /players: 123
    /teams: 98
    /matches: 156
    /player_search: 34

  /detailed_logs
    /2025-11-10
      /{log_id}
        timestamp: "2025-11-10T14:32:15"
        route: "/players"
        method: "GET"
        status_code: 200
        response_time_ms: 203.1
        ip: "192.168.1.xxx"
        user_agent: "Mozilla/5.0..."
        query_params: {"session": "6"}

  /errors
    /{error_id}
      timestamp: "2025-11-10T14:35:22"
      route: "/players/Unknown"
      status_code: 404
      ip: "192.168.1.xxx"
      error_details: "Player not found"
```

## Performance Impact

- **Console logging**: ~0.5ms per request
- **Firebase writes**: <1-2ms per request (background queue)
- **Total overhead**: ~2-3ms per request
- **Firebase storage**: ~10-20 MB/month at 500 requests/day

## Privacy

- IP addresses are **anonymized** (last octet removed)
  - Example: `192.168.1.100` → `192.168.1.xxx`
- User agents truncated to 200 characters
- No sensitive data logged

## Data Retention

- **Console logs**: Retained by Koyeb (typically 7-30 days)
- **Firebase detailed logs**: Auto-deleted after 30 days
- **Firebase counters**: Kept indefinitely (aggregate data only)

## Viewing Analytics

### Option 1: Firebase Console
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Navigate to Realtime Database
4. Browse to `/analytics`

### Option 2: Programmatic Access
```python
from logging_config import get_analytics_summary

# Get analytics data
analytics = get_analytics_summary()

print(f"Today's requests: {analytics['daily_stats']}")
print(f"Top players: {analytics['player_views']}")
print(f"Top teams: {analytics['team_views']}")
```

## What's Being Tracked

### Automatic Counters (100% of requests)
- Daily total requests
- Player page views (by player name)
- Team page views (by team name)
- General page views (players list, teams list, matches)
- Search queries count

### Detailed Logs (20% sample)
- Route, method, status code
- Response time
- IP address (anonymized)
- User agent
- Query parameters

### Error Tracking (100% of errors)
- All 4xx and 5xx responses
- Error details
- Full request context

## Configuration

### Adjust Sample Rate
Edit `logging_config.py`:
```python
SAMPLE_RATE = 0.2  # 20% of requests - increase for more detail
```

### Adjust Cleanup Period
Edit `logging_config.py`:
```python
CLEANUP_DAYS = 30  # Keep logs for 30 days
```

### Skip Additional Routes
Edit `log_request()` in `logging_config.py`:
```python
# Skip static files
if '/static' in route or '/favicon.ico' in route:
    return
```

## Testing

### Local Development Testing
Run the test script to verify logging works:
```bash
python test_logging.py
```

This simulates various requests and shows console output. You should see:
- `Firebase logging DISABLED (LOCAL DEVELOPMENT MODE)` message
- `[DEV]` tags on all log entries
- No Firebase write errors
- Console logs working correctly

### Testing in Production
When you run your server locally with `uvicorn app:app --reload`:
- Console logs will show `[DEV]` tags
- Firebase writes are disabled
- All route requests are logged to console

When deployed to Koyeb:
- No `[DEV]` tags
- Firebase analytics are enabled
- Logs appear in Koyeb dashboard AND Firebase

## Monitoring in Production

### Koyeb Dashboard
1. Open your Koyeb app
2. Click "Logs"
3. Filter by:
   - `WARNING` - For client errors (404, etc.)
   - `ERROR` - For server errors (500, etc.)
   - Search by route (e.g., `/players`)

### Firebase Dashboard
- Check `/analytics/daily_stats` for daily request counts
- Check `/analytics/player_views` for most popular players
- Check `/analytics/errors` for recent errors

## Troubleshooting

### No Firebase Data
- Check that Firebase is initialized in app.py
- Verify Firebase database rules allow writes
- Check Koyeb logs for Firebase errors

### High Storage Usage
- Reduce `SAMPLE_RATE` (e.g., 0.1 = 10%)
- Decrease `CLEANUP_DAYS` (e.g., 14 days)
- Skip more routes (add to skip list)

### Slow Performance
- Background queue should keep overhead minimal
- Check `response_time_ms` in logs
- If needed, disable Firebase logging temporarily
