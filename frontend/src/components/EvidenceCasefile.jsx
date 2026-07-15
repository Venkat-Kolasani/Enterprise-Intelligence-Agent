import { formatValue, humanizeMetric, shortId } from '../lib/api'

const componentLabels = {
  adjusted_significance: 'Adjusted significance',
  incremental_effect: 'Incremental effect',
  sample_adequacy: 'Sample adequacy',
  recency: 'Recency',
}

function formattedPValue(value) {
  return Number(value).toExponential(3)
}

function ReplayChart({ replay, title, tone }) {
  const values = replay.points.map((point) => Number(point.value))
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const range = maximum - minimum || 1
  const points = values.map((value, index) => {
    const x = 12 + (index / Math.max(values.length - 1, 1)) * 376
    const y = 78 - ((value - minimum) / range) * 62
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')

  return (
    <figure className={`replay-chart ${tone}`}>
      <figcaption>
        <span>{title}</span>
        <strong>{humanizeMetric(replay.metric)}</strong>
        <small>{replay.domain} · {replay.points.length} raw daily points</small>
      </figcaption>
      <svg viewBox="0 0 400 96" role="img" aria-label={`${title}: ${humanizeMetric(replay.metric)} replay across ${replay.points.length} daily observations`}>
        <line x1="12" y1="16" x2="388" y2="16" />
        <line x1="12" y1="47" x2="388" y2="47" />
        <line x1="12" y1="78" x2="388" y2="78" />
        <polyline points={points} />
      </svg>
      <div className="replay-axis"><span>{replay.points[0].date}</span><span>{formatValue(minimum)}</span><span>{formatValue(maximum)}</span><span>{replay.points.at(-1).date}</span></div>
    </figure>
  )
}

function ConfidenceBreakdown({ confidence }) {
  return (
    <div className="confidence-breakdown">
      {Object.entries(confidence.components).map(([component, value]) => (
        <div key={component}>
          <div><span>{componentLabels[component]}</span><small>{Math.round(confidence.weights[component] * 100)}% weight</small></div>
          <progress max="1" value={value}>{Math.round(value * 100)}%</progress>
          <b>{Math.round(value * 100)} / 100</b>
        </div>
      ))}
    </div>
  )
}

function PassportField({ label, value }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>
}

export function EvidenceCasefile({ casefile, error, loading, onSelectSignal, resilience, resilienceError, resilienceLoading, selectedSignalId, signals }) {
  const isSelectedCasefile = casefile?.signal?.id === selectedSignalId

  return (
    <section className="casefile-section">
      <div className="casefile-controlbar">
        <div>
          <span className="kicker">Forensic evidence record</span>
          <p>Read-only replay from the stored signal and event history. This view does not rerun or persist analysis.</p>
        </div>
        <label htmlFor="casefile-signal">Retained signal
          <select id="casefile-signal" value={selectedSignalId ?? ''} onChange={(event) => onSelectSignal(event.target.value)}>
            {signals.map((signal) => <option key={signal.id} value={signal.id}>{humanizeMetric(signal.source.metric)} → {humanizeMetric(signal.target.metric)}</option>)}
          </select>
        </label>
      </div>

      {loading && <p className="casefile-loading">Assembling event replay and test ledger…</p>}
      {error && <p className="casefile-error"><strong>Casefile unavailable.</strong> {error}</p>}
      {!loading && !error && !isSelectedCasefile && <p className="casefile-loading">Choose a retained signal to inspect its evidence.</p>}
      {isSelectedCasefile && <CasefileRecord casefile={casefile} resilience={resilience?.signal_id === selectedSignalId ? resilience : null} resilienceError={resilienceError} resilienceLoading={resilienceLoading} />}
    </section>
  )
}

function CasefileRecord({ casefile, resilience, resilienceError, resilienceLoading }) {
  const { claim_audit: claimAudit, model_evidence_packet: packet, recomputation, replay, signal, test_family: testFamily } = casefile
  const sourcePreparation = signal.test_metadata.source_preparation
  const targetPreparation = signal.test_metadata.target_preparation
  const confidence = claimAudit.confidence

  return (
    <div className="casefile-record">
      <header className="casefile-header">
        <div>
          <span className="kicker">Casefile {shortId(signal.id)}</span>
          <h2>{humanizeMetric(signal.source.metric)} <i>→</i> {humanizeMetric(signal.target.metric)}</h2>
          <p>Retained as predictive lead–lag evidence in a synthetic live simulation. The BIC-selected model history is not a claimed business delay or causal mechanism.</p>
        </div>
        <div className={recomputation.state === 'matches_persisted_evidence' ? 'casefile-seal verified' : 'casefile-seal'}>
          <span>Recomputed</span>
          <strong>{recomputation.state === 'matches_persisted_evidence' ? 'MATCH' : 'REVIEW'}</strong>
          <small>{signal.test_config_version}</small>
        </div>
      </header>

      <section className="casefile-replay" aria-labelledby="replay-heading">
        <div className="casefile-section-heading">
          <div><span className="casefile-index">01</span><h3 id="replay-heading">Event replay</h3></div>
          <p>The actual retained source and target series, before interpretation.</p>
        </div>
        <div className="replay-grid">
          <ReplayChart replay={replay.source} title="Source" tone="source" />
          <ReplayChart replay={replay.target} title="Target" tone="target" />
        </div>
      </section>

      <section className="casefile-test-family" aria-labelledby="test-family-heading">
        <div className="casefile-section-heading">
          <div><span className="casefile-index">02</span><h3 id="test-family-heading">Test family ledger</h3></div>
          <p>Every cross-domain candidate was corrected together; only q ≤ {testFamily.adjusted_q_threshold} survived.</p>
        </div>
        <div className="family-counts">
          <article><span>Candidate tests</span><strong>{testFamily.candidate_count}</strong><small>{testFamily.candidate_family_version}</small></article>
          <article><span>Retained signals</span><strong>{testFamily.retained_count}</strong><small>BH adjusted</small></article>
          <article><span>Rejected results</span><strong>{testFamily.rejected_count}</strong><small>Not narrated</small></article>
        </div>
        <div className="negative-controls">
          {testFamily.declared_negative_controls.map((control) => (
            <article key={`${control.source.metric}-${control.target.metric}`}>
              <span>Declared negative control</span>
              <h4>{humanizeMetric(control.source.metric)} <i>→</i> {humanizeMetric(control.target.metric)}</h4>
              <p><b>{control.status}</b> · {control.reason ?? 'No valid candidate observed'}</p>
              <small>p {control.granger_p_value === null ? '—' : formattedPValue(control.granger_p_value)} · q {control.adjusted_q_value === null ? '—' : formattedPValue(control.adjusted_q_value)}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="casefile-evidence-grid" aria-label="Statistical evidence and confidence audit">
        <article className="evidence-passport">
          <div className="casefile-section-heading compact"><div><span className="casefile-index">03</span><h3>Evidence passport</h3></div></div>
          <dl>
            <PassportField label="F statistic" value={Number(signal.f_statistic).toFixed(4)} />
            <PassportField label="Raw p value" value={formattedPValue(signal.granger_p_value)} />
            <PassportField label="Adjusted q" value={formattedPValue(signal.adjusted_q_value)} />
            <PassportField label="Effect ΔR²" value={Number(signal.effect_size).toFixed(6)} />
            <PassportField label="Model observations" value={signal.sample_size} />
            <PassportField label="BIC history" value={`${signal.bic_model_history_days} days`} />
            <PassportField label="Input data digest" value={signal.test_metadata.input_data_digest} />
            <PassportField label="Evidence fingerprint" value={signal.evidence_fingerprint} />
          </dl>
        </article>
        <article className="stationarity-record">
          <div className="casefile-section-heading compact"><div><span className="casefile-index">04</span><h3>ADF preparation</h3></div></div>
          <PreparationRecord label="Source" preparation={sourcePreparation} />
          <PreparationRecord label="Target" preparation={targetPreparation} />
          <p>{signal.test_metadata.lag_interpretation}</p>
        </article>
      </section>

      <section className="casefile-confidence" aria-labelledby="confidence-heading">
        <div className="casefile-section-heading">
          <div><span className="casefile-index">05</span><h3 id="confidence-heading">Immutable confidence</h3></div>
          <p>The configured model can narrate this score; it cannot set, alter, or round it.</p>
        </div>
        <div className="confidence-score"><strong>{Number(confidence.score).toFixed(1)}</strong><span>/ 100</span><small>{confidence.version}</small></div>
        <ConfidenceBreakdown confidence={confidence} />
        <p className="confidence-check">Formula recomputation: <b>{Number(confidence.recomputed_score).toFixed(1)} / 100</b> · {confidence.matches_deterministic_formula ? 'matches persisted signal' : 'mismatch requires review'} · model mutation: <b>blocked</b></p>
      </section>

      <ResilienceRecord resilience={resilience} error={resilienceError} loading={resilienceLoading} />

      <section className="casefile-model-boundary" aria-labelledby="model-boundary-heading">
        <div className="casefile-section-heading">
          <div><span className="casefile-index">07</span><h3 id="model-boundary-heading">Model boundary</h3></div>
          <p>Only this compact packet is passed to a configured reasoning provider—not the raw event history.</p>
        </div>
        <div className="model-boundary-grid">
          <details className="evidence-packet" open>
            <summary><span>Compact model evidence packet</span><b>Exact serialized fields</b></summary>
            <pre>{JSON.stringify(packet, null, 2)}</pre>
          </details>
          <div className="claim-audit">
            <article>
              <span>Cited-ID validation</span>
              <strong>{claimAudit.citation_checks.length} linked claim{claimAudit.citation_checks.length === 1 ? '' : 's'}</strong>
              {claimAudit.citation_checks.length === 0 ? <p>No persisted model narrative cites this signal yet.</p> : claimAudit.citation_checks.map((check) => <p key={check.insight_id}>Insight {shortId(check.insight_id)} · {check.unknown_cited_signal_ids.length === 0 ? 'accepted IDs only' : 'unknown IDs detected'} · confidence {check.confidence_matches_casefile ? 'matches' : 'mismatch'}</p>)}
            </article>
            <article className="causal-refusal">
              <span>Causal-language refusal</span>
              <strong>Server validation required</strong>
              <p>Refuses: {claimAudit.causal_language_guard.forbidden_terms.map((term) => <code key={term}>{term}</code>)}</p>
              <small>Required phrasing: “predictive lead–lag” or “evidence is consistent with.”</small>
            </article>
          </div>
        </div>
      </section>
    </div>
  )
}

function ResilienceRecord({ resilience, error, loading }) {
  if (loading) {
    return <section className="casefile-resilience"><p className="casefile-loading">Replaying rolling-origin validation windows…</p></section>
  }

  if (error) {
    return <section className="casefile-resilience"><p className="casefile-error"><strong>Resilience record unavailable.</strong> {error}</p></section>
  }

  if (!resilience) {
    return (
      <section className="casefile-resilience" aria-labelledby="resilience-heading">
        <div className="casefile-section-heading">
          <div><span className="casefile-index">06</span><h3 id="resilience-heading">Evidence resilience</h3></div>
          <p>Rolling-origin validation must be persisted before a new model narrative can be generated.</p>
        </div>
        <div className="resilience-empty"><strong>NO CURRENT ASSESSMENT</strong><p>Recommendation generation is blocked until <code>resilience_rolling_origin_v1</code> validates this exact evidence fingerprint.</p></div>
      </section>
    )
  }

  const { origins, summary } = resilience
  return (
    <section className="casefile-resilience" aria-labelledby="resilience-heading">
      <div className="casefile-section-heading">
        <div><span className="casefile-index">06</span><h3 id="resilience-heading">Evidence resilience</h3></div>
        <p>Each origin trains only on history available before its held-out observation.</p>
      </div>
      <div className={resilience.recommendation_eligible ? 'resilience-verdict eligible' : 'resilience-verdict suppressed'}>
        <div><span>{resilience.recommendation_eligible ? 'Recommendation eligible' : 'Recommendation suppressed'}</span><strong>{resilience.recommendation_eligible ? 'STABLE' : 'REVIEW'}</strong><small>{resilience.version}</small></div>
        <p>{summary.signal_retained_windows} / {summary.origin_count} retained · {summary.baseline_wins} / {summary.origin_count} beat target-history baseline · {summary.negative_controls_rejected_windows} / {summary.negative_controls_required_windows} control windows rejected</p>
      </div>
      <div className="origin-validation-grid">
        {origins.map((origin) => (
          <article key={origin.origin}>
            <span>Origin {origin.origin}</span>
            <strong>{origin.signal_retained ? 'retained' : 'not retained'}</strong>
            <p>Baseline error <b>{Number(origin.baseline_abs_error).toFixed(3)}</b><br />Signal error <b>{Number(origin.augmented_abs_error).toFixed(3)}</b></p>
            <small>{origin.beats_target_history_baseline ? 'beats target history' : 'does not beat target history'} · controls {origin.negative_controls_rejected ? 'rejected' : 'regressed'}</small>
          </article>
        ))}
      </div>
      {summary.suppression_reasons.length > 0 && <p className="resilience-reasons">Suppression reasons: {summary.suppression_reasons.map((reason) => <code key={reason}>{reason}</code>)}</p>}
    </section>
  )
}

function PreparationRecord({ label, preparation }) {
  return (
    <div className="preparation-record">
      <div><span>{label}</span><strong>{preparation.transformation.replaceAll('_', ' ')}</strong></div>
      <p>Raw ADF p <b>{formattedPValue(preparation.raw_adf_p_value)}</b></p>
      <p>Prepared ADF p <b>{formattedPValue(preparation.prepared_adf_p_value)}</b></p>
    </div>
  )
}
