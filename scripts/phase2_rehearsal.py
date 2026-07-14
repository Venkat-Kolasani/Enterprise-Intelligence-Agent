from __future__ import annotations

import os
import threading
import time
from dataclasses import asdict
from uuid import uuid4

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.live_pipeline import LivePipeline, SupabaseRestColdStore
from metricthread.streams import UpstashRedisStream


EVENT_COUNT = 600
EVENTS_PER_SECOND = 5


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    rest_url = required_environment("UPSTASH_REDIS_REST_URL")
    rest_token = required_environment("UPSTASH_REDIS_REST_TOKEN")
    supabase_url = required_environment("SUPABASE_URL")
    supabase_secret_key = required_environment("SUPABASE_SECRET_KEY")
    stream = UpstashRedisStream(
        rest_url,
        rest_token,
        stream_name=f"metricthread:phase2-rehearsal:{uuid4().hex}",
        retention=EVENT_COUNT + 100,
    )
    pipeline = LivePipeline(
        stream,
        SupabaseRestColdStore(supabase_url, supabase_secret_key),
        consumer_name="phase2-rehearsal",
    )
    events = list(generate_dataset(resolve_exact_keys(foundation_source_records())).events[:EVENT_COUNT])
    stop_worker = threading.Event()

    def consume() -> None:
        while not stop_worker.is_set():
            pipeline.process_once()
            time.sleep(0.1)

    try:
        pipeline.start()
        worker = threading.Thread(target=consume, daemon=True)
        worker.start()
        emission_started_at = time.monotonic()
        next_emit_at = time.monotonic()
        for event in events:
            pipeline.emit_events([event])
            next_emit_at += 1 / EVENTS_PER_SECOND
            time.sleep(max(0, next_emit_at - time.monotonic()))
        emission_elapsed_seconds = time.monotonic() - emission_started_at

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = pipeline.status()
            if status.hot_events_processed == EVENT_COUNT and status.cold_events_persisted == EVENT_COUNT:
                break
            time.sleep(0.1)

        status = pipeline.status()
        print(
            {
                "emission_elapsed_seconds": round(emission_elapsed_seconds, 2),
                "actual_events_per_second": round(EVENT_COUNT / emission_elapsed_seconds, 2),
                "status": asdict(status),
            },
            flush=True,
        )
        if (
            status.hot_events_processed != EVENT_COUNT
            or status.cold_events_persisted != EVENT_COUNT
            or status.hot_pending != 0
            or status.cold_pending != 0
            or status.p95_hot_visibility_ms is None
            or status.p95_hot_visibility_ms > 2_000
            or status.p95_cold_persistence_ms is None
            or status.p95_cold_persistence_ms > 10_000
            or not 4.75 <= EVENT_COUNT / emission_elapsed_seconds <= 5.25
        ):
            raise RuntimeError("Phase 2 reliability targets were not met")
    finally:
        stop_worker.set()
        stream.delete_stream()
        stream.close()


if __name__ == "__main__":
    main()
