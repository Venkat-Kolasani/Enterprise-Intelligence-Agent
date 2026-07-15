from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.streams import InMemoryStream


def test_each_simulated_day_reaches_independent_hot_and_cold_paths() -> None:
    stream = InMemoryStream()
    cold_store = InMemoryColdStore()
    pipeline = LivePipeline(stream, cold_store, consumer_name="test-worker")

    pipeline.start()
    assert pipeline.emit_next_day() == 9
    pipeline.process_once()

    status = pipeline.status()
    assert status.hot_events_processed == 9
    assert status.cold_events_persisted == 9
    assert status.hot_pending == 0
    assert status.cold_pending == 0
    assert len(cold_store.events) == 9
    assert len(pipeline.latest_metrics()) == 9


def test_cold_path_leaves_events_recoverable_when_durable_write_fails() -> None:
    class FailingStore:
        def persist(self, events: list[dict[str, object]]) -> None:
            raise RuntimeError("durable store unavailable")

    stream = InMemoryStream()
    pipeline = LivePipeline(stream, FailingStore(), consumer_name="test-worker")

    pipeline.start()
    pipeline.emit_next_day()
    pipeline.process_once()

    status = pipeline.status()
    assert status.hot_pending == 0
    assert status.cold_pending == 9
    assert status.last_cold_error == "durable store unavailable"


def test_fresh_simulation_defers_stale_recovery_until_after_first_live_batch() -> None:
    class TrackingStream(InMemoryStream):
        def __init__(self) -> None:
            super().__init__()
            self.reclaimed_groups: list[str] = []

        def reclaim_idle(self, group: str, consumer: str, minimum_idle_ms: int, count: int):  # type: ignore[no-untyped-def]
            self.reclaimed_groups.append(group)
            return super().reclaim_idle(group, consumer, minimum_idle_ms, count)

    stream = TrackingStream()
    pipeline = LivePipeline(stream, InMemoryColdStore(), consumer_name="test-worker")

    pipeline.start()
    pipeline.emit_next_day()
    pipeline.process_once()

    assert stream.reclaimed_groups == []
    assert pipeline.status().hot_events_processed == 9
    assert pipeline.status().cold_events_persisted == 9


def test_stale_stream_recovery_does_not_distort_current_simulation_latency() -> None:
    stream = InMemoryStream()
    pipeline = LivePipeline(stream, InMemoryColdStore(), consumer_name="test-worker")
    pipeline.start()

    stale_event = pipeline._events_by_day[0][0]
    stream.append(
        {
            "event_id": str(stale_event.id),
            "payload": json.dumps(
                {
                    "id": str(stale_event.id),
                    "entity_id": str(stale_event.entity_id),
                    "domain": stale_event.domain,
                    "metric_name": stale_event.metric_name,
                    "value": stale_event.value,
                    "unit": stale_event.unit,
                    "dimensions": stale_event.dimensions,
                    "event_time": stale_event.event_time.isoformat(),
                    "source_system": stale_event.source_system,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            "emitted_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
            "simulation_id": "prior-simulation",
        }
    )

    pipeline._next_day = 1
    assert pipeline.emit_next_day() == 9
    pipeline.process_once()

    status = pipeline.status()
    assert status.hot_events_processed == 10
    assert status.cold_events_persisted == 10
    assert status.p95_hot_visibility_ms is not None
    assert status.p95_cold_persistence_ms is not None
    assert status.p95_hot_visibility_ms < 1_000
    assert status.p95_cold_persistence_ms < 1_000
