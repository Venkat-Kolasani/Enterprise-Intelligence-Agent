from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from dotenv import load_dotenv

from metricthread.signals import (
    TEST_CONFIG_VERSION,
    DeterministicSignalEngine,
    MetricObservation,
    SignalAnalysisReport,
    SignalEvidence,
)


class SupabaseSignalRepository:
    """Server-side Supabase Data API adapter for signal analysis and evidence."""

    def __init__(self, supabase_url: str, secret_key: str) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
        }

    def list_accepted(self) -> list[SignalEvidence]:
        response = httpx.get(
            f"{self._base_url}/correlation_signals",
            params={"select": "*", "order": "confidence_score.desc"},
            headers=self._headers,
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase signal read failed: {error}") from error
        return [_signal_from_row(row) for row in response.json()]

    def run_analysis(self) -> SignalAnalysisReport:
        report = DeterministicSignalEngine().analyze(self._metric_observations())
        self._clear_prior_evidence_for_current_engine()
        if report.accepted:
            response = httpx.post(
                f"{self._base_url}/correlation_signals",
                params={"on_conflict": "evidence_fingerprint"},
                headers={
                    **self._headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                json=[signal.as_row() for signal in report.accepted],
                timeout=8.0,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise RuntimeError(f"Supabase signal write failed: {error}") from error
        return report

    def _clear_prior_evidence_for_current_engine(self) -> None:
        response = httpx.delete(
            f"{self._base_url}/correlation_signals",
            params={"test_config_version": f"eq.{TEST_CONFIG_VERSION}"},
            headers={**self._headers, "Prefer": "return=minimal"},
            timeout=8.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Supabase signal reconciliation failed: {error}") from error

    def _metric_observations(self) -> list[MetricObservation]:
        rows: list[dict[str, Any]] = []
        page_size = 1_000
        for offset in range(0, 10_000, page_size):
            response = httpx.get(
                f"{self._base_url}/metric_events",
                params={
                    "select": "domain,metric_name,value,event_time",
                    "order": "event_time.asc",
                    "limit": page_size,
                    "offset": offset,
                },
                headers=self._headers,
                timeout=8.0,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise RuntimeError(f"Supabase metric read failed: {error}") from error
            page = response.json()
            rows.extend(page)
            if len(page) < page_size:
                break
        else:
            raise RuntimeError("Supabase metric read exceeded the 10,000-event safety limit")
        return [
            MetricObservation(
                domain=str(row["domain"]),
                metric_name=str(row["metric_name"]),
                value=float(row["value"]),
                event_time=datetime.fromisoformat(str(row["event_time"])),
            )
            for row in rows
        ]


def signal_repository_from_environment() -> SupabaseSignalRepository:
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not supabase_url or not secret_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for signal analysis")
    return SupabaseSignalRepository(supabase_url, secret_key)


def _signal_from_row(row: dict[str, Any]) -> SignalEvidence:
    return SignalEvidence(
        id=UUID(str(row["id"])),
        domain_a=row["domain_a"],
        metric_a=row["metric_a"],
        domain_b=row["domain_b"],
        metric_b=row["metric_b"],
        lag_days=int(row["lag_days"]),
        correlation_coefficient=float(row["correlation_coefficient"]),
        effect_size=float(row["effect_size"]),
        direction=row["direction"],
        f_statistic=float(row["f_statistic"]),
        granger_p_value=float(row["granger_p_value"]),
        adjusted_q_value=float(row["adjusted_q_value"]),
        sample_size=int(row["sample_size"]),
        confidence_score=float(row["confidence_score"]),
        confidence_version=row["confidence_version"],
        test_config_version=row["test_config_version"],
        evidence_fingerprint=row["evidence_fingerprint"],
        window_start=datetime.fromisoformat(row["window_start"]),
        window_end=datetime.fromisoformat(row["window_end"]),
        confidence_components=dict(row["confidence_components"]),
        test_metadata=dict(row["test_metadata"]),
    )
