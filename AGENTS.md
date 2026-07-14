# AGENTS.md

## Before any work

Read `enterprise_intelligence_agent_project_charter.md` in full before proposing or writing anything. Follow the phases in Section 10 in order. Do not skip a phase or reorder it, and do not start Phase 1 until Phase 0 research is recorded in Section 13 of the charter.

## Sub-phase workflow

Each sub-phase in Section 10 follows this exact sequence, in order, every time:

1. Build the deliverables listed for that sub-phase.
2. Run the four checks from Section 12 of the charter: correctness, negative control, latency and reliability where applicable, and groundedness where applicable. Report the actual results, not a summary claiming success.
3. Add a decision log entry to Section 13 of the charter, in the format specified there, for every meaningful choice made in that sub-phase, including ones made under time pressure.
4. Stop and present a summary of what was built, the test results, and the documentation update. Wait for explicit approval before continuing.
5. Only after approval is given, commit the work with a clear, specific commit message describing what changed and why, and push to the remote repository. Do not batch multiple sub-phases into one commit and do not push before approval is given.

Do not mark a sub-phase complete or move to the next one until all five steps above are done.

## Demo checkpoints

At the end of every phase in Section 10, not just at the very end of the project, show a working demo of what that phase added, even if the rest of the system is unfinished. This means running the actual pipeline or interface for that phase and showing real output, not describing what it would do. If a phase has nothing visually demoable on its own, for example a schema-only phase, say so plainly instead of stretching another phase's output to fill the gap.

## Manual steps

Anything that cannot be done by Codex directly, such as creating a `.env` file with real API keys, creating a Supabase project and copying its connection string, creating an Upstash Redis instance, setting a Vercel or Render environment variable through their dashboards, or authorizing a GitHub token, must be flagged clearly and separately from regular progress updates. For each manual step, provide:

- What needs to be created or obtained, and where, for example the exact dashboard and setting name
- The exact variable name Codex expects it to be stored under
- Confirmation of what happens once it is provided, so it is clear the step actually unblocks something

Do not proceed past a step that depends on a manual input that has not been confirmed as complete. Do not invent placeholder keys or silently skip the step.

## Code quality

Write code the way a careful engineer would, not the way a language model defaults to when unsupervised. Concretely, this means:

- No unnecessary abstraction, no speculative generality for requirements that do not exist yet in the current phase
- No dead code, no commented-out blocks left in place, no unused imports or variables
- No filler comments that restate what the code already says, comments should explain why a non-obvious choice was made, not what a line does
- Function and variable names describe what they hold or do, not generic placeholders
- Errors are handled explicitly and specifically, not swallowed with a broad catch-all
- No inventing library methods or config options that were not verified to exist, check before using
- Match the conventions already established earlier in the project rather than introducing a new style each phase

If a shortcut is taken for time reasons, say so directly in the sub-phase summary and log it as a decision with a stated revisit trigger, rather than leaving it unmarked in the code.

## Testing

Run the project's test command before proposing any diff and before every commit. Do not report a sub-phase as tested without having actually run the tests in that session.

## Documentation

Every architectural choice is logged in Section 13 of the charter with its alternatives and rationale, not left only as a code comment. Code comments explain local, in-the-moment reasoning. The decision log explains the reasoning a person defending the project later would need.
