from __future__ import annotations

from datetime import timezone
from typing import Iterable
from uuid import UUID

from metricthread.insights import FORBIDDEN_CAUSAL_LANGUAGE, InsightRecord, InsightStore, evidence_packet_for_signal
from metricthread.signals import (
    CANDIDATE_FAMILY_VERSION,
    DECLARED_NEGATIVE_CONTROLS,
    SIGNIFICANCE_Q_THRESHOLD,
    DeterministicSignalEngine,
    MetricObservation,
    RejectedCandidate,
    SignalEvidence,
    SignalRepository,
)


CONFIDENCE_WEIGHTS = {
    "adjusted_significance": 0.40,
    "incremental_effect": 0.25,
    "sample_adequacy": 0.20,
    "recency": 0.15,
}
def build_signal_casefile(
    signal_id: UUID,
    signal_repository: SignalRepository,
    insight_store: InsightStore,
) -> dict[str, object]:
    """Build an inspectable, non-mutating evidence record for one active signal."""

    accepted_signals = signal_repository.list_accepted()
    signal = _active_signal(signal_id, accepted_signals)
    observations = signal_repository.list_metric_observations()
    report = DeterministicSignalEngine().analyze(observations)
    recomputed_signal = next(
        (
            candidate
            for candidate in report.accepted
            if candidate.evidence_fingerprint == signal.evidence_fingerprint
        ),
        None,
    )
    linked_claims = _linked_claims(signal, accepted_signals, insight_store.list_insights())

    return {
        "simulation_label": "synthetic live simulation",
        "evidence_language": "Predictive lead-lag evidence; not proof of causation.",
        "casefile": {
            "signal": signal.as_public_dict(),
            "recomputation": {
                "state": "matches_persisted_evidence" if recomputed_signal else "not_in_current_recomputation",
                "evidence_fingerprint": signal.evidence_fingerprint,
                "current_candidate_family_version": CANDIDATE_FAMILY_VERSION,
            },
            "replay": {
                "source": _series_replay(observations, signal.domain_a, signal.metric_a),
                "target": _series_replay(observations, signal.domain_b, signal.metric_b),
            },
            "test_family": {
                "candidate_count": report.candidate_count,
                "retained_count": len(report.accepted),
                "rejected_count": len(report.rejected),
                "adjusted_q_threshold": SIGNIFICANCE_Q_THRESHOLD,
                "candidate_family_version": CANDIDATE_FAMILY_VERSION,
                "declared_negative_controls": _negative_controls(report.rejected),
            },
            "model_evidence_packet": evidence_packet_for_signal(signal),
            "claim_audit": {
                "citation_checks": linked_claims,
                "confidence": _confidence_audit(signal, linked_claims),
                "causal_language_guard": {
                    "forbidden_terms": list(FORBIDDEN_CAUSAL_LANGUAGE),
                    "required_evidence_language": [
                        "predictive lead-lag relationship",
                        "evidence is consistent with",
                    ],
                    "outcome": "server_side_narrative_validation_required",
                },
            },
        },
    }


def _active_signal(signal_id: UUID, signals: Iterable[SignalEvidence]) -> SignalEvidence:
    for signal in signals:
        if signal.id == signal_id:
            return signal
    raise LookupError("Active signal was not found")


def _series_replay(
    observations: Iterable[MetricObservation], domain: str, metric_name: str
) -> dict[str, object]:
    daily_values: dict[str, float] = {}
    for observation in observations:
        if observation.domain != domain or observation.metric_name != metric_name:
            continue
        # The signal engine aligns observations by UTC day, so the replay must
        # use the same boundary even when an upstream source supplies an offset.
        event_day = observation.event_time.astimezone(timezone.utc).date().isoformat()
        if event_day in daily_values:
            raise ValueError(f"Casefile replay has duplicate daily data for {domain}.{metric_name}")
        daily_values[event_day] = observation.value

    if not daily_values:
        raise ValueError(f"Casefile replay is missing data for {domain}.{metric_name}")

    return {
        "domain": domain,
        "metric": metric_name,
        "points": [
            {"date": event_day, "value": daily_values[event_day]}
            for event_day in sorted(daily_values)
        ],
    }


def _negative_controls(rejections: Iterable[RejectedCandidate]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for domain_a, metric_a, domain_b, metric_b in DECLARED_NEGATIVE_CONTROLS:
        rejection = next(
            (
                candidate
                for candidate in rejections
                if (
                    candidate.domain_a,
                    candidate.metric_a,
                    candidate.domain_b,
                    candidate.metric_b,
                )
                == (domain_a, metric_a, domain_b, metric_b)
            ),
            None,
        )
        records.append(
            {
                "source": {"domain": domain_a, "metric": metric_a},
                "target": {"domain": domain_b, "metric": metric_b},
                "status": "rejected" if rejection else "not_observed_in_current_test_family",
                "reason": rejection.reason if rejection else None,
                "granger_p_value": rejection.granger_p_value if rejection else None,
                "adjusted_q_value": rejection.adjusted_q_value if rejection else None,
            }
        )
    return records


def _linked_claims(
    signal: SignalEvidence,
    accepted_signals: Iterable[SignalEvidence],
    insights: Iterable[InsightRecord],
) -> list[dict[str, object]]:
    accepted_ids = {str(candidate.id) for candidate in accepted_signals}
    signal_id = str(signal.id)
    claims: list[dict[str, object]] = []
    for insight in insights:
        cited_signal_ids = list(insight.related_signal_ids)
        if signal_id not in cited_signal_ids:
            continue
        unknown_signal_ids = sorted(set(cited_signal_ids).difference(accepted_ids))
        claims.append(
            {
                "insight_id": str(insight.id),
                "cited_signal_ids": cited_signal_ids,
                "cites_casefile_signal": True,
                "unknown_cited_signal_ids": unknown_signal_ids,
                "confidence_matches_casefile": insight.confidence_score == signal.confidence_score,
            }
        )
    return claims


def _confidence_audit(signal: SignalEvidence, linked_claims: Iterable[dict[str, object]]) -> dict[str, object]:
    recomputed_score = round(
        100
        * sum(
            CONFIDENCE_WEIGHTS[component] * signal.confidence_components[component]
            for component in CONFIDENCE_WEIGHTS
        ),
        2,
    )
    checks = list(linked_claims)
    return {
        "score": signal.confidence_score,
        "version": signal.confidence_version,
        "components": signal.confidence_components,
        "weights": CONFIDENCE_WEIGHTS,
        "recomputed_score": recomputed_score,
        "matches_deterministic_formula": recomputed_score == signal.confidence_score,
        "model_may_change_score": False,
        "all_persisted_claims_match": all(
            bool(check["confidence_matches_casefile"]) for check in checks
        ),
    }
