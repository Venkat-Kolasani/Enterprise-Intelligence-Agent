# Codex and model collaboration record

MetricThread was developed in approved, documented phases. This record is deliberately factual rather than promotional so a reviewer can distinguish implemented behavior from pending deployment evidence.

## Codex contribution

Codex was used to plan the architecture, implement the React/Vite and FastAPI application, create the synthetic generator, build Redis Stream consumer-group logic, implement deterministic ADF/BIC/Granger/BH analysis, write the evidence and recommendation stores, add automated tests, run browser and API checks, and produce deployment/runbook/submission documentation. Each completed phase is recorded with actual results and engineering choices in [the charter](../enterprise_intelligence_agent_project_charter.md#13-decision-log-and-documentation-protocol).

## Reasoning-model contribution and boundary

The product includes an OpenAI Responses structured-output integration for GPT-5.6. It provides the model only an accepted stored evidence packet; server validation requires the cited signal ID to match, rejects causal wording, preserves the deterministic confidence score, and refuses unsupported evidence.

During development, the supplied OpenAI account passed model preflight but returned `429 insufficient_quota` on inference. No GPT-5.6 narrative was persisted. With the user's approval, the running development fallback became Gemini 3.1 Flash-Lite using the same strict evidence contract. The verified live persisted insight in Phase 4 is therefore Gemini output, not GPT-5.6 output.

Before Build Week submission, a funded OpenAI call must complete successfully with the selected GPT-5.6 model and pass the same cited-ID, non-causal-language, confidence, and refusal checks. The public video and Devpost text must reflect the provider that actually generated the shown narrative.

## Audit trail

- The deterministic generator creates 180 daily points across nine metrics (1,620 events) with a seeded partner-referral-quality to CAC evaluation relationship and two unrelated negative controls.
- The signal engine tests the full directed cross-domain candidate family, corrects p-values using Benjamini–Hochberg, and persists only `q <= 0.05` active evidence with a fingerprint and confidence components.
- Insights retain related signal IDs. Scenario forecasts retain supporting signal IDs. The Phase 6 migration changes stale signal handling from deletion to an explicit `superseded` state so existing forecasts remain auditable.
- The deployed judge mode is intentionally non-destructive: it serves persisted evidence, chat, simulations, and ephemeral scenarios while blocking mutations to the evidence, insight, lifecycle, outcome, and briefing stores.

## Required manual record before submission

Add the following only after each item has actually been verified:

```text
Funded GPT-5.6 verification timestamp:
Verified OpenAI model identifier:
Grounded insight ID produced by GPT-5.6:
Public Vercel URL:
Public Render URL:
YouTube URL:
Codex /feedback session ID:
Devpost draft update authorization:
```
