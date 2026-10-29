# BodhCode

BodhCode turns public GitHub repositories (TypeScript / JavaScript) into interactive dependency maps, translates context into your native language, enables in-browser code editing with an AI coding agent, and pushes verified changes back to GitHub.

## Prerequisites

- **Python**: 3.12+
- **Node.js**: 20+
- **Package Managers**: `uv` (Python) and `pnpm` (Node.js)
- **Git**

## Quick Start

### 1. Backend

Navigate to `backend`, configure environment, synchronize dependencies, and start the development server:

```bash
cd backend
# Copy example environment file if you haven't already:
# cp .env.example .env (and configure required variables)
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Backend API will be running at [http://localhost:8000](http://localhost:8000).  
Interactive documentation available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Frontend


Navigate to `frontend`, configure environment, install dependencies, and launch Vite dev server:

```bash
cd frontend
# Copy example environment file if you haven't already:
# cp .env.example .env (and set VITE_API_URL=http://localhost:8000)
pnpm install
pnpm dev
```

Frontend application will be accessible at [http://localhost:5173](http://localhost:5173).

## Testing

Run tests on each side of the stack:

```bash
# Backend tests (run from backend directory)
cd backend && uv run pytest

# Frontend tests (run from frontend directory)
cd frontend && pnpm test
```

## Linting & Formatting

Enforce style, quality, and type standards:

```bash
# Backend lint check (run from backend directory)
cd backend && uv run ruff check .

# Frontend lint check (run from frontend directory)
cd frontend && pnpm lint
```
