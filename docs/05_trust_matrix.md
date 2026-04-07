# Trust Matrix

## Purpose
Determine whether the system has earned the right to recommend, certify, or execute a decision.

## Trust Inputs
| Input | Description | Scale |
|---|---|---|
| Evidence Quality | Source quality, freshness, completeness | 0-5 |
| Logic Integrity | Internal consistency and first-principles fit | 0-5 |
| Outcome History | Prior success in similar contexts | 0-5 |
| Context Fit | Relevance to current environment | 0-5 |
| Stakeholder Clarity | Known owners, incentives, and constraints | 0-5 |
| Risk Containment | Ability to bound downside | 0-5 |
| Auditability | Can rationale be reviewed later | 0-5 |

## Trust Tiers
- **T0 Unqualified** — insufficient basis
- **T1 Observed** — signal exists, not ready
- **T2 Qualified** — enough to recommend
- **T3 Certified** — enough to execute with bounded autonomy
- **T4 Delegated** — enough to automate recurring decision class

## Promotion Rules
A trust tier cannot be raised unless:
- evidence quality is documented,
- logic chain is explicit,
- owner and blast radius are known,
- decision class threshold is met.

## Demotion Rules
Automatically reduce trust when:
- outcome variance is high,
- evidence is stale,
- assumptions fail,
- environment materially changes,
- audit gap appears.
