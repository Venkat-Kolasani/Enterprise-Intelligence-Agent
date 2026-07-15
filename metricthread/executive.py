from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

import numpy as np

from metricthread.insights import InsightRecord, InsightStore, RecommendationRecord
from metricthread.signals import MetricObservation, SignalEvidence, SignalRepository


SCENARIO_MODEL_VERSION = "synthetic_marketing_spend_ols_v1"
_HOLDOUT_DAYS = 30


@dataclass(frozen=True)
class BriefingRecord:
    id: UUID
    summary_text: str
    insight_ids: tuple[str, ...]
    generated_at: datetime

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "summary_text": self.summary_text,
            "insight_ids": list(self.insight_ids),
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True)
class ScenarioForecast:
    id: UUID
    correlation_signal_id: UUID
    input_change_percent: float
    horizon_days: int
    baseline_values: dict[str, list[float]]
    forecast_values: dict[str, list[float]]
    prediction_intervals: dict[str, list[dict[str, float]]]
    reliability_score: float
    model_version: str
    assumptions: dict[str, object]
    generated_at: datetime

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "input_metric": "marketing_spend",
            "input_change_percent": self.input_change_percent,
            "horizon_days": self.horizon_days,
            "baseline_values": self.baseline_values,
            "forecast_values": self.forecast_values,
            "prediction_intervals": self.prediction_intervals,
            "reliability_score": self.reliability_score,
            "model_version": self.model_version,
            "assumptions": self.assumptions,
            "supporting_signal_ids": [str(self.correlation_signal_id)],
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True)
class ChatResult:
    result: str
    answer: str
    insight_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]

    def as_public_dict(self) -> dict[str, object]:
        return {
            "result": self.result,
            "answer": self.answer,
            "insight_ids": list(self.insight_ids),
            "signal_ids": list(self.signal_ids),
        }


class ExecutiveStore(Protocol):
    def list_briefings(self) -> list[BriefingRecord]: ...

    def persist_briefing(self, briefing: BriefingRecord) -> None: ...

    def persist_forecast(self, forecast: ScenarioForecast) -> None: ...

    def list_forecasts(self) -> list[ScenarioForecast]: ...


class InMemoryExecutiveStore:
    """A deterministic store used by executive-workflow tests and local demonstrations."""

    def __init__(self) -> None:
        self._briefings: dict[UUID, BriefingRecord] = {}
        self._forecasts: dict[UUID, ScenarioForecast] = {}

    def list_briefings(self) -> list[BriefingRecord]:
        return sorted(self._briefings.values(), key=lambda briefing: briefing.generated_at, reverse=True)

    def persist_briefing(self, briefing: BriefingRecord) -> None:
        self._briefings[briefing.id] = briefing

    def persist_forecast(self, forecast: ScenarioForecast) -> None:
        self._forecasts[forecast.id] = forecast

    def list_forecasts(self) -> list[ScenarioForecast]:
        return sorted(self._forecasts.values(), key=lambda forecast: forecast.generated_at, reverse=True)


class BriefingService:
    def __init__(
        self,
        insight_store: InsightStore,
        executive_store: ExecutiveStore,
        signal_repository: SignalRepository,
    ) -> None:
        self._insight_store = insight_store
        self._executive_store = executive_store
        self._signal_repository = signal_repository

    def generate(self) -> BriefingRecord | None:
        previously_briefed = {
            insight_id
            for briefing in self._executive_store.list_briefings()
            for insight_id in briefing.insight_ids
        }
        accepted_signal_ids = {str(signal.id) for signal in self._signal_repository.list_accepted()}
        new_insights = [
            insight
            for insight in self._insight_store.list_insights()
            if str(insight.id) not in previously_briefed
            and set(insight.related_signal_ids).issubset(accepted_signal_ids)
        ]
        if not new_insights:
            return None

        recommendations = _recommendations_by_insight(self._insight_store.list_recommendations())
        briefing = BriefingRecord(
            id=uuid4(),
            summary_text=_briefing_summary(new_insights, recommendations),
            insight_ids=tuple(str(insight.id) for insight in new_insights),
            generated_at=datetime.now(timezone.utc),
        )
        self._executive_store.persist_briefing(briefing)
        return briefing


