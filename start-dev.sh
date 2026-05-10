#!/usr/bin/env bash
# Start both backend and frontend in development mode.
# Usage: bash start-dev.sh
set -euo pipefail

G="\033[92m"; Y="\033[93m"; B="\033[94m"; BOLD="\033[1m"; RST="\033[0m"

echo -e "${BOLD}${B}  NewsDispatch — Development Mode${RST}"
echo -e "  API:      http://localhost:8000"
echo -e "  Frontend: http://localhost:5173"
echo -e "  API docs: http://localhost:8000/docs"
echo -e "  SSE:      http://localhost:8000/api/v1/events"
echo ""

cleanup() { kill 0; }
trap cleanup SIGINT SIGTERM

# Backend
cd backend
source .venv/bin/activate
uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload \
  --log-level info &
BACKEND_PID=$!
echo -e "${G}✔${RST}  Backend PID $BACKEND_PID"
cd ..

# Frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
echo -e "${G}✔${RST}  Frontend PID $FRONTEND_PID"
cd ..

echo ""
echo -e "  Press Ctrl+C to stop both services."
wait
