from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv

from metricthread.signals import SignalEvidence, SignalRepository
from metricthread.resilience import ResilienceStore, is_recommendation_eligible


FORBIDDEN_CAUSAL_LANGUAGE = ("root cause", "proves", "proof", "caused", "causes")
RECOMMENDATION_STATUSES = frozenset({"proposed", "planned", "implemented"})
RECOMMENDATION_TRANSITIONS = {
    "proposed": frozenset({"planned"}),
    "planned": frozenset({"implemented"}),
    "implemented": frozenset(),
}


@dataclass(frozen=True)
class GroundedNarrative:
    signal_id: str
    title: str
    narrative: str
    recommendation: str
    predicted_impact: str
    evidence_signal_ids: tuple[str, ...]


@dataclass(frozen=True)
class InsightRecord:
    id: UUID
    title: str
    narrative_text: str
    related_signal_ids: tuple[str, ...]
    confidence_score: float
    domains: tuple[str, ...]
    status: str
    generated_at: datetime

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "title": self.title,
            "narrative_text": self.narrative_text,
            "related_signal_ids": list(self.related_signal_ids),
            "confidence_score": self.confidence_score,
            "domains": list(self.domains),
            "status": self.status,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True)
class RecommendationRecord:
    id: UUID
    insight_id: UUID
    recommendation_text: str
    predicted_impact: dict[str, object]
    confidence_score: float
    status: str
    created_at: datetime
    outcome: dict[str, object] | None = None

    def as_public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "insight_id": str(self.insight_id),
            "recommendation_text": self.recommendation_text,
            "predicted_impact": self.predicted_impact,
            "confidence_score": self.confidence_score,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class GeneratedInsight:
    insight: InsightRecord
    recommendation: RecommendationRecord
    source_signal: SignalEvidence


class InsightStore(Protocol):
    def list_insights(self) -> list[InsightRecord]: ...

    def list_recommendations(self) -> list[RecommendationRecord]: ...

    def persist_generated(self, insight: InsightRecord, recommendation: RecommendationRecord) -> None: ...

    def update_recommendation_status(self, recommendation_id: UUID, status: str) -> RecommendationRecord: ...

    def record_outcome(
        self,
        recommendation_id: UUID,
        *,
        implemented_at: datetime,
        outcome_metric: str,
        outcome_value: float,
        measured_at: datetime,
        notes: str,
    ) -> RecommendationRecord: ...


class NarrativeGenerator(Protocol):
    def generate(self, signal: SignalEvidence) -> GroundedNarrative: ...


class OpenAIResponsesNarrativeGenerator:
    """Calls the Responses API only after a cost-free model availability preflight."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, signal: SignalEvidence) -> GroundedNarrative:
        self._validate_model()
        signal_id = str(signal.id)
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers=self._headers,
            json={
                "model": self._model,
                "store": False,
                "reasoning": {"effort": "low"},
                "max_output_tokens": 450,
                "input": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(evidence_packet_for_signal(signal), separators=(",", ":"), sort_keys=True),
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "grounded_recommendation",
                        "strict": True,
                        "schema": _narrative_schema(signal_id),
                    }
                },
            },
            timeout=45.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"OpenAI grounded recommendation request failed: {_http_error_detail(error)}") from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"OpenAI grounded recommendation request failed: {error}") from error
        return _validate_narrative(_response_output_text(response.json()), signal_id)

    def _validate_model(self) -> None:
        response = httpx.get(
            f"https://api.openai.com/v1/models/{self._model}",
            headers={"Authorization": self._headers["Authorization"]},
            timeout=10.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"OpenAI model preflight failed for {self._model}: {_http_error_detail(error)}") from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"OpenAI model preflight failed for {self._model}: {error}") from error


class GeminiNarrativeGenerator:
    """Calls Gemini with structured output while preserving the same evidence boundary."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    def generate(self, signal: SignalEvidence) -> GroundedNarrative:
        self._validate_model()
        signal_id = str(signal.id)
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            headers=self._headers,
            json={
                "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": json.dumps(
                                    evidence_packet_for_signal(signal), separators=(",", ":"), sort_keys=True
                                )
                            }
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 450,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": _narrative_schema(signal_id),
                },
            },
            timeout=45.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"Gemini grounded recommendation request failed: {_http_error_detail(error)}") from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"Gemini grounded recommendation request failed: {error}") from error
        return _validate_narrative(_gemini_response_text(response.json()), signal_id)

    def _validate_model(self) -> None:
        response = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}",
            headers={"x-goog-api-key": self._api_key},
            timeout=10.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"Gemini model preflight failed for {self._model}: {_http_error_detail(error)}") from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"Gemini model preflight failed for {self._model}: {error}") from error


