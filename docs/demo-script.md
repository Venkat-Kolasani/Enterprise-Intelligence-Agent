# MetricThread public demo script (target: 2 minutes 50 seconds)

Use the deployed Vercel URL after the API rehearsal passes. Keep the pace conversational and show the real interface rather than reading labels verbatim.

| Time | On screen | Voiceover |
| --- | --- | --- |
| 0:00–0:15 | Home, then open the workspace | “MetricThread is an Enterprise Intelligence Agent for a VP of Growth. Instead of asking an AI to guess at business patterns, it finds statistically validated cross-functional signals first, then turns them into an auditable decision workflow.” |
| 0:15–0:32 | Start live feed; wait for metrics | “This workspace watches Client, Financial, and Partner signals. A compressed business day arrives every five seconds through Redis Streams. One path powers the live view; a second durable path keeps the evidence available for analysis.” |
| 0:32–1:00 | Evidence Ledger, then primary Evidence Casefile | “Here is the key distinction: this relationship is not just a chart insight. The Evidence Casefile replays the source and target series, shows the candidate-test family, rejected negative controls, ADF preparation, q-value, F-statistic, effect size, fingerprint, and the confidence formula behind the signal.” |
| 1:00–1:25 | Evidence Resilience: primary then suppressed signal | “A full-history result is still not enough. MetricThread validates the evidence across rolling historical windows, compares it with a target-history baseline, and requires the negative controls to stay rejected. A relationship that fails this check is visibly suppressed before it can create a new recommendation.” |
| 1:25–1:52 | Recommendation and Explain Why | “This is where GPT-5.6 fits. It is the evidence-grounded reasoning layer, not the statistical engine. It receives only this compact validated evidence packet, must return structured output with the stored signal ID, and cannot alter the deterministic confidence score. The server rejects unsupported citations and causal language.” |
| 1:52–2:12 | Chat: CAC question, then unsupported question | “The same evidence boundary powers the briefing and chat experience. A supported question returns the stored insight and signal IDs. An unsupported question returns no evidence instead of a plausible-sounding answer.” |
| 2:12–2:30 | Scenario Lab: +10%, seven days | “For a what-if decision, I can change marketing spend within a constrained range. The forecast is deterministic and back-tested, with a baseline, prediction interval, reliability score, assumptions, and supporting evidence.” |
| 2:30–2:50 | Decision Record; move status and record outcome | “Finally, this is not a static dashboard. A team can move a recommendation from proposed to planned to implemented and record the measured outcome. I used Codex to help build the pipeline, statistical engine, evidence experience, testing, and deployment workflow. MetricThread makes every recommendation something a team can inspect before it acts.” |

## Recording checklist

- [ ] Public Vercel URL and Render API rehearsal pass before recording.
- [ ] Browser console is clean and the live workspace is usable.
- [ ] Audio explicitly explains both Codex use and GPT-5.6 use, as required by the challenge.
- [ ] Public YouTube visibility is selected and final duration is under three minutes.
- [ ] Video description links to the public repository and deployment.
