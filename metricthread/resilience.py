from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from typing import Iterable
from uuid import UUID, uuid5

import numpy as np
import pandas as pd

from metricthread.signals import (
    DECLARED_NEGATIVE_CONTROLS,
    MINIMUM_USABLE_OBSERVATIONS,
    SIGNIFICANCE_Q_THRESHOLD,
    DeterministicSignalEngine,
    MetricObservation,
    SignalEvidence,
)


RESILIENCE_NAMESPACE = UUID("0f4e8e95-c641-43a1-9d8d-8dd1fa5cb52f")
RESILIENCE_VERSION = "resilience_rolling_origin_v1"
BASELINE_MODEL_VERSION = "target_history_ols_v1"
AUGMENTED_MODEL_VERSION = "target_history_plus_source_ols_v1"
ORIGIN_COUNT = 4
MINIMUM_STABLE_ORIGINS = 3


@dataclass(frozen=True)
class ResilienceAssessment:
    id: UUID
    correlation_signal_id: UUID
    evidence_fingerprint: str
    resilience_version: str
    evaluation_config: dict[str, object]
    result: dict[str, object]
    recommendation_eligible: bool
    evaluated_at: datetime

    def as_row(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "correlation_signal_id": str(self.correlation_signal_id),
            "evidence_fingerprint": self.evidence_fingerprint,
            "resilience_version": self.resilience_version,
            "evaluation_config": self.evaluation_config,
            "result": self.result,
            "recommendation_eligible": self.recommendation_eligible,
            "evaluated_at": self.evaluated_at.isoformat(),
        }

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "signal_id": str(self.correlation_signal_id),
            "evidence_fingerprint": self.evidence_fingerprint,
            "version": self.resilience_version,
            "evaluation_config": self.evaluation_config,
            "recommendation_eligible": self.recommendation_eligible,
            "evaluated_at": self.evaluated_at.isoformat(),
            **self.result,
        }


class ResilienceStore:
    def latest_for_signal(self, signal_id: UUID) -> ResilienceAssessment | None:
        raise NotImplementedError

    def persist(self, assessment: ResilienceAssessment) -> None:
        raise NotImplementedError


class InMemoryResilienceStore(ResilienceStore):
    def __init__(self) -> None:
        self._assessments: dict[tuple[UUID, str, str], ResilienceAssessment] = {}

    def latest_for_signal(self, signal_id: UUID) -> ResilienceAssessment | None:
        matches = [
            assessment
            for assessment in self._assessments.values()
            if assessment.correlation_signal_id == signal_id
            and assessment.resilience_version == RESILIENCE_VERSION
        ]
        return max(matches, key=lambda assessment: assessment.evaluated_at) if matches else None

    def persist(self, assessment: ResilienceAssessment) -> None:
        self._assessments[
            (
                assessment.correlation_signal_id,
                assessment.resilience_version,
                assessment.evidence_fingerprint,
            )
        ] = assessment


