from __future__ import annotations

import hashlib
import json
import warnings
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from io import StringIO
from math import isfinite, log10
from typing import Iterable, Protocol
from uuid import UUID, uuid5

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import adfuller, grangercausalitytests
from statsmodels.tsa.vector_ar.var_model import VAR

from metricthread.generator import MetricEvent


SIGNAL_NAMESPACE = UUID("63d6733e-b54d-464c-82bb-33e6fa38febb")
MINIMUM_USABLE_OBSERVATIONS = 60
MAXIMUM_LAG_DAYS = 7
STATIONARITY_ALPHA = 0.05
SIGNIFICANCE_Q_THRESHOLD = 0.05
TEST_CONFIG_VERSION = "granger_bic_bh_v1"
CONFIDENCE_VERSION = "confidence_v1"
CANDIDATE_FAMILY_VERSION = "cross_domain_all_metrics_v1"


@dataclass(frozen=True)
class MetricObservation:
    domain: str
    metric_name: str
    value: float
    event_time: datetime


@dataclass(frozen=True)
class PreparedSeries:
    domain: str
    metric_name: str
    values: pd.Series
    raw_adf_p_value: float
    prepared_adf_p_value: float
    transformation: str


@dataclass(frozen=True)
class SignalEvidence:
    id: UUID
    domain_a: str
    metric_a: str
    domain_b: str
    metric_b: str
    lag_days: int
    correlation_coefficient: float
    effect_size: float
    direction: str
    f_statistic: float
    granger_p_value: float
    adjusted_q_value: float
    sample_size: int
    confidence_score: float
    confidence_version: str
    test_config_version: str
    evidence_fingerprint: str
    window_start: datetime
    window_end: datetime
    confidence_components: dict[str, float]
    test_metadata: dict[str, object]

    def as_row(self) -> dict[str, object]:
        row = asdict(self)
        row["id"] = str(self.id)
        row["window_start"] = self.window_start.isoformat()
        row["window_end"] = self.window_end.isoformat()
        return row

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "source": {"domain": self.domain_a, "metric": self.metric_a},
            "target": {"domain": self.domain_b, "metric": self.metric_b},
            "bic_model_history_days": self.lag_days,
            "correlation_coefficient": self.correlation_coefficient,
            "effect_size": self.effect_size,
            "direction": self.direction,
            "f_statistic": self.f_statistic,
            "granger_p_value": self.granger_p_value,
            "adjusted_q_value": self.adjusted_q_value,
            "sample_size": self.sample_size,
            "confidence_score": self.confidence_score,
            "confidence_version": self.confidence_version,
            "test_config_version": self.test_config_version,
            "evidence_fingerprint": self.evidence_fingerprint,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "confidence_components": self.confidence_components,
            "test_metadata": self.test_metadata,
        }


@dataclass(frozen=True)
class RejectedCandidate:
    domain_a: str
    metric_a: str
    domain_b: str
    metric_b: str
    reason: str
    granger_p_value: float | None = None
    adjusted_q_value: float | None = None


@dataclass(frozen=True)
class SignalAnalysisReport:
    accepted: tuple[SignalEvidence, ...]
    rejected: tuple[RejectedCandidate, ...]
    candidate_count: int


class SignalRepository(Protocol):
    def list_accepted(self) -> list[SignalEvidence]: ...

    def run_analysis(self) -> SignalAnalysisReport: ...


class InMemorySignalRepository:
    """A deterministic repository used by API tests and local demonstrations."""

    def __init__(self, observations: Iterable[MetricObservation]) -> None:
        self._observations = tuple(observations)
        self._signals: dict[str, SignalEvidence] = {}

    def list_accepted(self) -> list[SignalEvidence]:
        return sorted(self._signals.values(), key=lambda signal: signal.confidence_score, reverse=True)

    def run_analysis(self) -> SignalAnalysisReport:
        report = DeterministicSignalEngine().analyze(self._observations)
        self._signals = {signal.evidence_fingerprint: signal for signal in report.accepted}
        return report


