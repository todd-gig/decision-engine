/**
 * smooth-numbers.js
 * Smooth number utilities for scoring, scale generation, and categorical input design.
 * Grounded in Miller's Law (7±2) and 5-smooth / 7-smooth number theory.
 */

// RTQL-aligned score set: avoids false precision beyond 6, forces categorical judgment
export const RTQL_SCORES = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12];

// 2-smooth spacing grid (px) — powers of 2 × 4
export const SPACING = [4, 8, 12, 16, 24, 32, 48, 64, 96, 128];

// 5-smooth typography scale (px): 2^a × 3^b × 5^c
export const TYPE_SCALE = [12, 14, 16, 20, 24, 30, 36, 48, 60, 72];

// Cognitive budget limit — hard max items per UI group (Miller's Law)
export const COGNITIVE_LIMIT = 7;

// 7-point Likert categories (optimal scale per Krosnick & Fabrigar 1997)
export const LIKERT_7 = [
  { value: 1, label: "Strongly Disagree" },
  { value: 2, label: "Disagree" },
  { value: 3, label: "Slightly Disagree" },
  { value: 4, label: "Neutral" },
  { value: 5, label: "Slightly Agree" },
  { value: 6, label: "Agree" },
  { value: 7, label: "Strongly Agree" },
];

// Confidence scale — 7-point, qualitative labels (no numeric anchors)
export const CONFIDENCE_SCALE = [
  { value: 1, label: "Wild guess",      weight: 0.10 },
  { value: 2, label: "Rough estimate",  weight: 0.25 },
  { value: 3, label: "Informed guess",  weight: 0.45 },
  { value: 4, label: "Reasonable",      weight: 0.60 },
  { value: 5, label: "Well-informed",   weight: 0.75 },
  { value: 6, label: "Data-backed",     weight: 0.88 },
  { value: 7, label: "Measured",        weight: 0.97 },
];

// Urgency scale — 7-point (maps to DecisionContext.urgency 0.0–1.0)
export const URGENCY_SCALE = [
  { value: 1, label: "No rush",         urgency: 0.10 },
  { value: 2, label: "Low priority",    urgency: 0.22 },
  { value: 3, label: "Moderate",        urgency: 0.38 },
  { value: 4, label: "Timely",          urgency: 0.54 },
  { value: 5, label: "Pressing",        urgency: 0.70 },
  { value: 6, label: "Urgent",          urgency: 0.85 },
  { value: 7, label: "Critical",        urgency: 0.97 },
];

/**
 * Check if n is B-smooth (all prime factors ≤ B).
 */
export function isSmooth(n, B = 7) {
  if (n <= 1) return true;
  let remaining = n;
  for (let p = 2; p <= B; p++) {
    if (isPrime(p)) {
      while (remaining % p === 0) remaining /= p;
    }
  }
  return remaining === 1;
}

/**
 * Generate B-smooth numbers up to maxVal.
 */
export function smoothsUpTo(maxVal, B = 5) {
  const result = [];
  for (let n = 1; n <= maxVal; n++) {
    if (isSmooth(n, B)) result.push(n);
  }
  return result;
}

/**
 * Round a value to the nearest element in RTQL_SCORES.
 * Prevents false precision in automated scoring.
 */
export function snapToRTQL(value) {
  return RTQL_SCORES.reduce((prev, curr) =>
    Math.abs(curr - value) < Math.abs(prev - value) ? curr : prev
  );
}

/**
 * Build categorical bins for a numeric range using smooth-number midpoints.
 * Eliminates heaping bias by replacing freeform numeric input.
 *
 * @param {number} lo  - range minimum
 * @param {number} hi  - range maximum
 * @param {number} n   - number of bins (default: 5, max: COGNITIVE_LIMIT)
 */
export function buildSmoothBins(lo, hi, n = 5) {
  n = Math.min(n, COGNITIVE_LIMIT);
  const step = (hi - lo) / n;
  return Array.from({ length: n }, (_, i) => {
    const binLo = lo + i * step;
    const binHi = lo + (i + 1) * step;
    const mid = (binLo + binHi) / 2;
    return {
      lo: binLo,
      hi: binHi,
      mid,               // use as the analysis midpoint (avoids round-number anchoring)
      label: formatRange(binLo, binHi),
    };
  });
}

function formatRange(lo, hi) {
  const fmt = (v) => v >= 1000 ? `${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}k` : String(Math.round(v));
  return `${fmt(lo)} – ${fmt(hi)}`;
}

/**
 * Chunk an array into groups of at most COGNITIVE_LIMIT.
 * For progressive disclosure in multi-step forms.
 */
export function cognitiveChunk(items) {
  const chunks = [];
  for (let i = 0; i < items.length; i += COGNITIVE_LIMIT) {
    chunks.push(items.slice(i, i + COGNITIVE_LIMIT));
  }
  return chunks;
}

function isPrime(n) {
  if (n < 2) return false;
  for (let i = 2; i * i <= n; i++) if (n % i === 0) return false;
  return true;
}
