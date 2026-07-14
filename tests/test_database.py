from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.errors import UniqueViolation

from metricthread.database import (
    apply_foundation_migration,
    apply_signal_engine_migration,
    entity_resolution_counts,
    foundation_counts,
    seed_foundation,
    seed_foundation_via_data_api,
)


@pytest.fixture
def database_schema() -> tuple[str, str]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for Supabase integration checks")
    schema = f"metricthread_phase1_{uuid4().hex}"
    try:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    except psycopg.OperationalError as error:
        pytest.skip(f"Supabase raw Postgres integration is unavailable from this environment: {error}")
    try:
        yield url, schema
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_supabase_schema_accepts_seed_data_and_enforces_unique_source_records(database_schema: tuple[str, str]) -> None:
    url, schema = database_schema
    apply_foundation_migration(url, schema)
    apply_signal_engine_migration(url, schema)
    dataset = seed_foundation(url, schema)

    assert len(dataset.events) == 1_620
    assert foundation_counts(url, schema) == {
        "entities": 3,
        "entity_resolution_map": 6,
        "metric_events": 1_620,
    }
    assert entity_resolution_counts(url, schema) == {
        "South Growth Cohort": 2,
        "South Partner Network": 2,
        "South Growth Business Unit": 2,
    }

    with psycopg.connect(url) as connection:
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        with pytest.raises(UniqueViolation):
            connection.execute(
                """
                INSERT INTO entity_resolution_map (id, entity_id, source_system, source_id, match_confidence)
                SELECT %s, id, 'crm', 'crm-client-south-001', 1.0
                FROM entities
                LIMIT 1
                """,
                (uuid4(),),
            )
        connection.rollback()
        columns = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'correlation_signals'
            """
        ).fetchall()

    assert {column_name for (column_name,) in columns} >= {"confidence_components", "test_metadata"}


def test_data_api_seed_uses_the_canonical_generator_fixture_in_bounded_batches(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    def post(*_: object, **kwargs: object) -> SuccessfulResponse:
        calls.append(kwargs)
        return SuccessfulResponse()

    monkeypatch.setattr("metricthread.database.httpx.post", post)
    dataset = seed_foundation_via_data_api("https://example.supabase.co", "test-secret")

    assert len(dataset.events) == 1_620
    assert len(calls) == 17
    rows = [row for call in calls for row in call["json"]]
    assert len(rows) == 1_620
    assert rows[0]["value"] == dataset.events[0].value
    assert all(len(call["json"]) <= 100 for call in calls)
