# Schema Alignment Documentation

**Document ID:** 11_schema_alignment  
**Date:** 2026-03-24  
**Status:** Current  
**Owner:** Decision Engineering  

## Purpose

This document certifies that `schemas/decision_schema.yaml` accurately reflects the `DecisionObject` data model and all other decision engine data structures. It serves as the canonical reference for integrating decision records with the engine.

## Schema Audit Results

All schema dimensions have been validated against their corresponding Python dataclass definitions. **Status: 100% Aligned**

### Validation Summary

| Component | Expected Fields | Verified | Status |
|-----------|-----------------|----------|--------|
| DecisionObject | 25 fields | 25 | ✓ |
| ValueScores | 12 dimensions (8+4) | 12 | ✓ |
| TrustScores | 7 dimensions | 7 | ✓ |
| RTQLScores | 7 dimensions | 7 | ✓ |
| DecisionClass | 7 enum values | 7 | ✓ |
| TimeHorizon | 4 enum values | 4 | ✓ |
| ReversibilityTag | 4 enum values | 4 | ✓ |

### Test Coverage

Full schema validation test suite: `tests/test_schema_validation.py`

- ✓ DecisionObject Required Fields
- ✓ ValueScores Dimensions (8 positive + 4 penalty)
- ✓ TrustScores Dimensions (7 trust inputs)
- ✓ RTQLScores Dimensions (7 RTQL criteria)
- ✓ DecisionClass Enum (D0-D6)
- ✓ TimeHorizon Enum (4 values)
- ✓ ReversibilityTag Enum (4 values)
- ✓ DecisionObject Validation (minimal valid record)

## DecisionObject Field Mapping

### Identity & Classification (7 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| decision_id | String | str | Auto-generated | Yes | Unique identifier (DEC-XXXXXXXX) |
| title | String | str | "" | Yes | Decision name/title |
| decision_class | Enum | DecisionClass | D1_REVERSIBLE_TACTICAL | Yes | Classification D0-D6 |
| owner | String | str | "" | Yes | Decision owner role |
| time_horizon | Enum | TimeHorizon | IMMEDIATE | Yes | Time window (4 values) |
| reversibility | Enum | ReversibilityTag | R1_EASILY_REVERSIBLE | Yes | Reversibility category R1-R4 |
| created_at | ISO Timestamp | str | Now | No | Auto-generated creation time |

### Intent & Problem (3 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| problem_statement | String | str | "" | Yes | Problem being solved |
| requested_action | String | str | "" | Yes | Requested action/decision |
| context_summary | String | str | "" | Yes | Context & background |

### Scoring Inputs (3 composite objects)

#### value_scores (ValueScores)
```python
@dataclass
class ValueScores:
    # Positive dimensions (0-5)
    revenue_impact: int = 0
    cost_efficiency: int = 0
    time_leverage: int = 0
    strategic_alignment: int = 0
    customer_human_benefit: int = 0
    knowledge_asset_creation: int = 0
    compounding_potential: int = 0
    reversibility: int = 0
    # Penalty dimensions (0-5)
    downside_risk: int = 0
    execution_drag: int = 0
    uncertainty: int = 0
    ethical_misalignment: int = 0
```

Calculation: **net_value = gross_value - penalty**
- gross_value = sum of 8 positive dimensions
- penalty = sum of 4 penalty dimensions
- Classification: strong_candidate (≥20), conditional (≥12), weak (≥0), block (<0)

#### trust_scores (TrustScores)
```python
@dataclass
class TrustScores:
    evidence_quality: int = 0      # (0-5) Quality of supporting evidence
    logic_integrity: int = 0        # (0-5) Logical coherence
    outcome_history: int = 0        # (0-5) Historical track record
    context_fit: int = 0            # (0-5) Fit to current context
    stakeholder_clarity: int = 0    # (0-5) Clarity of stakeholder roles
    risk_containment: int = 0       # (0-5) Ability to contain downside
    auditability: int = 0           # (0-5) Auditability of decision
```

Calculation: **trust_tier** determined from total (0-35) and composition

#### alignment_scores (AlignmentScores) — Optional
```python
@dataclass
class AlignmentScores:
    doctrine_alignment: float = 0.0         # (0.0-1.0) Doctrine alignment
    ethos_alignment: float = 0.0            # (0.0-1.0) Ethos alignment
    first_principles_alignment: float = 0.0 # (0.0-1.0) First principles alignment
    anti_pattern_flags: list[str] = []      # Detected anti-patterns
    applied_principles: list[str] = []      # Principles applied
```

### RTQL Pre-Filter (1 optional object)