class GroundedChatService:
    def __init__(self, insight_store: InsightStore, signal_repository: SignalRepository) -> None:
        self._insight_store = insight_store
        self._signal_repository = signal_repository

    def answer(self, question: str, *, prior_insight_ids: tuple[str, ...] = ()) -> ChatResult:
        normalized_question = _normalize(question)
        persisted_signal_ids = {str(signal.id) for signal in self._signal_repository.list_accepted()}
        insights = [
            insight
            for insight in self._insight_store.list_insights()
            if set(insight.related_signal_ids).issubset(persisted_signal_ids)
        ]
        recommendations = _recommendations_by_insight(self._insight_store.list_recommendations())
        matching = [
            insight
            for insight in insights
            if _insight_matches_question(insight, recommendations.get(insight.id, []), normalized_question)
        ]
        if not matching and _is_evidence_follow_up(normalized_question):
            prior_ids = set(prior_insight_ids)
            matching = [insight for insight in insights if str(insight.id) in prior_ids]
        if not matching:
            return ChatResult(
                result="no_evidence",
                answer="No stored evidence supports that question in the synthetic live simulation.",
                insight_ids=(),
                signal_ids=(),
            )

        selected = matching[:2]
        answer_parts: list[str] = []
        for insight in selected:
            recommendation = recommendations.get(insight.id, [None])[0]
            recommendation_clause = ""
            if recommendation is not None:
                recommendation_clause = (
                    f" The human-controlled recommendation remains {recommendation.status}: "
                    f"{recommendation.recommendation_text}"
                )
            answer_parts.append(f"{insight.narrative_text}{recommendation_clause}")
        return ChatResult(
            result="answer",
            answer=" ".join(answer_parts),
            insight_ids=tuple(str(insight.id) for insight in selected),
            signal_ids=tuple(signal_id for insight in selected for signal_id in insight.related_signal_ids),
        )


class ScenarioForecastService:
    def __init__(self, signal_repository: SignalRepository, executive_store: ExecutiveStore) -> None:
        self._signal_repository = signal_repository
        self._executive_store = executive_store

    def forecast(self, *, input_change_percent: float, horizon_days: int) -> ScenarioForecast:
        if not -20 <= input_change_percent <= 20:
            raise ValueError("input_change_percent must be between -20 and 20")
        if not 1 <= horizon_days <= 7:
            raise ValueError("horizon_days must be between 1 and 7")

        supporting_signal = _marketing_spend_signal(self._signal_repository.list_accepted())
        series = _daily_metric_series(self._signal_repository.list_metric_observations())
        marketing_spend = series["marketing_spend"]
        recognized_revenue = series["recognized_revenue"]
        acquisition_cost = series["client_acquisition_cost"]
        referral_quality = series["partner_referral_quality"]

        revenue_model = _fit_revenue_model(marketing_spend, recognized_revenue)
        cac_model = _fit_cac_model(marketing_spend, referral_quality, acquisition_cost)
        spend_delta = float(marketing_spend[-1] * (input_change_percent / 100))
        baseline_values = {
            "recognized_revenue": _repeat(float(recognized_revenue[-1]), horizon_days),
            "client_acquisition_cost": _repeat(float(acquisition_cost[-1]), horizon_days),
        }
        forecast_values = {
            "recognized_revenue": [
                round(float(recognized_revenue[-1] + (revenue_model.marketing_coefficient * spend_delta if day >= 5 else 0)), 2)
                for day in range(1, horizon_days + 1)
            ],
            "client_acquisition_cost": [
                round(float(acquisition_cost[-1] + cac_model.marketing_coefficient * spend_delta), 2)
                for _ in range(horizon_days)
            ],
        }
        prediction_intervals = {
            "recognized_revenue": _prediction_intervals(forecast_values["recognized_revenue"], revenue_model.interval_half_width),
            "client_acquisition_cost": _prediction_intervals(forecast_values["client_acquisition_cost"], cac_model.interval_half_width),
        }
        reliability_score = _reliability_score(
            revenue_model,
            cac_model,
            revenue_baseline=float(recognized_revenue[-1]),
            cac_baseline=float(acquisition_cost[-1]),
        )
        forecast = ScenarioForecast(
            id=uuid4(),
            correlation_signal_id=supporting_signal.id,
            input_change_percent=round(float(input_change_percent), 2),
            horizon_days=horizon_days,
            baseline_values=baseline_values,
            forecast_values=forecast_values,
            prediction_intervals=prediction_intervals,
            reliability_score=reliability_score,
            model_version=SCENARIO_MODEL_VERSION,
            assumptions={
                "dataset": "synthetic live simulation",
                "other_drivers": "Held at their latest observed values.",
                "revenue_effect_timing": "Marketing-spend adjustment is applied from day 5 of the horizon.",
                "acquisition_cost_effect_timing": "Marketing-spend adjustment is applied within the forecast day.",
                "evidence_language": "Deterministic scenario forecast; not a causal guarantee.",
                "backtest": {
                    "holdout_days": _HOLDOUT_DAYS,
                    "recognized_revenue_rmse": round(revenue_model.rmse, 2),
                    "client_acquisition_cost_rmse": round(cac_model.rmse, 2),
                },
            },
            generated_at=datetime.now(timezone.utc),
        )
        self._executive_store.persist_forecast(forecast)
        return forecast


