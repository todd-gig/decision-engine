/**
 * bias-detection.js
 * Real-time cognitive bias detection for human-entered numeric data.
 *
 * Methods:
 *   - Benford's Law (leading-digit distribution)
 *   - Digit Preference Index (heaping at 0s and 5s)
 *   - Anchor Proximity Detection
 *   - Round-Number Clustering
 *   - Cross-field Inconsistency Detection
 *   - Three-Point Estimate Calibration Check
 */

// ── Benford's Law ─────────────────────────────────────────────────────────────
// P(d) = log10(1 + 1/d) for d = 1..9
export const BENFORD_EXPECTED = [0, 0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046];

export function firstSignificantDigit(n) {
  const abs = Math.abs(n);
  if (abs === 0 || !isFinite(abs)) return null;
  return parseInt(abs.toExponential()[0]);
}

/**
 * Benford's Law chi-square test.
 * Returns { score, verdict, detail } where score ∈ [0,1], 1 = perfectly Benford.
 * Valid only for n >= 5 spanning multiple orders of magnitude.
 */
export function benfordsTest(numbers) {
  const valid = numbers.filter(n => isFinite(n) && n !== 0);
  if (valid.length < 5) return { score: null, verdict: "insufficient_data", detail: "Need ≥5 values for Benford analysis." };

  const counts = new Array(10).fill(0);
  for (const n of valid) {
    const d = firstSignificantDigit(n);
    if (d !== null) counts[d]++;
  }

  let chiSq = 0;
  for (let d = 1; d <= 9; d++) {
    const observed = counts[d] / valid.length;
    const expected = BENFORD_EXPECTED[d];
    chiSq += Math.pow(observed - expected, 2) / expected;
  }

  // Critical value for df=8, α=0.05 → 15.51
  const violated = chiSq > 15.51;
  const score = Math.max(0, 1 - chiSq / 30);

  return {
    score: parseFloat(score.toFixed(3)),
    chiSquare: parseFloat(chiSq.toFixed(3)),
    verdict: violated ? "benford_violation" : "benford_ok",
    detail: violated
      ? `Leading-digit distribution deviates from natural (χ²=${chiSq.toFixed(2)}). Possible fabrication or strong rounding bias.`
      : `Leading-digit distribution is consistent with natural data (χ²=${chiSq.toFixed(2)}).`,
    counts: counts.slice(1),
  };
}

// ── Digit Preference / Heaping ────────────────────────────────────────────────
/**
 * Digit Preference Index: fraction of entries whose last non-zero digit is 0 or 5.
 * Expected for uniform distribution: ~0.20. Values > 0.30 indicate heaping.
 */
export function digitPreferenceIndex(numbers) {
  const valid = numbers.filter(n => isFinite(n));
  if (valid.length === 0) return { dpi: null, verdict: "no_data" };

  const heaped = valid.filter(n => {
    const rounded = Math.round(Math.abs(n));
    return rounded % 5 === 0;
  });
  const dpi = heaped.length / valid.length;

  return {
    dpi: parseFloat(dpi.toFixed(3)),
    heapedCount: heaped.length,
    total: valid.length,
    verdict: dpi > 0.45 ? "strong_heaping" : dpi > 0.30 ? "moderate_heaping" : "ok",
    detail: dpi > 0.30
      ? `${(dpi * 100).toFixed(0)}% of values end in 0 or 5 — indicates rounding bias. Consider categorical input instead.`
      : `Digit distribution looks natural (DPI=${dpi.toFixed(2)}).`,
  };
}

/**
 * Single-value round-number check. Returns true if value likely a rounded estimate.
 */
export function isRoundNumber(n) {
  if (!isFinite(n) || n === 0) return false;
  const abs = Math.abs(n);
  if (abs < 10) return false;
  // Check if divisible by 5, 10, 25, 50, 100, 500, 1000...
  const magnitude = Math.pow(10, Math.floor(Math.log10(abs)) - 1);
  return abs % (5 * magnitude) === 0;
}

