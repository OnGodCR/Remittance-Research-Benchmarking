/* Remittance Rails Benchmark -- explorer and replay tool.
 *
 * Everything shown is read from data/results.json, which website/build_data.py
 * builds with the paper's own analysis code. Nothing here invents a
 * measurement: the replay tool only ever re-draws payments that were recorded.
 */
"use strict";

const LOADS = [10, 25, 50, 100, 150, 200, 300];
const AMOUNTS = [10, 50, 200, 500];
// The measured window: 300 s minus the 10 s warm-up (same as analysis/results.py).
const WINDOW_S = 290;
const SYS = {
  polygon: { name: "Polygon Edge", kind: "Sidechain", color: "var(--polygon)" },
  near: { name: "NEAR", kind: "Sharding", color: "var(--near)" },
  lightning: { name: "Lightning", kind: "Off-chain", color: "var(--lightning)" },
};
const ARMS = {
  baseline: { label: "Normal" },
  adversarial: { label: "One computer failing" },
};

// Waugh & Holz (2020), arXiv:2006.14358 -- the real Lightning network.
const LN_SUCCESS = [
  { size: "$0.01", success: 71.9, reach: 35.2 },
  { size: "$1", success: 57.8, reach: 35.2 },
  { size: "$5", success: 44.1, reach: 25.7 },
  { size: "$10", success: 44.2, reach: 33.7 },
  { size: "$50", success: 30.9, reach: 9.2 },
  { size: "$100", success: 17.3, reach: 4.8 },
];
// Cost per payment, USD. Polygon/NEAR: measured gas at mainnet prices, flat
// with amount (COMPARISON.md §4). Lightning: measured route length x 1ML fee
// rates (LIGHTNING_ANALYSIS.md §3, amendment 10).
const COST = {
  polygon: { 10: 0.0006, 50: 0.0006, 200: 0.0006, 500: 0.0006 },
  near: { 10: 0.000365, 50: 0.000365, 200: 0.000365, 500: 0.000365 },
  lightning: { 10: 0.0032, 50: 0.0134, 200: 0.0523, 500: 0.1467 },
};
const COST_LIMIT = 0.10;

let DATA = null;

/* ------------------------------------------------------------ helpers */
const $ = (s) => document.querySelector(s);
const fmt = (v, d = 1) => (v == null || !isFinite(v) ? "–" : Number(v).toFixed(d));
const money = (v) => "$" + parseFloat(v.toPrecision(4));
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const svgNS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
// Draw at the container's real width (within limits) so text stays legible on phones.
const fitW = (target, max) => Math.max(340, Math.min(max, Math.round(target.clientWidth || max)));
function svg(w, h) {
  const s = document.createElementNS(svgNS, "svg");
  s.setAttribute("viewBox", `0 0 ${w} ${h}`);
  s.setAttribute("role", "img");
  return s;
}

function cellOf(system, arm, amount, load) {
  const m = DATA.cells.filter((c) => c.system === system && c.arm === arm && c.amount === amount && c.load === load);
  return m.find((c) => c.source === "clean") || m[0] || null;
}
function runsOf(cell) {
  if (!cell) return [];
  return DATA.runs.filter((r) => r.system === cell.system && r.arm === cell.arm && r.amount === cell.amount && r.load === cell.load && r.source === cell.source);
}

/* Notes that must travel with a number wherever it is shown. */
function cellNotes(c) {
  const n = [];
  if (!c) return n;
  if (c.source === "raw-sensitivity")
    n.push(["warn", "<b>Excluded from the clean results by a pre-set rule</b>: our sending program fell slightly behind schedule. All 20 tests at this level agree with each other, so the paper reports them as marked extra data, as here. They are never mixed into the clean results."]);
  if (c.system === "near" && c.arm === "baseline" && c.load >= 200)
    n.push(["hold", "<b>Under re-check.</b> We have not ruled out that part of this collapse is our own program, which checks every waiting payment one by one over the network. NEAR's 150-a-second result is not affected."]);
  if (c.system === "polygon" && c.arm === "baseline" && c.load === 300)
    n.push(["info", "<b>Later found to be partly our setup.</b> Every settlement check went to one computer. With checks spread over four, a follow-up reached 290.5 a second, and kept falling past 300: 202.5 at 400 and 96.5 at 600. That follow-up was exploratory, one test per level."]);
  if (c.arm === "adversarial")
    n.push(["info", c.system === "near"
      ? "<b>Harsher for NEAR than it looks.</b> Switching off 1 of 8 computers left one of NEAR's lanes with a single computer, the minimum allowed, and a failed computer was shut out for about four hours. For Polygon, 3 of 4 computers kept running. Both tests are far harsher than the real networks."
      : "<b>One of Polygon's four computers was switched off and on</b> during each test. This is far harsher than the real network, so it measures sensitivity to an outage, not everyday behaviour."]);
  if (c.repeats < 5)
    n.push(["warn", `<b>${SYS[c.system].name} at ${c.load}/sec, $${c.amount}: only ${c.repeats} of 5 planned tests</b> survived the pre-set cleaning rules.`]);
  return n;
}
function renderNotes(target, notes) {
  target.innerHTML = notes.map(([lvl, html]) => `<div class="note ${lvl}">${html}</div>`).join("");
}

