"""Unified backend: composes the RL engine, narrative engine, and behavioral
simulator (three independently-built FastAPI services) into a single process.

Run from the repo root (so `backend`, `narrative_engine`, etc. are importable):

    uvicorn backend.gateway:app --reload --host 0.0.0.0 --port 8000

Every route from all three services is exposed unprefixed, exactly as each
service defines it (/recommendation/*, /health, /predict, /session/*,
/portal/*) -- this is what the frontend already expects at a single base URL.

Not named main.py: server/main.py is imported below as a bare top-level
module named `main`, so naming this file the same would self-collide.
"""
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT_DIR / "server"
NARRATIVE_DIR = ROOT_DIR / "narrative_engine"
BEHAVIORAL_DIR = ROOT_DIR / "behavioural-simulation" / "backend"

# Each service's own code calls load_dotenv() with no path, which walks up
# from *the calling file's own directory* to find its .env -- except under
# uvicorn --reload, the actual server runs in a spawned subprocess where that
# lookup falls back to searching from the process's CWD instead (a
# python-dotenv heuristic quirk), so it can miss a .env that lives in a
# subdirectory of the CWD. Load all three explicitly by path here, before
# anything else runs, so startup doesn't depend on that fallback at all.
# (load_dotenv() no-ops silently if the given path doesn't exist, and never
# overrides a var already set, so this is always safe to call.)
for _env_path in (SERVER_DIR / ".env", NARRATIVE_DIR / ".env", BEHAVIORAL_DIR / ".env"):
    load_dotenv(_env_path)

# Each service imports its own siblings as bare top-level modules (model_env;
# game/estimation/reward/portal), so its own directory must be on sys.path.
# narrative_engine is a proper package, so the repo root must be on sys.path.
for p in (str(ROOT_DIR), str(SERVER_DIR), str(BEHAVIORAL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from main import app as rl_app  # noqa: E402  (server/main.py)
from app import app as behavioral_app  # noqa: E402  (behavioural-simulation/backend/app.py)
from narrative_engine.api.app import app as narrative_app  # noqa: E402

SUB_APPS = (rl_app, narrative_app, behavioral_app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs each service's own startup/shutdown (RL model + market data load,
    # narrative engine init, behavioral Cosmos index setup) unmodified,
    # regardless of whether it uses @app.on_event or lifespan=. No ordering
    # dependency between them -- RL reads Black-Litterman predictions from a
    # static JSON file (server/main.py's BL_PREDICTIONS_PATH), not from
    # narrative_app's in-process state, so it doesn't need narrative's
    # lifespan to have entered first.
    async with rl_app.router.lifespan_context(rl_app), \
            narrative_app.router.lifespan_context(narrative_app), \
            behavioral_app.router.lifespan_context(behavioral_app):
        yield


app = FastAPI(title="BiasBreakers Unified Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each sub-app's own CORSMiddleware.add_middleware(...) call still runs at
# import time above, but is never invoked as an ASGI wrapper once we copy
# routes out below -- only this app's CORS middleware actually applies.

_SKIP_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
for sub_app in SUB_APPS:
    app.router.routes.extend(
        r for r in sub_app.routes if getattr(r, "path", None) not in _SKIP_PATHS
    )
