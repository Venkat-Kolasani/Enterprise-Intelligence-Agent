import { useState } from 'react'
import { formatValue, shortId } from '../lib/api'

export function ScenarioLab({ data }) {
  const [change, setChange] = useState(10)
  const [horizon, setHorizon] = useState(7)

  function submit(event) {
    event.preventDefault()
    data.generateForecast(change, horizon)
  }

  const forecast = data.forecast

  return (
    <section className="scenario-layout">
      <article className="scenario-brief">
        <p className="kicker">Constrained scenario</p>
        <h2>Change marketing spend. See a bounded seven-day path.</h2>
        <p>This deterministic forecast accepts only marketing-spend changes between −20% and +20%. Reliability reflects backtesting and interval width.</p>
        <dl><div><dt>Input</dt><dd>Marketing spend</dd></div><div><dt>Horizon</dt><dd>1–7 days</dd></div><div><dt>Output</dt><dd>Revenue and CAC</dd></div></dl>
      </article>
      <article className="scenario-console">
        <form onSubmit={submit}>
          <label>Spend change (%)<input type="number" min="-20" max="20" step="1" value={change} onChange={(event) => setChange(event.target.value)} required /></label>
          <label>Forecast horizon<select value={horizon} onChange={(event) => setHorizon(event.target.value)}>{[1, 2, 3, 4, 5, 6, 7].map((day) => <option key={day} value={day}>{day} day{day === 1 ? '' : 's'}</option>)}</select></label>
          <button type="submit" className="ink-action" disabled={data.busy.forecast}>{data.busy.forecast ? 'Calculating…' : 'Run deterministic forecast'}</button>
        </form>
        {forecast ? (
          <div className="forecast-paper" aria-live="polite">
            <div><span>RELIABILITY</span><strong>{Number(forecast.reliability_score).toFixed(1)}<small>/ 100</small></strong></div>
            <p>Day {forecast.horizon_days} recognised revenue <b>{formatValue(forecast.forecast_values.recognized_revenue.at(-1), 0)}</b></p>
            <p>Day {forecast.horizon_days} client acquisition cost <b>{formatValue(forecast.forecast_values.client_acquisition_cost.at(-1))}</b></p>
            <small>Supporting signal {shortId(forecast.supporting_signal_ids[0])} · Deterministic scenario, not a causal guarantee.</small>
          </div>
        ) : <p className="empty-message">Run a scenario to reveal the predicted path and its reliability.</p>}
      </article>
    </section>
  )
}
