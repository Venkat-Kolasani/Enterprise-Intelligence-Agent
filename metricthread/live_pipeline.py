from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Protocol

import httpx
import psycopg
from psycopg.types.json import Jsonb

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import MetricEvent, generate_dataset
from metricthread.streams import StreamBus, StreamEntry


HOT_GROUP = "metricthread-hot"
COLD_GROUP = "metricthread-cold"
RECOVERY_IDLE_MS = 60_000


def _event_payload(event: MetricEvent) -> dict[str, object]:
    return {
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


def _parse_event(payload: str) -> dict[str, object]:
    event = json.loads(payload)
    required = {
        "id",
        "entity_id",
        "domain",
        "metric_name",
        "value",
        "unit",
        "dimensions",
        "event_time",
        "source_system",
    }
    if set(event) != required or not isinstance(event["dimensions"], dict):
        raise ValueError("stream payload does not match the MetricThread event contract")
    return event


class ColdStore(Protocol):
    def persist(self, events: list[dict[str, object]]) -> None: ...


class FailingColdStore:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def persist(self, events: list[dict[str, object]]) -> None:
        raise RuntimeError(self._reason)


class InMemoryColdStore:
    def __init__(self) -> None:
        self.events: dict[str, dict[str, object]] = {}

    def persist(self, events: list[dict[str, object]]) -> None:
        for event in events:
            self.events[str(event["id"])] = event


class PostgresColdStore:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def persist(self, events: list[dict[str, object]]) -> None:
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO metric_events (
                        id, entity_id, domain, metric_name, value, unit, dimensions, event_time, source_system
                    ) VALUES (
                        %(id)s, %(entity_id)s, %(domain)s, %(metric_name)s, %(value)s, %(unit)s,
                        %(dimensions)s, %(event_time)s, %(source_system)s
                    )
                    ON CONFLICT (entity_id, metric_name, event_time, source_system) DO UPDATE
                    SET value = EXCLUDED.value,
                        dimensions = EXCLUDED.dimensions,
                        ingested_at = now()
                    """,
                    [
                        {
                            **event,
                            "dimensions": Jsonb(event["dimensions"]),
                            "event_time": datetime.fromisoformat(str(event["event_time"])),
                        }
                        for event in events
                    ],
                )


class SupabaseRestColdStore:
    """Server-only Data API sink for environments where Postgres TCP is unavailable."""

    def __init__(self, supabase_url: str, secret_key: str) -> None:
        self._endpoint = f"{supabase_url.rstrip('/')}/rest/v1/metric_events"
        self._secret_key = secret_key

    def persist(self, events: list[dict[str, object]]) -> None:
        response = httpx.post(
            self._endpoint,
            params={"on_conflict": "entity_id,metric_name,event_time,source_system"},
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=events,
            timeout=5.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase Data API cold write failed: {error}") from error


@dataclass(frozen=True)
class PipelineStatus:
    simulation_state: str
    simulated_days_emitted: int
    monitored_metrics: int
    hot_events_processed: int
    cold_events_persisted: int
    stream_length: int
    hot_pending: int
    cold_pending: int
    p95_hot_visibility_ms: float | None
    p95_cold_persistence_ms: float | None
    last_event_time: str | None
    last_cold_error: str | None


class HotWindow:
    def __init__(self, maximum_events: int = 90) -> None:
        self._events: deque[dict[str, object]] = deque(maxlen=maximum_events)
        self._seen_ids: set[str] = set()
        self._latest_by_metric: dict[str, dict[str, object]] = {}

    def add(self, event: dict[str, object]) -> bool:
        event_id = str(event["id"])
        if event_id in self._seen_ids:
            return False
        if len(self._events) == self._events.maxlen:
            removed = self._events[0]
            self._seen_ids.discard(str(removed["id"]))
        self._events.append(event)
        self._seen_ids.add(event_id)
        self._latest_by_metric[str(event["metric_name"])] = event
        return True

    def latest_metrics(self) -> list[dict[str, object]]:
        return sorted(self._latest_by_metric.values(), key=lambda event: str(event["metric_name"]))


class LivePipeline:
    def __init__(self, stream: StreamBus, cold_store: ColdStore, *, consumer_name: str | None = None) -> None:
        entities = resolve_exact_keys(foundation_source_records())
        dataset = generate_dataset(entities)
        events_by_day: dict[object, list[MetricEvent]] = {}
        for event in dataset.events:
            events_by_day.setdefault(event.event_time.date(), []).append(event)
        self._events_by_day = list(events_by_day.values())
        self._stream = stream
        self._cold_store = cold_store
        self._consumer_name = consumer_name or f"worker-{os.getpid()}"
        self._window = HotWindow()
        self._simulation_state = "idle"
        self._next_day = 0
        self._hot_events_processed = 0
        self._cold_events_persisted = 0
        self._last_event_time: str | None = None
        self._last_cold_error: str | None = None
        self._hot_visibility_ms: list[float] = []
        self._cold_persistence_ms: list[float] = []
        self._next_recovery_at = 0.0

    def start(self) -> None:
        self._stream.ensure_group(HOT_GROUP)
        self._stream.ensure_group(COLD_GROUP)
        self._simulation_state = "running"

    def emit_next_day(self) -> int:
        if self._simulation_state != "running" or self._next_day >= len(self._events_by_day):
            if self._next_day >= len(self._events_by_day):
                self._simulation_state = "complete"
            return 0
        emitted = self.emit_events(self._events_by_day[self._next_day])
        self._next_day += 1
        return emitted

    def emit_events(self, events: list[MetricEvent]) -> int:
        if self._simulation_state != "running":
            return 0
        for event in events:
            payload = _event_payload(event)
            self._stream.append(
                {
                    "event_id": str(event.id),
                    "payload": json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    "emitted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return len(events)

    def _drain_group(self, group: str) -> list[StreamEntry]:
        reclaimed: list[StreamEntry] = []
        if time.monotonic() >= self._next_recovery_at:
            reclaimed = self._stream.reclaim_idle(group, self._consumer_name, RECOVERY_IDLE_MS, 50)
        return reclaimed + self._stream.read_new(group, self._consumer_name, 50)

    @staticmethod
    def _p95(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        return round(ordered[ceil(len(ordered) * 0.95) - 1], 2)

    @staticmethod
    def _emission_latency_ms(entry: StreamEntry) -> float:
        emitted_at = datetime.fromisoformat(entry.fields["emitted_at"])
        return (datetime.now(timezone.utc) - emitted_at).total_seconds() * 1_000

    def process_once(self) -> None:
        hot_entries = self._drain_group(HOT_GROUP)
        hot_ids: list[str] = []
        for entry in hot_entries:
            event = _parse_event(entry.fields["payload"])
            if self._window.add(event):
                self._hot_events_processed += 1
                self._last_event_time = str(event["event_time"])
                self._hot_visibility_ms.append(self._emission_latency_ms(entry))
            hot_ids.append(entry.stream_id)
        self._stream.acknowledge(HOT_GROUP, hot_ids)

        cold_entries = self._drain_group(COLD_GROUP)
        if not cold_entries:
            return
        try:
            events = [_parse_event(entry.fields["payload"]) for entry in cold_entries]
            self._cold_store.persist(events)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            self._last_cold_error = str(error)
            return
        self._stream.acknowledge(COLD_GROUP, [entry.stream_id for entry in cold_entries])
        self._cold_events_persisted += len(cold_entries)
        self._cold_persistence_ms.extend(self._emission_latency_ms(entry) for entry in cold_entries)
        self._last_cold_error = None
        self._next_recovery_at = time.monotonic() + RECOVERY_IDLE_MS / 1_000

    def status(self) -> PipelineStatus:
        groups_ready = self._simulation_state != "idle"
        return PipelineStatus(
            simulation_state=self._simulation_state,
            simulated_days_emitted=self._next_day,
            monitored_metrics=9,
            hot_events_processed=self._hot_events_processed,
            cold_events_persisted=self._cold_events_persisted,
            stream_length=self._stream.stream_length(),
            hot_pending=self._stream.pending_count(HOT_GROUP) if groups_ready else 0,
            cold_pending=self._stream.pending_count(COLD_GROUP) if groups_ready else 0,
            p95_hot_visibility_ms=self._p95(self._hot_visibility_ms),
            p95_cold_persistence_ms=self._p95(self._cold_persistence_ms),
            last_event_time=self._last_event_time,
            last_cold_error=self._last_cold_error,
        )

    def latest_metrics(self) -> list[dict[str, object]]:
        return self._window.latest_metrics()


def cold_store_from_environment() -> ColdStore:
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if supabase_url and supabase_secret_key:
        return SupabaseRestColdStore(supabase_url, supabase_secret_key)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return PostgresColdStore(database_url)
    return FailingColdStore("No server-side Supabase or Postgres cold-path credentials are configured")
