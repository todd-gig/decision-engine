/**
 * components.js
 * Reusable UI components:
 *  - ThreePointEstimate   (P10 / P50 / P90 input)
 *  - SmoothSlider         (qualitative labels, no numeric ticks)
 *  - CategorySelect       (smooth-number bins, max 7 options)
 *  - TrustRing            (SVG trust score dial)
 *  - BenfordChart         (observed vs expected first-digit bars)
 */

import {
  CONFIDENCE_SCALE, URGENCY_SCALE, buildSmoothBins, COGNITIVE_LIMIT,
} from "./smooth-numbers.js";
import { calibrateThreePoint, digitPreferenceIndex, isRoundNumber } from "./bias-detection.js";

// ── ThreePointEstimate ────────────────────────────────────────────────────────
/**
 * Renders a P10 / P50 / P90 three-point estimate input.
 * Returns the DOM element and an accessor { getValues, onChange }.
 *
 * @param {object} opts
 *   label          - field label
 *   unit           - e.g. "$", "hrs", "%"
 *   hint           - helper text shown below
 *   onChange       - callback({ p10, p50, p90, calibration })
 */
export function ThreePointEstimate({ label, unit = "", hint = "", onChange } = {}) {
  const el = document.createElement("div");
  el.className = "field";
  el.innerHTML = `
    <label>${label}</label>
    ${hint ? `<span class="field-hint">${hint}</span>` : ""}
    <div class="three-point">
      <div class="three-point-cell">
        <span class="three-point-label">P10 — Pessimistic</span>
        <input type="number" placeholder="Low" data-pt="p10" />
        <span class="three-point-hint">Only 1-in-10 chance it's this low</span>
      </div>
      <div class="three-point-cell p50">
        <span class="three-point-label">P50 — Most Likely</span>
        <input type="number" placeholder="Mid" data-pt="p50" />
        <span class="three-point-hint">Your best single estimate</span>
      </div>
      <div class="three-point-cell">
        <span class="three-point-label">P90 — Optimistic</span>
        <input type="number" placeholder="High" data-pt="p90" />
        <span class="three-point-hint">Only 1-in-10 chance it's this high</span>
      </div>
    </div>
    <div class="calibration-bar">
      <div class="calibration-fill" id="cal-fill" style="width:0%;background:#e2e8f0"></div>
    </div>
    <div class="bias-flag-container"></div>
  `;

  const inputs = el.querySelectorAll("input[type='number']");
  const calFill = el.querySelector("#cal-fill");
  const flagContainer = el.querySelector(".bias-flag-container");

  function update() {
    const p10 = parseFloat(el.querySelector("[data-pt=p10]").value);
    const p50 = parseFloat(el.querySelector("[data-pt=p50]").value);
    const p90 = parseFloat(el.querySelector("[data-pt=p90]").value);

    const values = { p10, p50, p90 };
    let calibration = null;

    if (!isNaN(p10) && !isNaN(p50) && !isNaN(p90)) {
      calibration = calibrateThreePoint(p10, p50, p90);
      const pct = (calibration.calibrationScore * 100).toFixed(0) + "%";
      const color = calibration.calibrationScore >= 0.75 ? "#16a34a"
        : calibration.calibrationScore >= 0.50 ? "#d97706" : "#dc2626";
      calFill.style.width = pct;
      calFill.style.background = color;

      flagContainer.innerHTML = "";
      for (const issue of calibration.issues) {
        flagContainer.appendChild(BiasFlag({ severity: "warn", message: issue }));
      }
      for (const insight of calibration.insights) {
        flagContainer.appendChild(BiasFlag({ severity: "ok", message: insight }));
      }
    }

    onChange?.({ ...values, calibration });
  }

  inputs.forEach(inp => inp.addEventListener("input", update));

  function getValues() {
    return {
      p10: parseFloat(el.querySelector("[data-pt=p10]").value),
      p50: parseFloat(el.querySelector("[data-pt=p50]").value),
      p90: parseFloat(el.querySelector("[data-pt=p90]").value),
    };
  }

  return { el, getValues };
}

// ── SmoothSlider ──────────────────────────────────────────────────────────────
/**
 * A qualitative slider with NO numeric ticks (prevents heaping).
 * Uses 7-point scale by default.
 *
 * @param {object} opts
 *   scale   - array of { value, label, ...extras }
 *   label   - field label
 *   onChange - callback(scaleItem)
 */
export function SmoothSlider({ label, scale = CONFIDENCE_SCALE, onChange } = {}) {
  const el = document.createElement("div");
  el.className = "field";

  const midIdx = Math.floor((scale.length - 1) / 2);

  el.innerHTML = `
    <label>${label}</label>
    <div class="smooth-slider-wrap">
      <div class="smooth-slider-value" id="slider-val">—</div>
      <input type="range" min="0" max="${scale.length - 1}" value="${midIdx}" step="1" />
      <div class="smooth-slider-labels">
        <span>${scale[0].label}</span>
        <span>${scale[scale.length - 1].label}</span>
      </div>
    </div>
  `;

  const input = el.querySelector("input[type='range']");
  const valDisplay = el.querySelector("#slider-val");

  function update() {
    const idx = parseInt(input.value);
    const item = scale[idx];
    valDisplay.textContent = item.label;
    const pct = (idx / (scale.length - 1)) * 100;
    input.style.setProperty("--slider-pct", pct + "%");
    onChange?.(item);
  }

  input.addEventListener("input", update);
  update(); // initialize

  return { el, getValue: () => scale[parseInt(input.value)] };
}

