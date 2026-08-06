"""
portal_db.py -- Cosmos DB (Mongo API) access for the investor portal.

Our data lives in the SHARED cluster but in clearly-prefixed collections
(portal_users, portal_profiles) so it never collides with the RL / Narrative
teams' collections. The connection string is read from the environment
(backend .env, git-ignored) and must never reach the frontend.
"""
import os
import certifi
from functools import lru_cache
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

PREFIX = "portal_"


@lru_cache(maxsize=1)
def _client():
    conn = os.getenv("COSMOS_MONGO_CONNECTION")
    if not conn:
        raise RuntimeError(
            "COSMOS_MONGO_CONNECTION is not set. Add it to behavioural-simulation/backend/.env"
        )
    allow_invalid = os.getenv("COSMOS_ALLOW_INVALID_CERTS", "false").lower() == "true"
    ca_file = os.getenv("COSMOS_TLS_CA_FILE") or certifi.where()
    return MongoClient(conn, tlsCAFile=ca_file, tlsAllowInvalidCertificates=allow_invalid)


def _db():
    name = os.getenv("COSMOS_DATABASE") or "biasbreakers"
    return _client()[name]


def users():
    return _db()[PREFIX + "users"]


def profiles():
    return _db()[PREFIX + "profiles"]


def recommendations():
    return _db()[PREFIX + "recommendations"]


def ensure_indexes():
    """Unique email per user, one profile per user. Safe to call repeatedly."""
    users().create_index([("email", ASCENDING)], unique=True)
    profiles().create_index([("user_id", ASCENDING)], unique=True)
    # Not unique on its own -- (user_id, date) together are the upsert key
    # RL's recommendation persistence uses (one doc per investor per day).
    recommendations().create_index([("user_id", ASCENDING), ("date", ASCENDING)])


def ping():
    """Quick connectivity check used by the /portal/health route."""
    _client().admin.command("ping")
    return True
