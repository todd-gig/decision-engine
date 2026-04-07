/* ============================================================
   dashboard.js — Executive Decision Engine Frontend
   Connects to FastAPI backend at /v1/* endpoints
   ============================================================ */

const API = '';  // same origin

// ── State ─────────────────────────────────────────────────────
let lastResult = null;

// ── DOM Ready ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initScoreSliders();
  initForms();
  initLifecycle();
  checkHealth();
  loadConfig();
  loadLearning();
  setDefaultReviewDate();
});

// ── Navigation ────────────────────────────────────────────────
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const views = document.querySelectorAll('.view');
  const title = document.getElementById('view-title');
  const toggle = document.getElementById('menu-toggle');
  const sidebar = document.getElementById('sidebar');

  navItems.forEach(btn => {
    btn.addEventListener('click', () => {
      const viewId = btn.dataset.view;
      navItems.forEach(n => n.classList.remove('active'));
      btn.classList.add('active');
      views.forEach(v => v.classList.remove('active'));
      document.getElementById(`view-${viewId}`).classList.add('active');
      title.textContent = btn.textContent.trim();
      sidebar.classList.remove('open');
    });
  });

  toggle?.addEventListener('click', () => sidebar.classList.toggle('open'));
}

// ── Score Sliders ─────────────────────────────────────────────
function initScoreSliders() {
  document.querySelectorAll('.score-row input[type="range"]').forEach(slider => {
    const valEl = slider.closest('.score-row').querySelector('.score-val');
    const isAlignment = slider.closest('#alignment-scores');

    const updateVal = () => {
      const v = parseFloat(slider.value);
      valEl.textContent = isAlignment ? (v / 10).toFixed(1) : v;
    };

    slider.addEventListener('input', () => {
      updateVal();
      updateScoreSummaries();
    });
    updateVal();
  });
  updateScoreSummaries();
}

function updateScoreSummaries() {
  // Value scores
  const positiveKeys = ['revenue_impact','cost_efficiency','time_leverage','strategic_alignment',
    'customer_human_benefit','knowledge_asset_creation','compounding_potential','reversibility'];
  const penaltyKeys = ['downside_risk','execution_drag','uncertainty','ethical_misalignment'];

  let gross = 0, penalty = 0;
  document.querySelectorAll('#value-scores input[type="range"]').forEach(s => {
    const key = s.dataset.key;
    const v = parseInt(s.value);
    if (positiveKeys.includes(key)) gross += v;
    else if (penaltyKeys.includes(key)) penalty += v;
  });

  const net = gross - penalty;
  const sumEl = document.getElementById('value-summary');
  if (sumEl) {
    sumEl.innerHTML = `
      <span>Gross: <strong>${gross}</strong></span>
      <span>Penalty: <strong>${penalty}</strong></span>
      <span>Net: <strong class="${net >= 0 ? 'net-positive' : 'net-negative'}">${net}</strong></span>
    `;
  }

  // Trust scores
  let trustTotal = 0;
  document.querySelectorAll('#trust-scores input[type="range"]').forEach(s => {
    trustTotal += parseInt(s.value);
  });

  const tier = trustTotal >= 30 ? 'T4' : trustTotal >= 24 ? 'T3' : trustTotal >= 17 ? 'T2' : trustTotal >= 10 ? 'T1' : 'T0';
  const trustEl = document.getElementById('trust-summary');
  if (trustEl) {
    trustEl.innerHTML = `
      <span>Total: <strong>${trustTotal}</strong> / 35</span>
      <span>Tier: <strong class="tier-badge ${tier.toLowerCase()}">${tier}</strong></span>
    `;
  }
}

// ── Forms ──────────────────────────────────────────────────────
function initForms() {
  document.getElementById('decision-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await processDecision();
  });

  document.getElementById('reset-btn').addEventListener('click', () => {
    document.getElementById('decision-form').reset();
    initScoreSliders();
  });

  document.getElementById('outcome-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await recordOutcome();
  });

  document.getElementById('check-transition-btn').addEventListener('click', checkTransition);
}

function setDefaultReviewDate() {
  const d = new Date();
  d.setDate(d.getDate() + 14);
  document.getElementById('f-review').value = d.toISOString().split('T')[0];
}

