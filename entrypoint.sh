#!/bin/sh
# Minimal web dyno — just a health-check endpoint so Heroku is happy.
# The actual work is done by Scheduler running: python3 langgraph-app/runner.py
set -e

PORT="${PORT:-8080}"
echo "Health-check server on PORT=$PORT"

exec python3 -c "
import http.server, os

port = int(os.environ.get('PORT', '${PORT}'))

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *a):
        pass

print(f'Listening on {port}')
http.server.HTTPServer(('0.0.0.0', port), H).serve_forever()
"
