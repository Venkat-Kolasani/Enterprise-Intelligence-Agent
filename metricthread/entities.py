from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5


ENTITY_NAMESPACE = UUID("4d446f0d-bcf4-4ca1-8ee0-a10565d9742f")


@dataclass(frozen=True)
class SourceEntityRecord:
    source_system: str
    source_id: str
    exact_key: str
    entity_type: str
    display_name: str


@dataclass(frozen=True)
class ResolvedEntity:
    id: UUID
    exact_key: str
    entity_type: str
    display_name: str
    source_records: tuple[SourceEntityRecord, ...]


def resolve_exact_keys(records: list[SourceEntityRecord]) -> list[ResolvedEntity]:
    """Resolve records that share an explicitly supplied cross-source key."""
    groups: dict[str, list[SourceEntityRecord]] = {}
    seen_source_records: set[tuple[str, str]] = set()

    for record in records:
        source_identity = (record.source_system, record.source_id)
        if source_identity in seen_source_records:
            raise ValueError(f"duplicate source record: {source_identity}")
        seen_source_records.add(source_identity)
        groups.setdefault(record.exact_key, []).append(record)

    resolved: list[ResolvedEntity] = []
    for exact_key, group in sorted(groups.items()):
        entity_types = {record.entity_type for record in group}
        display_names = {record.display_name for record in group}
        if len(entity_types) != 1 or len(display_names) != 1:
            raise ValueError(f"inconsistent records for exact key: {exact_key}")
        resolved.append(
            ResolvedEntity(
                id=uuid5(ENTITY_NAMESPACE, exact_key),
                exact_key=exact_key,
                entity_type=group[0].entity_type,
                display_name=group[0].display_name,
                source_records=tuple(sorted(group, key=lambda item: (item.source_system, item.source_id))),
            )
        )
    return resolved


def foundation_source_records() -> list[SourceEntityRecord]:
    return [
        SourceEntityRecord("crm", "crm-client-south-001", "client:south-growth", "client", "South Growth Cohort"),
        SourceEntityRecord("finance", "erp-client-south-091", "client:south-growth", "client", "South Growth Cohort"),
        SourceEntityRecord("partner_portal", "partner-network-south-001", "partner:south-network", "partner", "South Partner Network"),
        SourceEntityRecord("finance", "erp-partner-south-771", "partner:south-network", "partner", "South Partner Network"),
        SourceEntityRecord("erp", "business-unit-south-001", "business_unit:south-growth", "business_unit", "South Growth Business Unit"),
        SourceEntityRecord("analytics", "analytics-bu-south-001", "business_unit:south-growth", "business_unit", "South Growth Business Unit"),
    ]
