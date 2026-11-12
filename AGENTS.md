# Project instructions

Team Its IA — openJiuwen Challenge 2026.

- Read docs/requirements.md, docs/progress.md, docs/plan.md and docs/codex-handoff.md before implementing changes.
- Accepted harness research and experiment order: docs/harness-research-2026-11-12.md. Read the relevant experiment protocol before changing that component.
- Primary score is solved-task reward under a shared token budget, not predictor MAE.
- Use real openJiuwen execution; do not fake framework markers or harness evidence.
- Never commit API keys, invite codes, questionnaires, raw reports or unreviewed traces.
- Never use expected, sample IDs or future steps as solution/planning features.
- Keep public examples unchanged. The offline evaluator alone may read expected.
- Distinguish unsupported syntax from proven insufficient information.
- Preserve tests in coding tasks. Validate fixes by running them.
- Keep generated variants of the same source template together in validation groups.
- Record experiment configuration and measured results in docs/progress.md.
- Do not run bulk API experiments without a defined budget.
- A Python test is not a Docker test, and a parser test is not an API integration test.
- Runtime may access only the provided LLM proxy; no runtime downloads or GPU use.
- See the Nov 10 organizer clarification on CPU models in docs/requirements.md.
- Code and generated files must work with read-only /app and writable /tmp and tasks.
- Use branches/PRs for subsequent work. Do not overwrite another participant's changes.
