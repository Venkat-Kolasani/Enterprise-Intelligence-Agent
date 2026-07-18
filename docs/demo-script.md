# MetricThread public demo script (target: 2 minutes 40 seconds)

Use the deployed Vercel URL. This script is intentionally conditional on the required funded GPT-5.6 verification: do not say GPT-5.6 generated a result until that check has actually passed and is documented.

| Time | On screen | Narration |
| --- | --- | --- |
| 0:00–0:12 | Title and status rail | “MetricThread is an Enterprise Intelligence Agent for a VP of Growth. It watches signals across Client, Financial, and Partner data and connects the evidence to a real decision workflow.” |
| 0:12–0:25 | Start simulation; show metric cards update | “A compressed day of nine business events arrives every five seconds. Redis Streams send each event to both a hot dashboard path and a durable analytical path.” |
| 0:25–0:55 | Evidence Casefile; open primary signal | “This Casefile replays the actual source and target series, shows every candidate and rejection, ADF preparation, q, F, effect size, fingerprint, confidence formula, and the exact compact evidence packet. It says partner referral quality is predictive of CAC—not that it causes CAC.” |
| 0:55–1:15 | Evidence Resilience; show primary then suppressed secondary signal | “A full-history result is not enough. Four rolling historical origins must keep the signal, beat a target-history-only baseline at least three times, and reject both negative controls every time. The primary signal passes; this weaker retained signal is visibly suppressed, so no new model recommendation can be generated from it.” |
| 1:15–1:35 | Insight, Explain Why, recommendation | “Only resilience-eligible accepted evidence can reach the reasoning layer. [After the funded check: ‘GPT-5.6 received this compact evidence packet and produced this cited narrative.’] The stored confidence remains deterministic, and the recommendation is human-controlled: proposed, planned, then implemented.” |
| 1:35–1:55 | Ask “Why is CAC rising?” then unsupported competitor question | “The grounded chat returns the stored insight and signal IDs for the CAC question. An unsupported competitor-pricing question refuses with no evidence instead of inventing an answer.” |
| 1:55–2:15 | +10%, seven-day scenario | “For a limited what-if, I can change marketing spend by up to 20% for one to seven days. This forecast is deterministic and back-tested; it shows a baseline, prediction interval, assumptions, reliability, and its supporting signal ID. It is not a causal promise.” |
| 2:15–2:40 | Decision record and repository README | “A reviewer can move this recommendation through planned and implemented, then record the measured outcome. Codex was used to build the streaming pipeline, statistical checks, test suite, deployment setup, and documentation. The repository documents the evidence trail and how to reproduce the workspace.” |

## Recording checklist

- [ ] Public Vercel URL and Render API rehearsal pass before recording.
- [ ] Browser console is clean and the live workspace is usable.
- [ ] Live GPT-5.6 generation has passed only if that claim is spoken or shown.
- [ ] Audio explicitly explains both Codex use and GPT-5.6 use, as required by the challenge.
- [ ] Public YouTube visibility is selected and final duration is under three minutes.
- [ ] Video description links to the public repository and deployment.
