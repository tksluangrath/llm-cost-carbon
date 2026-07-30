"""Sourced, dated constants for the cost-only v1 tool.

Scope reduction, 2026-07-29: this file previously held the FLOP-based
energy/carbon model constants and the implied_markup() baseline (H100
FLOPs/J, PUE, grid carbon intensity, H100 $/GPU-hour, throughput). All of
that is cut along with carbon/energy modeling itself — see
planning/claude-plan.md's Revision note. Only the two constants below survived
because they aren't physical/energy constants: CCUSAGE_VERSION pins a
dependency, STALENESS_THRESHOLD_DAYS governs pricing-data freshness, which
still applies to a cost-only tool exactly as much as it did before.
"""

CCUSAGE_VERSION = "20.0.19"
"""Pinned exactly, not @latest. Source: github.com/ccusage/ccusage releases,
confirmed 2026-07-29. See Reliability hardening in planning/claude-plan.md for why
this deviates from ccusage's own @latest guidance."""

OUTPUT_PRECISION_USD_DECIMALS = 6
"""USD costs reported to 6 decimal places — at real token volumes, per-call
cost is fractions of a cent; fewer decimals rounds small estimate() calls
to $0.00 and makes the tool look broken."""

STALENESS_THRESHOLD_DAYS = 90
"""A model table entry older than this is flagged `stale: true` in every
response that depends on it, at runtime — not just caught by a CI lint
(see Reliability hardening, planning/claude-plan.md)."""
