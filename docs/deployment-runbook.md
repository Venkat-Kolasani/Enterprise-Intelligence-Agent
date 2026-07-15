# MetricThread deployment runbook

This runbook creates a **read-only, synthetic judge demo**. It never asks you to put a secret in the frontend or repository.

## 1. Apply the Phase 6 Supabase migration

1. Open **Supabase Dashboard → SQL Editor → New query** for the MetricThread project.
2. Paste the complete contents of [`../db/migrations/003_phase6_readiness.sql`](../db/migrations/003_phase6_readiness.sql) and click **Run**.
3. Confirm the result says success.

This adds reversible active/superseded evidence state and a transactionally atomic insight-and-recommendation persistence function. It unblocks the active-evidence filters used by the current API and ensures a signal re-analysis cannot delete records still referenced by persisted forecasts.

## 2. Prepare funded OpenAI verification

This is mandatory before the public submission or video claims live GPT-5.6 output.

1. Add inference credit to the OpenAI Platform account with the intended API key.
2. Set the deployment-only variables below in Render:

   ```text
   AI_PROVIDER=openai
   OPENAI_API_KEY=<funded key>
   OPENAI_REASONING_MODEL=<verified GPT-5.6 model identifier>
   ```

3. Use an interactive, non-judge environment to run one structured insight generation and verify that it is evidence-linked and uses no causal language.
4. Record the result in the charter before saying that GPT-5.6 generated the live narrative.

The current documented development fallback is Gemini 3.1 Flash-Lite. Do not mislabel it as GPT-5.6 in a demo or Devpost submission.

## 3. Deploy the FastAPI API to Render

1. Push the approved Phase 6 commit to GitHub.
2. In Render, choose **New → Blueprint** and select this repository. The committed [`../render.yaml`](../render.yaml) configures a Docker web service and `/health` probe.
3. In the Render service's **Environment** page, set:

   ```text
   DEMO_READ_ONLY=true
   UPSTASH_REDIS_REST_URL=<Upstash REST URL>
   UPSTASH_REDIS_REST_TOKEN=<Upstash REST token>
   SUPABASE_URL=<Supabase project URL>
   SUPABASE_SECRET_KEY=<Supabase server-side secret key>
   CORS_ALLOWED_ORIGINS=<set after Step 4>
   ```

   For a confirmed GPT-5.6 deployment, add the three OpenAI variables in Step 2. Until then, either configure the documented Gemini fallback for an **interactive non-submission environment** or do not invoke new model generation in the read-only judge demo.

4. Deploy. Open `https://YOUR-RENDER-API/health`; the expected response is `{"status":"ok","demo_access":"read_only"}`.

The Render service uses port `$PORT` when Render supplies one and otherwise defaults to 10000. It exposes only synthetic, read-only judge functionality.

## 4. Deploy the frontend to Vercel

1. Import the same GitHub repository in Vercel. The committed [`../vercel.json`](../vercel.json) installs and builds `frontend/` and publishes `frontend/dist`.
2. Under **Project → Settings → Environment Variables**, add this production variable before deploying:

   ```text
   VITE_API_BASE_URL=https://YOUR-RENDER-API
   ```

3. Deploy and copy the exact production origin, for example `https://metricthread.vercel.app`.
4. Back in Render, set:

   ```text
   CORS_ALLOWED_ORIGINS=https://metricthread.vercel.app
   ```

5. Redeploy Render, then hard-refresh the Vercel site. Confirm the dashboard loads evidence and insights without browser console errors.

`VITE_API_BASE_URL` is public by design. Never add `SUPABASE_SECRET_KEY`, OpenAI keys, Gemini keys, or Upstash tokens to Vercel.

## 5. Run the API rehearsal

With the Render URL in hand:

```bash
uv run python -m scripts.phase6_rehearsal --base-url https://YOUR-RENDER-API.onrender.com
```

The rehearsal checks health, the synthetic label, read-only safety, corrected evidence, a persisted insight, a grounded CAC answer, an explicit unsupported-question refusal, an evidence-linked scenario, hot-path simulator visibility, and rejection of a persistent signal-analysis write. Then run the browser journey in the demo script against the Vercel URL.

## 6. Record and submit

1. Record the public YouTube video using [`demo-script.md`](demo-script.md). Keep the total narrated duration below three minutes.
2. Capture the `/feedback` session ID from the Codex session where the core functionality was built.
3. Complete every item in [`submission-checklist.md`](submission-checklist.md).
4. Only after the artifacts are verified and the user explicitly authorizes it, update the existing Devpost draft. Do not create a duplicate project.

## Operational recovery

- If Render reports a failed health check, inspect Render logs and confirm the process is binding to `$PORT`; test `/health` directly before touching Vercel.
- If the Vercel site reports an API error, verify `VITE_API_BASE_URL` was available during its build, then confirm the exact Vercel origin is in Render's `CORS_ALLOWED_ORIGINS` and redeploy Render.
- If the judge demo returns 403 for a persistent action, that is intentional. The scenario, chat, existing evidence, and simulation remain usable.
- If no signals or insights display, confirm the Phase 6 migration was applied and the server-side Supabase variables point at the seeded project.