@dataclass(frozen=True)
class _FittedModel:
    marketing_coefficient: float
    rmse: float
    interval_half_width: float


def _briefing_summary(
    insights: list[InsightRecord], recommendations: dict[UUID, list[RecommendationRecord]]
) -> str:
    summary_parts = ["Executive briefing for the synthetic live simulation."]
    for insight in insights:
        recommendation = recommendations.get(insight.id, [None])[0]
        recommendation_text = "No recommendation record is available."
        if recommendation is not None:
            recommendation_text = f"Human-controlled next step: {recommendation.recommendation_text}"
        summary_parts.append(
            f"{insight.title} (confidence {insight.confidence_score:.1f}; signal IDs: "
            f"{', '.join(insight.related_signal_ids)}). {recommendation_text}"
        )
    return " ".join(summary_parts)


def _recommendations_by_insight(
    recommendations: list[RecommendationRecord],
) -> dict[UUID, list[RecommendationRecord]]:
    grouped: dict[UUID, list[RecommendationRecord]] = {}
    for recommendation in recommendations:
        grouped.setdefault(recommendation.insight_id, []).append(recommendation)
    return grouped


def _normalize(value: str) -> str:
    normalized = value.lower()
    aliases = {
        "cac": "client acquisition cost",
        "customer acquisition cost": "client acquisition cost",
        "partner quality": "partner referral quality",
    }
    for source, replacement in aliases.items():
        normalized = normalized.replace(source, replacement)
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _insight_matches_question(
    insight: InsightRecord,
    recommendations: list[RecommendationRecord],
    normalized_question: str,
) -> bool:
    if not normalized_question:
        return False
    searchable = " ".join(
        [
            insight.title,
            insight.narrative_text,
            " ".join(insight.domains),
            " ".join(insight.related_signal_ids),
            *[recommendation.recommendation_text for recommendation in recommendations],
        ]
    )
    normalized_searchable = _normalize(searchable)
    if any(identifier in normalized_question for identifier in (str(insight.id), *insight.related_signal_ids)):
        return True
    question_terms = {term for term in normalized_question.split() if len(term) >= 4}
    searchable_terms = set(normalized_searchable.split())
    return len(question_terms & searchable_terms) >= 2


def _is_evidence_follow_up(normalized_question: str) -> bool:
    return any(
        phrase in normalized_question
        for phrase in (
            "what action",
            "what should",
            "what next",
            "tell me more",
            "that insight",
            "that signal",
        )
    )


def _marketing_spend_signal(signals: list[SignalEvidence]) -> SignalEvidence:
    for signal in signals:
        if signal.metric_a == "marketing_spend":
            return signal
    raise ValueError("No accepted marketing_spend signal is available to support this scenario")


