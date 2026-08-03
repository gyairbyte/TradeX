# TradeX AI Development Workflow

## Purpose

This document defines how Gary, ChatGPT, Devin, and Codex work together to develop TradeX.

TradeX is a stock-market opportunity identification and trading-research application. It scans securities across intraday, short-term, and long-term timeframes and helps identify, monitor, and evaluate possible trading setups.

TradeX is currently a research and decision-support application. It is not authorized to execute live trades automatically.

Correctness, explainability, auditability, and research integrity are more important than adding features quickly or producing attractive historical performance.

## Roles

### Gary Yang

Gary is the product owner and final decision-maker.

Gary:

* Sets product priorities.
* Approves material scope and product decisions.
* Decides whether research evidence is sufficient to consider a production change.
* Makes the final decision when product or risk tradeoffs remain.

### ChatGPT

ChatGPT is the primary:

* Product manager
* Technical architect
* Research planner
* UX strategist
* Engineering manager
* Devin task designer
* Implementation reviewer

ChatGPT is responsible for:

* Understanding the user problem.
* Evaluating whether a feature should exist.
* Defining MVP scope and product priorities.
* Designing architecture and workflows.
* Turning trading ideas into testable hypotheses.
* Defining task scope, acceptance criteria, tests, and out-of-scope items.
* Reviewing Devin’s implementation and evidence.
* Separating research findings from production changes.
* Recommending the next action to Gary.

ChatGPT should inspect the current repository when behavior may have changed rather than relying only on conversational memory.

### Devin

Devin is the primary builder.

Devin is responsible for:

* Inspecting the repository and confirming current behavior.
* Identifying affected components, dependencies, risks, and edge cases.
* Producing a concise implementation plan.
* Implementing approved assignments.
* Adding and updating tests.
* Running required tests and lint checks.
* Updating documentation.
* Creating dedicated branches and focused pull requests.
* Addressing review feedback.
* Reporting limitations, deviations, and unresolved issues.

Devin must not silently expand scope, reinterpret product requirements, change trading behavior, or replace an approved research methodology.

### Codex

Codex is used only when a material technical disagreement between ChatGPT and Devin remains unresolved after reviewing:

* Repository code
* Tests
* Documentation
* Dependency behavior
* Reproducible examples

Codex may independently investigate:

* Conflicting interpretations of current behavior
* Difficult bugs
* Architecture disputes
* Lookahead bias
* Data leakage
* Research-validity concerns
* Whether acceptance criteria were actually met

Codex should not normally duplicate Devin’s implementation.

## Approval and Merge Authority

Gary remains the final product owner and decision-maker. He delegates authority to ChatGPT to approve and merge a pull request when all of the following are true:

* The assignment was previously approved by Gary.
* The implementation matches the approved scope.
* Required tests, lint checks, and CI pass.
* No unresolved material review comments or technical disagreements remain.
* Documentation and tracker updates are complete.
* The PR clearly states its behavior and trading impact.
* The change is not in a category requiring Gary's explicit approval.

ChatGPT may normally approve and merge routine documentation, testing, correctness, infrastructure, reliability, and non-trading UI work that meets those conditions.

Require Gary's explicit approval before merge for:

* Production signal, score, weight, threshold, ranking, eligibility, or default screener changes.
* Promotion of research-only logic into production.
* Live trading, brokerage, order, or account functionality.
* Major architecture changes.
* Destructive or difficult-to-reverse migrations.
* Material security, privacy, financial, legal, or compliance changes.
* Scope expansion beyond the approved assignment.
* PRs with failing checks, unresolved material comments, inconclusive evidence, or unresolved disagreement.

When delegated authority does not apply, ChatGPT should recommend the next action to Gary rather than approve or merge.

## Sources of Truth

Use the following as the source of truth:

* Current repository code
* Automated tests
* Locked research artifacts
* `README.md`
* `SETUP.md`
* `CLAUDE.md`
* `docs/AI-DEVELOPMENT-WORKFLOW.md`
* `docs/RESEARCH-PROTOCOL.md`
* `docs/PROJECT-TRACKER.md`
* Relevant architecture and decision records
* The approved task-specific assignment

When sources conflict, surface the inconsistency and resolve it explicitly. Do not silently choose whichever instruction is easiest to implement.

## Standard Development Workflow

For significant work:

1. Define the user problem and intended outcome.
2. Inspect the repository and relevant documentation.
3. Confirm current behavior.
4. Define required behavior, scope, risks, edge cases, and dependencies.
5. Classify the task.
6. Produce a bounded assignment.
7. Define objective acceptance criteria and testing requirements.
8. Implement the work in a dedicated branch.
9. Add or update tests.
10. Run required checks.
11. Update affected documentation and the project tracker.
12. Open a focused pull request.
13. Review implementation, tests, scope, assumptions, and limitations.
14. Use Codex only if a material disagreement remains.
15. Require passing tests and clear evidence before approving or merging, when delegated authority applies.

## Task Classification

Every assignment must be classified as one of the following.

### Research-only

The work evaluates a hypothesis or candidate policy and must not change production behavior.

### Production-facing without changing trading logic

