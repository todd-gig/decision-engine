# Execution Protocol

## Purpose
Control when automated action is allowed.

## Automatic Execution Allowed
Only when all are true:
- class is D1 or approved D2 recurrence,
- trust tier is T3 or T4,
- reversibility is R1 or R2,
- value score meets threshold,
- no policy or legal block exists,
- monitoring hooks exist.

## Escalate Instead of Execute
Escalate when:
- class is D3-D6,
- reversibility is R3-R4,
- affected stakeholders are unclear,
- model confidence conflicts with evidence,
- doctrine or ethics concerns appear.

## Required Execution Packet
- action steps
- owner
- timestamp
- dependencies
- monitoring metric
- rollback trigger
- review date
