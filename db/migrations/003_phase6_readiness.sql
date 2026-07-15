ALTER TABLE correlation_signals
    ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'superseded'));

ALTER TABLE correlation_signals
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS correlation_signals_active_confidence_idx
    ON correlation_signals (test_config_version, confidence_score DESC)
    WHERE state = 'active';

CREATE OR REPLACE FUNCTION public.persist_grounded_insight(
    insight_payload JSONB,
    recommendation_payload JSONB
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO insights (
        id, title, narrative_text, related_signal_ids, confidence_score, domains, status, generated_at
    ) VALUES (
        (insight_payload ->> 'id')::UUID,
        insight_payload ->> 'title',
        insight_payload ->> 'narrative_text',
        insight_payload -> 'related_signal_ids',
        (insight_payload ->> 'confidence_score')::DOUBLE PRECISION,
        insight_payload -> 'domains',
        insight_payload ->> 'status',
        (insight_payload ->> 'generated_at')::TIMESTAMPTZ
    );

    INSERT INTO recommendations (
        id, insight_id, recommendation_text, predicted_impact, confidence_score, status, created_at
    ) VALUES (
        (recommendation_payload ->> 'id')::UUID,
        (recommendation_payload ->> 'insight_id')::UUID,
        recommendation_payload ->> 'recommendation_text',
        recommendation_payload -> 'predicted_impact',
        (recommendation_payload ->> 'confidence_score')::DOUBLE PRECISION,
        recommendation_payload ->> 'status',
        (recommendation_payload ->> 'created_at')::TIMESTAMPTZ
    );
END;
$$;

REVOKE ALL ON FUNCTION public.persist_grounded_insight(JSONB, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.persist_grounded_insight(JSONB, JSONB) TO service_role;