/* ------------------------------------------------------------ tooltip */
const tip = () => $("#tip");
function showTip(evt, html) {
  const t = tip();
  t.innerHTML = html;
  t.hidden = false;
  const pad = 14, r = t.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  t.style.left = Math.max(8, x) + "px";
  t.style.top = Math.max(8, y) + "px";
}
function hideTip() { tip().hidden = true; }
function hover(node, html) {
  node.addEventListener("pointermove", (e) => showTip(e, typeof html === "function" ? html() : html));
  node.addEventListener("pointerleave", hideTip);
}

/* ------------------------------------------------------------ segmented controls */
function seg(container, options, current, onPick) {
  container.innerHTML = "";
  for (const o of options) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = (o.color ? `<span class="sw" style="background:${o.color}"></span>` : "") + o.label;
    b.setAttribute("aria-pressed", String(o.value === current));
    if (o.disabled) { b.disabled = true; b.title = o.why || "Not measured"; }
    b.addEventListener("click", () => onPick(o.value));
    container.appendChild(b);
  }
}

/* ------------------------------------------------------------ line chart over the load ladder */
function loadChart(target, { series, yMax, yTicks, yFmt, ref, unit, maxW = 520, H = 280 }) {
  const W = fitW(target, maxW), m = { l: 46, r: 100, t: 14, b: 40 };
  const s = svg(W, H);
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const x = (load) => m.l + (LOADS.indexOf(load) / (LOADS.length - 1)) * pw;
  const y = (v) => m.t + ph - (Math.min(v, yMax) / yMax) * ph;

  const g = el("g", { class: "grid" }, s);
  for (const t of yTicks) {
    el("line", { x1: m.l, x2: m.l + pw, y1: y(t), y2: y(t) }, g);
    const tx = el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end" }, s);
    tx.textContent = yFmt(t);
  }
  const ax = el("g", { class: "axis" }, s);
  el("line", { x1: m.l, x2: m.l + pw, y1: m.t + ph, y2: m.t + ph }, ax);
  for (const L of LOADS) {
    const tx = el("text", { x: x(L), y: m.t + ph + 18, "text-anchor": "middle" }, s);
    tx.textContent = L;
  }
  const xl = el("text", { x: m.l + pw / 2, y: H - 4, "text-anchor": "middle" }, s);
  xl.textContent = "Payments offered per second";

  if (ref?.type === "diag") {
    el("polyline", { class: "ref", points: LOADS.filter((L) => L <= yMax).map((L) => `${x(L)},${y(L)}`).join(" ") }, s);
  } else if (ref?.type === "h") {
    el("line", { class: "ref", x1: m.l, x2: m.l + pw, y1: y(ref.y), y2: y(ref.y) }, s);
    const t = el("text", { class: "ref-text", x: m.l + pw + 6, y: y(ref.y) + 4 }, s);
    t.textContent = ref.label;
  }

  const labelYs = [];
  for (const sr of series) {
    const pts = sr.points.filter((p) => p.y != null);
    if (!pts.length) continue;
    // Solid line through clean points; dashed into marked extra data.
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i];
      el("line", {
        x1: x(a.x), y1: y(a.y), x2: x(b.x), y2: y(b.y), stroke: sr.color, "stroke-width": 2,
        "stroke-dasharray": b.hollow ? "5 4" : "none", "stroke-linecap": "round",
      }, s);
    }
    for (const p of pts) {
      if (p.lo != null && p.hi != null) {
        el("line", { x1: x(p.x), x2: x(p.x), y1: y(p.lo), y2: y(p.hi), stroke: sr.color, "stroke-width": 1.5, opacity: 0.55 }, s);
        for (const v of [p.lo, p.hi]) el("line", { x1: x(p.x) - 4, x2: x(p.x) + 4, y1: y(v), y2: y(v), stroke: sr.color, "stroke-width": 1.5, opacity: 0.55 }, s);
      }
      el("circle", {
        cx: x(p.x), cy: y(p.y), r: 4.5, fill: p.hollow ? "var(--card)" : sr.color,
        stroke: p.hollow ? sr.color : "var(--card)", "stroke-width": 2,
      }, s);
      const hit = el("circle", { cx: x(p.x), cy: y(p.y), r: 13, fill: "transparent", style: "cursor:default" }, s);
      hover(hit, p.tip);
    }
    const last = pts[pts.length - 1];
    let ly = y(last.y) + 4;
    for (const o of labelYs) if (Math.abs(o - ly) < 16) ly = o + (ly >= o ? 16 : -16);
    labelYs.push(ly);
    const t = el("text", { class: "lbl", x: x(last.x) + 10, y: ly }, s);
    t.textContent = sr.label;
  }
  target.innerHTML = "";
  target.appendChild(s);
  const lg = document.createElement("div");
  lg.className = "legend";
  lg.innerHTML = series.map((sr) => `<span><i style="--c:${sr.color}"></i>${sr.label}</span>`).join("")
    + (series.some((sr) => sr.points.some((p) => p.hollow)) ? `<span><i class="hollow" style="--c:var(--muted)"></i>Marked extra data (excluded by rule)</span>` : "")
    + (ref ? `<span><i style="--c:var(--muted);height:0;border-top:2px dashed var(--muted)"></i>${ref.legend}</span>` : "");
  target.appendChild(lg);
  s.setAttribute("aria-label", `${unit} by offered load for ${series.map((x) => x.label).join(" and ")}`);
}

