from metricthread.entities import foundation_source_records, resolve_exact_keys


def test_exact_key_resolution_merges_sources_without_false_merges() -> None:
    resolved = resolve_exact_keys(foundation_source_records())

    assert len(resolved) == 3
    by_key = {entity.exact_key: entity for entity in resolved}
    assert len(by_key["client:south-growth"].source_records) == 2
    assert len(by_key["partner:south-network"].source_records) == 2
    assert len(by_key["business_unit:south-growth"].source_records) == 2
    assert len({entity.id for entity in resolved}) == 3
