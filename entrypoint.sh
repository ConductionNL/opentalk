#!/bin/bash
set -e

# Start the FastAPI wrapper for AppAPI communication
echo "Starting OpenTalk ExApp wrapper..."
exec python3 -m uvicorn ex_app.lib.main:app --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-9000}"