/* ------------------------------------------------------------ STORY extras */
function renderHero() {
  const p = cellOf("polygon", "baseline", 200, 200), n = cellOf("near", "baseline", 200, 150);
  const kept = DATA.runs.filter((r) => r.source === "clean");
  const payments = kept.reduce((a, r) => a + r.payments, 0);
  $("#hero-tiles").innerHTML = [
    [SYS.polygon, `${p.load}/sec`, `sustained at $200: ${fmt(p.achieved)} settled, ${fmt(p.failure_pct, 1)}% failed`],
    [SYS.near, `${n.load}/sec`, `sustained at $200: ${fmt(n.achieved)} settled, ${fmt(n.failure_pct, 2)}% failed`],
    [SYS.lightning, "17%", "of $100 payments got through on the real network (published study)"],
    [null, `${(payments / 1e6).toFixed(1)} million`, `test payments kept as results, from ${kept.length} five-minute tests`],
  ].map(([s, v, sub]) => `<div class="tile"><div class="k">${s ? `<span class="who"><span class="sw dot" style="--c:${s.color};margin:0"></span>${s.name}</span>` : "Evidence"}</div><div class="v">${v}</div><div class="s">${sub}</div></div>`).join("");
}

function renderMap() {
  const places = [
    { name: "Virginia", role: "US — largest sender", lat: 38.9, lon: -77.4 },
    { name: "London", role: "UK — sender to South Asia", lat: 51.5, lon: -0.1 },
    { name: "Mumbai", role: "India — largest receiver", lat: 19.1, lon: 72.9 },
    { name: "Singapore", role: "South-East Asia route", lat: 1.35, lon: 103.8 },
  ];
  const W = 760, H = 250, lon0 = -105, lon1 = 130, lat0 = -12, lat1 = 64;
  const X = (lon) => 20 + ((lon - lon0) / (lon1 - lon0)) * (W - 40);
  const Y = (lat) => 10 + ((lat1 - lat) / (lat1 - lat0)) * (H - 20);
  const s = svg(W, H);
  s.setAttribute("aria-label", "The four regions: Virginia, London, Mumbai and Singapore, all connected to each other");
  const g = el("g", { class: "grid" }, s);
  for (let lo = -90; lo <= 120; lo += 30) el("line", { x1: X(lo), x2: X(lo), y1: 10, y2: H - 10, stroke: "var(--grid)" }, g);
  for (let la = 0; la <= 60; la += 20) el("line", { x1: 20, x2: W - 20, y1: Y(la), y2: Y(la), stroke: "var(--grid)" }, g);
  for (let i = 0; i < places.length; i++) for (let j = i + 1; j < places.length; j++) {
    const a = places[i], b = places[j];
    const mx = (X(a.lon) + X(b.lon)) / 2, my = Math.min(Y(a.lat), Y(b.lat)) - 30 - Math.abs(X(a.lon) - X(b.lon)) * 0.08;
    el("path", { d: `M${X(a.lon)},${Y(a.lat)} Q${mx},${my} ${X(b.lon)},${Y(b.lat)}`, fill: "none", stroke: "var(--accent)", "stroke-width": 1.5, opacity: 0.45 }, s);
  }
  for (const p of places) {
    el("circle", { cx: X(p.lon), cy: Y(p.lat), r: 7, fill: "var(--accent)", stroke: "var(--card)", "stroke-width": 2 }, s);
    const below = p.name === "Singapore" || p.name === "Mumbai";
    const t = el("text", { x: X(p.lon), y: Y(p.lat) + (below ? 24 : -26), "text-anchor": "middle", style: "fill:var(--text);font-weight:700;font-size:14px" }, s);
    t.textContent = p.name;
    const r = el("text", { x: X(p.lon), y: Y(p.lat) + (below ? 40 : -12), "text-anchor": "middle", style: "font-size:12px" }, s);
    r.textContent = p.role;
  }
  $("#region-map").appendChild(s);
}

function renderFunnel() {
  const kept = DATA.runs.filter((r) => r.source === "clean").length;
  const extra = DATA.runs.filter((r) => r.source !== "clean").length;
  const rows = [
    ["Five-minute tests recorded", 610, ""],
    ["Kept as results", kept, ""],
    ["Shown as marked extra data", extra, "light"],
  ];
  $("#funnel").innerHTML = rows.map(([k, v, cls]) =>
    `<div class="row"><span>${k}</span><div class="bar ${cls}" style="width:${Math.max(6, (v / 610) * 100)}%">${v}</div></div>`).join("")
    + `<p class="muted small" style="margin:6px 0 0">The 610 include pipeline checks, trial runs and tests broken by known faults. Every removal and its reason is listed in <code>gcp-research/data/clean/exclusions.log</code>.</p>`;
}

