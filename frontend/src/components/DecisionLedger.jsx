import { useState } from 'react'
import { shortId } from '../lib/api'

function OutcomeForm({ onSubmit, disabled }) {
  const [draft, setDraft] = useState({ metric: 'client_acquisition_cost', value: '', notes: '' })

  function submit(event) {
    event.preventDefault()
    onSubmit(draft)
  }

  return (
    <form className="outcome-entry" onSubmit={submit}>
      <p>Record the observed result after implementation.</p>
      <label>Outcome metric<input value={draft.metric} disabled={disabled} onChange={(event) => setDraft({ ...draft, metric: event.target.value })} /></label>
      <label>Measured value<input type="number" step="any" required value={draft.value} disabled={disabled} onChange={(event) => setDraft({ ...draft, value: event.target.value })} /></label>
      <label>Notes<input value={draft.notes} disabled={disabled} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
      <button type="submit" className="ink-action" disabled={disabled}>Record outcome</button>
    </form>
  )
}

function RecommendationCard({ recommendation, data }) {
  const [lifecycleStatus, setLifecycleStatus] = useState(recommendation.status)
  const isUpdating = data.busy[`status-${recommendation.id}`]
  const isRecording = data.busy[`outcome-${recommendation.id}`]

  return (
    <article className="recommendation-record">
      <div className="record-state"><span>{recommendation.status}</span><small>Created {new Date(recommendation.created_at).toLocaleDateString()}</small></div>
      <h3>{recommendation.recommendation_text}</h3>
      <p>{recommendation.predicted_impact.statement}</p>
      <div className="record-evidence">Evidence signal <b>{recommendation.predicted_impact.evidence_signal_ids.map(shortId).join(', ')}</b> · Human review required</div>

      <div className="lifecycle-control">
        <label>Decision lifecycle
          <select value={lifecycleStatus} disabled={data.readOnlyDemo} onChange={(event) => setLifecycleStatus(event.target.value)}>
            <option value="proposed">Proposed</option>
            <option value="planned">Planned</option>
            <option value="implemented">Implemented</option>
          </select>
        </label>
        <button type="button" className="outline-action" disabled={data.readOnlyDemo || isUpdating} onClick={() => data.updateRecommendationStatus(recommendation.id, lifecycleStatus)}>
          {isUpdating ? 'Saving…' : 'Save lifecycle'}
        </button>
      </div>

      {recommendation.status === 'implemented' && (
        recommendation.outcome ? (
          <div className="recorded-outcome"><span>Measured outcome</span><strong>{recommendation.outcome.outcome_metric.replaceAll('_', ' ')} = {recommendation.outcome.outcome_value}</strong><p>{recommendation.outcome.notes || 'No implementation note was recorded.'}</p></div>
        ) : <OutcomeForm disabled={data.readOnlyDemo || isRecording} onSubmit={(draft) => data.recordOutcome(recommendation.id, draft)} />
      )}
    </article>
  )
}

export function DecisionLedger({ data }) {
  return (
    <section className="decision-section">
      <div className="decision-toolbar">
        <p>Language generation can describe accepted evidence; it cannot alter its confidence or execute an action.</p>
        <button type="button" className="ink-action" onClick={data.generateInsight} disabled={data.readOnlyDemo || data.busy.insight || data.signals.length === 0}>
          {data.busy.insight ? 'Writing grounded record…' : 'Generate recommendation'}
        </button>
      </div>
      {data.insights.length === 0 ? (
        <p className="empty-message ledger-empty">No recommendation exists yet. Create one only from a newly accepted evidence signal.</p>
      ) : data.insights.map((insight) => (
        <article className="insight-record" key={insight.id}>
          <div className="insight-title-row"><div><p className="kicker">{insight.domains.join(' / ')} · confidence {Number(insight.confidence_score).toFixed(1)}</p><h2>{insight.title}</h2></div><span>Insight {shortId(insight.id)}</span></div>
          <p className="insight-narrative">{insight.narrative_text}</p>
          <div className="recommendation-list">{insight.recommendations.map((recommendation) => <RecommendationCard key={recommendation.id} recommendation={recommendation} data={data} />)}</div>
        </article>
      ))}
    </section>
  )
}
