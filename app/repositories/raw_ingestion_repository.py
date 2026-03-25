from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import MetaData, Table, func, insert, select
from sqlalchemy.orm import Session


class RawIngestionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        metadata = MetaData()
        bind = db.get_bind()
        self.batch_table = Table("raw_ingestion_batch", metadata, autoload_with=bind)
        self.payload_table = Table("raw_raw_payload", metadata, autoload_with=bind)

    def record_api_call(
        self,
        *,
        source_system: str,
        source_topic: str | None,
        source_uri: str | None,
        payload: dict[str, Any],
        notes: str | None = None,
        entity_hint: str | None = None,
    ) -> int:
        raw_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        batch_id = self._create_batch(
            source_system=source_system,
            source_topic=source_topic,
            source_uri=source_uri,
            notes=notes,
        )
        self._store_payload(
            ingestion_batch_id=batch_id,
            payload=payload,
            raw_bytes=raw_bytes,
            entity_hint=entity_hint,
        )
        return batch_id

    def _create_batch(
        self,
        *,
        source_system: str,
        source_topic: str | None,
        source_uri: str | None,
        notes: str | None,
    ) -> int:
        values: dict[str, Any] = {"source_system": source_system}
        if "source_topic" in self.batch_table.c:
            values["source_topic"] = source_topic
        if "payload_format" in self.batch_table.c:
            values["payload_format"] = "json"
        if "source_uri" in self.batch_table.c:
            values["source_uri"] = source_uri
        if "notes" in self.batch_table.c:
            values["notes"] = notes
        if "status" in self.batch_table.c:
            values["status"] = "received"
        if self.db.get_bind().dialect.name == "sqlite" and "id" in self.batch_table.c:
            next_id = self.db.execute(select(func.coalesce(func.max(self.batch_table.c["id"]), 0) + 1)).scalar_one()
            values["id"] = int(next_id)
        result = self.db.execute(insert(self.batch_table).values(**values))
        return int(result.inserted_primary_key[0])

    def _store_payload(
        self,
        *,
        ingestion_batch_id: int,
        payload: dict[str, Any],
        raw_bytes: bytes,
        entity_hint: str | None,
    ) -> int:
        payload_column = self.payload_table.c["payload"]
        values: dict[str, Any] = {"ingestion_batch_id": ingestion_batch_id}
        if str(payload_column.type).lower().find("blob") >= 0:
            values[payload_column.key] = raw_bytes
        else:
            values[payload_column.key] = payload
        if "payload_bytes" in self.payload_table.c:
            values["payload_bytes"] = raw_bytes
        if "entity_hint" in self.payload_table.c:
            values["entity_hint"] = entity_hint
        if "payload_hash" in self.payload_table.c:
            values["payload_hash"] = hashlib.sha256(raw_bytes).hexdigest()
        if self.db.get_bind().dialect.name == "sqlite" and "id" in self.payload_table.c:
            next_id = self.db.execute(select(func.coalesce(func.max(self.payload_table.c["id"]), 0) + 1)).scalar_one()
            values["id"] = int(next_id)
        result = self.db.execute(insert(self.payload_table).values(**values))
        return int(result.inserted_primary_key[0])