/* ------------------------------------------------------------ EXPLORER */
const ex = { arm: "baseline", amount: 200 };

function cellTip(c) {
  return () => `<b>${SYS[c.system].name}, ${c.load}/sec offered, $${c.amount}</b>`
    + `Settled ${fmt(c.achieved)}/sec (95% range ${fmt(c.achieved_ci[0])}–${fmt(c.achieved_ci[1])})<br>`
    + `Failed ${fmt(c.failure_pct, 2)}%<br>Typical wait ${fmt(c.p50, 2)} s · 95 in 100 within ${fmt(c.p95, 2)} s<br>`
    + `${c.repeats} test${c.repeats === 1 ? "" : "s"}${c.source === "raw-sensitivity" ? " · <i>excluded by rule, marked extra data</i>" : ""}`;
}

function renderExplorer() {
  seg($("#ex-arm"), Object.entries(ARMS).map(([k, v]) => ({ value: k, label: v.label })), ex.arm, (v) => {
    ex.arm = v; if (v === "adversarial") ex.amount = 200; renderExplorer();
  });
  seg($("#ex-amount"), AMOUNTS.map((a) => ({ value: a, label: `$${a}`, disabled: ex.arm === "adversarial" && a !== 200, why: "The failing-computer tests were only run at $200" })), ex.amount, (v) => { ex.amount = v; renderExplorer(); });
  $("#ex-arm-note").textContent = ex.arm === "adversarial"
    ? "Run at $200 only, at three loads per network: low, near the limit, and above it."
    : "Amount makes almost no difference on Polygon or NEAR. They charge for computing work, and moving $500 is the same work as moving $10.";

  const cells = ["polygon", "near"].map((sysk) => ({
    sysk, cells: LOADS.map((L) => cellOf(sysk, ex.arm, ex.amount, L)).filter(Boolean),
  }));
  const mk = (f) => cells.map(({ sysk, cells }) => ({
    label: SYS[sysk].name, color: SYS[sysk].color,
    points: cells.map((c) => ({ x: c.load, hollow: c.source !== "clean", tip: cellTip(c), ...f(c) })),
  }));
  loadChart($("#ch-achieved"), {
    series: mk((c) => ({ y: c.achieved, lo: c.achieved_ci[0], hi: c.achieved_ci[1] })),
    yMax: 320, yTicks: [0, 100, 200, 300], yFmt: (t) => t, unit: "Payments settled per second",
    ref: { type: "diag", legend: "Every payment settled" },
  });
  loadChart($("#ch-failure"), {
    series: mk((c) => ({ y: c.failure_pct, lo: c.failure_ci[0], hi: c.failure_ci[1] })),
    yMax: 100, yTicks: [0, 25, 50, 75, 100], yFmt: (t) => t + "%", unit: "Share of payments failed",
  });
  loadChart($("#ch-latency"), {
    series: mk((c) => ({ y: c.p95 })),
    yMax: 60, yTicks: [0, 10, 20, 30, 40, 50, 60], yFmt: (t) => t + " s", unit: "Slow-end waiting time",
    ref: { type: "h", y: 10, label: "10 s limit", legend: "10-second limit set in advance" },
    maxW: 960, H: 300,
  });

  const notes = [];
  for (const { cells: cs } of cells) for (const c of cs) for (const n of cellNotes(c)) if (!notes.some((x) => x[1] === n[1])) notes.push(n);
  renderNotes($("#ex-notes"), notes);

  const rows = cells.flatMap(({ cells }) => cells).map((c) =>
    `<tr><td>${SYS[c.system].name}${c.source !== "clean" ? " †" : ""}</td><td>${c.load}</td><td>${c.repeats}</td><td>${fmt(c.achieved)}</td><td>${fmt(c.achieved_ci[0])}–${fmt(c.achieved_ci[1])}</td><td>${fmt(c.failure_pct, 2)}%</td><td>${fmt(c.p50, 2)}</td><td>${fmt(c.p95, 2)}</td><td>${fmt(c.p99, 2)}</td></tr>`).join("");
  $("#ex-table").innerHTML = `<table><thead><tr><th>Network</th><th>Offered /sec</th><th>Tests</th><th>Settled /sec</th><th>95% range</th><th>Failed</th><th>Typical wait (s)</th><th>95 in 100 within (s)</th><th>99 in 100 within (s)</th></tr></thead><tbody>${rows}</tbody></table><p class="muted small">† Excluded from the clean results by a pre-set rule; shown as marked extra data.</p>`;
}