def assess_signal_resilience(
    signal: SignalEvidence,
    observations: Iterable[MetricObservation],
    *,
    evaluated_at: datetime | None = None,
) -> ResilienceAssessment:
    """Evaluate a retained signal without changing the underlying evidence record."""

    source_observations = tuple(observations)
    timestamp = evaluated_at or datetime.now(timezone.utc)
    try:
        frame = _prepared_signal_frame(signal, source_observations)
        origin_indexes = _origin_indexes(len(frame), signal.lag_days)
    except ValueError as error:
        return _suppressed_assessment(signal, source_observations, timestamp, str(error))

    origins: list[dict[str, object]] = []
    for origin_index in origin_indexes:
        origin_at = frame.index[origin_index]
        train_observations = tuple(
            observation
            for observation in source_observations
            if observation.event_time.astimezone(timezone.utc).date() < origin_at.date()
        )
        try:
            report = DeterministicSignalEngine().analyze(train_observations)
            retained = _retained_in_report(signal, report.accepted)
            negative_controls = _negative_control_results(report.accepted)
            baseline_error, augmented_error = _forecast_errors(frame, origin_index, signal.lag_days)
        except (ValueError, np.linalg.LinAlgError) as error:
            return _suppressed_assessment(
                signal,
                source_observations,
                timestamp,
                f"rolling_origin_evaluation_failed:{type(error).__name__}",
            )
        origins.append(
            {
                "origin": origin_at.date().isoformat(),
                "training_event_count": len(train_observations),
                "candidate_count": report.candidate_count,
                "signal_retained": retained is not None,
                "adjusted_q_value": retained.adjusted_q_value if retained else None,
                "baseline_abs_error": baseline_error,
                "augmented_abs_error": augmented_error,
                "beats_target_history_baseline": bool(augmented_error < baseline_error),
                "negative_controls": negative_controls,
                "negative_controls_rejected": all(
                    control["status"] == "rejected" for control in negative_controls
                ),
            }
        )

    retained_windows = sum(bool(origin["signal_retained"]) for origin in origins)
    baseline_wins = sum(bool(origin["beats_target_history_baseline"]) for origin in origins)
    controls_rejected_windows = sum(bool(origin["negative_controls_rejected"]) for origin in origins)
    suppression_reasons = _suppression_reasons(
        retained_windows=retained_windows,
        baseline_wins=baseline_wins,
        controls_rejected_windows=controls_rejected_windows,
    )
    recommendation_eligible = not suppression_reasons
    input_data_digest = _frame_digest(frame)
    evaluation_config = _evaluation_config(signal)
    result = {
        "summary": {
            "origin_count": len(origins),
            "signal_retained_windows": retained_windows,
            "minimum_signal_retained_windows": MINIMUM_STABLE_ORIGINS,
            "baseline_wins": baseline_wins,
            "minimum_baseline_wins": MINIMUM_STABLE_ORIGINS,
            "negative_controls_rejected_windows": controls_rejected_windows,
            "negative_controls_required_windows": ORIGIN_COUNT,
            "input_data_digest": input_data_digest,
            "suppression_reasons": suppression_reasons,
        },
        "origins": origins,
    }
    return ResilienceAssessment(
        id=uuid5(
            RESILIENCE_NAMESPACE,
            f"{signal.id}:{RESILIENCE_VERSION}:{signal.evidence_fingerprint}:{input_data_digest}",
        ),
        correlation_signal_id=signal.id,
        evidence_fingerprint=signal.evidence_fingerprint,
        resilience_version=RESILIENCE_VERSION,
        evaluation_config=evaluation_config,
        result=result,
        recommendation_eligible=recommendation_eligible,
        evaluated_at=timestamp,
    )


def is_recommendation_eligible(
    signal: SignalEvidence, assessment: ResilienceAssessment | None
) -> bool:
    return bool(
        assessment
        and assessment.recommendation_eligible
        and assessment.evidence_fingerprint == signal.evidence_fingerprint
        and assessment.resilience_version == RESILIENCE_VERSION
    )


def _prepared_signal_frame(
    signal: SignalEvidence, observations: Iterable[MetricObservation]
) -> pd.DataFrame:
    source = _daily_series(
        observations,
        signal.domain_a,
        signal.metric_a,
        str(signal.test_metadata["source_preparation"]["transformation"]),
    )
    target = _daily_series(
        observations,
        signal.domain_b,
        signal.metric_b,
        str(signal.test_metadata["target_preparation"]["transformation"]),
    )
    frame = pd.concat([source.rename("source"), target.rename("target")], axis=1, join="inner").sort_index()
    if len(frame) < MINIMUM_USABLE_OBSERVATIONS + ORIGIN_COUNT:
        raise ValueError("insufficient_prepared_history_for_rolling_origins")
    if not frame.index.equals(pd.date_range(frame.index.min(), frame.index.max(), freq="D")):
        raise ValueError("non_contiguous_prepared_history")
    return frame