// ── Process Decision ──────────────────────────────────────────
async function processDecision() {
  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Processing...';

  const payload = buildDecisionPayload();

  try {
    const res = await fetch(`${API}/v1/decisions/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    lastResult = await res.json();
    renderResults(lastResult);
    toast('Decision processed successfully', 'success');

    // Switch to results view
    document.querySelector('[data-view="results"]').click();
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">&#9654;</span> Process Decision';
  }
}

function buildDecisionPayload() {
  const getVal = id => document.getElementById(id).value.trim();
  const getList = id => getVal(id).split(',').map(s => s.trim()).filter(Boolean);

  const valueScores = {};
  document.querySelectorAll('#value-scores input[type="range"]').forEach(s => {
    valueScores[s.dataset.key] = parseInt(s.value);
  });

  const trustScores = {};
  document.querySelectorAll('#trust-scores input[type="range"]').forEach(s => {
    trustScores[s.dataset.key] = parseInt(s.value);
  });

  const alignmentScores = {};
  document.querySelectorAll('#alignment-scores input[type="range"]').forEach(s => {
    alignmentScores[s.dataset.key] = parseFloat(s.value) / 10;
  });

  return {
    title: getVal('f-title'),
    decision_class: getVal('f-class'),
    owner: getVal('f-owner'),
    problem_statement: getVal('f-problem'),
    requested_action: getVal('f-action'),
    stakeholders: getList('f-stakeholders'),
    evidence_refs: getList('f-evidence'),
    execution_plan: getVal('f-exec-plan'),
    monitoring_metric: getVal('f-monitoring'),
    rollback_trigger: getVal('f-rollback'),
    review_date: getVal('f-review'),
    current_state: getVal('f-state'),
    actor_role: getVal('f-actor'),
    value_scores: valueScores,
    trust_scores: trustScores,
    alignment_scores: alignmentScores,
  };
}

// ── Render Results ────────────────────────────────────────────
function renderResults(r) {
  document.getElementById('results-empty').style.display = 'none';
  document.getElementById('results-content').style.display = 'block';

  // Verdict banner
  const banner = document.getElementById('verdict-banner');
  const verdict = r.recommended_action || 'unknown';
  banner.className = 'verdict-banner ' + getVerdictClass(verdict);
  document.getElementById('verdict-value').textContent = verdict.replace(/_/g, ' ').toUpperCase();
  document.getElementById('verdict-id').textContent = r.decision_id;

  // Metrics
  document.getElementById('m-value').textContent = r.net_value_score;
  document.getElementById('m-value-class').textContent = r.value_classification || '';
  document.getElementById('m-trust').textContent = r.trust_tier;
  document.getElementById('m-trust-total').textContent = `total: ${r.trust_total}`;
  document.getElementById('m-alignment').textContent = r.alignment_composite;
  document.getElementById('m-priority').textContent = r.priority_score;
  document.getElementById('m-state').textContent = r.next_state || '—';

  // Certificate chain
  const chainEl = document.getElementById('cert-chain');
  const certs = r.certificate_status || {};
  chainEl.innerHTML = ['QC', 'VC', 'TC', 'EC'].map((type, i) => {
    const status = certs[type] || 'none';
    const cls = status === 'issued' ? 'issued' : status === 'denied' ? 'denied' : 'none';
    const arrow = i < 3 ? '<span class="cert-arrow">&#8594;</span>' : '';
    return `<div class="cert-node ${cls}">
      <span class="cert-type">${type}</span>
      <span class="cert-status">${status}</span>
    </div>${arrow}`;
  }).join('');

  // Audit trail
  const auditEl = document.getElementById('audit-trail');
  const entries = r.audit_log || [];
  auditEl.innerHTML = entries.map(e => `
    <div class="audit-entry">
      <div class="audit-stage">${e.stage}</div>
      <div class="audit-detail">${e.detail?.action || ''}: ${e.detail?.notes || ''}</div>
    </div>
  `).join('');

  // Executive summary
  document.getElementById('exec-summary').textContent = r.executive_summary || JSON.stringify(r.full_result, null, 2);
}

function getVerdictClass(v) {
  if (v.includes('auto')) return 'auto';
  if (v.includes('escalate')) return 'escalate';
  if (v.includes('block')) return 'block';
  if (v.includes('needs')) return 'needs';
  return 'needs';
}

// ── Record Outcome ────────────────────────────────────────────
async function recordOutcome() {
  const getVal = id => document.getElementById(id).value.trim();
  const lessons = getVal('o-lessons').split('\n').map(s => s.trim()).filter(Boolean);
  const riskMat = document.querySelector('input[name="o-risk-mat"]:checked').value === 'true';

  const payload = {
    decision_id: getVal('o-decision-id'),
    decision_class: getVal('o-class'),
    original_verdict: getVal('o-verdict'),
    expected_value: parseFloat(document.getElementById('o-exp-val').value),
    expected_timeline_days: parseInt(document.getElementById('o-exp-days').value),
    expected_risk_level: getVal('o-risk-level'),
    actual_value: parseFloat(document.getElementById('o-act-val').value),
    actual_timeline_days: parseInt(document.getElementById('o-act-days').value),
    actual_risk_materialized: riskMat,
    actual_risk_description: '',
    outcome_summary: getVal('o-summary'),
    lessons_learned: lessons.length ? lessons : ['No specific lessons recorded'],
    recorded_by: getVal('o-by') || 'dashboard_user',
  };

  try {
    const res = await fetch(`${API}/v1/outcomes/record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById('outcome-result').innerHTML = `
      <div class="card">
        <div class="card-label">Variance Analysis Result</div>
        <dl class="data-kv">
          <dt>Record ID</dt><dd>${data.record_id}</dd>
          <dt>Trust Recommendation</dt><dd><strong>${data.trust_recommendation}</strong></dd>
          <dt>Composite Variance</dt><dd>${data.composite_variance}</dd>
          <dt>Suggested Actions</dt><dd>${(data.suggested_actions || []).join('<br>')}</dd>
        </dl>
      </div>
    `;
    toast('Outcome recorded', 'success');
    loadLearning();
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  }
}

// ── State Machine ─────────────────────────────────────────────
function initLifecycle() {
  const states = [
    { name: 'draft', certs: '—', pct: '0%' },
    { name: 'qualified', certs: 'QC', pct: '14%' },
    { name: 'value_confirmed', certs: 'QC VC', pct: '29%' },
    { name: 'trust_certified', certs: 'QC VC TC', pct: '43%' },
    { name: 'execution_cleared', certs: 'QC VC TC EC', pct: '57%' },
    { name: 'executed', certs: 'QC VC TC EC', pct: '71%' },
    { name: 'reviewed', certs: 'QC VC TC EC', pct: '86%' },
    { name: 'archived', certs: 'QC VC TC EC', pct: '100%' },
  ];

  const el = document.getElementById('lifecycle-visual');
  el.innerHTML = states.map((s, i) => {
    const arrow = i < states.length - 1 ? '<span class="lc-arrow">&#8594;</span>' : '';
    return `<div class="lc-node" data-state="${s.name}">
      <div class="lc-name">${s.name.replace(/_/g, ' ')}</div>
      <div class="lc-certs">${s.certs}</div>
      <div class="lc-pct">${s.pct}</div>
    </div>${arrow}`;
  }).join('');
}

async function checkTransition() {
  const from = document.getElementById('t-from').value;
  const to = document.getElementById('t-to').value;

  try {
    const res = await fetch(`${API}/v1/decisions/transition`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_state: from, target_state: to }),
    });
    const data = await res.json();

    const resultEl = document.getElementById('transition-result');
    if (data.allowed) {
      resultEl.innerHTML = `<div class="badge badge-success" style="font-size:13px;padding:6px 16px">
        &#10003; Transition allowed: ${from} &rarr; ${to}
        <br><small>Required certificates: ${(data.required_certificates || []).join(', ')}</small>
      </div>`;
    } else {
      resultEl.innerHTML = `<div class="badge badge-danger" style="font-size:13px;padding:6px 16px">
        &#10007; Transition blocked: ${from} &rarr; ${to}
      </div>`;
    }

    // Highlight nodes
    document.querySelectorAll('.lc-node').forEach(n => {
      n.classList.remove('active', 'completed');
      if (n.dataset.state === from) n.classList.add('active');
      if (n.dataset.state === to && data.allowed) n.classList.add('completed');
    });
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  }
}

