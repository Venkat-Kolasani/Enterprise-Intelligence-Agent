from __future__ import annotations

import argparse

from metricthread.database import apply_foundation_migration, database_url, foundation_counts, seed_foundation
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import lagged_pearson


def main() -> None:
    parser = argparse.ArgumentParser(description="MetricThread Phase 1 foundation commands")
    parser.add_argument("command", choices=("migrate", "seed", "demo"))
    args = parser.parse_args()
    url = database_url()

    if args.command == "migrate":
        apply_foundation_migration(url)
        print("foundation migration applied")
        return

    if args.command == "seed":
        apply_foundation_migration(url)
        dataset = seed_foundation(url)
        print(f"seeded {len(dataset.events)} metric events")
        return

    apply_foundation_migration(url)
    dataset = seed_foundation(url)
    quality_to_cac = lagged_pearson(
        dataset.values("partner_referral_quality"),
        dataset.values("client_acquisition_cost"),
        dataset.primary_lag_days,
    )
    resolved = resolve_exact_keys(foundation_source_records())
    print("MetricThread Phase 1 foundation demo")
    print(f"entities={len(resolved)} events={len(dataset.events)} counts={foundation_counts(url)}")
    print(f"partner_referral_quality -> client_acquisition_cost (lag 3): r={quality_to_cac:.3f}")


if __name__ == "__main__":
    main()
