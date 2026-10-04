"""Standalone local static HTML reviewer for LONG-002D3A."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_static_html_viewer(
    blinded_cases: list[dict[str, Any]],
    output_html_path: Path,
) -> Path:
    """Generate self-contained local static HTML review interface."""
    output_html_path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize blinded cases safely as JSON for embedded script
    cases_json = json.dumps(blinded_cases, indent=None)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradeX Blinded Review Pilot — LONG-002D3A</title>
<style>
  :root {{
    --bg-primary: #0f172a;
    --bg-card: #1e293b;
    --bg-input: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border-color: #475569;
    --accent-blue: #38bdf8;
    --accent-green: #22c55e;
    --accent-amber: #f59e0b;
    --accent-purple: #c084fc;
    --up-green: #4ade80;
    --down-red: #f87171;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.5;
    padding: 20px;
  }}
  header {{
    background: var(--bg-card);
    padding: 16px 24px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  h1 {{ font-size: 1.25rem; font-weight: 700; color: var(--accent-blue); }}
  .badge {{
    background: #0369a1;
    color: #e0f2fe;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .nav-controls {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  select, button, input, textarea {{
    background: var(--bg-input);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.875rem;
  }}
  button {{
    background: #2563eb;
    color: white;
    cursor: pointer;
    font-weight: 600;
    transition: background 0.15s ease;
  }}
  button:hover {{ background: #1d4ed8; }}
  button.secondary {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
  }}
  button.secondary:hover {{ background: var(--bg-input); }}
  .main-layout {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}
  @media (max-width: 1024px) {{
    .main-layout {{ grid-template-columns: 1fr; }}
  }}
  .card {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 10px;
  }}
  .card-title {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
  }}
  .stage-badge {{
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 4px;
    text-transform: uppercase;
  }}
  .stage-a-badge {{ background: #1e3a8a; color: #93c5fd; }}
  .stage-b-badge {{ background: #581c87; color: #e9d5ff; }}
  .chart-container {{
    width: 100%;
    height: 320px;
    background: #020617;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    position: relative;
    overflow: hidden;
  }}
  svg {{ width: 100%; height: 100%; }}
  .grid-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    font-size: 0.85rem;
  }}
  .grid-table th, .grid-table td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color);
    text-align: left;
  }}
  .grid-table th {{ color: var(--text-secondary); font-weight: 500; }}
  .form-group {{
    margin-bottom: 14px;
  }}
  label {{
    display: block;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }}
  .form-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  .tabs {{
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
  }}
  .tab {{
    padding: 8px 16px;
    border-radius: 6px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-secondary);
  }}
  .tab.active {{
    background: #0369a1;
    color: white;
    border-color: #0284c7;
  }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}
  .help-box {{
    background: #172554;
    border-left: 4px solid var(--accent-blue);
    padding: 10px 14px;
    border-radius: 4px;
    margin-bottom: 16px;
    font-size: 0.8rem;
    color: #bfdbfe;
  }}
  .status-pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .pill-saved {{ background: #065f46; color: #a7f3d0; }}
  .pill-unsaved {{ background: #78350f; color: #fde68a; }}
</style>
</head>
<body>

<header>
  <div>
    <h1>TradeX Blinded Review Pilot — LONG-002D3A</h1>
    <span class="badge">Workflow Pilot (24 Cases)</span>
    <span style="font-size: 0.75rem; color: var(--text-secondary); margin-left: 8px;">Development Split (2016–2020)</span>
  </div>
  <div class="nav-controls">
    <button class="secondary" onclick="prevCase()">← Prev</button>
    <select id="case-select" onchange="switchCase(parseInt(this.value))"></select>
    <button class="secondary" onclick="nextCase()">Next →</button>
    <button onclick="exportLabels()">Export All Labels</button>
  </div>
</header>

<div class="help-box">
  <strong>Blinding Invariant:</strong> All historical identities (ticker, name, security ID), exact calendar dates, and outcomes are completely hidden. Relative time extends strictly from <code>T-60</code> to <code>T0</code>. Prices are normalized to 100.0 at <code>T-60</code> while strictly preserving returns, moving averages, and volatility ratios. No future data exists beyond <code>T0</code>.
</div>

<div class="main-layout">
  <!-- Left Column: Technical and PIT Visuals -->
  <div>
    <!-- Stage A Card -->
    <div class="card">
      <div class="card-header">
        <div>
          <span class="card-title" id="display-case-id">D3A-PILOT-001</span>
          <span class="stage-badge stage-a-badge" style="margin-left: 8px;">Stage A: Technical</span>
        </div>
        <span id="case-status-pill" class="status-pill pill-unsaved">Unlabeled</span>
      </div>

      <div class="chart-container" id="chart-area">
        <!-- SVG Chart rendered by JS -->
      </div>

      <table class="grid-table" id="metrics-table">
        <tbody>
          <!-- Populated by JS -->
        </tbody>
      </table>
    </div>

    <!-- Stage B Context Card -->
    <div class="card" id="stage-b-card">
      <div class="card-header">
        <span class="card-title">Stage B: Qualified Point-in-Time Context</span>
        <span class="stage-badge stage-b-badge">Stage B Context</span>
      </div>
      <p style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 12px;">
        Information below reflects genuinely available point-in-time attributes known at the decision cutoff. Missing fields remain strictly unknown.
      </p>
      <table class="grid-table" id="pit-table">
        <tbody>
          <!-- Populated by JS -->
        </tbody>
      </table>
    </div>
  </div>

  <!-- Right Column: Labeling Interface -->
  <div>
    <div class="card">
      <div class="tabs">
        <div class="tab active" id="tab-btn-a" onclick="switchTab('stage-a')">Stage A Review</div>
        <div class="tab" id="tab-btn-b" onclick="switchTab('stage-b')">Stage B Review</div>
      </div>

      <!-- Stage A Form -->
      <div id="pane-stage-a" class="tab-pane active">
        <form id="form-stage-a" onsubmit="event.preventDefault(); saveCurrentLabel('stage_a');">
          <div class="form-row">
            <div class="form-group">
              <label>Surface Decision *</label>
              <select id="a-surface_decision" required onchange="toggleVisibleState('a')">
                <option value="surface">surface</option>
                <option value="do_not_surface">do_not_surface</option>
              </select>
            </div>
            <div class="form-group">
              <label>Visible State if Surfaced</label>
              <select id="a-visible_state_if_surfaced">
                <option value="Enter Now">Enter Now</option>
                <option value="Armed">Armed</option>
                <option value="Qualified Waitlist">Qualified Waitlist</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Expected Target Pct</label>
              <select id="a-expected_target_pct">
                <option value="">(Declined / None)</option>
                <option value="10">+10%</option>
                <option value="20">+20%</option>
                <option value="30">+30%</option>
              </select>
            </div>
            <div class="form-group">
              <label>Expected Horizon (Sessions)</label>
              <select id="a-expected_horizon_sessions">
                <option value="">(None)</option>
                <option value="5">5 sessions</option>
                <option value="10">10 sessions</option>
                <option value="21">21 sessions</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Qualitative Confidence (1–5) *</label>
              <select id="a-qualitative_confidence" required>
                <option value="1">1 — Very Low</option>
                <option value="2">2 — Low</option>
                <option value="3" selected>3 — Moderate</option>
                <option value="4">4 — High</option>
                <option value="5">5 — Very High</option>
              </select>
            </div>
            <div class="form-group">
              <label>Setup Archetype *</label>
              <select id="a-setup_archetype" required>
                <option value="setup_archetype">Setup Archetype</option>
                <option value="other">Other</option>
                <option value="unclear">Unclear</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label>Entry Plan</label>
            <input type="text" id="a-entry_plan" placeholder="e.g. Next open or breakout above resistance">
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Trigger or Zone</label>
              <input type="text" id="a-trigger_or_zone" placeholder="Specific price zone or trigger">
            </div>
            <div class="form-group">
              <label>Max Validity (Sessions, max 5)</label>
              <input type="number" id="a-max_validity_sessions" min="1" max="5" value="5">
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Gap Handling</label>
              <input type="text" id="a-gap_handling" placeholder="e.g. Reject if gap > 1.5%">
            </div>
            <div class="form-group">
              <label>Invalidation / Stop Concept</label>
              <input type="text" id="a-invalidation" placeholder="e.g. Close below 20-day SMA">
            </div>
          </div>

          <div class="form-group">
            <label>Positive Reasons (Up to 3, comma separated)</label>
            <input type="text" id="a-positive_reasons" placeholder="Reason 1, Reason 2, Reason 3">
          </div>

          <div class="form-group">
            <label>Material Risks & Counterarguments</label>
            <textarea id="a-material_risks_counterarguments" rows="2" placeholder="Visible technical or market risks"></textarea>
          </div>

          <button type="submit" style="width: 100%;">Save Stage A Label</button>
        </form>
      </div>

      <!-- Stage B Form -->
      <div id="pane-stage-b" class="tab-pane">
        <form id="form-stage-b" onsubmit="event.preventDefault(); saveCurrentLabel('stage_b');">
          <div class="form-row">
            <div class="form-group">
              <label>Surface Decision *</label>
              <select id="b-surface_decision" required onchange="toggleVisibleState('b')">
                <option value="surface">surface</option>
                <option value="do_not_surface">do_not_surface</option>
              </select>
            </div>
            <div class="form-group">
              <label>Visible State if Surfaced</label>
              <select id="b-visible_state_if_surfaced">
                <option value="Enter Now">Enter Now</option>
                <option value="Armed">Armed</option>
                <option value="Qualified Waitlist">Qualified Waitlist</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Expected Target Pct</label>
              <select id="b-expected_target_pct">
                <option value="">(Declined / None)</option>
                <option value="10">+10%</option>
                <option value="20">+20%</option>
                <option value="30">+30%</option>
              </select>
            </div>
            <div class="form-group">
              <label>Expected Horizon (Sessions)</label>
              <select id="b-expected_horizon_sessions">
                <option value="">(None)</option>
                <option value="5">5 sessions</option>
                <option value="10">10 sessions</option>
                <option value="21">21 sessions</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Qualitative Confidence (1–5) *</label>
              <select id="b-qualitative_confidence" required>
                <option value="1">1 — Very Low</option>
                <option value="2">2 — Low</option>
                <option value="3" selected>3 — Moderate</option>
                <option value="4">4 — High</option>
                <option value="5">5 — Very High</option>
              </select>
            </div>
            <div class="form-group">
              <label>Setup Archetype *</label>
              <select id="b-setup_archetype" required>
                <option value="setup_archetype">Setup Archetype</option>
                <option value="other">Other</option>
                <option value="unclear">Unclear</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label>Entry Plan</label>
            <input type="text" id="b-entry_plan" placeholder="Updated with fundamental / PIT context">
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Trigger or Zone</label>
              <input type="text" id="b-trigger_or_zone" placeholder="Specific price zone or trigger">
            </div>
            <div class="form-group">
              <label>Max Validity (Sessions, max 5)</label>
              <input type="number" id="b-max_validity_sessions" min="1" max="5" value="5">
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Gap Handling</label>
              <input type="text" id="b-gap_handling" placeholder="e.g. Reject if gap > 1.5%">
            </div>
            <div class="form-group">
              <label>Invalidation / Stop Concept</label>
              <input type="text" id="b-invalidation" placeholder="e.g. Invalidate before earnings">
            </div>
          </div>

          <div class="form-group">
            <label>Positive Reasons (Up to 3, comma separated)</label>
            <input type="text" id="b-positive_reasons" placeholder="Reason 1, Reason 2, Reason 3">
          </div>

          <div class="form-group">
            <label>Material Risks & Counterarguments</label>
            <textarea id="b-material_risks_counterarguments" rows="2" placeholder="Risks including earnings timing or market-cap cohort"></textarea>
          </div>

          <button type="submit" style="width: 100%; background: #7c3aed;">Save Stage B Label</button>
        </form>
      </div>

    </div>
  </div>
</div>

<script>
const CASES = {cases_json};
let currentIndex = 0;
const STORAGE_KEY = "tradex_d3a_pilot_labels_v1";

function loadSavedLabels() {{
  try {{
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {{}};
  }} catch (e) {{
    return {{}};
  }}
}}

function saveLabelRecord(caseId, stage, data) {{
  const store = loadSavedLabels();
  if (!store[caseId]) store[caseId] = {{}};
  store[caseId][stage] = data;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  updateStatusPill();
}}

function init() {{
  const sel = document.getElementById("case-select");
  sel.innerHTML = "";
  CASES.forEach((c, idx) => {{
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = `${{idx + 1}}/24: ${{c.case_id}}`;
    sel.appendChild(opt);
  }});
  switchCase(0);
}}

function switchCase(idx) {{
  if (idx < 0 || idx >= CASES.length) return;
  currentIndex = idx;
  document.getElementById("case-select").value = idx;
  const c = CASES[idx];
  document.getElementById("display-case-id").textContent = c.case_id;

  renderChart(c.stage_a.relative_bars);
  renderMetricsTable(c.stage_a.technical_metrics, c.stage_a.spy_context);
  renderPitTable(c.stage_b.pit_context);

  loadFormValues(c.case_id);
  updateStatusPill();
}}

function prevCase() {{ if (currentIndex > 0) switchCase(currentIndex - 1); }}
function nextCase() {{ if (currentIndex < CASES.length - 1) switchCase(currentIndex + 1); }}

function renderChart(bars) {{
  const container = document.getElementById("chart-area");
  if (!bars || bars.length === 0) {{
    container.innerHTML = "<p style='color:red;padding:20px;'>No bars</p>";
    return;
  }}

  const w = container.clientWidth || 550;
  const h = 320;
  const padL = 45, padR = 15, padT = 20, padB = 40;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;

  let minP = Infinity, maxP = -Infinity;
  bars.forEach(b => {{
    if (b.normalized_low < minP) minP = b.normalized_low;
    if (b.normalized_high > maxP) maxP = b.normalized_high;
  }});
  const pRange = (maxP - minP) || 1;
  const priceMargin = pRange * 0.05;
  const plotMin = minP - priceMargin;
  const plotMax = maxP + priceMargin;
  const plotRange = plotMax - plotMin;

  const n = bars.length;
  const barWidth = Math.max(2, (chartW / n) * 0.7);

  function getY(p) {{
    return padT + chartH * (1 - (p - plotMin) / plotRange);
  }}

  let svg = `<svg viewBox="0 0 ${{w}} ${{h}}">`;

  // Grid lines
  for (let i = 0; i <= 4; i++) {{
    const yVal = plotMin + (plotRange * i / 4);
    const yPx = getY(yVal);
    svg += `<line x1="${{padL}}" y1="${{yPx}}" x2="${{w - padR}}" y2="${{yPx}}" stroke="#334155" stroke-dasharray="2,2"/>`;
    svg += `<text x="${{padL - 6}}" y="${{yPx + 4}}" fill="#64748b" font-size="10" text-anchor="end">${{yVal.toFixed(1)}}</text>`;
  }}

  // SMA lines
  let sma20Pts = [];
  let sma50Pts = [];
  bars.forEach((b, idx) => {{
    const xPx = padL + (idx + 0.5) * (chartW / n);
    if (b.normalized_sma20 !== null) sma20Pts.push(`${{xPx}},${{getY(b.normalized_sma20)}}`);
    if (b.normalized_sma50 !== null) sma50Pts.push(`${{xPx}},${{getY(b.normalized_sma50)}}`);
  }});

  if (sma50Pts.length > 1) {{
    svg += `<polyline points="${{sma50Pts.join(" ")}}" fill="none" stroke="#f59e0b" stroke-width="1.5" opacity="0.8"/>`;
  }}
  if (sma20Pts.length > 1) {{
    svg += `<polyline points="${{sma20Pts.join(" ")}}" fill="none" stroke="#38bdf8" stroke-width="1.5"/>`;
  }}

  // Candlesticks
  bars.forEach((b, idx) => {{
    const xPx = padL + (idx + 0.5) * (chartW / n);
    const isUp = b.normalized_close >= b.normalized_open;
    const color = isUp ? "var(--up-green)" : "var(--down-red)";

    const yHigh = getY(b.normalized_high);
    const yLow = getY(b.normalized_low);
    const yOpen = getY(b.normalized_open);
    const yClose = getY(b.normalized_close);

    const bodyY = Math.min(yOpen, yClose);
    const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));

    // Wick
    svg += `<line x1="${{xPx}}" y1="${{yHigh}}" x2="${{xPx}}" y2="${{yLow}}" stroke="${{color}}" stroke-width="1"/>`;
    // Body
    svg += `<rect x="${{xPx - barWidth/2}}" y="${{bodyY}}" width="${{barWidth}}" height="${{bodyH}}" fill="${{color}}"/>`;
  }});

  // X Axis labels
  svg += `<text x="${{padL}}" y="${{h - 8}}" fill="#64748b" font-size="11" text-anchor="middle">T-60</text>`;
  svg += `<text x="${{padL + chartW * 0.5}}" y="${{h - 8}}" fill="#64748b" font-size="11" text-anchor="middle">T-30</text>`;
  svg += `<text x="${{w - padR}}" y="${{h - 8}}" fill="#38bdf8" font-size="11" font-weight="700" text-anchor="middle">T0</text>`;

  svg += `</svg>`;
  container.innerHTML = svg;
}}

function renderMetricsTable(metrics, spy) {{
  const tbody = document.querySelector("#metrics-table tbody");
  tbody.innerHTML = `
    <tr><th>Pre-Decision T0 Close (Norm)</th><td><strong>${{metrics.pre_decision_normalized_close_t0}}</strong></td><th>ATR% (14)</th><td>${{metrics.atr_pct_14_t0 || 'N/A'}}%</td></tr>
    <tr><th>5-Bar Return</th><td>${{metrics.return_5_bars_pct !== null ? metrics.return_5_bars_pct + '%' : 'N/A'}}</td><th>Relative Volume (20d)</th><td>${{metrics.relative_volume_t0 || 'N/A'}}x</td></tr>
    <tr><th>10-Bar Return</th><td>${{metrics.return_10_bars_pct !== null ? metrics.return_10_bars_pct + '%' : 'N/A'}}</td><th>Above SMA20 / SMA50</th><td>${{metrics.above_sma20_t0 ? 'Yes' : 'No'}} / ${{metrics.above_sma50_t0 ? 'Yes' : 'No'}}</td></tr>
    <tr><th>20-Bar Return</th><td>${{metrics.return_20_bars_pct !== null ? metrics.return_20_bars_pct + '%' : 'N/A'}}</td><th>SPY 20-Bar Return</th><td>${{spy.spy_return_20_bars_pct !== null ? spy.spy_return_20_bars_pct + '%' : 'N/A'}}</td></tr>
    <tr><th>60-Bar Return</th><td>${{metrics.return_60_bars_pct !== null ? metrics.return_60_bars_pct + '%' : 'N/A'}}</td><th>Stock vs SPY (20d)</th><td>${{spy.stock_minus_spy_20_bars_pct !== null ? spy.stock_minus_spy_20_bars_pct + ' pp' : 'N/A'}}</td></tr>
  `;
}}

function renderPitTable(pit) {{
  const tbody = document.querySelector("#pit-table tbody");
  tbody.innerHTML = `
    <tr><th>Security Classification</th><td>${{pit.security_type}}</td></tr>
    <tr><th>Market-Cap Cohort</th><td><strong>${{pit.market_cap_cohort}}</strong></td></tr>
    <tr><th>Trading History Cohort</th><td>${{pit.trading_history_cohort}}</td></tr>
    <tr><th>PIT Earnings Schedule Status</th><td><code>${{pit.pit_earnings_schedule_status}}</code></td></tr>
    <tr><th>Announcement Timing</th><td>${{pit.pit_earnings_announcement_timing || 'unknown'}}</td></tr>
    <tr><th>Sessions to Next Earnings</th><td>${{pit.pit_sessions_to_next_earnings !== null ? pit.pit_sessions_to_next_earnings : 'unknown'}}</td></tr>
    <tr><th>Reported Financial Facts</th><td><span style="color:#94a3b8">${{pit.reported_financial_facts}}</span></td></tr>
  `;
}}

function switchTab(tab) {{
  document.getElementById("tab-btn-a").classList.toggle("active", tab === "stage-a");
  document.getElementById("tab-btn-b").classList.toggle("active", tab === "stage-b");
  document.getElementById("pane-stage-a").classList.toggle("active", tab === "stage-a");
  document.getElementById("pane-stage-b").classList.toggle("active", tab === "stage-b");
}}

function toggleVisibleState(pfx) {{
  const dec = document.getElementById(`${{pfx}}-surface_decision`).value;
  const stateSel = document.getElementById(`${{pfx}}-visible_state_if_surfaced`);
  if (dec === "do_not_surface") {{
    stateSel.value = "";
    stateSel.disabled = true;
  }} else {{
    stateSel.disabled = false;
    if (!stateSel.value) stateSel.value = "Enter Now";
  }}
}}

function saveCurrentLabel(stage) {{
  const c = CASES[currentIndex];
  const pfx = stage === "stage_a" ? "a" : "b";

  const data = {{
    case_id: c.case_id,
    stage: stage,
    surface_decision: document.getElementById(`${{pfx}}-surface_decision`).value,
    visible_state_if_surfaced: document.getElementById(`${{pfx}}-surface_decision`).value === "surface" ? document.getElementById(`${{pfx}}-visible_state_if_surfaced`).value : null,
    expected_target_pct: document.getElementById(`${{pfx}}-expected_target_pct`).value ? parseInt(document.getElementById(`${{pfx}}-expected_target_pct`).value) : null,
    expected_horizon_sessions: document.getElementById(`${{pfx}}-expected_horizon_sessions`).value ? parseInt(document.getElementById(`${{pfx}}-expected_horizon_sessions`).value) : null,
    qualitative_confidence: parseInt(document.getElementById(`${{pfx}}-qualitative_confidence`).value),
    setup_archetype: document.getElementById(`${{pfx}}-setup_archetype`).value,
    entry_plan: document.getElementById(`${{pfx}}-entry_plan`).value,
    trigger_or_zone: document.getElementById(`${{pfx}}-trigger_or_zone`).value,
    max_validity_sessions: document.getElementById(`${{pfx}}-max_validity_sessions`).value ? parseInt(document.getElementById(`${{pfx}}-max_validity_sessions`).value) : null,
    gap_handling: document.getElementById(`${{pfx}}-gap_handling`).value,
    invalidation: document.getElementById(`${{pfx}}-invalidation`).value,
    positive_reasons: document.getElementById(`${{pfx}}-positive_reasons`).value ? document.getElementById(`${{pfx}}-positive_reasons`).value.split(",").map(s => s.trim()).filter(Boolean) : [],
    material_risks_counterarguments: document.getElementById(`${{pfx}}-material_risks_counterarguments`).value,
    submitted_at_utc: new Date().toISOString()
  }};

  saveLabelRecord(c.case_id, stage, data);
  alert(`Saved ${{stage.toUpperCase()}} label for ${{c.case_id}}!`);
}}

function loadFormValues(caseId) {{
  const store = loadSavedLabels();
  const cData = store[caseId] || {{}};

  ['a', 'b'].forEach(pfx => {{
    const stage = pfx === 'a' ? 'stage_a' : 'stage_b';
    const d = cData[stage] || {{}};

    document.getElementById(`${{pfx}}-surface_decision`).value = d.surface_decision || "surface";
    toggleVisibleState(pfx);
    if (d.visible_state_if_surfaced) {{
      document.getElementById(`${{pfx}}-visible_state_if_surfaced`).value = d.visible_state_if_surfaced;
    }}
    document.getElementById(`${{pfx}}-expected_target_pct`).value = d.expected_target_pct !== null && d.expected_target_pct !== undefined ? d.expected_target_pct : "";
    document.getElementById(`${{pfx}}-expected_horizon_sessions`).value = d.expected_horizon_sessions !== null && d.expected_horizon_sessions !== undefined ? d.expected_horizon_sessions : "";
    document.getElementById(`${{pfx}}-qualitative_confidence`).value = d.qualitative_confidence || "3";
    document.getElementById(`${{pfx}}-setup_archetype`).value = d.setup_archetype || "setup_archetype";
    document.getElementById(`${{pfx}}-entry_plan`).value = d.entry_plan || "";
    document.getElementById(`${{pfx}}-trigger_or_zone`).value = d.trigger_or_zone || "";
    document.getElementById(`${{pfx}}-max_validity_sessions`).value = d.max_validity_sessions || "5";
    document.getElementById(`${{pfx}}-gap_handling`).value = d.gap_handling || "";
    document.getElementById(`${{pfx}}-invalidation`).value = d.invalidation || "";
    document.getElementById(`${{pfx}}-positive_reasons`).value = (d.positive_reasons || []).join(", ");
    document.getElementById(`${{pfx}}-material_risks_counterarguments`).value = d.material_risks_counterarguments || "";
  }});
}}

function updateStatusPill() {{
  const c = CASES[currentIndex];
  const store = loadSavedLabels();
  const cData = store[c.case_id] || {{}};
  const hasA = Boolean(cData.stage_a);
  const hasB = Boolean(cData.stage_b);
  const pill = document.getElementById("case-status-pill");

  if (hasA && hasB) {{
    pill.className = "status-pill pill-saved";
    pill.textContent = "Stages A & B Labeled";
  }} else if (hasA) {{
    pill.className = "status-pill pill-unsaved";
    pill.textContent = "Stage A Only";
  }} else if (hasB) {{
    pill.className = "status-pill pill-unsaved";
    pill.textContent = "Stage B Only";
  }} else {{
    pill.className = "status-pill pill-unsaved";
    pill.textContent = "Unlabeled";
  }}
}}

function exportLabels() {{
  const store = loadSavedLabels();
  const jsonStr = JSON.stringify(store, null, 2);
  const blob = new Blob([jsonStr], {{ type: "application/json" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "pilot_review_labels.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

window.addEventListener("DOMContentLoaded", init);
window.addEventListener("resize", () => renderChart(CASES[currentIndex].stage_a.relative_bars));
</script>
</body>
</html>
"""

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_html_path
