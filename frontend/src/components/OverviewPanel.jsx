import { formatValue, humanizeMetric, shortId } from '../lib/api'

function OperationalStat({ label, value, detail, tone = 'neutral' }) {
  return (
    <article className={`operational-stat ${tone}`}>
      <span className="stat-bar" aria-hidden="true" />
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}

function MetricRail({ metrics }) {
  if (metrics.length === 0) {
    return <div className="metric-rail empty-rail"><span>LIVE WINDOW</span><p>Waiting for the next simulated event batch. The stored evidence below remains inspectable.</p></div>
  }

  return (
    <div className="metric-rail" aria-label="Latest observed metrics">
      {metrics.map((metric) => (
        <article key={metric.id}>
          <span>{metric.domain}</span>
          <strong>{humanizeMetric(metric.metric_name)}</strong>
          <b>{formatValue(metric.value)}</b>
          <small>{metric.unit}</small>
        </article>
      ))}
    </div>
  )
}

export function OverviewPanel({ data, onNavigate }) {
  const primarySignal = data.signals[0]
  const primaryInsight = data.insights[0]
  const signalSource = primarySignal?.source.metric ?? 'partner_referral_quality'
  const signalTarget = primarySignal?.target.metric ?? 'client_acquisition_cost'
  const historyDays = primarySignal?.bic_model_history_days ?? '—'
  const usesEphemeralDemoSink = data.status?.cold_path_mode === 'ephemeral_demo_sink'

  return (
    <div className="overview-panel">
      <section className="thread-brief">
        <div className="thread-brief-head">
          <div>
            <p className="kicker">Priority evidence thread</p>
            <h2>From a change in the signal to an accountable decision.</h2>
          </div>
          {primarySignal && <span className="confidence-stamp">{Number(primarySignal.confidence_score).toFixed(1)} <small>confidence</small></span>}
        </div>

        <div className="operational-thread">
          <article className="thread-stage observed">
            <span>Observed signal</span>
            <h3>{humanizeMetric(signalSource)}</h3>
            <p>Partner / South region</p>
          </article>
          <div className="stage-link"><i /><span>{historyDays}d BIC history</span></div>
          <article className="thread-stage tested">
            <span>Retained evidence</span>
            <h3>Predictive lead–lag</h3>
            <p>{primarySignal ? `q ${Number(primarySignal.adjusted_q_value).toExponential(2)}` : 'analysis available'}</p>
          </article>
          <div className="stage-link"><i /><span>human review</span></div>
          <article className="thread-stage decided">
            <span>Decision record</span>
            <h3>{primaryInsight ? 'Review proposed' : 'No decision yet'}</h3>
            <p>{primaryInsight ? shortId(primaryInsight.id) : 'awaiting evidence link'}</p>
          </article>
        </div>

        <div className="thread-brief-footer">
          <p>
            {primaryInsight?.narrative_text ?? `MetricThread has retained evidence consistent with ${humanizeMetric(signalSource)} predicting ${humanizeMetric(signalTarget)}. It does not claim causation.`}
          </p>
          <div>
            <button type="button" className="ink-action" onClick={() => onNavigate('evidence')}>Inspect evidence <span aria-hidden="true">→</span></button>
            <button type="button" className="text-button" onClick={() => onNavigate('decisions')}>Open decision record</button>
          </div>
        </div>
      </section>

      <section className="operational-stats" aria-label="Live operating status">
        <OperationalStat label="Ingestion" value={data.status?.simulation_state ?? 'connecting'} detail={`${data.status?.stream_length ?? 0} retained stream events`} tone={data.isRunning ? 'healthy' : 'neutral'} />
        <OperationalStat label="Hot path" value={`${data.status?.hot_events_processed ?? 0} processed`} detail={`${data.status?.p95_hot_visibility_ms ?? '—'} ms p95 · ${data.status?.hot_pending ?? 0} pending`} tone="healthy" />
        <OperationalStat
          label="Cold path"
          value={`${data.status?.cold_events_persisted ?? 0} ${usesEphemeralDemoSink ? 'demo sink' : 'durable'}`}
          detail={usesEphemeralDemoSink
            ? `in-memory read-only sink · ${data.status?.p95_cold_persistence_ms ?? '—'} ms p95 · ${data.status?.cold_pending ?? 0} pending`
            : `${data.status?.p95_cold_persistence_ms ?? '—'} ms p95 · ${data.status?.cold_pending ?? 0} pending`}
          tone={data.coldBlocked ? 'attention' : 'healthy'}
        />
        <OperationalStat label="Evidence engine" value={`${data.signals.length} retained`} detail="BH-corrected q ≤ 0.05" tone={data.signals.length ? 'healthy' : 'neutral'} />
      </section>

      <section className="metric-window">
        <div className="section-intro"><p className="kicker">Live metric window</p><h2>Latest observations</h2></div>
        <MetricRail metrics={data.metrics} />
      </section>

      <section className="attention-ledger">
        <div className="section-intro">
          <div><p className="kicker">Evidence at a glance</p><h2>Signals that passed correction</h2></div>
          <button type="button" className="text-button" onClick={() => onNavigate('evidence')}>View full ledger <span aria-hidden="true">→</span></button>
        </div>
        {data.signals.length === 0 ? (
          <p className="empty-message">No retained signal is available yet. Run deterministic analysis against the seeded history to evaluate it.</p>
        ) : (
          <div className="signal-list">
            {data.signals.slice(0, 4).map((signal) => (
              <article key={signal.id}>
                <span className="signal-direction">{signal.direction === 'negative' ? '↓' : '↑'}</span>
                <div><strong>{humanizeMetric(signal.source.metric)} <i>→</i> {humanizeMetric(signal.target.metric)}</strong><small>{signal.source.domain} / {signal.target.domain} · evidence {shortId(signal.id)}</small></div>
                <b>{Number(signal.confidence_score).toFixed(1)}<small>confidence</small></b>
                <em>q {Number(signal.adjusted_q_value).toExponential(1)}</em>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
