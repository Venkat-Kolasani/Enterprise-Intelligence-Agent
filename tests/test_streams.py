from __future__ import annotations

from metricthread.streams import InMemoryStream


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
