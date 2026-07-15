CREATE TABLE IF NOT EXISTS signal_resilience_results (
    id UUID PRIMARY KEY,
    correlation_signal_id UUID NOT NULL REFERENCES correlation_signals(id) ON DELETE RESTRICT,
    evidence_fingerprint TEXT NOT NULL CHECK (char_length(TRIM(evidence_fingerprint)) = 64),
    resilience_version TEXT NOT NULL CHECK (char_length(TRIM(resilience_version)) > 0),
    evaluation_config JSONB NOT NULL CHECK (jsonb_typeof(evaluation_config) = 'object'),
    result JSONB NOT NULL CHECK (jsonb_typeof(result) = 'object'),
    recommendation_eligible BOOLEAN NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (correlation_signal_id, resilience_version, evidence_fingerprint)
);

CREATE INDEX IF NOT EXISTS signal_resilience_latest_idx
    ON signal_resilience_results (correlation_signal_id, resilience_version, evaluated_at DESC);
