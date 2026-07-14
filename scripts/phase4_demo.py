from __future__ import annotations

import uvicorn

from metricthread.api import AgentRuntime, create_app
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.insights import GroundedNarrative, InMemoryInsightStore
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events
from metricthread.streams import InMemoryStream


class DemoNarrator:
    def generate(self, signal) -> GroundedNarrative:
        signal_id = str(signal.id)
        return GroundedNarrative(
            signal_id=signal_id,
            title="Partner referral quality predicts higher acquisition cost",
            narrative="This predictive lead-lag evidence is consistent with a negative relationship in the synthetic live simulation.",
            recommendation="Propose a human review of partner referral quality before changing any partner-program action.",
            predicted_impact="Any impact remains predictive and must be measured after a human-controlled implementation.",
            evidence_signal_ids=(signal_id,),
        )


def demo_app():
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    signals = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    signals.run_analysis()
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="phase4-demo")
    return create_app(AgentRuntime(pipeline), signals, InMemoryInsightStore(), DemoNarrator())


if __name__ == "__main__":
    uvicorn.run(demo_app(), host="127.0.0.1", port=8000)
