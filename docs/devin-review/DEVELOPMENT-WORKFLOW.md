# TradeX Development Workflow

> **Superseded by canonical documentation.** This historical review document is retained for context. Current TradeX AI-development and research-governance instructions live in [`docs/AI-DEVELOPMENT-WORKFLOW.md`](../AI-DEVELOPMENT-WORKFLOW.md) and [`docs/RESEARCH-PROTOCOL.md`](../RESEARCH-PROTOCOL.md), and the canonical project tracker is [`docs/PROJECT-TRACKER.md`](../PROJECT-TRACKER.md).

This document defines how TradeX should be developed after the initial audit. The goal is to keep each change small, reviewable, and focused on one coherent objective.

## Branch naming

Use the `devin/` prefix for Devin-authored work, followed by a concise description:

- `devin/fix-outcome-timing`
- `devin/redesign-signal-history`
- `devin/add-ci`
- `devin/refactor-dashboard-boundaries`
- `devin/add-backtest-engine`

Avoid vague names:
- `devin/updates`
- `devin/improvements`
- `devin/misc-fixes`

## Commit practices

- One logical purpose per commit.
- Keep commits small enough to review in a single diff screen.
- Do not mix automated formatting of the entire repository with functional changes.
- Do not commit credentials, `.env`, local databases, or generated artifacts.
- Write commit messages in the imperative: `Fix outcome tracker MultiIndex crash`, `Add signal-history audit table`.

## Pull-request scope

Each PR should address one coherent objective. Do not combine the following in a single PR unless they are genuinely inseparable:

- File reorganization
- Functional behavior changes
- Trading-logic changes
- Database migrations
- UI redesign
- Dependency upgrades
- Whole-repo formatting
- New features

When a file must be both moved and changed, prefer two PRs:
1. A mechanical move with no behavior change.
2. A separate PR containing the functional change.

## Pull-request template

A TradeX PR should answer:

1. **What changed?**
2. **Why does it matter?**
3. **What trading behavior is affected?** (if any)
4. **What tests were added or updated?**
5. **What documentation was updated?**
6. **How was it verified?** (e.g., `pytest`, manual dashboard check, backtest)

## Testing expectations

- Every bug fix must include a regression test.
- Every trading-logic change must include a characterization or backtest test.
- Every new module must include at least one unit test.
- Tests that require live credentials or external services must be marked and excluded from the default suite.
- Use deterministic fixtures; do not rely on live Yahoo/Alpaca/Schwab/IBKR responses for basic correctness tests.

### Running tests locally

```bash
cd /path/to/TradeX
uv run pytest
```

### Lint and typecheck

```bash
# Python linting
uv run ruff check .

# Type checking — add only after mypy is configured and an agreed baseline is fixed
# uv run mypy tradex
```

All PRs must pass `ruff check tests` and `pytest tests -q` before being opened. Add `mypy` to the CI workflow only after it is added as a dependency, configured, and an agreed baseline is established.

### CI checks

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every pull request and push to `main`:

```bash
uv sync --extra dev
uv run ruff check tests
uv run pytest tests -q
```

- The seven known bugs continue to be reported as `xfail`.
- An unexpected `XPASS` from a `strict=True` xfail fails the build.
- The workflow does not require external credentials or live market-data services.

## Documentation expectations

- Update the canonical doc for the topic (see `REPOSITORY-ORGANIZATION.md` for the map).
- Keep `README.md`, `CLAUDE.md`, and `SETUP.md` in sync after any user-facing change.
- If a change affects trading assumptions, document them in the relevant scorer docstring and in `TRADING-FEATURE-REVIEW.md` if it changes the feature verdict.
- Do not duplicate detailed information across multiple files; link instead.

## Decision-record process

Major architectural and trading decisions are recorded as lightweight ADRs in `docs/decisions/`.

Create an ADR when:
- Defining what an intraday signal means
- Defining what a coil is
- Deciding how signal episodes are deduplicated
- Deciding whether confluence requires all timeframes
- Choosing a backtesting execution model
- Defining the canonical market timezone
- Deciding how live and historical data are normalized
- Removing a feature
- Changing the database schema
- Drawing the boundary between research code and production code

Do not create ADRs for minor implementation details.

### ADR template

Each ADR should be short and contain:

```markdown
# ADR-NNNN: Title

## Status
Proposed / Accepted / Deprecated / Superseded by ADR-XXXX

## Context
What problem are we solving?

## Options
Briefly list the options considered.

## Decision
What was chosen.

## Rationale
Why this option over the others.

## Consequences
Positive and negative effects.

## What would change our minds
Evidence that would cause us to reconsider.
```

## Definition of done

A change is not complete until:

- Its purpose is documented.
- Its scope is clear and matches the PR title.
- Relevant tests pass.
- New behavior has test coverage.
- User-facing behavior is documented.
- Trading assumptions are stated.
- Error cases are handled.
- Logs provide enough information to diagnose failures.
- No credentials or runtime data are committed.
- The project tracker is updated.
- Any major decision is recorded in an ADR.
- The PR contains acceptance criteria.
- Documentation and implementation agree.

## How Devin should approach future TradeX assignments

1. **Read the project tracker first.** `docs/PROJECT-TRACKER.md` is the single source of truth for recommended next work.
2. **Confirm the assignment maps to one coherent project.** If it spans multiple roadmap projects, ask the user which to start with.
3. **Open a branch** named `devin/<description>` from the latest `main`.
4. **Add or update tests** before or alongside any code change.
5. **Run `pytest` and `ruff`** before opening a PR. Add `mypy` after it is configured and an agreed baseline is fixed.
6. **Update documentation** in the canonical location.
7. **Open a draft PR early** if the change is large or uncertain.
8. **Stop after opening the PR** unless explicitly asked to iterate on CI or review feedback.

## Research workflow

1. Create a new directory under `research/experiments/YYYY-MM-DD_<short_name>`.
2. Write a `README.md` with hypothesis, universe, signal, entry/exit, costs, and decision criteria.
3. Use notebooks or scripts; do not modify `tradex/` production code from research.
4. Record results and limitations.
5. If the experiment is adopted, create a separate PR to implement it in `tradex/` with tests.

## Security and credentials

- Never commit API keys, tokens, or passwords.
- Keep `.env` in `.gitignore`.
- For local development, create `.env` from `.env.example` and fill in only what is needed.
- Use repo/org secrets for CI; never hardcode them.

---

This workflow is itself a living document. Propose changes via ADR or a PR to this file.