// ── Anchor Proximity ──────────────────────────────────────────────────────────
/**
 * Detects if a value is suspiciously close to a known anchor.
 * anchorValues: array of reference numbers the user may have seen.
 * proximityThreshold: fraction of anchor value considered "close" (default 10%).
 */
export function anchorProximity(value, anchorValues, proximityThreshold = 0.10) {
  if (!isFinite(value) || !anchorValues?.length) return { anchored: false };

  for (const anchor of anchorValues) {
    if (anchor === 0) continue;
    const proximity = Math.abs(value - anchor) / Math.abs(anchor);
    if (proximity <= proximityThreshold) {
      return {
        anchored: true,
        anchor,
        proximity: parseFloat(proximity.toFixed(3)),
        detail: `Value (${value}) is within ${(proximityThreshold * 100).toFixed(0)}% of anchor ${anchor}. Possible anchoring bias.`,
      };
    }
  }
  return { anchored: false };
}

// ── Three-Point Estimate Calibration ─────────────────────────────────────────
/**
 * Checks a P10/P50/P90 estimate for overconfidence and internal consistency.
 *
 * Rules:
 *  - P10 < P50 < P90 (must be ordered)
 *  - Ratio P90/P10 should be > 1.1 (some uncertainty acknowledged)
 *  - If P10 ≈ P50 ≈ P90, the user is hiding behind false precision (overconfident)
 *  - If P90 >> P50 >> P10, skewness is meaningful and should be captured
 */
export function calibrateThreePoint(p10, p50, p90) {
  const issues = [];
  const insights = [];

  // Order check
  if (!(p10 <= p50 && p50 <= p90)) {
    issues.push("Values are out of order: P10 must ≤ P50 must ≤ P90.");
  }

  const range = p90 - p10;
  const midpoint = (p10 + p90) / 2;

  // Overconfidence: too tight
  if (p90 > 0 && p10 > 0 && p90 / p10 < 1.05) {
    issues.push("Range is extremely tight — this suggests overconfidence. Real-world uncertainty is typically wider.");
  }

  // Collapse: all three identical
  if (p10 === p50 && p50 === p90) {
    issues.push("All three estimates are identical. This suppresses uncertainty — use a range.");
  }

  // Skewness
  const skew = (p50 - p10) / range;
  if (isFinite(skew)) {
    if (skew < 0.3) insights.push("Distribution skewed toward lower values — upside scenario considered unlikely.");
    else if (skew > 0.7) insights.push("Distribution skewed toward higher values — downside scenario considered unlikely.");
    else insights.push("Distribution roughly symmetric — balanced uncertainty acknowledged.");
  }

  // Round number contamination across all three
  const roundCount = [p10, p50, p90].filter(isRoundNumber).length;
  if (roundCount === 3) {
    issues.push("All three estimates are round numbers — suggests estimation rather than measurement. Consider anchoring analysis.");
  }

  const calibrationScore = Math.max(0, 1 - (issues.length * 0.25));

  return {
    calibrationScore,
    range,
    midpoint,
    skew: isFinite(skew) ? parseFloat(skew.toFixed(3)) : null,
    issues,
    insights,
    verdict: issues.length === 0 ? "well_calibrated" : issues.length === 1 ? "minor_issues" : "poorly_calibrated",
  };
}

// ── Cross-Field Inconsistency ─────────────────────────────────────────────────
/**
 * Detects logical inconsistencies between related numeric fields.
 * fieldPairs: array of { a, b, relation } where relation is "a_lt_b" | "a_gt_b" | "a_sums_to_b"
 */