function renderCost() {
  const head = `<tr><th>Amount</th>${["polygon", "near", "lightning"].map((k) => `<th><span class="sw dot" style="--c:${SYS[k].color};margin:0 6px 0 0;vertical-align:0"></span>${SYS[k].name}</th>`).join("")}</tr>`;
  const body = AMOUNTS.map((a) => `<tr><td>$${a}</td>${["polygon", "near", "lightning"].map((k) => {
    const v = COST[k][a], over = v > COST_LIMIT;
    return `<td class="${over ? "over" : ""}">${money(v)}${over ? " ⚠ over limit" : ""}${k === "lightning" && a === 50 ? " *" : ""}</td>`;
  }).join("")}</tr>`).join("");
  $("#cost-table").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>
  <p class="muted small" style="margin-top:8px">Polygon and NEAR cost the same at every amount, because moving more money is not more computing work. Lightning charges a percentage, so its cost grows with the amount. * $50 was never run on Lightning; its cost uses an assumed route length. Lightning's $200 and $500 figures rest on 3 and 2 tests, and it moves bitcoin, not a stablecoin.</p>`;
}

function renderLightning() {
  const W = 520, H = 250, m = { l: 46, r: 12, t: 22, b: 40 };
  const s = svg(W, H);
  s.setAttribute("aria-label", "Lightning payment success rate by payment size, falling from 71.9% at one cent to 17.3% at $100");
  const pw = W - m.l - m.r, ph = H - m.t - m.b, n = LN_SUCCESS.length;
  const bw = Math.min(46, (pw / n) * 0.62);
  const y = (v) => m.t + ph - (v / 100) * ph;
  const g = el("g", { class: "grid" }, s);
  for (const t of [0, 25, 50, 75, 100]) {
    el("line", { x1: m.l, x2: m.l + pw, y1: y(t), y2: y(t) }, g);
    el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end" }, s).textContent = t + "%";
  }
  LN_SUCCESS.forEach((d, i) => {
    const cx = m.l + (i + 0.5) * (pw / n);
    const top = y(d.success), h = m.t + ph - top, r = Math.min(4, h);
    el("path", { d: `M${cx - bw / 2},${m.t + ph} V${top + r} Q${cx - bw / 2},${top} ${cx - bw / 2 + r},${top} H${cx + bw / 2 - r} Q${cx + bw / 2},${top} ${cx + bw / 2},${top + r} V${m.t + ph} Z`, fill: "var(--lightning)" }, s);
    el("text", { x: cx, y: top - 6, "text-anchor": "middle", class: "lbl" }, s).textContent = d.success + "%";
    el("text", { x: cx, y: m.t + ph + 18, "text-anchor": "middle" }, s).textContent = d.size;
    const hit = el("rect", { x: cx - (pw / n) / 2, y: m.t, width: pw / n, height: ph, fill: "transparent" }, s);
    hover(hit, `<b>${d.size} payments</b>${d.success}% got through<br>${d.reach}% of the network reachable at all`);
  });
  el("text", { x: m.l + pw / 2, y: H - 4, "text-anchor": "middle" }, s).textContent = "Payment size";
  $("#ch-lightning").innerHTML = "";
  $("#ch-lightning").appendChild(s);
}