def _daily_metric_series(observations: list[MetricObservation]) -> dict[str, np.ndarray]:
    grouped: dict[str, list[MetricObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.metric_name, []).append(observation)
    required = {"marketing_spend", "recognized_revenue", "client_acquisition_cost", "partner_referral_quality"}
    missing = required - grouped.keys()
    if missing:
        raise ValueError(f"Scenario data is missing required metrics: {', '.join(sorted(missing))}")

    output: dict[str, np.ndarray] = {}
    expected_days: tuple[datetime, ...] | None = None
    for metric_name in required:
        entries = sorted(grouped[metric_name], key=lambda observation: observation.event_time)
        days = tuple(observation.event_time for observation in entries)
        if expected_days is None:
            expected_days = days
        elif days != expected_days:
            raise ValueError("Scenario metrics must share one complete daily window")
        output[metric_name] = np.asarray([observation.value for observation in entries], dtype=float)
    if len(output["marketing_spend"]) < _HOLDOUT_DAYS + 60:
        raise ValueError("Scenario requires at least 90 daily observations")
    return output


def _fit_revenue_model(marketing_spend: np.ndarray, recognized_revenue: np.ndarray) -> _FittedModel:
    lag = 5
    features = marketing_spend[:-lag, np.newaxis]
    target = recognized_revenue[lag:]
    return _fit_model(features, target, marketing_column=0)


def _fit_cac_model(
    marketing_spend: np.ndarray,
    referral_quality: np.ndarray,
    acquisition_cost: np.ndarray,
) -> _FittedModel:
    lag = 3
    day_index = np.arange(lag, len(acquisition_cost), dtype=float)
    features = np.column_stack((marketing_spend[lag:], referral_quality[:-lag], day_index))
    target = acquisition_cost[lag:]
    return _fit_model(features, target, marketing_column=0)


def _fit_model(features: np.ndarray, target: np.ndarray, *, marketing_column: int) -> _FittedModel:
    if len(target) <= _HOLDOUT_DAYS + 20:
        raise ValueError("Scenario backtest has insufficient observations")
    split = len(target) - _HOLDOUT_DAYS
    train_features, holdout_features = features[:split], features[split:]
    train_target, holdout_target = target[:split], target[split:]
    train_design = np.column_stack((np.ones(len(train_features)), train_features))
    holdout_design = np.column_stack((np.ones(len(holdout_features)), holdout_features))
    train_coefficients, *_ = np.linalg.lstsq(train_design, train_target, rcond=None)
    holdout_predictions = holdout_design @ train_coefficients
    rmse = float(np.sqrt(np.mean((holdout_target - holdout_predictions) ** 2)))

    full_design = np.column_stack((np.ones(len(features)), features))
    full_coefficients, *_ = np.linalg.lstsq(full_design, target, rcond=None)
    residuals = target - (full_design @ full_coefficients)
    interval_half_width = max(float(np.sqrt(np.mean(residuals**2)) * 1.96), 0.01)
    return _FittedModel(
        marketing_coefficient=float(full_coefficients[marketing_column + 1]),
        rmse=rmse,
        interval_half_width=interval_half_width,
    )


def _prediction_intervals(values: list[float], half_width: float) -> list[dict[str, float]]:
    return [
        {"lower": round(value - half_width, 2), "upper": round(value + half_width, 2)}
        for value in values
    ]


def _reliability_score(
    revenue_model: _FittedModel,
    cac_model: _FittedModel,
    *,
    revenue_baseline: float,
    cac_baseline: float,
) -> float:
    model_pairs = (
        (revenue_model, revenue_baseline),
        (cac_model, cac_baseline),
    )
    components: list[float] = []
    for model, baseline in model_pairs:
        denominator = max(abs(baseline), 1.0)
        accuracy = max(0.0, 1 - (model.rmse / denominator))
        interval_compactness = max(0.0, 1 - ((2 * model.interval_half_width) / denominator))
        components.append(0.60 * accuracy + 0.40 * interval_compactness)
    return round(100 * float(np.mean(components)), 2)


def _repeat(value: float, count: int) -> list[float]:
    return [round(value, 2) for _ in range(count)]
