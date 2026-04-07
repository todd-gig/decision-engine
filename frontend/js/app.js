/**
 * app.js — Decision Logic Pack Frontend
 * Orchestrates the 4-step bias-aware form flow:
 *   Step 1: Context (domain, situation, urgency)
 *   Step 2: Data entry (three-point estimates, categories, sliders)
 *   Step 3: Discrepancy review (bias prompts)
 *   Step 4: Trust summary + decision readiness
 */

import {
  URGENCY_SCALE, CONFIDENCE_SCALE, buildSmoothBins, cognitiveChunk, snapToRTQL, COGNITIVE_LIMIT,
} from "./smooth-numbers.js";
import {
  benfordsTest, digitPreferenceIndex, anchorProximity,
  aggregateTrustScore, discrepancyContextPrompts, firstSignificantDigit,
} from "./bias-detection.js";
import {
  ThreePointEstimate, SmoothSlider, CategorySelect,
  BiasFlag, TrustRing, renderTrustMeter, renderBenfordChart,
} from "./components.js";

// ── App state ─────────────────────────────────────────────────────────────────
const state = {
  currentStep: 1,
  context: { domain: "", situation: "", urgency: 0.5 },
  fields: {},             // field_id -> { label, values, analysis }
  discrepancyAnswers: {}, // prompt_id -> answer
  trustScores: {},        // field_id -> score 0–1
  overallTrust: 0,
  allNumericValues: [],   // flat list for Benford across all fields
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const steps = document.querySelectorAll(".form-step");
const stepItems = document.querySelectorAll(".step-list li");
const budgetDots = document.querySelectorAll(".budget-dot");
const trustRingWrap = document.getElementById("trust-ring-container");
const trustMeterEl = document.getElementById("trust-meter");
const promptList = document.getElementById("prompt-list");
const benfordEl = document.getElementById("benford-chart");

// ── Trust ring init ───────────────────────────────────────────────────────────
const trustRing = TrustRing(trustRingWrap);
trustRing.update(0);

// ── Step navigation ───────────────────────────────────────────────────────────
function goToStep(n) {
  state.currentStep = n;
  steps.forEach((s, i) => s.classList.toggle("active", i + 1 === n));
  stepItems.forEach((s, i) => {
    s.classList.remove("active", "completed");
    if (i + 1 === n) s.classList.add("active");
    if (i + 1 < n) s.classList.add("completed");
  });
  if (n === 3) renderDiscrepancyStep();
  if (n === 4) renderSummaryStep();
}

document.querySelectorAll("[data-goto]").forEach(btn => {
  btn.addEventListener("click", () => goToStep(parseInt(btn.dataset.goto)));
});

// ── Cognitive budget dots ─────────────────────────────────────────────────────
function updateBudgetDots(used, total = COGNITIVE_LIMIT) {
  budgetDots.forEach((dot, i) => dot.classList.toggle("used", i < Math.min(used, total)));
}

// ── STEP 1: Context ───────────────────────────────────────────────────────────
(function buildStep1() {
  const step = document.getElementById("step-1");

  // Domain selector (max 7 options)
  const domainField = CategorySelect({
    label: "Decision domain",
    hint: "Select the area this decision belongs to.",
    options: ["Scheduling", "Finance", "Communication", "Operations", "Strategy", "Personnel", "Technology"],
    onChange(selected) {
      state.context.domain = selected?.label?.toLowerCase() ?? "";
      analyzeAll();
    },
  });
  step.querySelector("#domain-slot").appendChild(domainField.el);

  // Urgency slider
  const urgencySlider = SmoothSlider({
    label: "Urgency",
    scale: URGENCY_SCALE,
    onChange(item) {
      state.context.urgency = item.urgency;
      analyzeAll();
    },
  });
  step.querySelector("#urgency-slot").appendChild(urgencySlider.el);

  // Situation textarea
  const situationInput = step.querySelector("#situation-input");
  situationInput.addEventListener("input", () => {
    state.context.situation = situationInput.value;
  });

  updateBudgetDots(3); // domain + urgency + situation = 3 of 7
})();

// ── STEP 2: Data entry ────────────────────────────────────────────────────────
(function buildStep2() {
  const step = document.getElementById("step-2");

  // ── Field 1: Primary value (three-point estimate)
  const primaryEst = ThreePointEstimate({
    label: "Primary value estimate",
    hint: "Enter your pessimistic, most-likely, and optimistic values. Avoids anchoring from a single number.",
    onChange({ p10, p50, p90, calibration }) {
      state.fields["primary"] = {
        label: "Primary estimate",
        values: { p10, p50, p90 },
        calibration,
      };
      analyzeAll();
    },
  });
  step.querySelector("#field-1-slot").appendChild(primaryEst.el);

  // ── Field 2: Scale / magnitude (smooth-number bins)
  const scaleBins = buildSmoothBins(0, 1000000, 6); // 6 bins for illustration
  const scaleCat = CategorySelect({
    label: "Order of magnitude",
    hint: "Choose a range instead of a precise number — prevents false precision.",
    bins: scaleBins,
    onChange(selected) {
      state.fields["scale"] = { label: "Order of magnitude", values: { selected }, analysis: null };
      analyzeAll();
    },
  });
  step.querySelector("#field-2-slot").appendChild(scaleCat.el);

  // ── Field 3: Confidence
  const confidenceSlider = SmoothSlider({
    label: "Your confidence in this data",
    scale: CONFIDENCE_SCALE,
    onChange(item) {
      state.fields["confidence"] = { label: "Confidence", values: { level: item.value, weight: item.weight } };
      analyzeAll();
    },
  });
  step.querySelector("#field-3-slot").appendChild(confidenceSlider.el);

  // ── Fields 4–7: Additional contextual numbers (for Benford analysis)
  ["Comparable A", "Comparable B", "Comparable C", "Comparable D"].forEach((lbl, i) => {
    const f = document.createElement("div");
    f.className = "field";
    f.innerHTML = `
      <label>${lbl} <span class="field-hint" style="display:inline">(optional — used for cross-dataset bias analysis)</span></label>
      <input type="number" placeholder="Enter a value (or skip)" data-cmp="${i}" />
      <div class="bias-flag-container" id="cmp-flag-${i}"></div>
    `;
    const inp = f.querySelector("input");
    inp.addEventListener("input", () => {
      const v = parseFloat(inp.value);
      state.fields[`comparable_${i}`] = { label: lbl, values: { v }, analysis: null };
      analyzeAll();
    });
    step.querySelector("#comparables-slot").appendChild(f);
  });

  updateBudgetDots(7); // all 7 fields in step 2
})();

// ── Analysis engine (runs on every input change) ──────────────────────────────
function analyzeAll() {
  // Collect all numeric values across all fields
  const nums = [];
  for (const [id, field] of Object.entries(state.fields)) {
    if (field.values?.p50 && isFinite(field.values.p50)) nums.push(field.values.p50);
    if (field.values?.p10 && isFinite(field.values.p10)) nums.push(field.values.p10);
    if (field.values?.p90 && isFinite(field.values.p90)) nums.push(field.values.p90);
    if (field.values?.v && isFinite(field.values.v)) nums.push(field.values.v);
  }
  state.allNumericValues = nums;

  // Benford test across all values
  const benford = benfordsTest(nums);
  const dpi = digitPreferenceIndex(nums);

  // Per-field trust scores
  const trustFields = [];
  for (const [id, field] of Object.entries(state.fields)) {
    const calibration = field.calibration;
    const threePoint = calibration ?? null;

    const fieldNums = [field.values?.p10, field.values?.p50, field.values?.p90, field.values?.v].filter(v => isFinite(v));
    const fieldDpi = digitPreferenceIndex(fieldNums);

    const score = aggregateTrustScore({
      benford: fieldNums.length >= 3 ? benford : null,
      dpi: fieldDpi,
      threePoint,
      crossField: null,
      anchored: false,
    });

    state.trustScores[id] = score;
    trustFields.push({ label: field.label, score });
  }

  // Overall trust
  const scores = Object.values(state.trustScores);
  state.overallTrust = scores.length
    ? scores.reduce((a, b) => a + b, 0) / scores.length
    : 0;

  // Update right panel
  trustRing.update(state.overallTrust);
  renderTrustMeter(trustMeterEl, trustFields);

  // Benford chart
  if (benford.counts) {
    renderBenfordChart(benfordEl, benford.counts, nums.length);
  }

  // Discrepancy prompts (pre-compute, render in step 3)
  const combinedAnalysis = {
    benford,
    dpi,
    threePoint: Object.values(state.fields).find(f => f.calibration)?.calibration ?? null,
    crossField: null,
    anchored: false,
  };
  state.discrepancyPrompts = discrepancyContextPrompts(combinedAnalysis);
  updatePromptBadge();
}

function updatePromptBadge() {
  const badge = document.getElementById("prompt-count-badge");
  const n = state.discrepancyPrompts?.length ?? 0;
  if (badge) {
    badge.textContent = n > 0 ? `${n} question${n !== 1 ? "s" : ""}` : "";
    badge.style.display = n > 0 ? "inline" : "none";
  }
}

// ── STEP 3: Discrepancy review ────────────────────────────────────────────────
function renderDiscrepancyStep() {
  promptList.innerHTML = "";
  const prompts = state.discrepancyPrompts ?? [];

  if (!prompts.length) {
    promptList.innerHTML = `<div class="empty-state">✓ No significant bias patterns detected. Your data looks clean.</div>`;
    return;
  }

  for (const prompt of prompts) {
    const card = document.createElement("div");
    card.className = `prompt-card severity-${prompt.severity} fade-in`;

    if (prompt.type === "radio") {
      card.innerHTML = `
        <div class="prompt-question">${prompt.question}</div>
        <div class="prompt-options">
          ${prompt.options.map((opt, i) => `
            <label class="prompt-option">
              <input type="radio" name="${prompt.id}" value="${i}" />
              ${opt}
            </label>
          `).join("")}
        </div>
      `;
      card.querySelectorAll("input[type='radio']").forEach(r => {
        r.addEventListener("change", () => {
          state.discrepancyAnswers[prompt.id] = { type: "radio", answer: prompt.options[parseInt(r.value)] };
        });
      });
    } else {
      card.innerHTML = `
        <div class="prompt-question">${prompt.question}</div>
        <textarea class="prompt-textarea" placeholder="Describe…"></textarea>
      `;
      card.querySelector("textarea").addEventListener("input", e => {
        state.discrepancyAnswers[prompt.id] = { type: "text", answer: e.target.value };
      });
    }
    promptList.appendChild(card);
  }
}

// ── STEP 4: Summary ───────────────────────────────────────────────────────────
function renderSummaryStep() {
  const summaryEl = document.getElementById("step-4-summary");
  const trust = state.overallTrust;
  const rtqlScore = snapToRTQL(trust * 12);

  const canAutoExecute = trust >= 0.75;
  const status = canAutoExecute ? "Auto-execute eligible" : trust >= 0.50 ? "Escalate for review" : "Insufficient data quality";
  const statusColor = canAutoExecute ? "#16a34a" : trust >= 0.50 ? "#d97706" : "#dc2626";

  const answers = Object.entries(state.discrepancyAnswers);

  summaryEl.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Decision Readiness</div>
          <div class="card-subtitle" style="color:${statusColor};font-weight:600">${status}</div>
        </div>
        <div style="font-size:var(--text-3xl);font-weight:800;color:${statusColor}">${Math.round(trust * 100)}%</div>
      </div>
      <div style="margin-bottom:var(--sp-4)">
        <div style="font-size:var(--text-sm);color:var(--color-text-muted);margin-bottom:var(--sp-2)">RTQL Score (smooth-number aligned)</div>
        <div style="font-size:var(--text-2xl);font-weight:700">${rtqlScore} / 12</div>
      </div>
      <div style="font-size:var(--text-sm);color:var(--color-text-muted)">
        Domain: <strong>${state.context.domain || "—"}</strong> &nbsp;|&nbsp;
        Urgency: <strong>${state.context.urgency?.toFixed(2)}</strong> &nbsp;|&nbsp;
        Fields analyzed: <strong>${Object.keys(state.fields).length}</strong>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><div class="card-title">Context captured from discrepancies</div></div>
      ${answers.length > 0
        ? answers.map(([id, { type, answer }]) => `
          <div style="margin-bottom:var(--sp-4)">
            <div style="font-size:var(--text-xs);text-transform:uppercase;letter-spacing:.05em;color:var(--color-text-muted);margin-bottom:var(--sp-1)">${id.replace("_", " ")}</div>
            <div style="font-size:var(--text-sm);background:var(--color-background);padding:var(--sp-3);border-radius:var(--radius-sm)">${answer}</div>
          </div>
        `).join("")
        : `<div class="empty-state" style="text-align:left">No discrepancy context captured.</div>`
      }
    </div>

    <div class="card">
      <div class="card-title" style="margin-bottom:var(--sp-4)">Raw decision payload</div>
      <pre style="font-size:var(--text-xs);background:var(--color-background);padding:var(--sp-4);border-radius:var(--radius-sm);overflow-x:auto;white-space:pre-wrap">${
        JSON.stringify({
          domain: state.context.domain,
          situation: state.context.situation,
          urgency: state.context.urgency,
          fields: state.fields,
          trust: {
            overall: state.overallTrust,
            rtql_score: rtqlScore,
            per_field: state.trustScores,
          },
          discrepancy_context: state.discrepancyAnswers,
        }, null, 2)
      }</pre>
    </div>
  `;
}

// ── Init ──────────────────────────────────────────────────────────────────────
goToStep(1);
