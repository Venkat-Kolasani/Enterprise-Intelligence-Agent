CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (char_length(trim(entity_type)) > 0),
    display_name TEXT NOT NULL CHECK (char_length(trim(display_name)) > 0),
    external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entity_resolution_map (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_system TEXT NOT NULL CHECK (char_length(trim(source_system)) > 0),
    source_id TEXT NOT NULL CHECK (char_length(trim(source_id)) > 0),
    match_confidence DOUBLE PRECISION NOT NULL CHECK (match_confidence >= 0 AND match_confidence <= 1),
    matched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_system, source_id)
);

CREATE TABLE IF NOT EXISTS metric_events (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    domain TEXT NOT NULL CHECK (char_length(trim(domain)) > 0),
    metric_name TEXT NOT NULL CHECK (char_length(trim(metric_name)) > 0),
    value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL CHECK (char_length(trim(unit)) > 0),
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(dimensions) = 'object'),
    event_time TIMESTAMPTZ NOT NULL,
    source_system TEXT NOT NULL CHECK (char_length(trim(source_system)) > 0),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, metric_name, event_time, source_system)
);

CREATE INDEX IF NOT EXISTS metric_events_metric_time_idx
    ON metric_events (domain, metric_name, event_time);

CREATE TABLE IF NOT EXISTS correlation_signals (
    id UUID PRIMARY KEY,
    domain_a TEXT NOT NULL,
    metric_a TEXT NOT NULL,
    domain_b TEXT NOT NULL,
    metric_b TEXT NOT NULL,
    lag_days INTEGER NOT NULL CHECK (lag_days > 0),
    correlation_coefficient DOUBLE PRECISION NOT NULL,
    effect_size DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('positive', 'negative')),
    f_statistic DOUBLE PRECISION NOT NULL CHECK (f_statistic >= 0),
    granger_p_value DOUBLE PRECISION NOT NULL CHECK (granger_p_value >= 0 AND granger_p_value <= 1),
    adjusted_q_value DOUBLE PRECISION NOT NULL CHECK (adjusted_q_value >= 0 AND adjusted_q_value <= 1),
    sample_size INTEGER NOT NULL CHECK (sample_size >= 0),
    confidence_score DOUBLE PRECISION NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    confidence_version TEXT NOT NULL,
    test_config_version TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL UNIQUE,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (window_end >= window_start)
);

CREATE TABLE IF NOT EXISTS insights (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    narrative_text TEXT NOT NULL,
    related_signal_ids JSONB NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    domains JSONB NOT NULL,
    status TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY,
    insight_id UUID NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    recommendation_text TEXT NOT NULL,
    predicted_impact JSONB NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    status TEXT NOT NULL CHECK (status IN ('proposed', 'planned', 'implemented')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id UUID PRIMARY KEY,
    recommendation_id UUID NOT NULL UNIQUE REFERENCES recommendations(id) ON DELETE CASCADE,
    implemented_at TIMESTAMPTZ NOT NULL,
    outcome_metric TEXT NOT NULL,
    outcome_value DOUBLE PRECISION NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scenario_forecasts (
    id UUID PRIMARY KEY,
    correlation_signal_id UUID NOT NULL REFERENCES correlation_signals(id) ON DELETE RESTRICT,
    input_metric TEXT NOT NULL CHECK (input_metric = 'marketing_spend'),
    input_change_percent DOUBLE PRECISION NOT NULL CHECK (input_change_percent BETWEEN -20 AND 20),
    horizon_days INTEGER NOT NULL CHECK (horizon_days BETWEEN 1 AND 7),
    baseline_values JSONB NOT NULL,
    forecast_values JSONB NOT NULL,
    prediction_intervals JSONB NOT NULL,
    reliability_score DOUBLE PRECISION NOT NULL CHECK (reliability_score >= 0 AND reliability_score <= 100),
    model_version TEXT NOT NULL,
    assumptions JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS briefings (
    id UUID PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary_text TEXT NOT NULL,
    insight_ids JSONB NOT NULL
);
