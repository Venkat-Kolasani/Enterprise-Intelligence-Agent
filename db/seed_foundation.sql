-- Phase 1 manual fallback for Supabase SQL Editor.
-- All rows are synthetic and the script is safe to re-run.

INSERT INTO entities (id, entity_type, display_name, external_ids)
VALUES
    ('927962ef-4a5f-5f3b-bf60-562451a076b2', 'business_unit', 'South Growth Business Unit',
        '{"analytics":"analytics-bu-south-001","erp":"business-unit-south-001"}'::jsonb),
    ('b4c18052-4aa7-5360-bd3b-e2f06bd58e04', 'client', 'South Growth Cohort',
        '{"crm":"crm-client-south-001","finance":"erp-client-south-091"}'::jsonb),
    ('1639eb40-f7e1-5a34-a134-4156333186ef', 'partner', 'South Partner Network',
        '{"finance":"erp-partner-south-771","partner_portal":"partner-network-south-001"}'::jsonb)
ON CONFLICT (id) DO UPDATE
SET entity_type = EXCLUDED.entity_type,
    display_name = EXCLUDED.display_name,
    external_ids = EXCLUDED.external_ids;

INSERT INTO entity_resolution_map (id, entity_id, source_system, source_id, match_confidence)
VALUES
    ('1dbe5c7c-96e8-4269-9c46-073fbcb3d043', 'b4c18052-4aa7-5360-bd3b-e2f06bd58e04', 'crm', 'crm-client-south-001', 1.0),
    ('d2b45d61-8f12-4d52-8bb7-4ab7bf9d0599', 'b4c18052-4aa7-5360-bd3b-e2f06bd58e04', 'finance', 'erp-client-south-091', 1.0),
    ('2018971b-f10f-4220-9ecb-ef8a64e2d39e', '1639eb40-f7e1-5a34-a134-4156333186ef', 'partner_portal', 'partner-network-south-001', 1.0),
    ('c5ec82bc-e0cc-4183-9c31-311eae5c6d90', '1639eb40-f7e1-5a34-a134-4156333186ef', 'finance', 'erp-partner-south-771', 1.0),
    ('30ed143a-f48b-482f-a7dc-61222bfda222', '927962ef-4a5f-5f3b-bf60-562451a076b2', 'erp', 'business-unit-south-001', 1.0),
    ('b034ad01-8e1d-4126-853d-92cc1f12c811', '927962ef-4a5f-5f3b-bf60-562451a076b2', 'analytics', 'analytics-bu-south-001', 1.0)
ON CONFLICT (source_system, source_id) DO UPDATE
SET entity_id = EXCLUDED.entity_id,
    match_confidence = EXCLUDED.match_confidence,
    matched_at = now();

WITH days AS (
    SELECT day, ('2026-01-01'::date + day) AS event_day
    FROM generate_series(0, 179) AS day
),
metric_values AS (
    SELECT
        days.event_day,
        metric.metric_name,
        metric.entity_id,
        metric.domain,
        metric.unit,
        round(metric.value::numeric, 4)::double precision AS value
    FROM days
    CROSS JOIN LATERAL (
        VALUES
            ('marketing_spend', '927962ef-4a5f-5f3b-bf60-562451a076b2'::uuid, 'financial', 'USD',
                120000 + 12000 * sin(days.day / 9.0) + 2500 * sin(days.day * 1.7)),
            ('recognized_revenue', '927962ef-4a5f-5f3b-bf60-562451a076b2'::uuid, 'financial', 'USD',
                680000 + 2.25 * (120000 + 12000 * sin(greatest(days.day - 5, 0) / 9.0) + 2500 * sin(greatest(days.day - 5, 0) * 1.7)) + 9000 * sin(days.day * 0.73)),
            ('partner_incentive_budget', '927962ef-4a5f-5f3b-bf60-562451a076b2'::uuid, 'financial', 'USD',
                24000 + 1800 * cos(days.day / 7.0) + 700 * sin(days.day * 1.31)),
            ('partner_referral_quality', '1639eb40-f7e1-5a34-a134-4156333186ef'::uuid, 'partner', 'score',
                82 - 0.025 * days.day - CASE WHEN days.day >= 105 THEN 7 ELSE 0 END + 1.8 * sin(days.day / 13.0) + 0.8 * sin(days.day * 1.11)),
            ('partner_referral_volume', '1639eb40-f7e1-5a34-a134-4156333186ef'::uuid, 'partner', 'referrals',
                310 + 2.8 * (82 - 0.025 * days.day - CASE WHEN days.day >= 105 THEN 7 ELSE 0 END + 1.8 * sin(days.day / 13.0) + 0.8 * sin(days.day * 1.11)) + 7 * sin(days.day * 0.67)),
            ('partner_active_rate', '1639eb40-f7e1-5a34-a134-4156333186ef'::uuid, 'partner', 'percent',
                74 + 3.5 * sin(days.day / 5.3) + 2 * sin(days.day * 1.41)),
            ('client_acquisition_cost', 'b4c18052-4aa7-5360-bd3b-e2f06bd58e04'::uuid, 'client', 'USD',
                97 + 2.1 * (82 - (82 - 0.025 * greatest(days.day - 3, 0) - CASE WHEN greatest(days.day - 3, 0) >= 105 THEN 7 ELSE 0 END + 1.8 * sin(greatest(days.day - 3, 0) / 13.0) + 0.8 * sin(greatest(days.day - 3, 0) * 1.11))) + 0.00008 * (120000 + 12000 * sin(days.day / 9.0) + 2500 * sin(days.day * 1.7)) + 1.1 * sin(days.day * 0.91)),
            ('qualified_leads', 'b4c18052-4aa7-5360-bd3b-e2f06bd58e04'::uuid, 'client', 'leads',
                850 + 0.0048 * (120000 + 12000 * sin(greatest(days.day - 2, 0) / 9.0) + 2500 * sin(greatest(days.day - 2, 0) * 1.7)) + 22 * sin(days.day * 0.59)),
            ('new_customer_conversion', 'b4c18052-4aa7-5360-bd3b-e2f06bd58e04'::uuid, 'client', 'percent',
                19 + 0.013 * (82 - 0.025 * greatest(days.day - 2, 0) - CASE WHEN greatest(days.day - 2, 0) >= 105 THEN 7 ELSE 0 END + 1.8 * sin(greatest(days.day - 2, 0) / 13.0) + 0.8 * sin(greatest(days.day - 2, 0) * 1.11)) + 0.7 * sin(days.day * 0.83))
    ) AS metric(metric_name, entity_id, domain, unit, value)
)
INSERT INTO metric_events (
    id, entity_id, domain, metric_name, value, unit, dimensions, event_time, source_system
)
SELECT
    (
        substr(md5(metric_name || ':' || event_day::text), 1, 8) || '-' ||
        substr(md5(metric_name || ':' || event_day::text), 9, 4) || '-' ||
        substr(md5(metric_name || ':' || event_day::text), 13, 4) || '-' ||
        substr(md5(metric_name || ':' || event_day::text), 17, 4) || '-' ||
        substr(md5(metric_name || ':' || event_day::text), 21, 12)
    )::uuid,
    entity_id,
    domain,
    metric_name,
    value,
    unit,
    '{"region":"South","simulation":"synthetic"}'::jsonb,
    event_day::timestamp AT TIME ZONE 'UTC',
    'synthetic_generator'
FROM metric_values
ON CONFLICT (entity_id, metric_name, event_time, source_system) DO UPDATE
SET value = EXCLUDED.value,
    dimensions = EXCLUDED.dimensions,
    ingested_at = now();
