#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Parfums Price Comparator — Local startup script
# Starts: PostgreSQL · FastAPI backend · Next.js frontend
#
# Postgres strategy (auto-detected):
#   1. Docker   — preferred, zero local setup
#   2. Homebrew — brew install postgresql@16
#   3. Native   — any pg_ctl already on PATH
#
# Usage:  bash start.sh
# ─────────────────────────────────────────────────────────────
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 1. Check common prerequisites ────────────────────────────
command -v python3 >/dev/null 2>&1 || error "Python 3 not found. Install from https://python.org"
command -v npm     >/dev/null 2>&1 || error "Node/npm not found. Install from https://nodejs.org"

# ── 2. Create .env if missing ────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn ".env created from .env.example — review ADMIN_TOKEN before production use."
fi

DB_URL="postgresql+psycopg://parfums:parfums@localhost:5432/parfums"

# ── 3. PostgreSQL — Docker → Homebrew → native fallback ──────
POSTGRES_MODE=""

start_postgres_docker() {
  info "Starting PostgreSQL via Docker..."
  docker run -d --name parfums-postgres \
    -e POSTGRES_USER=parfums \
    -e POSTGRES_PASSWORD=parfums \
    -e POSTGRES_DB=parfums \
    -p 5432:5432 \
    --health-cmd="pg_isready -U parfums" \
    --health-interval=3s \
    --health-timeout=3s \
    --health-retries=10 \
    postgres:16 2>/dev/null || \
    docker start parfums-postgres 2>/dev/null || true

  info "Waiting for Postgres (Docker)..."
  for i in $(seq 1 20); do
    docker exec parfums-postgres pg_isready -U parfums -q 2>/dev/null && return 0
    sleep 1
  done
  return 1
}

start_postgres_brew() {
  # Find the Homebrew pg_ctl (supports multiple PG versions)
  BREW_PG=$(ls /usr/local/opt/postgresql*/bin/pg_ctl 2>/dev/null | tail -1 || \
            ls /opt/homebrew/opt/postgresql*/bin/pg_ctl 2>/dev/null | tail -1 || true)
  [ -z "$BREW_PG" ] && return 1

  BREW_PG_BIN="$(dirname "$BREW_PG")"
  info "Starting PostgreSQL via Homebrew ($BREW_PG_BIN)..."
  "$BREW_PG" start 2>/dev/null || true
  sleep 3

  # Ensure DB + user exist
  "$BREW_PG_BIN/createuser" --superuser parfums 2>/dev/null || true
  "$BREW_PG_BIN/createdb"   -U parfums parfums  2>/dev/null || true

  "$BREW_PG_BIN/pg_isready" -U parfums -d parfums -q 2>/dev/null && return 0
  return 1
}

start_postgres_native() {
  command -v pg_ctl >/dev/null 2>&1 || return 1
  info "Starting PostgreSQL via native pg_ctl..."
  pg_ctl start 2>/dev/null || true
  sleep 3

  createuser --superuser parfums 2>/dev/null || true
  createdb   -U parfums parfums  2>/dev/null || true

  pg_isready -U parfums -d parfums -q 2>/dev/null && return 0
  return 1
}

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  start_postgres_docker && POSTGRES_MODE="docker" || warn "Docker Postgres failed, trying Homebrew..."
fi

if [ -z "$POSTGRES_MODE" ]; then
  start_postgres_brew && POSTGRES_MODE="brew" || warn "Homebrew Postgres failed, trying native..."
fi

if [ -z "$POSTGRES_MODE" ]; then
  start_postgres_native && POSTGRES_MODE="native" || true
fi

if [ -z "$POSTGRES_MODE" ]; then
  error "Could not start PostgreSQL. Please install one of:
  • Docker Desktop  https://docker.com
  • Homebrew Postgres: brew install postgresql@16
  • Postgres.app     https://postgresapp.com"
fi

info "Postgres is ready (mode: $POSTGRES_MODE)."

# ── 4. Backend: venv + deps + migrate + run ──────────────────
cd "$ROOT/backend"

if [ ! -d .venv ]; then
  info "Creating Python virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate

info "Installing Python dependencies..."
pip install -e ".[dev]" -q

info "Running database migrations..."
DATABASE_URL="$DB_URL" alembic upgrade head

info "Starting FastAPI backend on http://localhost:8000 ..."
DATABASE_URL="$DB_URL" \
ADMIN_TOKEN="change-me" \
CORS_ORIGINS="http://localhost:3000" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

info "Waiting for backend to be healthy..."
for i in $(seq 1 20); do
  curl -s http://localhost:8000/api/health | grep -q '"status":"ok"' && break
  sleep 1
done
curl -s http://localhost:8000/api/health | grep -q '"status":"ok"' \
  || error "Backend did not start — check backend logs above."
info "Backend is up → http://localhost:8000  (docs: http://localhost:8000/docs)"

# ── 5. Frontend: npm deps + dev server ───────────────────────
cd "$ROOT/web"

# Detect stale node_modules built on a different platform (e.g. Linux sandbox →
# Mac). lightningcss and other native addons ship platform-specific .node binaries;
# if the installed ones don't match the current OS/arch, nuke and reinstall.
NEED_INSTALL=false
if [ ! -d node_modules ]; then
  NEED_INSTALL=true
elif [ -d node_modules/lightningcss ]; then
  # Check if the darwin-arm64 native binary exists for this Mac
  if ! ls node_modules/lightningcss/lightningcss.darwin-arm64.node \
          node_modules/lightningcss/lightningcss.darwin-x64.node 2>/dev/null | grep -q .; then
    warn "node_modules has wrong platform binaries — reinstalling for this Mac..."
    rm -rf node_modules .next
    NEED_INSTALL=true
  fi
fi

if [ "$NEED_INSTALL" = true ]; then
  info "Installing npm dependencies..."
  npm install
fi

info "Starting Next.js frontend on http://localhost:3000 ..."
NEXT_PUBLIC_API_URL="http://localhost:8000" \
NEXT_PUBLIC_USE_MOCK="false" \
  npm run dev &
FRONTEND_PID=$!

sleep 5
info "Frontend is up → http://localhost:3000"

# ── 6. Summary ───────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Parfums Price Comparator is running!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "  Frontend   →  http://localhost:3000"
echo -e "  API        →  http://localhost:8000"
echo -e "  API docs   →  http://localhost:8000/docs"
echo -e "  Admin tok  →  change-me"
echo -e "  Postgres   →  $POSTGRES_MODE"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop everything."
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""

# ── 7. Cleanup on exit ───────────────────────────────────────
cleanup() {
  echo ""
  warn "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  if [ "$POSTGRES_MODE" = "docker" ]; then
    warn "Stopping Postgres container..."
    docker stop parfums-postgres 2>/dev/null || true
  fi
  info "Done. Goodbye!"
}
trap cleanup INT TERM

wait $BACKEND_PID $FRONTEND_PID