// ── CategorySelect ────────────────────────────────────────────────────────────
/**
 * Smooth-number categorical input. Replaces freeform numeric input.
 * Max COGNITIVE_LIMIT options enforced.
 *
 * @param {object} opts
 *   label    - field label
 *   bins     - array of { label, lo, hi, mid } (from buildSmoothBins)
 *   options  - OR plain array of strings for non-numeric categories
 *   onChange - callback(selected)
 */
export function CategorySelect({ label, hint, bins, options, onChange } = {}) {
  const el = document.createElement("div");
  el.className = "field";

  const items = bins || options?.map(o => ({ label: o, mid: null })) || [];
  const limited = items.slice(0, COGNITIVE_LIMIT); // hard cognitive limit

  el.innerHTML = `
    <label>${label}</label>
    ${hint ? `<span class="field-hint">${hint}</span>` : ""}
    <div class="category-grid">
      ${limited.map((item, i) => `
        <button class="category-btn" data-idx="${i}">${item.label}</button>
      `).join("")}
    </div>
  `;

  let selected = null;
  el.querySelectorAll(".category-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      el.querySelectorAll(".category-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      selected = limited[parseInt(btn.dataset.idx)];
      onChange?.(selected);
    });
  });

  return { el, getValue: () => selected };
}

// ── BiasFlag ──────────────────────────────────────────────────────────────────
export function BiasFlag({ severity, message }) {
  const icons = { ok: "✓", warn: "⚠", alert: "✕" };
  const el = document.createElement("div");
  el.className = `bias-flag ${severity} fade-in`;
  el.innerHTML = `<span class="bias-icon">${icons[severity] || "•"}</span><span class="bias-text">${message}</span>`;
  return el;
}

// ── TrustRing ─────────────────────────────────────────────────────────────────
/**
 * SVG circular trust score dial.
 * score: 0.0–1.0
 */
export function TrustRing(container) {
  const R = 40;
  const C = 2 * Math.PI * R;
  container.innerHTML = `
    <div class="trust-ring-wrap">
      <div class="trust-ring">
        <svg width="96" height="96" viewBox="0 0 96 96">
          <circle class="trust-ring-bg" cx="48" cy="48" r="${R}" />
          <circle class="trust-ring-fill" cx="48" cy="48" r="${R}"
            stroke-dasharray="${C}" stroke-dashoffset="${C}" stroke="#3b82f6" />
        </svg>
        <div class="trust-ring-label">
          <span class="trust-ring-pct" id="ring-pct">—</span>
          <span class="trust-ring-sub">trust</span>
        </div>
      </div>
    </div>
  `;

  const fill = container.querySelector(".trust-ring-fill");
  const pctEl = container.querySelector("#ring-pct");

  return {
    update(score) {
      const pct = Math.max(0, Math.min(1, score));
      const offset = C * (1 - pct);
      fill.style.strokeDashoffset = offset;
      fill.style.stroke = pct >= 0.75 ? "#16a34a" : pct >= 0.50 ? "#d97706" : "#dc2626";
      pctEl.textContent = Math.round(pct * 100) + "%";
      pctEl.style.color = pct >= 0.75 ? "#16a34a" : pct >= 0.50 ? "#d97706" : "#dc2626";
    },
  };
}

// ── TrustMeter ────────────────────────────────────────────────────────────────
/**
 * Renders a list of per-field trust bars.
 * fields: [{ label, score }]
 */
export function renderTrustMeter(container, fields) {
  container.innerHTML = "";
  if (!fields.length) {
    container.innerHTML = `<div class="empty-state">No fields analyzed yet.</div>`;
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "trust-meter";
  for (const { label, score } of fields) {
    const pct = Math.round((score ?? 0) * 100);
    const color = score >= 0.75 ? "#16a34a" : score >= 0.50 ? "#d97706" : "#dc2626";
    const item = document.createElement("div");
    item.className = "trust-item";
    item.innerHTML = `
      <div class="trust-row">
        <span class="trust-label">${label}</span>
        <span class="trust-score" style="color:${color}">${pct}%</span>
      </div>
      <div class="trust-bar">
        <div class="trust-fill" style="width:${pct}%;background:${color}"></div>
      </div>
    `;
    wrap.appendChild(item);
  }
  container.appendChild(wrap);
}

// ── BenfordChart ──────────────────────────────────────────────────────────────
/**
 * Renders side-by-side bars (expected vs observed first-digit frequency).
 */
export function renderBenfordChart(container, observedCounts, total) {
  const EXPECTED = [0, 0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046];
  const maxExpected = 0.301;

  container.innerHTML = `
    <div class="benford-chart" id="benford-bars"></div>
    <div class="benford-legend">
      <div class="benford-legend-item"><div class="legend-dot" style="background:#e2e8f0"></div>Expected</div>
      <div class="benford-legend-item"><div class="legend-dot" style="background:#3b82f6"></div>Observed</div>
    </div>
  `;

  const barsEl = container.querySelector("#benford-bars");
  for (let d = 1; d <= 9; d++) {
    const expectedPct = EXPECTED[d] / maxExpected * 100;
    const observedPct = total > 0 ? (observedCounts[d - 1] / total) / maxExpected * 100 : 0;

    const wrap = document.createElement("div");
    wrap.className = "benford-bar-wrap";
    wrap.innerHTML = `
      <div style="display:flex;gap:2px;align-items:flex-end;height:52px">
        <div class="benford-bar expected" style="height:${expectedPct.toFixed(0)}%;flex:1"></div>
        <div class="benford-bar observed" style="height:${observedPct.toFixed(0)}%;flex:1"></div>
      </div>
      <span class="benford-digit">${d}</span>
    `;
    barsEl.appendChild(wrap);
  }
}
