from __future__ import annotations

import httpx

from metricthread.streams import InMemoryStream, UpstashRedisStream


def test_stream_groups_receive_the_same_event_independently() -> None:
    stream = InMemoryStream()
    stream.ensure_group("hot")
    stream.ensure_group("cold")
    stream.append({"payload": "event"})

    hot = stream.read_new("hot", "hot-worker", 10)
    cold = stream.read_new("cold", "cold-worker", 10)

    assert [entry.stream_id for entry in hot] == [entry.stream_id for entry in cold]
    assert stream.acknowledge("hot", [entry.stream_id for entry in hot]) == 1
    assert stream.pending_count("hot") == 0
    assert stream.pending_count("cold") == 1


def test_existing_upstash_consumer_group_is_idempotent_even_when_reported_as_http_400() -> None:
    stream = UpstashRedisStream("https://example.upstash.io", "test-token")
    stream._client = httpx.Client(
        base_url="https://example.upstash.io",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"error": "BUSYGROUP Consumer Group name already exists"})
        )
    )

    stream.ensure_group("metricthread-hot")
