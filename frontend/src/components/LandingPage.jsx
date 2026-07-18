import { BrandLockup } from './BrandMark'

const operatingPrinciples = [
  ['Observe', 'Bring client, partner, and financial signals into a single, replayable event history.'],
  ['Verify', 'Retain only statistically corrected lead–lag evidence, with its model history and fingerprint.'],
  ['Decide', 'Give people a proposed action, its evidence IDs, a lifecycle, and an outcome record.'],
]

export function LandingPage() {
  return (
    <main className="home-shell">
      <header className="site-header">
        <a className="brand-link" href="/" aria-label="MetricThread home"><BrandLockup /></a>
        <nav className="site-nav" aria-label="Primary navigation">
          <a href="#method">Method</a>
          <a href="#protocol">Protocol</a>
          <a href="/app">Workspace</a>
        </nav>
        <a className="text-action" href="/app">Open workspace <span aria-hidden="true">↗</span></a>
      </header>

      <section className="home-hero" aria-labelledby="home-title">
        <div className="hero-copy">
          <p className="kicker">Grounded enterprise intelligence</p>
          <h1 id="home-title">A decision should carry the thread of its evidence.</h1>
          <p className="hero-intro">
            MetricThread observes cross-functional business signals, tests what deserves attention, and gives teams an auditable path from signal to human action.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="/app">Enter the live workspace <span aria-hidden="true">→</span></a>
            <a className="quiet-action" href="#method">See the method <span aria-hidden="true">↓</span></a>
          </div>
        </div>

        <div className="thread-study" aria-label="Example evidence thread from partner referral quality to human review">
          <div className="study-topline"><span>LIVE STUDY / SOUTH GROWTH</span><b>ACTIVE</b></div>
          <div className="study-grid">
            <article className="thread-card observation">
              <span className="thread-number">01</span>
              <p>Observed</p>
              <h2>Partner referral<br />quality</h2>
              <strong>↓ change detected</strong>
            </article>
            <div className="thread-connector"><span>evidence</span><i /></div>
            <article className="thread-card evidence">
              <span className="thread-number">02</span>
              <p>Verified</p>
              <h2>Predictive<br />lead–lag</h2>
              <strong>q &lt; 0.05</strong>
            </article>
            <div className="thread-connector"><span>review</span><i /></div>
            <article className="thread-card action">
              <span className="thread-number">03</span>
              <p>Human action</p>
              <h2>Referral criteria<br />review</h2>
              <strong>proposed</strong>
            </article>
          </div>
          <div className="study-caption"><span className="pulse-dot" aria-hidden="true" /> Evidence is predictive, not proof of causation.</div>
        </div>
      </section>

      <section className="proof-band" aria-label="MetricThread principles">
        <p><span>01</span> Evidence first</p>
        <p><span>02</span> Human controlled</p>
        <p><span>03</span> Accountable decisions</p>
      </section>

      <section className="method-section" id="method" aria-labelledby="method-title">
        <div className="method-heading">
          <p className="kicker">The operating method</p>
          <h2 id="method-title">Less dashboard theatre.<br />More defensible judgment.</h2>
        </div>
        <ol className="principle-list">
          {operatingPrinciples.map(([step, detail], index) => (
            <li key={step}>
              <span>0{index + 1}</span>
              <div><h3>{step}</h3><p>{detail}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="protocol-section" id="protocol">
        <div>
          <p className="kicker">A claim has a boundary</p>
          <h2>Designed to say<br />what it knows.</h2>
        </div>
        <div className="protocol-copy">
          <p>
            MetricThread uses deterministic statistics before language generation. A narrative can explain a retained signal, but it cannot alter the evidence, confidence score, or decision record.
          </p>
          <dl>
            <div><dt>Input</dt><dd>Seeded, cross-functional event history</dd></div>
            <div><dt>Test</dt><dd>BIC selection + Benjamini–Hochberg correction</dd></div>
            <div><dt>Output</dt><dd>Evidence-linked, human-controlled recommendation</dd></div>
          </dl>
        </div>
      </section>

      <section className="home-cta">
        <p className="kicker">Ready for inspection</p>
        <h2>Follow one signal<br />all the way through.</h2>
        <a className="primary-action" href="/app">Open the decision workspace <span aria-hidden="true">→</span></a>
      </section>

      <footer className="site-footer">
        <BrandLockup />
        <p>MetricThread / Enterprise intelligence agent</p>
      </footer>
    </main>
  )
}
