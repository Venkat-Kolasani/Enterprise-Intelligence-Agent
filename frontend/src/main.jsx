import { useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? ''

async function getJson(path, options) {
  const response = await fetch(`${apiBase}${path}`, options)
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`)
  }
  return response.json()
}

function StateCard({ label, value, detail, tone = 'neutral' }) {
  return (
    <article className={`state-card ${tone}`}>
      <span className="state-dot" aria-hidden="true" />
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  )
}

function App() {
  const [status, setStatus] = useState(null)
  const [metrics, setMetrics] = useState([])
  const [signals, setSignals] = useState([])
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [signalError, setSignalError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, nextMetrics] = await Promise.all([
        getJson('/agent/status'),
        getJson('/metrics/live'),
      ])
      setStatus(nextStatus)
      setMetrics(nextMetrics.metrics)
      setError(null)
    } catch (requestError) {
      setError(requestError.message)
    }
    try {
      const nextSignals = await getJson('/signals')
      setSignals(nextSignals.signals)
      setSignalError(null)
    } catch (requestError) {
      setSignalError(requestError.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 1000)
    return () => window.clearInterval(interval)
  }, [refresh])

  async function startSimulation() {
    setStarting(true)
    try {
      await getJson('/simulation/start', { method: 'POST' })
      await refresh()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setStarting(false)
    }
  }

  async function runSignalAnalysis() {
    setAnalyzing(true)
    try {
      const result = await getJson('/signals/run', { method: 'POST' })
      setSignals(result.signals)
      setSignalError(null)
      await refresh()
    } catch (requestError) {
      setSignalError(requestError.message)
    } finally {
      setAnalyzing(false)
    }
  }

  const isRunning = status?.simulation_state === 'running'
  const coldBlocked = Boolean(status?.last_cold_error)

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">MetricThread / Enterprise Intelligence Agent</p>
          <h1>Watch the signals<br />before they become outcomes.</h1>
          <p className="subtitle">Grounded cross-functional intelligence for auditable business decisions.</p>
        </div>
        <div className="simulation-box">
          <span className="pulse" aria-hidden="true" />
          <span>SYNTHETIC LIVE SIMULATION</span>
          <strong>{status?.simulated_days_emitted ?? 0} / 180 days</strong>
        </div>
      </section>

      <section className="control-row" aria-label="Simulation controls">
        <div>
          <p className="eyebrow">Agent status</p>
          <h2>{isRunning ? 'Monitoring 9 business metrics' : 'Ready to monitor 9 business metrics'}</h2>
        </div>
        <div className="control-actions">
          <button type="button" onClick={runSignalAnalysis} disabled={analyzing} className="secondary-action">
            {analyzing ? 'Analyzing…' : 'Run evidence analysis'}
          </button>
          <button type="button" onClick={startSimulation} disabled={isRunning || starting}>
            {isRunning ? 'Simulation running' : starting ? 'Starting…' : 'Start simulation'}
          </button>
        </div>
      </section>

      {error && <p className="error" role="alert">Connection issue: {error}</p>}
      {coldBlocked && (
        <p className="warning" role="status">
          Cold-path write is pending recovery. Events remain unacknowledged in Redis Streams: {status.last_cold_error}
        </p>
      )}
      {signalError && (
        <p className="warning" role="status">
          Evidence analysis is unavailable: {signalError}
        </p>
      )}

      <section className="status-grid" aria-live="polite">
        <StateCard label="Ingestion" value={status?.simulation_state ?? 'connecting'} detail={`${status?.stream_length ?? 0} retained events`} tone={isRunning ? 'healthy' : 'neutral'} />
        <StateCard label="Hot path" value={`${status?.hot_events_processed ?? 0} processed`} detail={`${status?.p95_hot_visibility_ms ?? '—'} ms p95 · ${status?.hot_pending ?? 0} pending`} tone="healthy" />
        <StateCard label="Cold path" value={`${status?.cold_events_persisted ?? 0} durable`} detail={`${status?.p95_cold_persistence_ms ?? '—'} ms p95 · ${status?.cold_pending ?? 0} pending`} tone={coldBlocked ? 'warning' : 'healthy'} />
        <StateCard
          label="Signal engine"
          value={`${signals.length} evidence-backed`}
          detail="BIC lag selection · BH-corrected q ≤ 0.05"
          tone={signals.length ? 'healthy' : 'neutral'}
        />
      </section>

      <section className="metrics-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Live metric window</p>
            <h2>Latest observed business signals</h2>
          </div>
          <span>{metrics.length} metrics active</span>
        </div>
        {metrics.length === 0 ? (
          <p className="empty-state">Start the synthetic live simulation to populate the rolling metric window.</p>
        ) : (
          <div className="metric-grid">
            {metrics.map((metric) => (
              <article className="metric-card" key={metric.id}>
                <p>{metric.domain}</p>
                <h3>{metric.metric_name.replaceAll('_', ' ')}</h3>
                <strong>{Number(metric.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
                <span>{metric.unit} · South region</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="evidence-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Explain why</p>
            <h2>Auditable predictive lead–lag evidence</h2>
          </div>
          <span>{signals.length} retained after correction</span>
        </div>
        {signals.length === 0 ? (
          <p className="empty-state">Run deterministic evidence analysis to evaluate the stored synthetic history.</p>
        ) : (
          <div className="evidence-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Predictive relationship</th>
                  <th scope="col">Direction</th>
                  <th scope="col">Adjusted q</th>
                  <th scope="col">Incremental effect</th>
                  <th scope="col">Confidence</th>
                  <th scope="col">BIC history</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((signal) => (
                  <tr key={signal.id}>
                    <td>
                      <strong>{signal.source.metric.replaceAll('_', ' ')}</strong>
                      <span> {signal.source.domain} → {signal.target.metric.replaceAll('_', ' ')}</span>
                    </td>
                    <td>{signal.direction}</td>
                    <td>{Number(signal.adjusted_q_value).toExponential(2)}</td>
                    <td>{Number(signal.effect_size).toFixed(3)} ΔR²</td>
                    <td>{Number(signal.confidence_score).toFixed(1)} / 100</td>
                    <td>{signal.bic_model_history_days} days</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="evidence-note">
          Evidence is consistent with predictive lead–lag relationships, not proof of causation. “BIC history” is the
          selected model history and is not an asserted business delay.
        </p>
      </section>

      <footer>All values are labelled synthetic. Recommendations remain unavailable until the grounded reasoning phase.</footer>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<App />)
