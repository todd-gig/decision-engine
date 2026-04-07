# Value Matrix

## Purpose
Score decisions based on expected net value relative to cost, time, risk, and strategic fit.

## Scoring Dimensions
| Dimension | Description | Scale |
|---|---|---|
| Revenue Impact | Direct or indirect income effect | 0-5 |
| Cost Efficiency | Savings or better deployment of resources | 0-5 |
| Time Leverage | How much faster value is realized | 0-5 |
| Strategic Alignment | Fit with doctrine and long-term direction | 0-5 |
| Customer / Human Benefit | Improves lived experience or trust | 0-5 |
| Knowledge Asset Creation | Produces reusable intelligence | 0-5 |
| Compounding Potential | Creates future flywheel effects | 0-5 |
| Reversibility | Can be undone cheaply if wrong | 0-5 |

## Penalty Dimensions
| Dimension | Description | Scale |
|---|---|---|
| Downside Risk | Magnitude of harm if wrong | 0-5 |
| Execution Drag | Coordination burden / friction | 0-5 |
| Uncertainty | Unknowns not yet bounded | 0-5 |
| Ethical Misalignment | Conflict with doctrine or values | 0-5 |

## Formula
```text
Gross Value Score = sum(all positive dimensions)
Penalty Score = sum(all penalty dimensions)
Net Value Score = Gross Value Score - Penalty Score
```

## Decision Thresholds
- 20+ = strong candidate
- 12-19 = conditional candidate
- 0-11 = weak candidate
- below 0 = block unless exceptional reason exists
