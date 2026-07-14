from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.errors import UniqueViolation

from metricthread.database import (
    apply_foundation_migration,
    entity_resolution_counts,
    foundation_counts,
    seed_foundation,
)


@pytest.fixture
def database_schema() -> tuple[str, str]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for Supabase integration checks")
    schema = f"metricthread_phase1_{uuid4().hex}"
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield url, schema
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_supabase_schema_accepts_seed_data_and_enforces_unique_source_records(database_schema: tuple[str, str]) -> None:
    url, schema = database_schema
    apply_foundation_migration(url, schema)
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