// ── Health Check ──────────────────────────────────────────────
async function checkHealth() {
  const dot = document.getElementById('health-dot');
  const label = document.getElementById('health-label');
  const badge = document.getElementById('api-status');

  try {
    const res = await fetch(`${API}/health`);
    const data = await res.json();
    dot.className = 'health-indicator ok';
    label.textContent = `Engine v${data.engine_version || '2.0.0'}`;
    badge.className = 'status-badge ok';
    badge.textContent = 'API: connected';
  } catch {
    dot.className = 'health-indicator err';
    label.textContent = 'Offline';
    badge.className = 'status-badge err';
    badge.textContent = 'API: offline';
  }
}

// ── Load Config ───────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch(`${API}/v1/config`);
    const data = await res.json();

    document.getElementById('config-content').innerHTML = `
      <div class="card-label">Engine Configuration</div>
      <div class="form-grid-2" style="margin-top:16px">
        <div>
          <h3 style="font-size:14px;font-weight:700;margin-bottom:12px;color:var(--gray-700)">Thresholds</h3>
          <dl class="data-kv">
            <dt>Value Execute Min</dt><dd>${data.thresholds?.value_execute_min}</dd>
            <dt>Value Escalate Min</dt><dd>${data.thresholds?.value_escalate_min}</dd>
            <dt>Trust Execute Min</dt><dd>${data.thresholds?.trust_execute_min}</dd>
            <dt>Trust Recommend Min</dt><dd>${data.thresholds?.trust_recommend_min}</dd>
          </dl>
        </div>
        <div>
          <h3 style="font-size:14px;font-weight:700;margin-bottom:12px;color:var(--gray-700)">Trust Multipliers</h3>
          <dl class="data-kv">
            ${Object.entries(data.trust_multiplier || {}).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}
          </dl>
        </div>
      </div>
      <div style="margin-top:24px">
        <h3 style="font-size:14px;font-weight:700;margin-bottom:12px;color:var(--gray-700)">Valid Transitions</h3>
        <pre style="font-family:'SF Mono',monospace;font-size:12px;background:var(--gray-50);padding:16px;border-radius:8px;overflow-x:auto">${JSON.stringify(data.valid_transitions, null, 2)}</pre>
      </div>
    `;
  } catch {
    document.getElementById('config-content').innerHTML = '<div class="data-display">Failed to load configuration.</div>';
  }
}