The work may affect infrastructure, data handling, persistence, reliability, testing, documentation, or UI, but must not change how opportunities are scored, selected, ranked, or described as eligible.

### Explicitly approved production trading-logic change

The assignment has explicit approval to change production:

* Signals
* Scores
* Weights
* Thresholds
* Eligibility
* Rankings
* Trading-related alerts
* Default screener behavior

If an assignment is unclear, treat it as research-only or as production-facing without changing trading logic.

## Scope Discipline

Each assignment should normally represent one bounded unit of work suitable for one branch and pull request.

Do not:

* Add unrelated features.
* Perform broad cleanup without approval.
* Redesign unrelated components.
* Change public interfaces unnecessarily.
* Modify production trading logic without explicit approval.
* Promote research-only logic into production.
* Optimize parameters against a holdout dataset.
* Hide failures with broad exception handling.
* Weaken tests merely to make the suite pass.
* Expose secrets or credentials.

Necessary supporting changes are allowed only when they are directly required for the assignment and are explained in the pull request.

## Devin Assignment Requirements

Every Devin assignment should include:

* Task ID and title
* Objective
* Why the work matters
* Verified current behavior
* Required behavior
* In-scope items
* Out-of-scope items
* Relevant files and dependencies
* Task classification
* Expected impact on production and research outputs
* Functional and data requirements
* Research safeguards when applicable
* Acceptance criteria
* Required tests
* Documentation requirements
* Branch and pull-request requirements
* Required completion report

Before coding, Devin must:

1. Read the relevant repository instructions.
2. Inspect and verify current behavior.
3. Report material discrepancies or concerns.
4. Classify the task.
5. Explain affected outputs.
6. Provide a concise implementation plan.

## Handling Disagreements

If Devin believes a requirement is technically incorrect, unsafe, incompatible with the repository, or likely to create invalid research, Devin must:

1. Identify the exact disputed requirement.
2. Cite relevant files, functions, tests, documentation, or dependency behavior.
3. Provide a reproducible example when practical.
4. Explain the consequence.
5. Recommend a specific alternative.
6. State whether safe implementation can continue.

Devin must not silently implement a different interpretation.

Use Codex only when repository evidence does not resolve a material disagreement.

Gary remains the final product decision-maker.

## Implementation Standards

Prefer code that is:

* Simple
* Readable
* Explicit
* Modular
* Testable
* Auditable
* Consistent with existing repository patterns

Preserve:

* Human-readable signal reasons
* Provider provenance
* Stable schemas
* Backward compatibility where practical
* Deterministic behavior where required
* Visible and actionable failures

Avoid unnecessary abstraction and unvalidated complexity.

## Testing Standards

Tests must prove intended behavior rather than merely execute the new code.

When applicable, cover:

* Expected behavior
* Empty input
* No-result behavior
* Missing or malformed data
* Invalid numeric values
* Partial provider failure
* Boundary conditions
* Timezone and market-session boundaries
* Weekend and holiday handling
* Database migrations
* Backward compatibility
* Determinism
* Regression cases
* Explicitly prohibited behavior
* Research split integrity
* Point-in-time correctness

Do not remove or weaken an existing test unless it is demonstrably incorrect and the reason is documented.

Keep real-provider smoke tests separate from deterministic credential-free CI tests.

## Error Handling

TradeX must not fail silently.

Errors should be:

* Visible
* Actionable
* Associated with the relevant ticker, provider, timeframe, scan, or study
* Preserved in audit output when appropriate

Graceful degradation is acceptable only when partial or missing behavior is clearly surfaced.

Do not turn unknown failures into successful empty results.

## Security

Never commit or expose:

* API keys
* OAuth tokens
* Brokerage credentials
* Account identifiers
* Passwords
* Private certificates
* `.env` contents
* Local token files
* Personally identifiable financial information

Use environment variables and existing credential-handling patterns.

TradeX is not currently authorized to place live trades or perform account actions.

## Pull Request Requirements

Each pull request should include:

### Problem

What problem is being solved.

### Scope

What is included.

### Out of Scope

What was intentionally not changed.

### Implementation

The important technical changes.

### Behavior Before and After

What changed from the user or system perspective.

### Trading Impact

State whether the PR changes:

* Production signals
* Scores
* Weights
* Thresholds
* Rankings
* Eligibility
* Alerts
* Backtests
* Research outputs
* Stored data
* Dashboard behavior

### Testing

List the commands run and their results.

### Research Safeguards

For research or trading work, describe applicable protections for point-in-time correctness, split isolation, provider provenance, determinism, execution assumptions, and leakage prevention.

### Risks and Limitations

Document known limitations and unresolved questions.

### Follow-Up Work

List related work intentionally deferred.

## Required Completion Report

Devin’s final report must include:

* Summary
* Branch and pull-request link
* Important files changed
* Behavior before and after
* Trading impact
* Test and validation commands with results
* Research safeguards when applicable
* Documentation updated
* Limitations and unresolved questions
* Any deviation from the approved assignment

Do not represent incomplete, blocked, untested, or inconclusive work as completed.

## Operating Principle

The goal is not merely to produce code.

The goal is to implement approved TradeX work accurately, safely, transparently, and with enough evidence for Gary and ChatGPT to approve or merge it, when delegated authority applies.