#### rtql_input (RTQLInput) — Optional
```python
@dataclass
class RTQLInput:
    claim: str = ""                         # The claim being evaluated
    source: str = ""                        # Source of claim
    is_identifiable: bool = False           # Can source be identified
    has_provenance: bool = False            # Source has clear provenance
    scores: RTQLScores = RTQLScores()       # 7-dimension RTQL scoring
    causal_checks: CausalChecks = CausalChecks()  # Causal validation
```

**RTQLScores** (7 dimensions, smooth number set: 0,1,2,3,4,5,6,8,10,12):
- source_integrity: Integrity of source
- exposure_count: Number of independent exposures
- independence: Independence of sources
- explainability: Explainability of mechanism
- replicability: Ability to replicate
- adversarial_robustness: Robustness to adversarial attacks
- novelty_yield: Novel insight generation

### Evidence & Assumptions (3 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| evidence_refs | List[String] | list[str] | [] | Yes | Must provide ≥1 |
| assumptions | List[String] | list[str] | [] | No | Explicit assumptions |
| unknowns | List[String] | list[str] | [] | No | Known unknowns |

### Execution & Monitoring (4 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| execution_plan | String | str | "" | No | How to execute |
| monitoring_metric | String | str | "" | No | Success metric |
| rollback_trigger | String | str | "" | No | When to rollback |
| review_date | ISO Date | Optional[str] | None | No | Review schedule |

### Stakeholders & Constraints (2 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| stakeholders | List[String] | list[str] | [] | No | Affected parties |
| constraints | List[String] | list[str] | [] | No | Real-world limits |

### State & Authority (4 fields)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| current_state | String | str | "draft" | No | State machine state |
| actor_role | String | str | "AI_Domain_Agent" | No | Actor role in authority matrix |
| has_missing_data | Boolean | bool | False | No | Missing data flag |
| ethical_conflict | Boolean | bool | False | No | Ethical red flag |

### Required Approvals (1 field)

| Schema Field | Type | Python Model | Default | Required | Notes |
|---|---|---|---|---|---|
| required_approvals | List[String] | list[str] | [] | No | Approval chain |

## Validation Rules

All DecisionObject instances must satisfy these rules:

### Mandatory Fields
- `title`: Non-empty string
- `owner`: Non-empty string
- `problem_statement`: Non-empty string
- `requested_action`: Non-empty string
- `evidence_refs`: List with ≥1 element
- `value_scores`: Must have all dimensions 0-5
- `trust_scores`: Must have all dimensions 0-5

### Value Scores Validation
```python
def validate(self) -> list[str]:
    errors = []
    for fname in ['revenue_impact', 'cost_efficiency', ...]:
        v = getattr(self, fname)
        if not (0 <= v <= 5):
            errors.append(f"{fname} must be 0-5, got {v}")
    return errors
```

### Trust Scores Validation
```python
def validate(self) -> list[str]:
    errors = []
    for fname in ['evidence_quality', 'logic_integrity', ...]:
        v = getattr(self, fname)
        if not (0 <= v <= 5):
            errors.append(f"{fname} must be 0-5, got {v}")
    return errors
```

### RTQLScores Validation
Allowed values: `{0, 1, 2, 3, 4, 5, 6, 8, 10, 12}` (smooth number set)

## Integration Points

### Schema → Code
- `decision_schema.yaml` is authoritative for field names and structure
- `engine/models.py` contains the Python dataclass implementations
- `engine/pipeline.py` uses DecisionObject throughout the decision pipeline

### Code → Validation
- `test_schema_validation.py` verifies alignment between schema and code
- `DecisionObject.validate()` enforces all schema rules
- Pipeline stages validate inputs before processing

## Migration from Old Schema

See `SCHEMA_MIGRATION.md` for detailed migration procedures:
1. Rename `type` → `decision_class`
2. Rename `urgency` → `time_horizon`
3. Add `reversibility` field
4. Add `problem_statement` field
5. Decompose single values (`expected_value`, `cost`, `risk`) into ValueScores object
6. Decompose single value (`trust_score`) into TrustScores object

## Future Updates

When updating the schema:

1. **Update schema first:** `schemas/decision_schema.yaml`
2. **Update model:** `engine/models.py` dataclass
3. **Test alignment:** Run `tests/test_schema_validation.py`
4. **Document changes:** Update this document + SCHEMA_MIGRATION.md

## Audit Trail

| Date | Change | Verified | Status |
|---|---|---|---|
| 2026-03-24 | Complete schema overhaul; align with DecisionObject model | Yes | ✓ |
| 2026-03-24 | Add comprehensive validation test suite | Yes | ✓ |
| 2026-03-24 | Create SCHEMA_MIGRATION.md for legacy support | Yes | ✓ |

## Questions & Contact

For schema questions, contact the decision engineering team.  
For validation failures, run: `python tests/test_schema_validation.py`