export function crossFieldCheck(fields) {
  const flags = [];

  for (const check of fields) {
    const { label, a, b, relation, tolerance = 0.01 } = check;
    if (!isFinite(a) || !isFinite(b)) continue;

    switch (relation) {
      case "a_lt_b":
        if (a >= b) flags.push({ label, detail: `Expected "${check.aLabel || 'A'}" < "${check.bLabel || 'B'}", but ${a} ≥ ${b}.` });
        break;
      case "a_gt_b":
        if (a <= b) flags.push({ label, detail: `Expected "${check.aLabel || 'A'}" > "${check.bLabel || 'B'}", but ${a} ≤ ${b}.` });
        break;
      case "a_plus_b_eq_c": {
        const diff = Math.abs((a + b) - check.c) / (Math.abs(check.c) || 1);
        if (diff > tolerance) flags.push({ label, detail: `${check.aLabel}(${a}) + ${check.bLabel}(${b}) should equal ${check.cLabel}(${check.c}), but sum is ${a + b}.` });
        break;
      }
      case "ratio": {
        const ratio = a / b;
        if (ratio < check.minRatio || ratio > check.maxRatio) {
          flags.push({ label, detail: `Ratio ${check.aLabel}/${check.bLabel} = ${ratio.toFixed(2)}, outside expected range [${check.minRatio}, ${check.maxRatio}].` });
        }
        break;
      }
    }
  }

  return {
    flags,
    verdict: flags.length === 0 ? "consistent" : "inconsistent",
    detail: flags.length === 0 ? "All cross-field relationships are logically consistent." : `${flags.length} inconsistency(ies) detected.`,
  };
}

// ── Aggregate Bias Score ──────────────────────────────────────────────────────
/**
 * Produces an overall data quality / trust score for a field set.
 * Returns a value in [0,1]: 1 = no bias detected, 0 = highly suspect.
 */
export function aggregateTrustScore({ benford, dpi, threePoint, crossField, anchored }) {
  let score = 1.0;

  if (benford?.score != null) score *= (0.5 + 0.5 * benford.score);
  if (dpi?.verdict === "strong_heaping") score *= 0.60;
  else if (dpi?.verdict === "moderate_heaping") score *= 0.80;
  if (threePoint?.calibrationScore != null) score *= (0.5 + 0.5 * threePoint.calibrationScore);
  if (crossField?.flags?.length > 0) score *= Math.max(0.4, 1 - crossField.flags.length * 0.15);
  if (anchored) score *= 0.75;

  return parseFloat(Math.max(0, Math.min(1, score)).toFixed(3));
}

// ── Discrepancy Context Prompts ───────────────────────────────────────────────
/**
 * Maps detected bias patterns to follow-up questions for context capture.
 */
export function discrepancyContextPrompts(analysisResult) {
  const prompts = [];

  if (analysisResult.benford?.verdict === "benford_violation") {
    prompts.push({
      id: "benford",
      severity: "high",
      question: "The leading-digit distribution of your data is unusual. Were these values measured directly, or estimated/recalled?",
      type: "radio",
      options: ["Measured directly from a source", "Estimated from memory", "Derived from another calculation", "Copied from a document"],
    });
  }

  if (["strong_heaping", "moderate_heaping"].includes(analysisResult.dpi?.verdict)) {
    prompts.push({
      id: "heaping",
      severity: "medium",
      question: "Several values end in 0 or 5. Are these exact figures, or approximations rounded for convenience?",
      type: "radio",
      options: ["Exact figures", "Rounded approximations", "I'm not sure"],
    });
  }

  if (analysisResult.threePoint?.issues?.length > 0) {
    for (const issue of analysisResult.threePoint.issues) {
      prompts.push({
        id: "three_point",
        severity: "medium",
        question: `Your estimate range may be too narrow: "${issue}" Can you describe what would need to happen for the outcome to be much lower or higher than your estimates?`,
        type: "textarea",
      });
    }
  }

  if (analysisResult.anchored) {
    prompts.push({
      id: "anchoring",
      severity: "medium",
      question: `Your value is close to a reference number you may have seen earlier. Did that reference influence your estimate?`,
      type: "radio",
      options: ["Yes, I used it as a starting point", "No, I arrived at this independently", "I'm not sure"],
    });
  }

  if (analysisResult.crossField?.flags?.length > 0) {
    for (const flag of analysisResult.crossField.flags) {
      prompts.push({
        id: "cross_field",
        severity: "high",
        question: `Potential inconsistency detected: ${flag.detail} Can you clarify?`,
        type: "textarea",
      });
    }
  }

  return prompts;
}
