from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import DAY_COUNT, generate_dataset, lagged_pearson


def test_generator_has_complete_repeatable_metric_coverage() -> None:
    entities = resolve_exact_keys(foundation_source_records())
    first = generate_dataset(entities)
    second = generate_dataset(entities)

    assert len(first.events) == DAY_COUNT * 9
    assert first.events == second.events
    assert {event.domain for event in first.events} == {"client", "financial", "partner"}
    assert all(event.dimensions == {"region": "South", "simulation": "synthetic"} for event in first.events)


def test_primary_relationship_is_detectable_at_declared_lag() -> None:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    correlation = lagged_pearson(
        dataset.values("partner_referral_quality"),
        dataset.values("client_acquisition_cost"),
        dataset.primary_lag_days,
    )

    assert correlation < -0.85


def test_declared_negative_controls_are_not_strong_lagged_relationships() -> None:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))

    for source_metric, target_metric in dataset.negative_control_pairs:
        correlation = lagged_pearson(dataset.values(source_metric), dataset.values(target_metric), dataset.primary_lag_days)
        assert abs(correlation) < 0.35