def _daily_series(
    observations: Iterable[MetricObservation], domain: str, metric_name: str, transformation: str
) -> pd.Series:
    daily_values: dict[date, float] = {}
    for observation in observations:
        if observation.domain != domain or observation.metric_name != metric_name:
            continue
        event_day = observation.event_time.astimezone(timezone.utc).date()
        if event_day in daily_values:
            raise ValueError(f"duplicate_daily_observation:{domain}.{metric_name}")
        if not isfinite(observation.value):
            raise ValueError(f"non_finite_observation:{domain}.{metric_name}")
        daily_values[event_day] = observation.value
    if not daily_values:
        raise ValueError(f"missing_metric_history:{domain}.{metric_name}")
    ordered_days = sorted(daily_values)
    expected_days = pd.date_range(ordered_days[0], ordered_days[-1], freq="D").date
    if tuple(expected_days) != tuple(ordered_days):
        raise ValueError(f"non_contiguous_metric_history:{domain}.{metric_name}")
    series = pd.Series(
        [daily_values[day] for day in ordered_days],
        index=pd.DatetimeIndex(ordered_days),
        dtype=float,
    )
    if transformation == "none":
        return series
    if transformation == "first_difference":
        return series.diff().dropna()
    raise ValueError(f"unsupported_signal_transformation:{transformation}")


def _origin_indexes(history_length: int, lag_days: int) -> tuple[int, ...]:
    first_origin = max(MINIMUM_USABLE_OBSERVATIONS, lag_days + 20)
    if history_length - first_origin < ORIGIN_COUNT:
        raise ValueError("insufficient_prepared_history_for_rolling_origins")
    origins = tuple(int(value) for value in np.linspace(first_origin, history_length - 1, ORIGIN_COUNT))
    if len(set(origins)) != ORIGIN_COUNT:
        raise ValueError("insufficient_distinct_rolling_origins")
    return origins


def _evaluation_config(signal: SignalEvidence) -> dict[str, object]:
    return {
        "resilience_version": RESILIENCE_VERSION,
        "origin_count": ORIGIN_COUNT,
        "minimum_stable_origins": MINIMUM_STABLE_ORIGINS,
        "minimum_training_observations": MINIMUM_USABLE_OBSERVATIONS,
        "baseline_model_version": BASELINE_MODEL_VERSION,
        "augmented_model_version": AUGMENTED_MODEL_VERSION,
        "negative_control_policy": "every_declared_control_must_be_rejected_at_every_origin",
        "evaluated_signal_config": {
            "test_config_version": signal.test_config_version,
            "bic_model_history_days": signal.lag_days,
            "source_transformation": signal.test_metadata["source_preparation"]["transformation"],
            "target_transformation": signal.test_metadata["target_preparation"]["transformation"],
        },
    }


def _retained_in_report(
    signal: SignalEvidence, accepted: Iterable[SignalEvidence]
) -> SignalEvidence | None:
    return next(
        (
            candidate
            for candidate in accepted
            if (
                candidate.domain_a,
                candidate.metric_a,
                candidate.domain_b,
                candidate.metric_b,
            )
            == (signal.domain_a, signal.metric_a, signal.domain_b, signal.metric_b)
            and candidate.adjusted_q_value <= SIGNIFICANCE_Q_THRESHOLD
        ),
        None,
    )


def _negative_control_results(accepted: Iterable[SignalEvidence]) -> list[dict[str, object]]:
    accepted_pairs = {
        (signal.domain_a, signal.metric_a, signal.domain_b, signal.metric_b) for signal in accepted
    }
    return [
        {
            "source": {"domain": domain_a, "metric": metric_a},
            "target": {"domain": domain_b, "metric": metric_b},
            "status": "accepted_regression"
            if (domain_a, metric_a, domain_b, metric_b) in accepted_pairs
            else "rejected",
        }
        for domain_a, metric_a, domain_b, metric_b in DECLARED_NEGATIVE_CONTROLS
    ]


