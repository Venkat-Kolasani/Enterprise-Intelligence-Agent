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
  const [insights, setInsights] = useState([])
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [signalError, setSignalError] = useState(null)
  const [decisionError, setDecisionError] = useState(null)
  const [executiveError, setExecutiveError] = useState(null)
  const [statusDrafts, setStatusDrafts] = useState({})
  const [outcomeDrafts, setOutcomeDrafts] = useState({})
  const [briefingResult, setBriefingResult] = useState(null)
  const [briefingBusy, setBriefingBusy] = useState(false)
  const [chatQuestion, setChatQuestion] = useState('Why is CAC rising?')
  const [chatResult, setChatResult] = useState(null)
  const [chatBusy, setChatBusy] = useState(false)
  const [scenarioInput, setScenarioInput] = useState({ change: 10, horizon: 7 })
  const [forecast, setForecast] = useState(null)
  const [forecastBusy, setForecastBusy] = useState(false)

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
    try {
      const nextInsights = await getJson('/insights')
      setInsights(nextInsights.insights)
      setDecisionError(null)
    } catch (requestError) {
      setDecisionError(requestError.message)
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

  async function generateInsight() {
    setGenerating(true)
    try {
      await getJson('/insights/generate', { method: 'POST' })
      await refresh()
    } catch (requestError) {
      setDecisionError(requestError.message)
    } finally {
      setGenerating(false)
    }
  }

  async function updateRecommendationStatus(recommendation) {
    const status = statusDrafts[recommendation.id] ?? recommendation.status
    try {
      await getJson(`/recommendations/${recommendation.id}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      await refresh()
    } catch (requestError) {
      setDecisionError(requestError.message)
    }
  }

  function updateOutcomeDraft(recommendationId, field, value) {
    setOutcomeDrafts((drafts) => ({
      ...drafts,
      [recommendationId]: { ...drafts[recommendationId], [field]: value },
    }))
  }

  async function recordOutcome(event, recommendation) {
    event.preventDefault()
    const draft = outcomeDrafts[recommendation.id] ?? {}
    try {
      await getJson(`/recommendations/${recommendation.id}/outcomes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          implemented_at: new Date().toISOString(),
          outcome_metric: draft.metric ?? 'client_acquisition_cost',
          outcome_value: Number(draft.value ?? 0),
          measured_at: new Date().toISOString(),
          notes: draft.notes ?? '',
        }),
      })
      await refresh()
    } catch (requestError) {
      setDecisionError(requestError.message)
    }
  }

  async function generateBriefing() {
    setBriefingBusy(true)
    try {
      const result = await getJson('/briefings/generate', { method: 'POST' })
      setBriefingResult(result)
      setExecutiveError(null)
    } catch (requestError) {
      setExecutiveError(requestError.message)
    } finally {
      setBriefingBusy(false)
    }
  }

  async function askGroundedQuestion(event) {
    event.preventDefault()
    setChatBusy(true)
    try {
      const result = await getJson('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: chatQuestion,
          prior_insight_ids: chatResult?.insight_ids ?? [],
        }),
      })
      setChatResult(result)
      setExecutiveError(null)
    } catch (requestError) {
      setExecutiveError(requestError.message)
    } finally {
      setChatBusy(false)
    }
  }

  async function generateForecast(event) {
    event.preventDefault()
    setForecastBusy(true)
    try {
      const result = await getJson('/scenarios/forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_metric: 'marketing_spend',
          input_change_percent: Number(scenarioInput.change),
          horizon_days: Number(scenarioInput.horizon),
        }),
      })
      setForecast(result.forecast)
      setExecutiveError(null)
    } catch (requestError) {
      setExecutiveError(requestError.message)
    } finally {
      setForecastBusy(false)
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
          <button type="button" onClick={generateInsight} disabled={generating || signals.length === 0} className="secondary-action">
            {generating ? 'Generating…' : 'Generate grounded recommendation'}
          </button>
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
      {decisionError && (
        <p className="warning" role="status">
          Grounded recommendation workflow is unavailable: {decisionError}
        </p>
      )}
      {executiveError && (
        <p className="warning" role="status">
          Executive workflow is unavailable: {executiveError}
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

      <section className="recommendation-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Agent recommendation</p>
            <h2>Human-controlled decision tracking</h2>
          </div>
          <span>{insights.length} grounded insight{insights.length === 1 ? '' : 's'}</span>
        </div>
        {insights.length === 0 ? (
          <p className="empty-state">Generate one grounded recommendation from a newly accepted evidence signal. The agent cannot execute actions.</p>
        ) : (
          <div className="recommendation-grid">
            {insights.map((insight) => (
              <article className="recommendation-card" key={insight.id}>
                <p className="eyebrow">{insight.domains.join(' / ')} · confidence {Number(insight.confidence_score).toFixed(1)}</p>
                <h3>{insight.title}</h3>
                <p className="narrative">{insight.narrative_text}</p>
                <p className="evidence-id">Evidence: {insight.related_signal_ids.map((id) => id.slice(0, 8)).join(', ')}</p>
                {insight.recommendations.map((recommendation) => {
                  const draft = outcomeDrafts[recommendation.id] ?? {}
                  return (
                    <div className="recommendation-action" key={recommendation.id}>
                      <h4>Proposed action</h4>
                      <p>{recommendation.recommendation_text}</p>
                      <p className="impact">{recommendation.predicted_impact.statement}</p>
                      <div className="lifecycle-row">
                        <label>
                          Lifecycle
                          <select
                            value={statusDrafts[recommendation.id] ?? recommendation.status}
                            onChange={(event) => setStatusDrafts((drafts) => ({ ...drafts, [recommendation.id]: event.target.value }))}
                          >
                            <option value="proposed">Proposed</option>
                            <option value="planned">Planned</option>
                            <option value="implemented">Implemented</option>
                          </select>
                        </label>
                        <button type="button" className="secondary-action" onClick={() => updateRecommendationStatus(recommendation)}>
                          Save status
                        </button>
                      </div>
                      {recommendation.status === 'implemented' && (
                        recommendation.outcome ? (
                          <p className="outcome-summary">
                            Outcome: {recommendation.outcome.outcome_metric} = {recommendation.outcome.outcome_value}
                          </p>
                        ) : (
                          <form className="outcome-form" onSubmit={(event) => recordOutcome(event, recommendation)}>
                            <label>
                              Outcome metric
                              <input
                                value={draft.metric ?? 'client_acquisition_cost'}
                                onChange={(event) => updateOutcomeDraft(recommendation.id, 'metric', event.target.value)}
                              />
                            </label>
                            <label>
                              Measured value
                              <input
                                type="number"
                                step="any"
                                value={draft.value ?? ''}
                                onChange={(event) => updateOutcomeDraft(recommendation.id, 'value', event.target.value)}
                                required
                              />
                            </label>
                            <label>
                              Notes
                              <input
                                value={draft.notes ?? ''}
                                onChange={(event) => updateOutcomeDraft(recommendation.id, 'notes', event.target.value)}
                              />
                            </label>
                            <button type="submit">Record outcome</button>
                          </form>
                        )
                      )}
                    </div>
                  )
                })}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="executive-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Executive workflow</p>
            <h2>Brief, ask, and test a bounded decision</h2>
          </div>
          <span>Stored evidence only</span>
        </div>
        <div className="executive-grid">
          <article className="executive-card">
            <p className="eyebrow">Morning briefing</p>
            <h3>New material, on demand</h3>
            <button type="button" className="secondary-action" onClick={generateBriefing} disabled={briefingBusy}>
              {briefingBusy ? 'Generating…' : 'Generate executive briefing'}
            </button>
            {briefingResult && (
              briefingResult.generated ? (
                <div className="executive-result">
                  <p>{briefingResult.briefing.summary_text}</p>
                  <small>Insight IDs: {briefingResult.briefing.insight_ids.map((id) => id.slice(0, 8)).join(', ')}</small>
                </div>
              ) : <p className="empty-inline">{briefingResult.reason}</p>
            )}
          </article>

          <article className="executive-card">
            <p className="eyebrow">Grounded follow-up</p>
            <h3>Ask the stored evidence</h3>
            <form className="chat-form" onSubmit={askGroundedQuestion}>
              <label>
                Question
                <input value={chatQuestion} onChange={(event) => setChatQuestion(event.target.value)} maxLength="1000" required />
              </label>
              <button type="submit" className="secondary-action" disabled={chatBusy}>
                {chatBusy ? 'Answering…' : 'Ask grounded question'}
              </button>
            </form>
            {chatResult && (
              <div className="executive-result" aria-live="polite">
                <p>{chatResult.answer}</p>
                {chatResult.result === 'answer' && (
                  <small>Insight IDs: {chatResult.insight_ids.map((id) => id.slice(0, 8)).join(', ')} · Signal IDs: {chatResult.signal_ids.map((id) => id.slice(0, 8)).join(', ')}</small>
                )}
              </div>
            )}
          </article>

          <article className="executive-card scenario-card">
            <p className="eyebrow">What-if scenario</p>
            <h3>Marketing spend only</h3>
            <form className="scenario-form" onSubmit={generateForecast}>
              <label>
                Spend change (%)
                <input type="number" min="-20" max="20" step="1" value={scenarioInput.change} onChange={(event) => setScenarioInput((input) => ({ ...input, change: event.target.value }))} required />
              </label>
              <label>
                Horizon (days)
                <select value={scenarioInput.horizon} onChange={(event) => setScenarioInput((input) => ({ ...input, horizon: event.target.value }))}>
                  {[1, 2, 3, 4, 5, 6, 7].map((day) => <option key={day} value={day}>{day}</option>)}
                </select>
              </label>
              <button type="submit" disabled={forecastBusy}>{forecastBusy ? 'Forecasting…' : 'Run deterministic forecast'}</button>
            </form>
            {forecast && (
              <div className="forecast-result" aria-live="polite">
                <strong>Reliability {Number(forecast.reliability_score).toFixed(1)} / 100</strong>
                <p>Day {forecast.horizon_days} revenue: {Number(forecast.forecast_values.recognized_revenue.at(-1)).toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                <p>Day {forecast.horizon_days} CAC: {Number(forecast.forecast_values.client_acquisition_cost.at(-1)).toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>
                <small>Signal ID: {forecast.supporting_signal_ids[0].slice(0, 8)} · Deterministic scenario, not a causal guarantee.</small>
              </div>
            )}
          </article>
        </div>
      </section>

      <footer>All values are labelled synthetic. Recommendations are grounded in persisted evidence and remain human-controlled.</footer>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<App />)
