ALTER TABLE correlation_signals
    ADD COLUMN IF NOT EXISTS confidence_components JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(confidence_components) = 'object');

ALTER TABLE correlation_signals
    ADD COLUMN IF NOT EXISTS test_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(test_metadata) = 'object');

CREATE INDEX IF NOT EXISTS correlation_signals_computed_at_idx
    ON correlation_signals (computed_at DESC);
