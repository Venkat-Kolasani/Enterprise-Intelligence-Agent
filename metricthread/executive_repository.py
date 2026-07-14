from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from dotenv import load_dotenv

from metricthread.executive import BriefingRecord, ExecutiveStore, ScenarioForecast


class SupabaseExecutiveStore:
    """Server-side persistence for generated briefings and deterministic scenarios."""

    def __init__(self, supabase_url: str, secret_key: str) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
        }

    def list_briefings(self) -> list[BriefingRecord]:
        rows = self._get("briefings", {"select": "*", "order": "generated_at.desc"})
        return [_briefing_from_row(row) for row in rows]

    def persist_briefing(self, briefing: BriefingRecord) -> None:
        self._post(
            "briefings",
            {
                "id": str(briefing.id),
                "summary_text": briefing.summary_text,
                "insight_ids": list(briefing.insight_ids),
                "generated_at": briefing.generated_at.isoformat(),
            },
        )

    def persist_forecast(self, forecast: ScenarioForecast) -> None:
        self._post(
            "scenario_forecasts",
            {
                "id": str(forecast.id),
                "correlation_signal_id": str(forecast.correlation_signal_id),
                "input_metric": "marketing_spend",
                "input_change_percent": forecast.input_change_percent,
                "horizon_days": forecast.horizon_days,
                "baseline_values": forecast.baseline_values,
                "forecast_values": forecast.forecast_values,
                "prediction_intervals": forecast.prediction_intervals,
                "reliability_score": forecast.reliability_score,
                "model_version": forecast.model_version,
                "assumptions": forecast.assumptions,
                "generated_at": forecast.generated_at.isoformat(),
            },
        )

    def list_forecasts(self) -> list[ScenarioForecast]:
        rows = self._get("scenario_forecasts", {"select": "*", "order": "generated_at.desc"})
        return [_forecast_from_row(row) for row in rows]

    def _get(self, table: str, params: dict[str, object]) -> list[dict[str, Any]]:
        response = httpx.get(f"{self._base_url}/{table}", params=params, headers=self._headers, timeout=8.0)
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase {table} read failed: {error}") from error
        return response.json()

    def _post(self, table: str, payload: dict[str, object]) -> None:
        response = httpx.post(
            f"{self._base_url}/{table}",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=payload,
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase {table} write failed: {error}") from error


def executive_store_from_environment() -> ExecutiveStore:
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not supabase_url or not secret_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for executive workflow storage")
    return SupabaseExecutiveStore(supabase_url, secret_key)


def _briefing_from_row(row: dict[str, Any]) -> BriefingRecord:
    return BriefingRecord(
        id=UUID(str(row["id"])),
        summary_text=str(row["summary_text"]),
        insight_ids=tuple(str(insight_id) for insight_id in row["insight_ids"]),
        generated_at=datetime.fromisoformat(str(row["generated_at"])),
    )


def _forecast_from_row(row: dict[str, Any]) -> ScenarioForecast:
    return ScenarioForecast(
        id=UUID(str(row["id"])),
        correlation_signal_id=UUID(str(row["correlation_signal_id"])),
        input_change_percent=float(row["input_change_percent"]),
        horizon_days=int(row["horizon_days"]),
        baseline_values=dict(row["baseline_values"]),
        forecast_values=dict(row["forecast_values"]),
        prediction_intervals=dict(row["prediction_intervals"]),
        reliability_score=float(row["reliability_score"]),
        model_version=str(row["model_version"]),
        assumptions=dict(row["assumptions"]),
        generated_at=datetime.fromisoformat(str(row["generated_at"])),
    )
