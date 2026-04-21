# Pro-IDE (VSCode/Cursor-style Web IDE)

A web-based IDE rebuild of ProDA with **FastAPI** backend + **React + TypeScript + Vite** frontend. Looks and feels like VSCode / Cursor.

> The original Streamlit app under `ui/` still works (`streamlit run ui/streamlit_app.py`). The new IDE UI lives in `backend/` and `frontend/`.

## Architecture

```
Pro-IDE/
├── proda/           # Existing Python business logic (reused as-is)
├── backend/         # NEW FastAPI wrapper
│   ├── main.py
│   └── api/
│       ├── health.py
│       ├── projects.py
│       ├── llm.py
│       └── workspace.py
├── frontend/        # NEW React + Vite + Tailwind IDE shell
│   └── src/
│       ├── components/ide/   # TitleBar, ActivityBar, Explorer, TabBar,
│       │                     # StatusBar, CommandPalette, IdeShell,
│       │                     # EditorArea, BottomPanel
│       ├── components/modals/
│       ├── pages/            # Welcome, Placeholder, LlmConfigPage
│       ├── api/              # axios client + endpoints
│       ├── store/            # zustand session store
│       ├── hooks/            # useI18n, usePageLabels
│       ├── lib/              # i18n, workflow definitions
│       └── styles/globals.css
└── ui/              # Legacy Streamlit UI (kept for now)
```

## Prerequisites

- Python 3.10+ (3.12 tested) with `fastapi` + `uvicorn` installed (already in `requirements.txt`)
- Node.js 22+ and npm 10+
- Tested on Windows 11

## One-time setup

```bash
# Python deps (if not already installed)
pip install fastapi uvicorn

# Frontend deps
cd frontend
npm install
```

## Run in development

Open **two terminals**.

**Terminal 1 — backend** (port `8001`, because `8000` is often used by Cursor / other tools):

```bash
# from repo root
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 — frontend** (Vite dev on `5173`, proxies `/api/*` → `:8001`):

```bash
cd frontend
npm run dev
```

Then open <http://localhost:5173>.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+P` | Open command palette |
| `Ctrl+P` | Quick open (alias of palette) |
| `Ctrl+B` | Toggle sidebar (Explorer) |

## IDE layout

```
┌──────────────────────────────────────────────────────┐
│ Title bar (menus · project · model · config · lang)  │ 35px
├──┬─────────────┬────────────────────────────────────┤
│A │ Explorer    │ ┌ Tab bar                        ─┐ │
│c │  · Current  │ │ welcome.md × │ 1_extract.py ×  │ │  35px
│t │  · Workflow │ └─────────────────────────────────┘ │
│i │  · Recent   │                                     │
│v │             │    Editor area (active tab)         │
│i │             │                                     │
│t │             │                                     │
│y │             ├─────────────────────────────────────┤
│  │             │ Bottom panel (PROBLEMS · OUTPUT ·   │
│  │             │ TERMINAL · PORTS)                   │
├──┴─────────────┴─────────────────────────────────────┤
│ Status bar (conn · branch · project · model · lang)  │ 22px
└──────────────────────────────────────────────────────┘
```

- **Activity bar** (48px, left): switch between Explorer / Workflow / Search views and open settings.
- **Explorer** (resizable): project tree + workflow step list (click to open as tab) + recent projects.
- **Tabs**: each workflow step opens as a pseudo-file (`1_data_processing.py`, `2_benchmark.py`, …). Close, reorder visually, keep Welcome pinned.
- **Bottom panel** (resizable): live connection log + process ports.
- **Status bar**: VSCode blue when backend is reachable, red otherwise.

## Backend endpoints

All under `/api`. Swagger UI at <http://localhost:8001/docs>.

```
GET    /api/health
GET    /api/projects
POST   /api/projects              { name, description }
GET    /api/projects/{id}
PUT    /api/projects/{id}         { name, description }
DELETE /api/projects/{id}
POST   /api/projects/{id}/open
PUT    /api/projects/{id}/state   { state }

GET    /api/llm/defaults
POST   /api/llm/test              { provider, api_key, api_base, model_name }
POST   /api/llm/normalize         { profiles }
POST   /api/llm/options           { profiles }
POST   /api/llm/parse             { key }

GET    /api/workspace/{id}/tree
```

## What's already migrated

- **Project management**: create / list / open / rename / delete — full CRUD backed by `.proda_projects/`.
- **LLM configuration modal**: test connection + save verified models (reuses `ui/utils/llm_config.py`).
- **i18n (zh / en)**: built-in translations, toggle in title bar or status bar.
- **VSCode Dark+ theme**: Tailwind palette matches official VSCode colors. Font stack defaults to Segoe UI → Cascadia Code for mono.
- **Welcome page**: mirrors VSCode / Cursor welcome tab.

## What's still placeholder (Phase 2+)

Each of the 6 workflow steps currently shows a "coming soon" panel listing the features to port from Streamlit:

1. **Data Processing** — document upload + L1/L2/L3 extraction
2. **Benchmark Generation** — MCQ from L3 chains
3. **FineTune Generation** — SFT data + diagnosis mode
4. **Fine-Tuning** — LLaMA-Factory integration + live training logs
5. **OpenCompass Evaluation** — local/API eval + leaderboard
6. **Results** — aggregated dashboard

Migration order follows user priority. Each page will be a full-featured React component backed by additional FastAPI endpoints (with WebSocket streaming for long-running jobs).

## Production build

```bash
cd frontend
npm run build        # outputs frontend/dist
npm run preview      # serve the build on port 4173
```

The backend can be fronted by any ASGI server (uvicorn / gunicorn+uvicorn workers). The built frontend can be served as static files by nginx, or mounted directly via FastAPI `StaticFiles`.

## Notes on the Streamlit → IDE migration

- All existing Python logic (`proda/*`, `ui/utils/project_store.py`, `ui/utils/llm_config.py`) is reused unchanged — the FastAPI layer is a thin wrapper.
- Streamlit's `session_state` → Zustand store (persists to `localStorage` so the language + LLM config survive reloads).
- Streamlit's rerun model is gone — UI updates are driven by React state, not a full script rerun. Typing, scrolling, and tab switching no longer trigger backend calls.
