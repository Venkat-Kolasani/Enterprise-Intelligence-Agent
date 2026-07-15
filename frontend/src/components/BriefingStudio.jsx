import { useState } from 'react'
import { shortId } from '../lib/api'

export function BriefingStudio({ data }) {
  const [question, setQuestion] = useState('Why is CAC rising?')

  function askQuestion(event) {
    event.preventDefault()
    data.askGroundedQuestion(question)
  }

  const displayedBriefing = data.briefingResult?.generated ? data.briefingResult.briefing : data.latestBriefing

  return (
    <section className="briefing-layout">
      <article className="briefing-paper">
        <div className="paper-header"><div><p className="kicker">Executive briefing</p><h2>What needs attention</h2></div><span>{displayedBriefing ? 'STORED' : 'WAITING'}</span></div>
        {displayedBriefing ? (
          <div className="briefing-copy"><p>{displayedBriefing.summary_text}</p><small>Insight IDs: {displayedBriefing.insight_ids.map(shortId).join(', ')}</small></div>
        ) : <p className="empty-message">No persisted briefing is available yet.</p>}
        {data.briefingResult && !data.briefingResult.generated && <p className="briefing-reason">{data.briefingResult.reason}</p>}
        <button type="button" className="ink-action" onClick={data.generateBriefing} disabled={data.readOnlyDemo || data.busy.briefing}>
          {data.busy.briefing ? 'Preparing briefing…' : 'Generate a current briefing'}
        </button>
      </article>

      <article className="grounded-question">
        <p className="kicker">Evidence-bound follow-up</p>
        <h2>Ask the record.</h2>
        <p>Questions without stored support return an explicit no-evidence result.</p>
        <form onSubmit={askQuestion}>
          <label>Your question<input value={question} maxLength="1000" required onChange={(event) => setQuestion(event.target.value)} /></label>
          <button type="submit" className="outline-action" disabled={data.busy.chat}>{data.busy.chat ? 'Checking evidence…' : 'Ask grounded question'}</button>
        </form>
        {data.chatResult && (
          <div className="chat-answer" aria-live="polite"><p>{data.chatResult.answer}</p>{data.chatResult.result === 'answer' && <small>Insights {data.chatResult.insight_ids.map(shortId).join(', ')} · Signals {data.chatResult.signal_ids.map(shortId).join(', ')}</small>}</div>
        )}
      </article>
    </section>
  )
}
