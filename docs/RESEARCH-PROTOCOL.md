# TradeX Research Protocol

## Purpose

This document defines the minimum standards for evaluating TradeX trading hypotheses, signals, filters, scores, thresholds, and strategy changes.

The purpose of TradeX research is to determine whether a candidate idea provides credible decision value. It is not to manufacture an attractive backtest.

An appealing historical result is not proof of a durable trading edge.

## Applicability

Follow this protocol for proposed changes involving:

* Signals
* Indicators
* Features
* Scoring components
* Weights
* Thresholds
* Eligibility rules
* Market-regime filters
* Relative-strength filters
* Coil logic
* Confluence logic
* Pattern matching
* Entry or exit rules
* Stops and targets
* Holding periods
* Position-sizing assumptions
* Trading-related alerts
* Any policy that may affect candidate ranking or selection

Correctness, infrastructure, documentation, and UI changes that do not alter trading behavior may use normal software-development standards instead.

## Begin With a Hypothesis

A research assignment should begin with a falsifiable hypothesis.

A useful hypothesis identifies:

* The observable condition
* The target population
* The expected outcome
* The comparison or baseline
* The evaluation horizon

Avoid vague objectives such as:

* Improve the strategy
* Increase the win rate
* Find the best indicators
* Optimize the weights
* Make TradeX more accurate

Convert them into testable questions.

## Predefine the Study

Before examining validation or holdout results, define when applicable:

* Securities universe
* Inclusion and exclusion rules
* Market-data provider
* Dataset version or manifest
* Date range
* Development period
* Validation period
* Untouched holdout period
* Warm-up period
* Signal timestamp
* Entry timing
* Exit timing
* Holding period
* Stop-loss rule
* Take-profit rule
* Same-bar execution policy
* Slippage
* Commissions
* Liquidity assumptions
* Benchmark
* Minimum number of observations
* Per-ticker and pooled reporting
* Success criteria
* Failure criteria
* Inconclusive criteria
* Promotion requirements

Do not redefine success criteria after seeing holdout performance.

## Dataset Integrity

Research inputs should be:

* Versioned or manifest-locked
* Reproducible
* Provider-aware
* Timestamped
* Auditable
* Validated before evaluation

Record enough information to identify:

* Provider
* Request parameters
* Symbols
* Date coverage
* Timeframe
* Adjustment policy
* Missing observations
* Duplicates
* Data-quality failures
* Dataset or manifest hash when practical

Do not silently replace missing observations with zero.

Do not silently switch providers.

Do not fabricate historical values that cannot be reconstructed.

## Point-in-Time Correctness

At every simulated decision point, the model or scorer may use only information that would have been available at that time.

Examples:

* A score on bar `i` must not use bar `i+1`.
* Entry based on an end-of-bar signal should normally occur no earlier than the next executable bar.
* Earnings information must use the announcement schedule known at the decision time.
* Index or sector membership must use point-in-time membership when required by the study.
* Market-regime inputs must not include future bars.
* Forward returns must not cross dataset split boundaries.

Explicitly test point-in-time behavior.

## Research Splits

Separate research into:

### Development

Used to design features, policies, and candidate parameters.

### Validation

Used to compare predefined candidates and make selection decisions.

### Holdout

Used only for the final locked evaluation.

Do not repeatedly inspect the holdout while refining the candidate.

Do not use holdout performance to choose:

* Parameters
* Thresholds
* Weights
* Filters
* Universes
* Holding periods
* Entry rules
* Exit rules

If the holdout influences design, it is no longer an untouched holdout.

## Bias and Leakage Checks

Every applicable study must consider:

* Lookahead bias
* Survivorship bias
* Delisting bias
* Selection bias
* Data leakage
* Cross-split contamination
* Duplicate events
* Overlapping outcomes
* Parameter fishing
* Threshold fishing
* Multiple-comparison risk
* Corporate actions
* Adjusted versus unadjusted prices
* Timestamp and timezone errors
* Market-calendar errors
* Missing bars
* Stale data
* Provider inconsistencies
* Small samples
* Regime dependence
* Hidden user configuration
* Saved production weights
* Non-deterministic computation

