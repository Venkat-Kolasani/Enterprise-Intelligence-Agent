from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5

import httpx
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from metricthread.entities import ENTITY_NAMESPACE, foundation_source_records, resolve_exact_keys
from metricthread.generator import GeneratedDataset, generate_dataset


MIGRATION_PATH = Path(__file__).parents[1] / "db" / "migrations" / "001_foundation.sql"
SIGNAL_ENGINE_MIGRATION_PATH = Path(__file__).parents[1] / "db" / "migrations" / "002_signal_engine.sql"


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL must be set before database operations")
    return value


def _set_search_path(connection: psycopg.Connection, schema: str | None) -> None:
    if schema:
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))


def _apply_migration(url: str, migration_path: Path, schema: str | None = None) -> None:
    statements = [statement.strip() for statement in migration_path.read_text().split(";") if statement.strip()]
    with psycopg.connect(url) as connection:
        _set_search_path(connection, schema)
        for statement in statements:
            connection.execute(statement)


def apply_foundation_migration(url: str, schema: str | None = None) -> None:
    _apply_migration(url, MIGRATION_PATH, schema)


def apply_signal_engine_migration(url: str, schema: str | None = None) -> None:
    _apply_migration(url, SIGNAL_ENGINE_MIGRATION_PATH, schema)


def seed_foundation(url: str, schema: str | None = None) -> GeneratedDataset:
    resolved_entities = resolve_exact_keys(foundation_source_records())
    dataset = generate_dataset(resolved_entities)

    with psycopg.connect(url) as connection:
        _set_search_path(connection, schema)
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO entities (id, entity_type, display_name, external_ids)
                VALUES (%(id)s, %(entity_type)s, %(display_name)s, %(external_ids)s)
                ON CONFLICT (id) DO UPDATE
                SET entity_type = EXCLUDED.entity_type,
                    display_name = EXCLUDED.display_name,
                    external_ids = EXCLUDED.external_ids
                """,
                [
                    {
                        "id": entity.id,
                        "entity_type": entity.entity_type,
                        "display_name": entity.display_name,
                        "external_ids": Jsonb({record.source_system: record.source_id for record in entity.source_records}),
                    }
                    for entity in resolved_entities
                ],
            )
            cursor.executemany(
                """
                INSERT INTO entity_resolution_map (id, entity_id, source_system, source_id, match_confidence)
                VALUES (%(id)s, %(entity_id)s, %(source_system)s, %(source_id)s, 1.0)
                ON CONFLICT (source_system, source_id) DO UPDATE
                SET entity_id = EXCLUDED.entity_id,
                    match_confidence = EXCLUDED.match_confidence,
                    matched_at = now()
                """,
                [
                    {
                        "id": uuid5(ENTITY_NAMESPACE, f"{record.source_system}:{record.source_id}"),
                        "entity_id": entity.id,
                        "source_system": record.source_system,
                        "source_id": record.source_id,
                    }
                    for entity in resolved_entities
                    for record in entity.source_records
                ],
            )
            cursor.executemany(
                """
                INSERT INTO metric_events (
                    id, entity_id, domain, metric_name, value, unit, dimensions, event_time, source_system, ingested_at
                ) VALUES (
                    %(id)s, %(entity_id)s, %(domain)s, %(metric_name)s, %(value)s, %(unit)s,
                    %(dimensions)s, %(event_time)s, %(source_system)s, %(ingested_at)s
                )
                ON CONFLICT (id) DO UPDATE
                SET value = EXCLUDED.value,
                    dimensions = EXCLUDED.dimensions,
                    ingested_at = EXCLUDED.ingested_at
                """,
                [
                    {
                        "id": event.id,
                        "entity_id": event.entity_id,
                        "domain": event.domain,
                        "metric_name": event.metric_name,
                        "value": event.value,
                        "unit": event.unit,
                        "dimensions": Jsonb(event.dimensions),
                        "event_time": event.event_time,
                        "source_system": event.source_system,
                        "ingested_at": datetime.now(timezone.utc),
                    }
                    for event in dataset.events
                ],
            )
    return dataset


def seed_foundation_via_data_api(supabase_url: str, secret_key: str) -> GeneratedDataset:
    """Synchronize the canonical fixture when raw Postgres access is unavailable."""
    resolved_entities = resolve_exact_keys(foundation_source_records())
    dataset = generate_dataset(resolved_entities)
    rows = [
        {
            "id": str(event.id),
            "entity_id": str(event.entity_id),
            "domain": event.domain,
            "metric_name": event.metric_name,
            "value": event.value,
            "unit": event.unit,
            "dimensions": event.dimensions,
            "event_time": event.event_time.isoformat(),
            "source_system": event.source_system,
        }
        for event in dataset.events
    ]
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/metric_events"
    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for offset in range(0, len(rows), 100):
        response = httpx.post(
            endpoint,
            params={"on_conflict": "entity_id,metric_name,event_time,source_system"},
            headers=headers,
            json=rows[offset : offset + 100],
            timeout=10.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase canonical seed write failed at row {offset}: {error}") from error
    return dataset


def foundation_counts(url: str, schema: str | None = None) -> dict[str, int]:
    with psycopg.connect(url) as connection:
        _set_search_path(connection, schema)
        with connection.cursor() as cursor:
            counts = {}
            for table_name in ("entities", "entity_resolution_map", "metric_events"):
                cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name)))
                counts[table_name] = cursor.fetchone()[0]
    return counts


def entity_resolution_counts(url: str, schema: str | None = None) -> Counter[str]:
    with psycopg.connect(url) as connection:
        _set_search_path(connection, schema)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT entities.display_name, count(*)
                FROM entity_resolution_map
                JOIN entities ON entities.id = entity_resolution_map.entity_id
                GROUP BY entities.display_name
                """
            )
            return Counter(dict(cursor.fetchall()))
