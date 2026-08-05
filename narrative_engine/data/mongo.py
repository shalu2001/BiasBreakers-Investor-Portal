"""Cosmos DB (Mongo API) connection management.

A single ``MongoClient`` is shared across all repositories in a request/process, since the
prices, market caps, index, news, and ticker-info collections all live on the same Cosmos
cluster (in different databases). TLS is configured exactly as the research repo did.
"""

from __future__ import annotations

import logging
from typing import Optional

import certifi
from pymongo import MongoClient

from narrative_engine.config import NarrativePipelineSettings

logger = logging.getLogger(__name__)


class MongoConnection:
    """Lazy, reusable Cosmos DB (Mongo API) client wrapper."""

    def __init__(self, settings: NarrativePipelineSettings):
        self.settings = settings
        self._client: Optional[MongoClient] = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self._client = self._connect()
        return self._client

    def _connect(self) -> MongoClient:
        client_options = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 20000,
            "socketTimeoutMS": 20000,
        }
        if self.settings.cosmos_allow_invalid_certs:
            client_options["tlsAllowInvalidCertificates"] = True
        else:
            client_options["tlsCAFile"] = self.settings.cosmos_tls_ca_file or certifi.where()

        client = MongoClient(self.settings.mongo_connection_string, **client_options)
        client.admin.command("ping")
        logger.info("Connected to Cosmos DB (Mongo API).")
        return client

    def database(self, name: str):
        return self.client[name]

    def collection(self, database_name: str, collection_name: str):
        return self.client[database_name][collection_name]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Closed Cosmos DB connection.")