// ── Load Learning ─────────────────────────────────────────────
async function loadLearning() {
  try {
    const [summaryRes, unappliedRes] = await Promise.all([
      fetch(`${API}/v1/learning/summary`),
      fetch(`${API}/v1/learning/unapplied`),
    ]);

    const summary = await summaryRes.json();
    const unapplied = await unappliedRes.json();

    const sumEl = document.getElementById('learning-summary');
    if (summary.summary) {
      sumEl.innerHTML = `<pre>${summary.summary}</pre>`;
    } else {
      sumEl.innerHTML = `
        <div class="empty-state" style="padding:24px">
          <div>No learning data yet. Record decision outcomes to build institutional knowledge.</div>
        </div>
      `;
    }

    const unapEl = document.getElementById('unapplied-learnings');
    if (unapplied.count > 0) {
      unapEl.innerHTML = `
        <div style="margin-bottom:12px;font-weight:600;color:var(--gray-700)">${unapplied.count} unapplied learning(s)</div>
        ${unapplied.records.map(r => `
          <div style="padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;font-size:13px">
            <strong>${r.decision_id}</strong> (${r.decision_class})
            <br>Recommendation: <span class="badge ${r.trust_recommendation === 'upgrade' ? 'badge-success' : r.trust_recommendation === 'downgrade' ? 'badge-danger' : 'badge-info'}">${r.trust_recommendation}</span>
            ${r.suggested_actions?.map(a => `<br><small>${a}</small>`).join('') || ''}
          </div>
        `).join('')}
      `;
    } else {
      unapEl.innerHTML = `
        <div class="empty-state" style="padding:24px">
          <div>All learnings applied. System is current.</div>
        </div>
      `;
    }
  } catch {
    document.getElementById('learning-summary').textContent = 'Unable to load learning data.';
    document.getElementById('unapplied-learnings').textContent = 'Unable to load.';
  }
}

// ── Toast ─────────────────────────────────────────────────────
function toast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
