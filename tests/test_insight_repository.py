from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from metricthread.insight_repository import SupabaseInsightStore
from metricthread.insights import InsightRecord, RecommendationRecord


def test_supabase_store_persists_an_insight_and_recommendation_through_one_rpc(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    insight = InsightRecord(
        id=uuid4(),
        title="Grounded title",
        narrative_text="Predictive lead-lag evidence only.",
        related_signal_ids=(str(uuid4()),),
        confidence_score=91.2,
        domains=("partner", "client"),
        status="active",
        generated_at=now,
    )
    recommendation = RecommendationRecord(
        id=uuid4(),
        insight_id=insight.id,
        recommendation_text="Complete a human review.",
        predicted_impact={"human_review_required": True},
        confidence_score=91.2,
        status="proposed",
        created_at=now,
    )

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    def post(url: str, **kwargs: object) -> SuccessfulResponse:
        calls.append({"url": url, **kwargs})
        return SuccessfulResponse()

    monkeypatch.setattr("metricthread.insight_repository.httpx.post", post)
    SupabaseInsightStore("https://example.supabase.co", "test-secret").persist_generated(insight, recommendation)

    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.supabase.co/rest/v1/rpc/persist_grounded_insight"
    payload = calls[0]["json"]
    assert payload["insight_payload"]["id"] == str(insight.id)
    assert payload["recommendation_payload"]["insight_id"] == str(insight.id)
