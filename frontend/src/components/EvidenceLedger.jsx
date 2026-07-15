import { humanizeMetric, shortId } from '../lib/api'

export function EvidenceLedger({ data }) {
  return (
    <section className="ledger-section">
      <div className="ledger-toolbar">
        <p>Candidate relationships are corrected as a family. Only retained results appear in this ledger.</p>
        <button type="button" className="outline-action" onClick={data.runSignalAnalysis} disabled={data.readOnlyDemo || data.busy.analysis}>
          {data.busy.analysis ? 'Testing history…' : 'Run deterministic analysis'}
        </button>
      </div>
      {data.signals.length === 0 ? (
        <p className="empty-message ledger-empty">No evidence retained yet. The engine requires at least 60 aligned observations and q ≤ 0.05 after correction.</p>
      ) : (
        <div className="ledger-table-wrap">
          <table className="evidence-ledger">
            <thead><tr><th scope="col">Thread</th><th scope="col">Evidence</th><th scope="col">Effect</th><th scope="col">Confidence</th><th scope="col">Model record</th></tr></thead>
            <tbody>
              {data.signals.map((signal) => (
                <tr key={signal.id}>
                  <td><strong>{humanizeMetric(signal.source.metric)}</strong><span>{signal.source.domain} <i>→</i> {humanizeMetric(signal.target.metric)}</span></td>
                  <td><b>{signal.direction}</b><span>q {Number(signal.adjusted_q_value).toExponential(2)} · F {Number(signal.f_statistic).toFixed(2)}</span></td>
                  <td><b>{Number(signal.effect_size).toFixed(3)} ΔR²</b><span>{signal.sample_size} observations</span></td>
                  <td><b>{Number(signal.confidence_score).toFixed(1)} / 100</b><span>{signal.confidence_version}</span></td>
                  <td><b>{shortId(signal.id)}</b><span>{signal.test_config_version}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="evidence-footnotes">
        <p><strong>Interpretation:</strong> evidence is consistent with predictive lead–lag relationships; it is not proof of causation.</p>
        <p><strong>Negative controls:</strong> planted unrelated series are intentionally absent when they fail the retention threshold.</p>
      </div>
    </section>
  )
}
