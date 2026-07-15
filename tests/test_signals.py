from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
from statsmodels.tools.sm_exceptions import InfeasibleTestError

import metricthread.signals as signals_module
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.signals import (
    DeterministicSignalEngine,
    MetricObservation,
    PreparedSeries,
    RejectedCandidate,
    observations_from_metric_events,
)


def _observations() -> list[MetricObservation]:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    return observations_from_metric_events(dataset.events)


def test_corrected_granger_engine_accepts_the_primary_signal_and_rejects_declared_controls() -> None:
    report = DeterministicSignalEngine().analyze(_observations())
    accepted = {(signal.metric_a, signal.metric_b): signal for signal in report.accepted}

    assert report.candidate_count == 54
    assert set(accepted) == {
        ("partner_referral_quality", "client_acquisition_cost"),
        ("marketing_spend", "qualified_leads"),
        ("qualified_leads", "recognized_revenue"),
        ("partner_referral_volume", "client_acquisition_cost"),
    }

    primary = accepted[("partner_referral_quality", "client_acquisition_cost")]
    assert primary.adjusted_q_value <= 0.05
    assert primary.lag_days == 5
    assert primary.sample_size == 174
    assert primary.effect_size > 0.5
    assert primary.test_metadata["source_preparation"]["transformation"] == "first_difference"
    assert primary.test_metadata["target_preparation"]["transformation"] == "first_difference"
    assert primary.test_metadata["lag_interpretation"] == "BIC-selected model history, not a causal delay claim"

    assert ("partner_active_rate", "recognized_revenue") not in accepted
    assert ("partner_incentive_budget", "qualified_leads") not in accepted


def test_signal_evidence_is_reproducible_and_confidence_is_deterministic() -> None:
    first = DeterministicSignalEngine(as_of=date(2026, 6, 29)).analyze(_observations())
    second = DeterministicSignalEngine(as_of=date(2026, 6, 29)).analyze(_observations())

    assert [signal.evidence_fingerprint for signal in first.accepted] == [
        signal.evidence_fingerprint for signal in second.accepted
    ]
    assert [signal.id for signal in first.accepted] == [signal.id for signal in second.accepted]
    primary = next(
        signal
        for signal in first.accepted
        if (signal.metric_a, signal.metric_b) == ("partner_referral_quality", "client_acquisition_cost")
    )
    components = primary.confidence_components
    expected_score = round(
        100
        * (
            0.40 * components["adjusted_significance"]
            + 0.25 * components["incremental_effect"]
            + 0.20 * components["sample_adequacy"]
            + 0.15 * components["recency"]
        ),
        2,
    )
    assert primary.confidence_score == expected_score
    assert primary.confidence_version == "confidence_v1"


def test_missing_daily_data_rejects_the_metric_instead_of_silently_dropping_the_day() -> None:
    observations = _observations()
    incomplete = [
        observation
        for observation in observations
        if not (observation.metric_name == "partner_referral_quality" and observation.event_time.date().day == 15)
    ]

    report = DeterministicSignalEngine().analyze(incomplete)

    assert ("partner_referral_quality", "client_acquisition_cost") not in {
        (signal.metric_a, signal.metric_b) for signal in report.accepted
    }
    assert any(
        rejection.metric_a == "partner_referral_quality" and rejection.reason == "invalid_daily_series:missing_day"
        for rejection in report.rejected
    )


def test_zero_bic_order_is_rejected_instead_of_forcing_a_lag(monkeypatch) -> None:
    index = pd.date_range("2026-01-01", periods=80, freq="D")
    source = PreparedSeries("partner", "source_metric", pd.Series(np.arange(80), index=index), 0.01, 0.01, "none")
    target = PreparedSeries("client", "target_metric", pd.Series(np.arange(80), index=index), 0.01, 0.01, "none")

    class ZeroLagVar:
        def select_order(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(selected_orders={"bic": 0})

    monkeypatch.setattr(signals_module, "VAR", lambda _: ZeroLagVar())
    outcome = DeterministicSignalEngine()._test_candidate(source, target)

    assert isinstance(outcome, RejectedCandidate)
    assert outcome.reason == "bic_selected_zero_lags"


def test_infeasible_granger_fit_is_rejected_instead_of_crashing_a_resilience_window(monkeypatch) -> None:
    index = pd.date_range("2026-01-01", periods=80, freq="D")
    source = PreparedSeries("partner", "source_metric", pd.Series(np.arange(80), index=index), 0.01, 0.01, "none")
    target = PreparedSeries("client", "target_metric", pd.Series(np.arange(80), index=index), 0.01, 0.01, "none")

    class OneLagVar:
        def select_order(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(selected_orders={"bic": 1})

    monkeypatch.setattr(signals_module, "VAR", lambda _: OneLagVar())

    def infeasible_test(*_: object, **__: object):
        raise InfeasibleTestError("perfect fit")

    monkeypatch.setattr(signals_module, "grangercausalitytests", infeasible_test)
    outcome = DeterministicSignalEngine()._test_candidate(source, target)

    assert isinstance(outcome, RejectedCandidate)
    assert outcome.reason == "granger_test_failed:InfeasibleTestError"
