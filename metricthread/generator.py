from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import cos, sin, sqrt
from random import Random
from statistics import mean
from uuid import UUID, uuid5

from metricthread.entities import ResolvedEntity


EVENT_NAMESPACE = UUID("d04d642c-9d7d-437d-a135-0c2a3d076d5d")
START_DATE = date(2026, 1, 1)
DAY_COUNT = 180


@dataclass(frozen=True)
class MetricEvent:
    id: UUID
    entity_id: UUID
    domain: str
    metric_name: str
    value: float
    unit: str
    dimensions: dict[str, str]
    event_time: datetime
    source_system: str = "synthetic_generator"


@dataclass(frozen=True)
class GeneratedDataset:
    events: tuple[MetricEvent, ...]
    primary_lag_days: int
    negative_control_pairs: tuple[tuple[str, str], ...]

    def values(self, metric_name: str) -> list[float]:
        return [event.value for event in self.events if event.metric_name == metric_name]


def generate_dataset(entities: list[ResolvedEntity], seed: int = 20260714) -> GeneratedDataset:
    """Generate a repeatable regional growth dataset with declared test relationships."""
    entity_ids = {entity.exact_key: entity.id for entity in entities}
    rng = Random(seed)
    days = range(DAY_COUNT)

    marketing_spend = [120_000 + 12_000 * sin(day / 9) + rng.gauss(0, 2_500) for day in days]
    partner_incentive_budget = [24_000 + 1_800 * cos(day / 7) + rng.gauss(0, 700) for day in days]
    partner_referral_quality = [
        82 - 0.025 * day - (7 if day >= 105 else 0) + 1.8 * sin(day / 13) + rng.gauss(0, 0.8)
        for day in days
    ]
    partner_referral_volume = [310 + 2.8 * quality + rng.gauss(0, 7) for quality in partner_referral_quality]
    partner_active_rate = [74 + 3.5 * sin(day / 5.3) + rng.gauss(0, 2.0) for day in days]

    client_acquisition_cost: list[float] = []
    qualified_leads: list[float] = []
    new_customer_conversion: list[float] = []
    recognized_revenue: list[float] = []
    for day in days:
        quality_lag = partner_referral_quality[max(0, day - 3)]
        spend_lag = marketing_spend[max(0, day - 5)]
        client_acquisition_cost.append(97 + 2.1 * (82 - quality_lag) + 0.00008 * marketing_spend[day] + rng.gauss(0, 1.1))
        qualified_leads.append(850 + 0.0048 * marketing_spend[max(0, day - 2)] + rng.gauss(0, 22))
        new_customer_conversion.append(19 + 0.013 * partner_referral_quality[max(0, day - 2)] + rng.gauss(0, 0.7))
        recognized_revenue.append(680_000 + 2.25 * spend_lag + rng.gauss(0, 9_000))

    series = {
        "marketing_spend": ("financial", "USD", entity_ids["business_unit:south-growth"], marketing_spend),
        "recognized_revenue": ("financial", "USD", entity_ids["business_unit:south-growth"], recognized_revenue),
        "partner_incentive_budget": ("financial", "USD", entity_ids["business_unit:south-growth"], partner_incentive_budget),
        "partner_referral_quality": ("partner", "score", entity_ids["partner:south-network"], partner_referral_quality),
        "partner_referral_volume": ("partner", "referrals", entity_ids["partner:south-network"], partner_referral_volume),
        "partner_active_rate": ("partner", "percent", entity_ids["partner:south-network"], partner_active_rate),
        "client_acquisition_cost": ("client", "USD", entity_ids["client:south-growth"], client_acquisition_cost),
        "qualified_leads": ("client", "leads", entity_ids["client:south-growth"], qualified_leads),
        "new_customer_conversion": ("client", "percent", entity_ids["client:south-growth"], new_customer_conversion),
    }

    events: list[MetricEvent] = []
    for metric_name, (domain, unit, entity_id, values) in series.items():
        for day, value in enumerate(values):
            event_date = START_DATE + timedelta(days=day)
            event_time = datetime.combine(event_date, time.min, tzinfo=timezone.utc)
            events.append(
                MetricEvent(
                    id=uuid5(EVENT_NAMESPACE, f"{metric_name}:{event_date.isoformat()}"),
                    entity_id=entity_id,
                    domain=domain,
                    metric_name=metric_name,
                    value=round(value, 4),
                    unit=unit,
                    dimensions={"region": "South", "simulation": "synthetic"},
                    event_time=event_time,
                )
            )

    return GeneratedDataset(
        events=tuple(sorted(events, key=lambda event: (event.event_time, event.metric_name))),
        primary_lag_days=3,
        negative_control_pairs=(
            ("partner_active_rate", "recognized_revenue"),
            ("partner_incentive_budget", "qualified_leads"),
        ),
    )


def lagged_pearson(source: list[float], target: list[float], lag_days: int) -> float:
    if lag_days <= 0 or len(source) != len(target) or len(source) <= lag_days + 1:
        raise ValueError("series must be aligned and longer than the requested lag")
    left = source[:-lag_days]
    right = target[lag_days:]
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_scale == 0 or right_scale == 0:
        raise ValueError("series variance must be non-zero")
    return numerator / (left_scale * right_scale)