class InMemoryInsightStore:
    """Small deterministic store for API tests and local demonstrations."""

    def __init__(self) -> None:
        self._insights: dict[UUID, InsightRecord] = {}
        self._recommendations: dict[UUID, RecommendationRecord] = {}

    def list_insights(self) -> list[InsightRecord]:
        return sorted(self._insights.values(), key=lambda insight: insight.generated_at, reverse=True)

    def list_recommendations(self) -> list[RecommendationRecord]:
        return sorted(self._recommendations.values(), key=lambda recommendation: recommendation.created_at, reverse=True)

    def persist_generated(self, insight: InsightRecord, recommendation: RecommendationRecord) -> None:
        self._insights[insight.id] = insight
        self._recommendations[recommendation.id] = recommendation

    def update_recommendation_status(self, recommendation_id: UUID, status: str) -> RecommendationRecord:
        try:
            recommendation = self._recommendations[recommendation_id]
        except KeyError as error:
            raise LookupError("recommendation was not found") from error
        validate_recommendation_transition(recommendation.status, status)
        updated = replace(recommendation, status=status)
        self._recommendations[recommendation_id] = updated
        return updated

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
        try:
            recommendation = self._recommendations[recommendation_id]
        except KeyError as error:
            raise LookupError("recommendation was not found") from error
        if recommendation.status != "implemented":
            raise ValueError("recommendation must be implemented before recording an outcome")
        updated = replace(
            recommendation,
            outcome={
                "implemented_at": implemented_at.isoformat(),
                "outcome_metric": outcome_metric,
                "outcome_value": outcome_value,
                "measured_at": measured_at.isoformat(),
                "notes": notes,
            },
        )
        self._recommendations[recommendation_id] = updated
        return updated


class GroundedInsightService:
    def __init__(
        self,
        signal_repository: SignalRepository,
        insight_store: InsightStore,
        narrative_generator: NarrativeGenerator,
        resilience_store: ResilienceStore | None = None,
    ) -> None:
        self._signal_repository = signal_repository
        self._insight_store = insight_store
        self._narrative_generator = narrative_generator
        self._resilience_store = resilience_store

    def generate_next(self) -> GeneratedInsight | None:
        existing_signal_ids = {
            signal_id
            for insight in self._insight_store.list_insights()
            for signal_id in insight.related_signal_ids
        }
        pending = []
        for signal in self._signal_repository.list_accepted():
            if str(signal.id) in existing_signal_ids:
                continue
            if self._resilience_store is not None and not is_recommendation_eligible(
                signal, self._resilience_store.latest_for_signal(signal.id)
            ):
                continue
            pending.append(signal)
        if not pending:
            return None

        source_signal = pending[0]
        narrative = self._narrative_generator.generate(source_signal)
        if narrative.signal_id != str(source_signal.id):
            raise RuntimeError("Narrative response cited a signal outside the supplied evidence packet")
        if narrative.evidence_signal_ids != (str(source_signal.id),):
            raise RuntimeError("Narrative response must cite exactly the supplied persisted signal ID")

        now = datetime.now(timezone.utc)
        insight = InsightRecord(
            id=uuid4(),
            title=narrative.title,
            narrative_text=narrative.narrative,
            related_signal_ids=narrative.evidence_signal_ids,
            confidence_score=source_signal.confidence_score,
            domains=(source_signal.domain_a, source_signal.domain_b),
            status="active",
            generated_at=now,
        )
        recommendation = RecommendationRecord(
            id=uuid4(),
            insight_id=insight.id,
            recommendation_text=narrative.recommendation,
            predicted_impact={
                "statement": narrative.predicted_impact,
                "evidence_signal_ids": list(narrative.evidence_signal_ids),
                "human_review_required": True,
            },
            confidence_score=source_signal.confidence_score,
            status="proposed",
            created_at=now,
        )
        self._insight_store.persist_generated(insight, recommendation)
        return GeneratedInsight(insight=insight, recommendation=recommendation, source_signal=source_signal)


def narrative_generator_from_environment() -> NarrativeGenerator:
    load_dotenv()
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_REASONING_MODEL")
        if not api_key or not model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_REASONING_MODEL are required for grounded recommendations")
        return OpenAIResponsesNarrativeGenerator(api_key, model)
    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        model = os.environ.get("GEMINI_MODEL")
        if not api_key or not model:
            raise RuntimeError("GEMINI_API_KEY and GEMINI_MODEL are required for grounded recommendations")
        return GeminiNarrativeGenerator(api_key, model)
    raise RuntimeError("AI_PROVIDER must be 'openai' or 'gemini'")