/* ------------------------------------------------------------ REPLAY: sampling */
// Normal approximation to a binomial draw. Every cell has thousands of
// payments per test, where the approximation is far finer than the
// test-to-test differences being shown.
function gauss() {
  let u = 0, v = 0;
  while (!u) u = Math.random();
  while (!v) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
function binom(n, p) {
  if (p <= 0) return 0;
  if (p >= 1) return n;
  return Math.max(0, Math.min(n, Math.round(n * p + Math.sqrt(n * p * (1 - p)) * gauss())));
}
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const okRate = (r) => 1 - r.failure_pct / 100;

// Draw one settlement time from a run's stored distribution (201 points).
function drawLatency(run) {
  const q = run.quantiles;
  if (!q.length) return NaN;
  const pos = Math.random() * (q.length - 1), i = Math.floor(pos), f = pos - i;
  return i + 1 < q.length ? q[i] + (q[i + 1] - q[i]) * f : q[i];
}
function pctl(sorted, p) {
  if (!sorted.length) return NaN;
  const pos = (p / 100) * (sorted.length - 1), i = Math.floor(pos), f = pos - i;
  return i + 1 < sorted.length ? sorted[i] + (sorted[i + 1] - sorted[i]) * f : sorted[i];
}

/* One replayed test. "cluster": pick a recorded test, then draw its payments
 * from inside it. "srs": every payment drawn independently from the pooled
 * payments of all tests in the cell. */
function oneTest(runs, method) {
  if (method === "cluster") {
    const run = pick(runs), n = run.payments, k = binom(n, okRate(run));
    return { n, k, from: run, draw: () => drawLatency(run) };
  }
  const n = Math.round(runs.reduce((a, r) => a + r.payments, 0) / runs.length);
  const okTot = runs.reduce((a, r) => a + r.payments * okRate(r), 0);
  const allTot = runs.reduce((a, r) => a + r.payments, 0);
  const k = binom(n, okTot / allTot);
  // A settled payment comes from a test in proportion to how many it settled.
  const weights = runs.map((r) => r.payments * okRate(r)), wsum = weights.reduce((a, b) => a + b, 0);
  const draw = () => {
    let u = Math.random() * wsum, i = 0;
    while (i < runs.length - 1 && (u -= weights[i]) > 0) i++;
    return drawLatency(runs[i]);
  };
  return { n, k, from: null, draw };
}

/* ------------------------------------------------------------ REPLAY: UI */
const sim = { system: "polygon", arm: "baseline", amount: 200, load: 200, method: "cluster" };

function simCell() { return cellOf(sim.system, sim.arm, sim.amount, sim.load); }

function renderSimControls() {
  seg($("#sim-system"), [
    { value: "polygon", label: SYS.polygon.name, color: SYS.polygon.color },
    { value: "near", label: SYS.near.name, color: SYS.near.color },
    { value: "lightning", label: SYS.lightning.name, color: SYS.lightning.color, disabled: true, why: "Lightning's reliability and capacity come from a published study of the real network, not our tests, so there are no recorded tests to replay." },
  ], sim.system, (v) => { sim.system = v; settle(); });
  seg($("#sim-arm"), Object.entries(ARMS).map(([k, v]) => ({ value: k, label: v.label })), sim.arm, (v) => { sim.arm = v; if (v === "adversarial") sim.amount = 200; settle(); });
  seg($("#sim-amount"), AMOUNTS.map((a) => ({ value: a, label: `$${a}`, disabled: sim.arm === "adversarial" && a !== 200, why: "The failing-computer tests were only run at $200" })), sim.amount, (v) => { sim.amount = v; settle(); });
  seg($("#sim-load"), LOADS.map((L) => {
    const c = cellOf(sim.system, sim.arm, sim.amount, L);
    return { value: L, label: c && c.source !== "clean" ? `${L} †` : String(L), disabled: !c, why: "Not measured. We don't guess between measured levels." };
  }), sim.load, (v) => { sim.load = v; settle(); });
  seg($("#sim-method"), [
    { value: "cluster", label: "Whole runs (cluster)" },
    { value: "srs", label: "Individual payments (simple random)" },
  ], sim.method, (v) => { sim.method = v; renderSimControls(); });
  renderNotes($("#sim-notes"), cellNotes(simCell()));
}
function settle() {
  if (!simCell()) {
    const avail = LOADS.filter((L) => cellOf(sim.system, sim.arm, sim.amount, L));
    sim.load = avail.reduce((b, L) => (Math.abs(L - sim.load) < Math.abs(b - sim.load) ? L : b), avail[0]);
  }
  $("#sim-one").hidden = true;
  $("#sim-many").hidden = true;
  renderSimControls();
}

function tileHTML(k, v, s) { return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`; }

let anim = null;
function replayOne() {
  const c = simCell(), runs = runsOf(c);
  const t = oneTest(runs, sim.method);
  const m = Math.min(t.k, 5000), lat = [];
  for (let i = 0; i < m; i++) lat.push(t.draw());
  lat.sort((a, b) => a - b);
  const achieved = t.k / WINDOW_S, fail = 100 * (1 - t.k / t.n);
  $("#sim-tiles").innerHTML =
    tileHTML("Settled per second", fmt(achieved), `of ${sim.load} offered · paper: ${fmt(c.achieved)}`)
    + tileHTML("Failed", fmt(fail, 2) + "%", `paper: ${fmt(c.failure_pct, 2)}%`)
    + tileHTML("Typical wait", fmt(pctl(lat, 50), 2) + " s", `half of settled payments were faster`)
    + tileHTML("95 in 100 settled within", fmt(pctl(lat, 95), 2) + " s", `the slow end of the wait`);

  let series, sub;
  if (t.from) {
    series = t.from.series;
    sub = `This replay drew its ${t.n.toLocaleString()} payments from inside recorded test <code>${t.from.id}</code> (repeat ${t.from.repeat + 1} of ${runs.length}). The chart shows that test as it happened.`;
  } else {
    const b = runs[0].series, len = Math.max(...runs.map((r) => r.series.settled.length));
    const avg = (key) => Array.from({ length: len }, (_, i) => runs.reduce((a, r) => a + (r.series[key][i] || 0), 0) / runs.length);
    series = { start: b.start, bin: b.bin, settled: avg("settled"), submitted: avg("submitted"), failed: avg("failed") };
    sub = `Each of the ${t.n.toLocaleString()} payments was drawn independently from all ${runs.length} recorded tests pooled together. The chart shows their average, which is smoother than any real test was.`;
  }
  $("#sim-tl-sub").innerHTML = sub;
  $("#sim-one").hidden = false;
  $("#sim-many").hidden = true;
  drawTimeline(series, sim.load);
}

function drawTimeline(series, load) {
  const W = fitW($("#ch-timeline"), 960), H = 280, m = { l: 44, r: 70, t: 16, b: 42 };
  const s = svg(W, H), pw = W - m.l - m.r, ph = H - m.t - m.b;
  const n = series.settled.length, t0 = series.start, t1 = t0 + n * series.bin;
  const perSec = series.settled.map((v) => v / series.bin);
  const yMax = Math.max(load * 1.25, ...perSec) * 1.05;
  const x = (t) => m.l + ((t - t0) / (t1 - t0)) * pw;
  const y = (v) => m.t + ph - (v / yMax) * ph;
  const step = yMax > 200 ? 100 : yMax > 80 ? 50 : yMax > 30 ? 10 : 5;
  const g = el("g", { class: "grid" }, s);
  for (let v = 0; v <= yMax; v += step) {
    el("line", { x1: m.l, x2: m.l + pw, y1: y(v), y2: y(v) }, g);
    el("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end" }, s).textContent = v;
  }
  for (let tt = W < 600 ? 60 : 30; tt <= t1; tt += W < 600 ? 60 : 30) el("text", { x: x(tt), y: m.t + ph + 18, "text-anchor": "middle" }, s).textContent = tt + "s";
  el("text", { x: m.l + pw / 2, y: H - 4, "text-anchor": "middle" }, s).textContent = W < 600 ? "Seconds since the test started" : "Seconds since the test started (sending stops at 300 s; payments can still settle for 60 s after)";
  el("line", { x1: x(300), x2: x(300), y1: m.t, y2: m.t + ph, stroke: "var(--line)", "stroke-width": 1 }, s);
  const bw = Math.max(1, pw / n - 2);
  const bars = perSec.map((v, i) => {
    const r = el("rect", { x: x(t0 + i * series.bin) + 1, y: y(0), width: bw, height: 0, rx: Math.min(2, bw / 2), fill: SYS[sim.system].color }, s);
    const sub = series.submitted[i] / series.bin, fl = series.failed[i] / series.bin;
    const hit = el("rect", { x: x(t0 + i * series.bin), y: m.t, width: pw / n, height: ph, fill: "transparent" }, s);
    const a = t0 + i * series.bin;
    hover(hit, `<b>${a}–${a + series.bin} s</b>${fmt(v)} settled per second<br>${fmt(sub)} sent per second${fl ? `<br>${fmt(fl)} per second of those sent went on to fail` : ""}`);
    return [r, v];
  });
  // Offered-load line drawn after the bars so it stays visible on top of them.
  el("line", { class: "ref", x1: x(t0), x2: x(300), y1: y(load), y2: y(load), style: "pointer-events:none" }, s);
  el("text", { class: "ref-text", x: x(300) + 6, y: y(load) + 4, style: "pointer-events:none" }, s).textContent = `${load}/sec offered`;
  s.setAttribute("aria-label", `Payments settled per second over the test, against ${load} offered per second`);
  $("#ch-timeline").innerHTML = "";
  $("#ch-timeline").appendChild(s);
  const lg = document.createElement("div");
  lg.className = "legend";
  lg.innerHTML = `<span><i style="--c:${SYS[sim.system].color};height:10px;width:10px;border-radius:2px"></i>Settled per second (5-second blocks)</span><span><i style="--c:var(--muted);height:0;border-top:2px dashed var(--muted)"></i>Offered load</span>`;
  $("#ch-timeline").appendChild(lg);

  if (anim) cancelAnimationFrame(anim);
  const setBar = ([r, v], f) => { const h = (y(0) - y(v)) * f; r.setAttribute("y", y(0) - h); r.setAttribute("height", h); };
  if (reduceMotion) { bars.forEach((b) => setBar(b, 1)); return; }
  const dur = 3500, start = performance.now();
  const frame = (now) => {
    const p = Math.min(1, (now - start) / dur), upto = p * bars.length;
    bars.forEach((b, i) => setBar(b, Math.max(0, Math.min(1, upto - i))));
    if (p < 1) anim = requestAnimationFrame(frame);
  };
  anim = requestAnimationFrame(frame);
}

/* 1,000 replays of a five-test study, both methods side by side. */
function replayMany() {
  const c = simCell(), runs = runsOf(c), N = 1000, reps = 5;
  const study = (method) => {
    const ach = [], fail = [];
    for (let i = 0; i < N; i++) {
      let a = 0, f = 0;
      for (let j = 0; j < reps; j++) { const t = oneTest(runs, method); a += t.k / WINDOW_S; f += 100 * (1 - t.k / t.n); }
      ach.push(a / reps); fail.push(f / reps);
    }
    return { ach: ach.sort((x, y) => x - y), fail: fail.sort((x, y) => x - y) };
  };
  const cl = study("cluster"), sr = study("srs");
  drawHist([["Whole runs (cluster)", cl.ach], ["Individual payments (simple random)", sr.ach]], c.achieved_ci);
  const r95 = (a, d = 1) => `${fmt(pctl(a, 2.5), d)}–${fmt(pctl(a, 97.5), d)}`;
  const wClu = pctl(cl.ach, 97.5) - pctl(cl.ach, 2.5), wSrs = pctl(sr.ach, 97.5) - pctl(sr.ach, 2.5);
  const ratio = wSrs > 0 ? wClu / wSrs : Infinity;
  // "Matches" = both ends within 15% of the paper's range width (or 0.3/sec).
  const tol = Math.max(0.15 * (c.achieved_ci[1] - c.achieved_ci[0]), 0.3);
  const agrees = Math.abs(pctl(cl.ach, 2.5) - c.achieved_ci[0]) <= tol && Math.abs(pctl(cl.ach, 97.5) - c.achieved_ci[1]) <= tol;
  $("#sim-many-text").innerHTML =
    `<div class="note"><b>Whole runs:</b> the middle 95% of averages fell between ${r95(cl.ach)} settled per second and ${r95(cl.fail, 2)}% failed. <b>The paper's 95% range is ${fmt(c.achieved_ci[0])}–${fmt(c.achieved_ci[1])}</b> settled per second, ${agrees ? "so the replay reproduces the paper's uncertainty" : "which this replay does not match closely. Press again, as 1,000 replays still carry some chance variation"}.</div>`
    + `<div class="note warn"><b>Individual payments:</b> ${r95(sr.ach)} settled per second and ${r95(sr.fail, 2)}% failed. That range is ${isFinite(ratio) ? `about ${ratio < 10 ? ratio.toFixed(1) : Math.round(ratio)} times` : "far"} narrower. It looks more certain only because it ignores that payments in one test share that test's conditions.</div>`;
  $("#sim-many").hidden = false;
  $("#sim-one").hidden = true;
}

function drawHist(rows, band) {
  const W = fitW($("#ch-hist"), 960), rowH = 120, m = { l: 12, r: 12, t: 10, b: 40 };
  const H = m.t + rows.length * rowH + m.b;
  const s = svg(W, H), pw = W - m.l - m.r;
  const all = rows.flatMap(([, a]) => a).concat(band);
  let lo = Math.min(...all), hi = Math.max(...all);
  const pad = Math.max((hi - lo) * 0.08, 0.5); lo = Math.max(0, lo - pad); hi += pad;
  const x = (v) => m.l + ((v - lo) / (hi - lo)) * pw;
  const nb = 48, bwid = (hi - lo) / nb;
  el("rect", { x: x(band[0]), y: m.t, width: Math.max(2, x(band[1]) - x(band[0])), height: rows.length * rowH, fill: "var(--muted)", opacity: 0.14 }, s);
  rows.forEach(([label, arr], ri) => {
    const counts = new Array(nb).fill(0);
    for (const v of arr) counts[Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / bwid)))]++;
    const cmax = Math.max(...counts), top = m.t + ri * rowH + 20, base = m.t + (ri + 1) * rowH - 8, hh = base - top - 6;
    el("line", { x1: m.l, x2: m.l + pw, y1: base, y2: base, stroke: "var(--line)" }, s);
    const t = el("text", { x: m.l, y: top - 2, class: "lbl" }, s);
    t.textContent = label;
    counts.forEach((cnt, i) => {
      if (!cnt) return;
      const h = (cnt / cmax) * hh, bx = x(lo + i * bwid) + 1, w = Math.max(1.5, pw / nb - 2), r = Math.min(3, h, w / 2);
      el("path", { d: `M${bx},${base} V${base - h + r} Q${bx},${base - h} ${bx + r},${base - h} H${bx + w - r} Q${bx + w},${base - h} ${bx + w},${base - h + r} V${base} Z`, fill: SYS[sim.system].color }, s);
      const hit = el("rect", { x: bx, y: top, width: w, height: hh, fill: "transparent" }, s);
      hover(hit, `<b>${fmt(lo + i * bwid)}–${fmt(lo + (i + 1) * bwid)} settled/sec</b>${cnt} of 1,000 replays`);
    });
  });
  const ticks = W < 600 ? 4 : 6;
  for (let i = 0; i <= ticks; i++) {
    const v = lo + (i / ticks) * (hi - lo);
    el("text", { x: x(v), y: H - 22, "text-anchor": "middle" }, s).textContent = fmt(v, hi - lo < 5 ? 2 : 1);
  }
  el("text", { x: m.l + pw / 2, y: H - 4, "text-anchor": "middle" }, s).textContent = "Average payments settled per second across the five tests";
  s.setAttribute("aria-label", "Histograms of 1,000 replayed study averages for both drawing methods, against the paper's 95% range");
  $("#ch-hist").innerHTML = "";
  $("#ch-hist").appendChild(s);
  const lg = document.createElement("div");
  lg.className = "legend";
  lg.innerHTML = `<span><i style="--c:${SYS[sim.system].color};height:10px;width:10px;border-radius:2px"></i>Replayed study averages</span><span><i style="--c:var(--muted);opacity:.35;height:10px;width:14px;border-radius:2px"></i>Paper's 95% range</span>`;
  $("#ch-hist").appendChild(lg);
}

/* ------------------------------------------------------------ boot */
fetch("data/results.json")
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((d) => {
    DATA = d;
    renderHero(); renderMap(); renderFunnel();
    renderExplorer(); renderCost(); renderLightning();
    renderSimControls();
    $("#btn-one").addEventListener("click", replayOne);
    $("#btn-many").addEventListener("click", replayMany);
    let rt, lastW = innerWidth;
    addEventListener("resize", () => {
      clearTimeout(rt);
      rt = setTimeout(() => { if (innerWidth !== lastW) { lastW = innerWidth; renderExplorer(); } }, 200);
    });
  })
  .catch((e) => {
    document.querySelector("main").insertAdjacentHTML("afterbegin",
      `<div class="wrap"><div class="note hold" style="margin-top:16px"><b>Could not load the results file</b> (${e.message}). Open this page through a web server, not straight from disk. See website/README.md.</div></div>`);
  });