@dataclass(frozen=True)
class _Candidate:
    source: PreparedSeries
    target: PreparedSeries
    aligned: pd.DataFrame
    selected_lag: int
    f_statistic: float
    p_value: float
    sample_size: int
    effect_size: float
    correlation: float
    input_data_digest: str


def observations_from_metric_events(events: Iterable[MetricEvent]) -> list[MetricObservation]:
    return [
        MetricObservation(
            domain=event.domain,
            metric_name=event.metric_name,
            value=event.value,
            event_time=event.event_time,
        )
        for event in events
    ]


class DeterministicSignalEngine:
    """Auditable cross-domain predictive lead-lag detection for daily metric data."""

    def __init__(self, *, as_of: date | None = None) -> None:
        self._as_of = as_of

    def analyze(self, observations: Iterable[MetricObservation]) -> SignalAnalysisReport:
        prepared, invalid = self._prepare_series(observations)
        candidates: list[_Candidate] = []
        rejected: list[RejectedCandidate] = list(invalid)

        for source in prepared:
            for target in prepared:
                if source.domain == target.domain:
                    continue
                candidate_or_rejection = self._test_candidate(source, target)
                if isinstance(candidate_or_rejection, RejectedCandidate):
                    rejected.append(candidate_or_rejection)
                else:
                    candidates.append(candidate_or_rejection)

        if not candidates:
            return SignalAnalysisReport(accepted=(), rejected=tuple(rejected), candidate_count=0)

        _, adjusted_q_values, _, _ = multipletests(
            [candidate.p_value for candidate in candidates],
            alpha=SIGNIFICANCE_Q_THRESHOLD,
            method="fdr_bh",
        )
        accepted: list[SignalEvidence] = []
        for candidate, q_value in zip(candidates, adjusted_q_values, strict=True):
            q_value = float(q_value)
            if q_value > SIGNIFICANCE_Q_THRESHOLD:
                rejected.append(
                    RejectedCandidate(
                        domain_a=candidate.source.domain,
                        metric_a=candidate.source.metric_name,
                        domain_b=candidate.target.domain,
                        metric_b=candidate.target.metric_name,
                        reason="failed_benjamini_hochberg_threshold",
                        granger_p_value=candidate.p_value,
                        adjusted_q_value=q_value,
                    )
                )
                continue
            accepted.append(self._evidence_for(candidate, q_value))

        return SignalAnalysisReport(
            accepted=tuple(sorted(accepted, key=lambda signal: signal.confidence_score, reverse=True)),
            rejected=tuple(rejected),
            candidate_count=len(candidates),
        )

    def _prepare_series(
        self, observations: Iterable[MetricObservation]
    ) -> tuple[list[PreparedSeries], list[RejectedCandidate]]:
        grouped: dict[tuple[str, str], list[MetricObservation]] = {}
        for observation in observations:
            if not isfinite(observation.value):
                continue
            grouped.setdefault((observation.domain, observation.metric_name), []).append(observation)

        prepared: list[PreparedSeries] = []
        rejected: list[RejectedCandidate] = []
        for (domain, metric_name), values in sorted(grouped.items()):
            series_or_reason = self._daily_series(values)
            if isinstance(series_or_reason, str):
                rejected.append(
                    RejectedCandidate(domain, metric_name, "", "", f"invalid_daily_series:{series_or_reason}")
                )
                continue
            try:
                prepared.append(self._make_stationary(domain, metric_name, series_or_reason))
            except ValueError as error:
                rejected.append(
                    RejectedCandidate(domain, metric_name, "", "", f"stationarity_rejected:{error}")
                )
        return prepared, rejected

    @staticmethod
    def _daily_series(observations: list[MetricObservation]) -> pd.Series | str:
        daily_values: dict[date, float] = {}
        for observation in observations:
            event_day = observation.event_time.astimezone(timezone.utc).date()
            if event_day in daily_values:
                return "duplicate_day"
            daily_values[event_day] = observation.value
        if not daily_values:
            return "no_finite_values"

        ordered_days = sorted(daily_values)
        expected_days = pd.date_range(ordered_days[0], ordered_days[-1], freq="D").date
        if tuple(expected_days) != tuple(ordered_days):
            return "missing_day"
        return pd.Series(
            [daily_values[day] for day in ordered_days],
            index=pd.DatetimeIndex(ordered_days),
            dtype=float,
        )

    @staticmethod
    def _adf_p_value(series: pd.Series) -> float:
        if len(series) < MINIMUM_USABLE_OBSERVATIONS:
            raise ValueError("fewer_than_minimum_observations")
        maximum_adf_lag = min(MAXIMUM_LAG_DAYS, max(0, len(series) // 2 - 5))
        return float(adfuller(series.to_numpy(), maxlag=maximum_adf_lag, autolag="BIC", regression="c")[1])

    def _make_stationary(self, domain: str, metric_name: str, series: pd.Series) -> PreparedSeries:
        raw_adf_p_value = self._adf_p_value(series)
        if raw_adf_p_value <= STATIONARITY_ALPHA:
            return PreparedSeries(
                domain=domain,
                metric_name=metric_name,
                values=series,
                raw_adf_p_value=raw_adf_p_value,
                prepared_adf_p_value=raw_adf_p_value,
                transformation="none",
            )

        differenced = series.diff().dropna()
        prepared_adf_p_value = self._adf_p_value(differenced)
        if prepared_adf_p_value > STATIONARITY_ALPHA:
            raise ValueError("non_stationary_after_first_difference")
        return PreparedSeries(
            domain=domain,
            metric_name=metric_name,
            values=differenced,
            raw_adf_p_value=raw_adf_p_value,
            prepared_adf_p_value=prepared_adf_p_value,
            transformation="first_difference",
        )

    def _test_candidate(self, source: PreparedSeries, target: PreparedSeries) -> _Candidate | RejectedCandidate:
        aligned = pd.concat(
            [target.values.rename("target"), source.values.rename("source")], axis=1, join="inner"
        ).sort_index()
        if not self._has_contiguous_days(aligned.index):
            return self._reject(source, target, "non_contiguous_aligned_window")
        if len(aligned) < MINIMUM_USABLE_OBSERVATIONS:
            return self._reject(source, target, "fewer_than_minimum_aligned_observations")

        try:
            selected_lag = int(VAR(aligned[["target", "source"]].to_numpy()).select_order(
                maxlags=MAXIMUM_LAG_DAYS,
                trend="c",
            ).selected_orders["bic"])
        except (ValueError, np.linalg.LinAlgError) as error:
            return self._reject(source, target, f"bic_selection_failed:{type(error).__name__}")
        if selected_lag <= 0:
            return self._reject(source, target, "bic_selected_zero_lags")

        values = aligned[["target", "source"]].to_numpy()
        try:
            with warnings.catch_warnings(), redirect_stdout(StringIO()):
                warnings.filterwarnings("ignore", message="verbose is deprecated", category=FutureWarning)
                results = grangercausalitytests(values, maxlag=[selected_lag], addconst=True, verbose=False)
            test_results, models = results[selected_lag]
            f_statistic, p_value, _, _ = test_results["ssr_ftest"]
            restricted_model, unrestricted_model, _ = models
        except (ValueError, np.linalg.LinAlgError) as error:
            return self._reject(source, target, f"granger_test_failed:{type(error).__name__}")

        sample_size = int(unrestricted_model.nobs)
        effect_size = max(0.0, float(unrestricted_model.rsquared - restricted_model.rsquared))
        source_values = aligned["source"].to_numpy()
        target_values = aligned["target"].to_numpy()
        correlation = float(np.corrcoef(source_values[:-selected_lag], target_values[selected_lag:])[0, 1])
        if not isfinite(correlation):
            return self._reject(source, target, "undefined_lagged_correlation")

        return _Candidate(
            source=source,
            target=target,
            aligned=aligned,
            selected_lag=selected_lag,
            f_statistic=float(f_statistic),
            p_value=float(p_value),
            sample_size=sample_size,
            effect_size=effect_size,
            correlation=correlation,
            input_data_digest=self._input_data_digest(aligned),
        )

    @staticmethod
    def _has_contiguous_days(index: pd.DatetimeIndex) -> bool:
        if index.empty:
            return False
        expected = pd.date_range(index.min(), index.max(), freq="D")
        return index.equals(expected)

    @staticmethod
    def _reject(source: PreparedSeries, target: PreparedSeries, reason: str) -> RejectedCandidate:
        return RejectedCandidate(source.domain, source.metric_name, target.domain, target.metric_name, reason)

    @staticmethod
    def _input_data_digest(aligned: pd.DataFrame) -> str:
        payload = [
            {
                "date": timestamp.date().isoformat(),
                "source": round(float(source), 10),
                "target": round(float(target), 10),
            }
            for timestamp, target, source in aligned.itertuples()
        ]
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _evidence_for(self, candidate: _Candidate, q_value: float) -> SignalEvidence:
        window_start = _date_as_utc(candidate.aligned.index.min().date())
        window_end = _date_as_utc(candidate.aligned.index.max().date())
        confidence_components = self._confidence_components(candidate, q_value, window_end.date())
        confidence_score = round(
            100
            * (
                0.40 * confidence_components["adjusted_significance"]
                + 0.25 * confidence_components["incremental_effect"]
                + 0.20 * confidence_components["sample_adequacy"]
                + 0.15 * confidence_components["recency"]
            ),
            2,
        )
        metadata: dict[str, object] = {
            "candidate_family_version": CANDIDATE_FAMILY_VERSION,
            "source_preparation": {
                "raw_adf_p_value": candidate.source.raw_adf_p_value,
                "prepared_adf_p_value": candidate.source.prepared_adf_p_value,
                "transformation": candidate.source.transformation,
            },
            "target_preparation": {
                "raw_adf_p_value": candidate.target.raw_adf_p_value,
                "prepared_adf_p_value": candidate.target.prepared_adf_p_value,
                "transformation": candidate.target.transformation,
            },
            "bic_selected_lag_order": candidate.selected_lag,
            "model_observations": candidate.sample_size,
            "input_data_digest": candidate.input_data_digest,
            "lag_interpretation": "BIC-selected model history, not a causal delay claim",
        }
        fingerprint_payload = {
            "test_config_version": TEST_CONFIG_VERSION,
            "source": {"domain": candidate.source.domain, "metric": candidate.source.metric_name},
            "target": {"domain": candidate.target.domain, "metric": candidate.target.metric_name},
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "f_statistic": round(candidate.f_statistic, 10),
            "p_value": round(candidate.p_value, 100),
            "q_value": round(q_value, 100),
            "effect_size": round(candidate.effect_size, 10),
            "metadata": metadata,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        return SignalEvidence(
            id=uuid5(SIGNAL_NAMESPACE, fingerprint),
            domain_a=candidate.source.domain,
            metric_a=candidate.source.metric_name,
            domain_b=candidate.target.domain,
            metric_b=candidate.target.metric_name,
            lag_days=candidate.selected_lag,
            correlation_coefficient=round(candidate.correlation, 6),
            effect_size=round(candidate.effect_size, 6),
            direction="positive" if candidate.correlation >= 0 else "negative",
            f_statistic=round(candidate.f_statistic, 6),
            granger_p_value=candidate.p_value,
            adjusted_q_value=q_value,
            sample_size=candidate.sample_size,
            confidence_score=confidence_score,
            confidence_version=CONFIDENCE_VERSION,
            test_config_version=TEST_CONFIG_VERSION,
            evidence_fingerprint=fingerprint,
            window_start=window_start,
            window_end=window_end,
            confidence_components=confidence_components,
            test_metadata=metadata,
        )

    def _confidence_components(self, candidate: _Candidate, q_value: float, window_end: date) -> dict[str, float]:
        as_of = self._as_of or window_end
        age_days = max(0, (as_of - window_end).days)
        return {
            "adjusted_significance": round(min(-log10(max(q_value, 1e-300)) / 4, 1.0), 6),
            "incremental_effect": round(min(candidate.effect_size / 0.25, 1.0), 6),
            "sample_adequacy": round(min(candidate.sample_size / 180, 1.0), 6),
            "recency": round(max(0.0, 1 - age_days / 180), 6),
        }


def _date_as_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)