def validate_recommendation_transition(current_status: str, next_status: str) -> None:
    if next_status not in RECOMMENDATION_STATUSES:
        raise ValueError(f"unsupported recommendation status: {next_status}")
    if next_status not in RECOMMENDATION_TRANSITIONS.get(current_status, frozenset()):
        raise ValueError(f"recommendation cannot transition from {current_status} to {next_status}")


def evidence_packet_for_signal(signal: SignalEvidence) -> dict[str, object]:
    return {
        "signal_id": str(signal.id),
        "source": {"domain": signal.domain_a, "metric": signal.metric_a},
        "target": {"domain": signal.domain_b, "metric": signal.metric_b},
        "direction": signal.direction,
        "correlation_coefficient": signal.correlation_coefficient,
        "effect_size_delta_r_squared": signal.effect_size,
        "f_statistic": signal.f_statistic,
        "adjusted_q_value": signal.adjusted_q_value,
        "sample_size": signal.sample_size,
        "confidence_score": signal.confidence_score,
        "bic_model_history_days": signal.lag_days,
        "lag_interpretation": signal.test_metadata["lag_interpretation"],
        "simulation_label": "synthetic live simulation",
    }


def _narrative_schema(signal_id: str) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "signal_id": {"type": "string", "enum": [signal_id]},
            "title": {"type": "string", "minLength": 1, "maxLength": 120},
            "narrative": {"type": "string", "minLength": 1, "maxLength": 900},
            "recommendation": {"type": "string", "minLength": 1, "maxLength": 500},
            "predicted_impact": {"type": "string", "minLength": 1, "maxLength": 500},
            "evidence_signal_ids": {
                "type": "array",
                "items": {"type": "string", "enum": [signal_id]},
                "minItems": 1,
                "maxItems": 1,
            },
        },
        "required": [
            "signal_id",
            "title",
            "narrative",
            "recommendation",
            "predicted_impact",
            "evidence_signal_ids",
        ],
        "additionalProperties": False,
    }


def _response_output_text(response: dict[str, object]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    return part["text"]
    raise RuntimeError("OpenAI response did not contain structured output text")


def _gemini_response_text(response: dict[str, object]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        raise RuntimeError("Gemini response did not contain a candidate")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]:
                return part["text"]
    raise RuntimeError("Gemini response did not contain structured output text")


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    response = error.response
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"HTTP {response.status_code}"
    error_payload = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error_payload, dict):
        return f"HTTP {response.status_code}"
    code = error_payload.get("code") or error_payload.get("type") or "unknown_error"
    message = str(error_payload.get("message", "OpenAI rejected the request"))
    return f"HTTP {response.status_code} {code}: {message}"


def _validate_narrative(output_text: str, signal_id: str) -> GroundedNarrative:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("Narrative structured response was not valid JSON") from error
    required_fields = {
        "signal_id",
        "title",
        "narrative",
        "recommendation",
        "predicted_impact",
        "evidence_signal_ids",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise RuntimeError("Narrative structured response did not match the grounded recommendation schema")
    if payload["signal_id"] != signal_id or payload["evidence_signal_ids"] != [signal_id]:
        raise RuntimeError("Narrative structured response cited unsupported evidence")
    text_fields = ("title", "narrative", "recommendation", "predicted_impact")
    if not all(isinstance(payload[field], str) and payload[field].strip() for field in text_fields):
        raise RuntimeError("Narrative structured response contained an empty narrative field")
    normalized = " ".join(payload[field].lower() for field in text_fields)
    forbidden_pattern = re.compile(r"\b(root cause|proves?|caused|causes)\b")
    allowed_evidence_language = "predictive" in normalized or "evidence is consistent with" in normalized
    if not allowed_evidence_language or forbidden_pattern.search(normalized):
        raise RuntimeError("Narrative structured response did not preserve the required evidence language")
    return GroundedNarrative(
        signal_id=signal_id,
        title=payload["title"].strip(),
        narrative=payload["narrative"].strip(),
        recommendation=payload["recommendation"].strip(),
        predicted_impact=payload["predicted_impact"].strip(),
        evidence_signal_ids=(signal_id,),
    )


_SYSTEM_PROMPT = """You are MetricThread's grounded enterprise recommendation narrator.
You receive exactly one persisted signal evidence packet from a synthetic live simulation.
Return only the required JSON object. Cite only its signal_id in evidence_signal_ids.
Use the phrase 'predictive lead-lag evidence' or 'evidence is consistent with' in your narrative.
Never claim causation, a root cause, proof, a guaranteed impact, or an exact business delay.
Do not invent metrics, events, numeric forecasts, or evidence beyond the packet.
Frame the recommendation as a human-reviewed proposal; it must not execute an external action.
"""