Document which risks apply and how they were addressed.

## Event Studies and Backtests

An event study and an executable backtest answer different questions.

### Event Study

An event study evaluates what tends to happen after a signal or score observation.

It may allow overlapping observations but must report that fact.

### Executable Backtest

A backtest simulates a defined trading policy subject to capital, position, timing, and execution constraints.

Do not represent an overlapping event study as an executable strategy.

Where appropriate, evaluate both.

## Execution Assumptions

Execution rules must be explicit.

Define:

* Signal time
* Entry bar and price
* Exit bar and price
* Gap behavior
* Stop and target anchoring
* Same-bar stop and target priority
* Slippage
* Commissions
* Position sizing
* Fractional-share handling
* Partial-fill assumptions
* Liquidity or capacity assumptions

Use conservative assumptions when bar-level data cannot determine the true execution sequence.

Do not assume fills at prices that were not executable after the signal became known.

## Benchmarks

Compare candidate logic with relevant simple alternatives, such as:

* Buy and hold
* Broad-market return
* Sector return
* Simple momentum
* Moving-average structure
* Existing production score
* Existing production policy
* Random or frequency-matched baseline when appropriate

A complicated model should demonstrate value beyond a simpler baseline.

## Reporting

Report enough information to understand both performance and uncertainty.

When applicable, include:

* Observation count
* Ticker count
* Date coverage
* Score or signal distribution
* Mean and median returns
* Win rate
* Drawdown
* Volatility
* Sharpe-like metrics with assumptions
* Performance by ticker
* Performance by regime
* Performance by period
* Performance by score bucket
* Transaction-cost sensitivity
* Missing-data summary
* Provider summary
* Benchmark comparison
* Development, validation, and holdout results
* Limitations

Do not report only the most favorable metric.

Avoid conclusions based solely on pooled averages when results are driven by a small number of securities or periods.

## Determinism and Reproducibility

When practical, the same:

* Dataset or manifest
* Configuration
* Code version
* Random seed
* Environment

should produce identical outputs.

Lock and serialize material study configuration.

Prevent reproducible studies from silently loading local user settings, saved weights, or machine-specific configuration.

Research outputs should be JSON-safe and schema-stable when consumed programmatically.

## Valid Outcomes

A study may conclude:

* Evidence supports promotion consideration.
* Evidence is insufficient.
* Evidence does not support the hypothesis.
* The data is inadequate.
* The methodology is inadequate.
* Additional research is required.

“Inconclusive” is an acceptable result.

Do not automatically select or promote the best-performing candidate.

## Promotion to Production

Research code must not silently change production behavior.

A candidate may be considered for promotion only when:

* The methodology was predefined.
* Point-in-time correctness was demonstrated.
* Data and split integrity checks passed.
* Required sample sizes were met.
* Validation criteria passed.
* Holdout criteria passed.
* Results were not dependent on a small number of securities or periods without disclosure.
* Transaction-cost sensitivity was acceptable.
* Limitations were documented.
* Gary explicitly approved consideration of a production change.

Promotion must occur in a separate pull request.

The production PR must identify:

* The supporting study
* Locked inputs and configuration
* Promotion criteria
* Actual results
* Exact production behavior being changed
* Tests
* Rollback plan
* Known limitations

A successful study does not itself authorize a production change.

## Research Review Checklist

Before accepting a study, verify:

* The hypothesis was defined.
* The universe and provider were recorded.
* Development, validation, and holdout periods were enforced.
* Events and outcomes did not cross split boundaries.
* Features were point-in-time correct.
* Entry and exit assumptions were executable.
* Costs were modeled where applicable.
* Same-bar ambiguity was handled.
* Missing and duplicate data were reported.
* Provider provenance was preserved.
* Results were reproducible.
* Simple benchmarks were included.
* Per-ticker and regime dependence were examined.
* Limitations were documented.
* Production behavior remained unchanged unless separately approved.

## Operating Principle

TradeX research should make it easier to reject weak ideas, not easier to justify them.