def _forecast_errors(frame: pd.DataFrame, origin_index: int, lag_days: int) -> tuple[float, float]:
    target = frame["target"].to_numpy(dtype=float)
    source = frame["source"].to_numpy(dtype=float)
    baseline_prediction = _predict_target(target, source, origin_index, lag_days, include_source=False)
    augmented_prediction = _predict_target(target, source, origin_index, lag_days, include_source=True)
    actual = target[origin_index]
    return float(abs(actual - baseline_prediction)), float(abs(actual - augmented_prediction))


def _predict_target(
    target: np.ndarray, source: np.ndarray, origin_index: int, lag_days: int, *, include_source: bool
) -> float:
    if origin_index <= lag_days:
        raise ValueError("insufficient_training_rows_for_forecast")
    features: list[list[float]] = []
    outcomes: list[float] = []
    for index in range(lag_days, origin_index):
        row = [1.0, *target[index - lag_days : index][::-1]]
        if include_source:
            row.extend(source[index - lag_days : index][::-1])
        features.append(row)
        outcomes.append(target[index])
    coefficients, _, rank, _ = np.linalg.lstsq(np.asarray(features), np.asarray(outcomes), rcond=None)
    if rank < len(features[0]):
        raise ValueError("rank_deficient_rolling_origin_model")
    current_features = [1.0, *target[origin_index - lag_days : origin_index][::-1]]
    if include_source:
        current_features.extend(source[origin_index - lag_days : origin_index][::-1])
    prediction = float(np.dot(coefficients, np.asarray(current_features)))
    if not isfinite(prediction):
        raise ValueError("non_finite_rolling_origin_prediction")
    return prediction


def _suppression_reasons(
    *, retained_windows: int, baseline_wins: int, controls_rejected_windows: int
) -> list[str]:
    reasons: list[str] = []
    if retained_windows < MINIMUM_STABLE_ORIGINS:
        reasons.append("signal_not_retained_in_enough_origins")
    if baseline_wins < MINIMUM_STABLE_ORIGINS:
        reasons.append("does_not_consistently_beat_target_history_baseline")
    if controls_rejected_windows < ORIGIN_COUNT:
        reasons.append("negative_control_regression")
    return reasons


def _frame_digest(frame: pd.DataFrame) -> str:
    rows = [
        {
            "date": timestamp.date().isoformat(),
            "source": round(float(source), 10),
            "target": round(float(target), 10),
        }
        for timestamp, source, target in frame.itertuples()
    ]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _suppressed_assessment(
    signal: SignalEvidence,
    observations: Iterable[MetricObservation],
    timestamp: datetime,
    reason: str,
) -> ResilienceAssessment:
    observation_digest = hashlib.sha256(
        str(
            sorted(
                (
                    observation.domain,
                    observation.metric_name,
                    observation.event_time.isoformat(),
                    observation.value,
                )
                for observation in observations
            )
        ).encode()
    ).hexdigest()
    evaluation_config = _evaluation_config(signal)
    result = {
        "summary": {
            "origin_count": 0,
            "signal_retained_windows": 0,
            "minimum_signal_retained_windows": MINIMUM_STABLE_ORIGINS,
            "baseline_wins": 0,
            "minimum_baseline_wins": MINIMUM_STABLE_ORIGINS,
            "negative_controls_rejected_windows": 0,
            "negative_controls_required_windows": ORIGIN_COUNT,
            "input_data_digest": observation_digest,
            "suppression_reasons": [reason],
        },
        "origins": [],
    }
    return ResilienceAssessment(
        id=uuid5(
            RESILIENCE_NAMESPACE,
            f"{signal.id}:{RESILIENCE_VERSION}:{signal.evidence_fingerprint}:{observation_digest}",
        ),
        correlation_signal_id=signal.id,
        evidence_fingerprint=signal.evidence_fingerprint,
        resilience_version=RESILIENCE_VERSION,
        evaluation_config=evaluation_config,
        result=result,
        recommendation_eligible=False,
        evaluated_at=timestamp,
    )
