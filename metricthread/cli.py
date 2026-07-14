from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from metricthread.database import (
    apply_foundation_migration,
    apply_signal_engine_migration,
    database_url,
    foundation_counts,
    seed_foundation,
    seed_foundation_via_data_api,
)
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import lagged_pearson
from metricthread.signal_repository import signal_repository_from_environment


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="MetricThread development commands")
    parser.add_argument("command", choices=("migrate", "seed", "seed-rest", "demo", "signals"))
    args = parser.parse_args()

    if args.command == "migrate":
        url = database_url()
        apply_foundation_migration(url)
        apply_signal_engine_migration(url)
        print("foundation and signal-engine migrations applied")
        return

    if args.command == "signals":
        report = signal_repository_from_environment().run_analysis()
        print(
            "signal analysis complete "
            f"candidates={report.candidate_count} accepted={len(report.accepted)} rejected={len(report.rejected)}"
        )
        for signal in report.accepted:
            print(
                f"{signal.metric_a} -> {signal.metric_b} "
                f"q={signal.adjusted_q_value:.3g} confidence={signal.confidence_score:.2f}"
            )
        return

    if args.command == "seed-rest":
        supabase_url = os.environ.get("SUPABASE_URL")
        secret_key = os.environ.get("SUPABASE_SECRET_KEY")
        if not supabase_url or not secret_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for seed-rest")
        dataset = seed_foundation_via_data_api(supabase_url, secret_key)
        print(f"canonical fixture synchronized through Data API: {len(dataset.events)} metric events")
        return

    url = database_url()

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
