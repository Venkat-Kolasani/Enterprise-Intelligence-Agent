from __future__ import annotations

import uvicorn

from metricthread.api import AgentRuntime, create_app
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events
from metricthread.streams import InMemoryStream


def demo_app():
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    repository = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="phase3-demo")
    return create_app(AgentRuntime(pipeline), repository)


if __name__ == "__main__":
    uvicorn.run(demo_app(), host="127.0.0.1", port=8000)
