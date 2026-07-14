from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

import httpx
from dotenv import load_dotenv

from metricthread.insights import InsightRecord, InsightStore, RecommendationRecord, RECOMMENDATION_STATUSES


OUTCOME_NAMESPACE = UUID("af68a735-1845-4e89-8f7c-c0fe043b5c31")


class SupabaseInsightStore:
    """Server-side persistence for grounded insights and human-controlled decisions."""

    def __init__(self, supabase_url: str, secret_key: str) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
        }

    def list_insights(self) -> list[InsightRecord]:
        rows = self._get("insights", {"select": "*", "order": "generated_at.desc"})
        return [_insight_from_row(row) for row in rows]

    def list_recommendations(self) -> list[RecommendationRecord]:
        recommendations = self._get("recommendations", {"select": "*", "order": "created_at.desc"})
        outcomes = self._get("decision_outcomes", {"select": "*"})
        outcomes_by_recommendation = {str(row["recommendation_id"]): row for row in outcomes}
        return [
            _recommendation_from_row(row, outcomes_by_recommendation.get(str(row["id"])))
            for row in recommendations
        ]

    def persist_generated(self, insight: InsightRecord, recommendation: RecommendationRecord) -> None:
        self._post(
            "insights",
            {
                "id": str(insight.id),
                "title": insight.title,
                "narrative_text": insight.narrative_text,
                "related_signal_ids": list(insight.related_signal_ids),
                "confidence_score": insight.confidence_score,
                "domains": list(insight.domains),
                "status": insight.status,
                "generated_at": insight.generated_at.isoformat(),
            },
        )
        self._post(
            "recommendations",
            {
                "id": str(recommendation.id),
                "insight_id": str(recommendation.insight_id),
                "recommendation_text": recommendation.recommendation_text,
                "predicted_impact": recommendation.predicted_impact,
                "confidence_score": recommendation.confidence_score,
                "status": recommendation.status,
                "created_at": recommendation.created_at.isoformat(),
            },
        )

    def update_recommendation_status(self, recommendation_id: UUID, status: str) -> RecommendationRecord:
        if status not in RECOMMENDATION_STATUSES:
            raise ValueError(f"unsupported recommendation status: {status}")
        rows = self._patch(
            "recommendations",
            {"id": f"eq.{recommendation_id}"},
            {"status": status},
        )
        if len(rows) != 1:
            raise LookupError("recommendation was not found")
        outcome = self._get("decision_outcomes", {"select": "*", "recommendation_id": f"eq.{recommendation_id}"})
        return _recommendation_from_row(rows[0], outcome[0] if outcome else None)

    def record_outcome(
        self,
        recommendation_id: UUID,
        *,
        implemented_at: datetime,
        outcome_metric: str,
        outcome_value: float,
        measured_at: datetime,
        notes: str,
    ) -> RecommendationRecord:
        recommendations = self._get("recommendations", {"select": "*", "id": f"eq.{recommendation_id}"})
        if len(recommendations) != 1:
            raise LookupError("recommendation was not found")
        if recommendations[0]["status"] != "implemented":
            raise ValueError("recommendation must be implemented before recording an outcome")
        self._post(
            "decision_outcomes",
            {
                "id": str(uuid5(OUTCOME_NAMESPACE, str(recommendation_id))),
                "recommendation_id": str(recommendation_id),
                "implemented_at": implemented_at.isoformat(),
                "outcome_metric": outcome_metric,
                "outcome_value": outcome_value,
                "measured_at": measured_at.isoformat(),
                "notes": notes,
            },
            params={"on_conflict": "recommendation_id"},
        )
        outcomes = self._get("decision_outcomes", {"select": "*", "recommendation_id": f"eq.{recommendation_id}"})
        return _recommendation_from_row(recommendations[0], outcomes[0])

    def _get(self, table: str, params: dict[str, object]) -> list[dict[str, Any]]:
        response = httpx.get(f"{self._base_url}/{table}", params=params, headers=self._headers, timeout=8.0)
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase {table} read failed: {error}") from error
        return response.json()

    def _post(self, table: str, payload: dict[str, object], *, params: dict[str, object] | None = None) -> None:
        response = httpx.post(
            f"{self._base_url}/{table}",
            params=params,
            headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload,
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase {table} write failed: {error}") from error

    def _patch(self, table: str, params: dict[str, object], payload: dict[str, object]) -> list[dict[str, Any]]:
        response = httpx.patch(
            f"{self._base_url}/{table}",
            params=params,
            headers={**self._headers, "Prefer": "return=representation"},
            json=payload,
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase {table} update failed: {error}") from error
        return response.json()


def insight_store_from_environment() -> SupabaseInsightStore:
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not supabase_url or not secret_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for grounded insights")
    return SupabaseInsightStore(supabase_url, secret_key)


def _insight_from_row(row: dict[str, Any]) -> InsightRecord:
    return InsightRecord(
        id=UUID(str(row["id"])),
        title=str(row["title"]),
        narrative_text=str(row["narrative_text"]),
        related_signal_ids=tuple(str(signal_id) for signal_id in row["related_signal_ids"]),
        confidence_score=float(row["confidence_score"]),
        domains=tuple(str(domain) for domain in row["domains"]),
        status=str(row["status"]),
        generated_at=datetime.fromisoformat(str(row["generated_at"])),
    )


def _recommendation_from_row(row: dict[str, Any], outcome: dict[str, Any] | None) -> RecommendationRecord:
    return RecommendationRecord(
        id=UUID(str(row["id"])),
        insight_id=UUID(str(row["insight_id"])),
        recommendation_text=str(row["recommendation_text"]),
        predicted_impact=dict(row["predicted_impact"]),
        confidence_score=float(row["confidence_score"]),
        status=str(row["status"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        outcome=dict(outcome) if outcome else None,
    )
