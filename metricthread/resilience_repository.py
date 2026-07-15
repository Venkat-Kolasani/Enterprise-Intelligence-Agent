from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from dotenv import load_dotenv

from metricthread.resilience import RESILIENCE_VERSION, ResilienceAssessment, ResilienceStore


class SupabaseResilienceStore(ResilienceStore):
    """Persisted, versioned resilience records behind the server-side Data API key."""

    def __init__(self, supabase_url: str, secret_key: str) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
        }

    def latest_for_signal(self, signal_id: UUID) -> ResilienceAssessment | None:
        response = httpx.get(
            f"{self._base_url}/signal_resilience_results",
            params={
                "select": "*",
                "correlation_signal_id": f"eq.{signal_id}",
                "resilience_version": f"eq.{RESILIENCE_VERSION}",
                "order": "evaluated_at.desc",
                "limit": 1,
            },
            headers=self._headers,
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase resilience read failed: {error}") from error
        rows = response.json()
        return _assessment_from_row(rows[0]) if rows else None

    def persist(self, assessment: ResilienceAssessment) -> None:
        response = httpx.post(
            f"{self._base_url}/signal_resilience_results",
            params={
                "on_conflict": "correlation_signal_id,resilience_version,evidence_fingerprint",
            },
            headers={
                **self._headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=assessment.as_row(),
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase resilience write failed: {error}") from error


def resilience_store_from_environment() -> SupabaseResilienceStore:
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not supabase_url or not secret_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for resilience records")
    return SupabaseResilienceStore(supabase_url, secret_key)


def _assessment_from_row(row: dict[str, Any]) -> ResilienceAssessment:
    return ResilienceAssessment(
        id=UUID(str(row["id"])),
        correlation_signal_id=UUID(str(row["correlation_signal_id"])),
        evidence_fingerprint=str(row["evidence_fingerprint"]),
        resilience_version=str(row["resilience_version"]),
        evaluation_config=dict(row["evaluation_config"]),
        result=dict(row["result"]),
        recommendation_eligible=bool(row["recommendation_eligible"]),
        evaluated_at=datetime.fromisoformat(str(row["evaluated_at"])),
    )
