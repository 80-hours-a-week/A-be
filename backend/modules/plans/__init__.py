"""U16 Subscription/Plans — admin-granted plus tier + plan-aware agent quotas.

SSOT: aidlc-docs/construction/u16-subscription/functional-design/functional-design.md.
free is the ABSENCE of a PlanAssignment row (BR-SB1); activity is a derived state
(``now < expiresAt`` — no expiry job, BR-SB2); the plan layer only SUPPLIES quota values —
the limiter/CostGuard enforcement mechanisms are untouched (BR-SB3/NFR-C1). No payment
surface whatsoever (C-12).
"""
