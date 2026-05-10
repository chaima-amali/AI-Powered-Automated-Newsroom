#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
# NewsDispatch — One-time setup script
# Run once after cloning / unzipping the project.
# ════════════════════════════════════════════════════════════
set -euo pipefail

G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[94m"; BOLD="\033[1m"; RST="\033[0m"
ok()   { echo -e "${G}✔${RST}  $*"; }
err()  { echo -e "${R}✘${RST}  $*"; }
info() { echo -e "${Y}▸${RST}  $*"; }
banner() { echo -e "\n${BOLD}${B}══════════════════════════════════════════${RST}"; echo -e "${BOLD}${B}  $*${RST}"; echo -e "${BOLD}${B}══════════════════════════════════════════${RST}"; }

# ── Check Python ─────────────────────────────────────────────
banner "1. Python check"
PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3 || true)
if [ -z "$PYTHON" ]; then err "Python 3.11+ required"; exit 1; fi
PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PYVER at $PYTHON"

# ── Backend virtualenv ────────────────────────────────────────
banner "2. Backend Python environment"
cd backend
if [ ! -d ".venv" ]; then
  info "Creating virtual environment…"
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
ok "Virtualenv active"

info "Installing Python dependencies (this may take a few minutes)…"
pip install --upgrade pip -q
pip install -r requirements.txt -q
ok "Python packages installed"

# ── .env ──────────────────────────────────────────────────────
banner "3. Environment config"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo -e "${Y}⚠${RST}  Created .env from .env.example"
  echo -e "   ${BOLD}Edit backend/.env and fill in DB_HOST, DB_USER, DB_PASSWORD, DB_NAME${RST}"
  echo -e "   Optionally add OPENROUTER_API_KEY or GROQ_API_KEY for LLM rewriting."
else
  ok ".env already exists"
fi

# ── DB schema ─────────────────────────────────────────────────
banner "4. Database schema"
if grep -q "DB_HOST=db\." .env 2>/dev/null; then
  echo -e "${Y}⚠${RST}  DB_HOST still has placeholder — edit .env before running schema."
  echo -e "   After editing, run:  psql \"\$DATABASE_URL\" -f db/schema.sql"
else
  info "Attempting to apply schema…"
  export $(grep -v '^#' .env | grep -E 'DB_' | xargs) 2>/dev/null || true
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" \
    -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" \
    -d "${DB_NAME:-postgres}" \
    -f db/schema.sql \
    --set ON_ERROR_STOP=off \
    2>&1 | grep -v "already exists" | head -30 || true
  ok "Schema applied (errors for existing tables are normal)"
fi

cd ..

# ── Frontend ──────────────────────────────────────────────────
banner "5. Frontend Node.js packages"
if ! command -v node &>/dev/null; then
  err "Node.js not found — install from https://nodejs.org (v18+)"
  exit 1
fi
ok "Node $(node -v)"

cd frontend
npm install --silent
ok "Frontend packages installed"
cd ..

# ── Media dir ─────────────────────────────────────────────────
banner "6. Media directory"
mkdir -p backend/media/images backend/logs
ok "backend/media/ and backend/logs/ created"

# ── Done ──────────────────────────────────────────────────────
banner "✅ Setup complete!"
echo ""
echo "  Next steps:"
echo ""
echo "  1.  Edit backend/.env — fill in DB_HOST, DB_PASSWORD, etc."
echo "  2.  Start the API:      cd backend && source .venv/bin/activate && uvicorn api_main:app --reload"
echo "  3.  Start the frontend: cd frontend && npm run dev"
echo "  4.  Open: http://localhost:5173"
echo "  5.  Run a pipeline: cd backend && source .venv/bin/activate && python main.py"
echo ""
echo "  Login: alex@newsdispatch.com / news1234"
echo ""
