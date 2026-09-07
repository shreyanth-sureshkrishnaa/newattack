/**
 * app.js — Q-ATT&CK Academic Research Workbench Client Engine
 *
 * Includes:
 *  - Start Payload Modal Configuration
 *  - All-Trial Scatter & Running Observable Data Point Plotting
 *  - High-resolution Chart.js graph stage
 *  - Real-time trial telemetry inspector
 *  - Live SSE streaming
 */

// ---------------------------------------------------------------------------
// Global Application State
// ---------------------------------------------------------------------------
const state = {
  totalTrials: 0,
  totalAlerts: 0,
  latestTrials: [],
  config: {},
  sseConnected: false,
};

// ---------------------------------------------------------------------------
// Chart References
// ---------------------------------------------------------------------------
const charts = {
  liveQber: null,
  liveChsh: null,
  angleCorrelator: null,
  correctionDist: null,
  pauliSyndrome: null,
  benchmarkIntensity: null,
  noiseDegradation: null,
};

// ---------------------------------------------------------------------------
// Initialization Entry Point
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  initGraphTabs();
  initModalEvents();
  initAllCharts();
  initSSE();
  fetchInitialConfig();
  fetchBenchmarkData();
  bindEventHandlers();
});

// ---------------------------------------------------------------------------
// Modal Dialog Handling
// ---------------------------------------------------------------------------
function initModalEvents() {
  const modal = document.getElementById("payload-modal");
  const btnOpen = document.getElementById("btn-open-payload-modal");
  const btnClose = document.getElementById("btn-close-modal");
  const btnCancel = document.getElementById("btn-modal-cancel");
  const btnExecute = document.getElementById("btn-modal-execute");
  const btnClean = document.getElementById("btn-modal-inject-clean");

  btnOpen.addEventListener("click", () => {
    modal.style.display = "flex";
  });

  const closeModal = () => {
    modal.style.display = "none";
  };

  btnClose.addEventListener("click", closeModal);
  btnCancel.addEventListener("click", closeModal);

  // Close on outside click
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  btnExecute.addEventListener("click", () => {
    runQuantumBatchFromModal();
    closeModal();
  });

  btnClean.addEventListener("click", () => {
    document.getElementById("modal-attack-type").value = "clean";
    runQuantumBatchFromModal("clean");
    closeModal();
  });

  // Modal slider readouts
  document.getElementById("modal-slider-intensity").addEventListener("input", (e) => {
    document.getElementById("modal-disp-intensity").textContent = parseFloat(e.target.value).toFixed(2);
  });
  document.getElementById("modal-slider-noise").addEventListener("input", (e) => {
    document.getElementById("modal-disp-noise").textContent = parseFloat(e.target.value).toFixed(3);
  });

  // Modal threshold sliders
  ["modal-slider-qber-alpha", "modal-slider-chsh-alpha", "modal-slider-pauli-alpha", "modal-slider-corr-alpha"].forEach((id) => {
    const el = document.getElementById(id);
    const valId = id.replace("slider-", "val-");
    el.addEventListener("input", (e) => {
      document.getElementById(valId).textContent = parseFloat(e.target.value).toFixed(3);
      pushConfigFromServerModal();
    });
  });
}

function pushConfigFromServerModal() {
  const payload = {
    qber_alpha: parseFloat(document.getElementById("modal-slider-qber-alpha").value),
    chsh_alpha: parseFloat(document.getElementById("modal-slider-chsh-alpha").value),
    pauli_alpha: parseFloat(document.getElementById("modal-slider-pauli-alpha").value),
    corr_alpha: parseFloat(document.getElementById("modal-slider-corr-alpha").value),
  };
  fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch((e) => console.error("Config update failed:", e));
}

// ---------------------------------------------------------------------------
// Graph Tab Navigation
// ---------------------------------------------------------------------------
function initGraphTabs() {
  const tabs = document.querySelectorAll(".graph-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".graph-tab-content").forEach((c) => c.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-graph-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }

      setTimeout(() => {
        Object.values(charts).forEach((chart) => {
          if (chart) chart.resize();
        });
      }, 50);
    });
  });
}

// ---------------------------------------------------------------------------
// Chart.js Setups with All-Trial Scatter & Running Observable Curves
// ---------------------------------------------------------------------------
function initAllCharts() {
  const fontMain = { family: "'Inter', sans-serif", size: 11 };
  const fontMono = { family: "'JetBrains Mono', monospace", size: 10 };
  const gridColor = "rgba(226, 232, 240, 0.8)";
  const tickColor = "#64748b";

  // 1. Live QBER with All-Trial Datapoint Scatter Overlay
  const ctxQber = document.getElementById("liveQberChart").getContext("2d");
  charts.liveQber = new Chart(ctxQber, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Cumulative Running QBER",
          data: [],
          borderColor: "#1d4ed8",
          backgroundColor: "rgba(29, 78, 216, 0.04)",
          borderWidth: 2.5,
          pointRadius: 0,
          fill: true,
          tension: 0.1,
          order: 2,
        },
        {
          label: "Individual Trial Decodes (0 = Valid, 1 = Error)",
          data: [],
          type: "scatter",
          borderColor: "rgba(220, 38, 38, 0.7)",
          backgroundColor: function(context) {
            const val = context.raw ? context.raw.y : 0;
            return val === 1 ? "#dc2626" : "#059669";
          },
          pointRadius: 3,
          pointHoverRadius: 5,
          showLine: false,
          order: 1,
        },
        {
          label: "Null Model Baseline (p_null)",
          data: [],
          borderColor: "#64748b",
          borderWidth: 1.5,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          order: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
          title: { display: true, text: "Individual Quantum Trial Index", font: fontMain, color: "#334155" },
        },
        y: {
          min: -0.05,
          max: 1.05,
          grid: { color: gridColor },
          ticks: {
            font: fontMono,
            color: tickColor,
            callback: (v) => (v * 100).toFixed(0) + "%",
          },
          title: { display: true, text: "Observed Error Rate", font: fontMain, color: "#334155" },
        },
      },
      plugins: {
        legend: { labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 2. Live CHSH with All-Trial Correlator Product Scatter Overlay
  const ctxChsh = document.getElementById("liveChshChart").getContext("2d");
  charts.liveChsh = new Chart(ctxChsh, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Running Cumulative CHSH S",
          data: [],
          borderColor: "#7c3aed",
          backgroundColor: "rgba(124, 58, 237, 0.04)",
          borderWidth: 2.5,
          pointRadius: 0,
          fill: true,
          tension: 0.1,
          yAxisID: "y",
          order: 2,
        },
        {
          label: "Single-Trial Bell Pair Outcome (s_A · s_B)",
          data: [],
          type: "scatter",
          borderColor: "#0284c7",
          backgroundColor: function(context) {
            const v = context.raw ? context.raw.y : 1;
            return v > 0 ? "rgba(2, 132, 199, 0.6)" : "rgba(220, 38, 38, 0.6)";
          },
          pointRadius: 3,
          pointHoverRadius: 5,
          showLine: false,
          yAxisID: "yScatter",
          order: 1,
        },
        {
          label: "Tsirelson Bound (2√2 ≈ 2.828)",
          data: [],
          borderColor: "#059669",
          borderWidth: 1.5,
          borderDash: [6, 3],
          pointRadius: 0,
          fill: false,
          yAxisID: "y",
          order: 3,
        },
        {
          label: "Classical Bell Bound (S = 2.0)",
          data: [],
          borderColor: "#dc2626",
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: false,
          yAxisID: "y",
          order: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
          title: { display: true, text: "Individual Quantum Trial Index", font: fontMain, color: "#334155" },
        },
        y: {
          min: 0,
          max: 3.5,
          position: "left",
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
          title: { display: true, text: "CHSH Correlator S", font: fontMain, color: "#334155" },
        },
        yScatter: {
          min: -1.5,
          max: 1.5,
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: {
            font: fontMono,
            color: "#64748b",
            callback: (v) => (v === 1 ? "+1 (Aligned)" : v === -1 ? "-1 (Anti)" : ""),
          },
          title: { display: true, text: "Trial Product (s_A · s_B)", font: fontMain, color: "#64748b" },
        },
      },
      plugins: {
        legend: { labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 3. Angle Correlator E(a,b) Bar Chart
  const ctxAngle = document.getElementById("angleCorrelatorChart").getContext("2d");
  charts.angleCorrelator = new Chart(ctxAngle, {
    type: "bar",
    data: {
      labels: ["E(0°, 22.5°)", "E(0°, 67.5°)", "E(45°, 22.5°)", "E(45°, 67.5°)"],
      datasets: [
        {
          label: "Observed Correlator E",
          data: [0.707, -0.707, 0.707, 0.707],
          backgroundColor: ["#1d4ed8", "#dc2626", "#1d4ed8", "#1d4ed8"],
          borderRadius: 3,
        },
        {
          label: "Theoretical Target (±1/√2)",
          data: [0.7071, -0.7071, 0.7071, 0.7071],
          backgroundColor: "rgba(100, 116, 139, 0.25)",
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: -1.0,
          max: 1.0,
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
        },
        x: {
          grid: { display: false },
          ticks: { font: fontMono, color: "#334155" },
        },
      },
      plugins: {
        legend: { labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 4. Correction Bit Distribution (m0, m1)
  const ctxCorr = document.getElementById("correctionDistChart").getContext("2d");
  charts.correctionDist = new Chart(ctxCorr, {
    type: "bar",
    data: {
      labels: ["Outcome |00⟩", "Outcome |01⟩", "Outcome |10⟩", "Outcome |11⟩"],
      datasets: [
        {
          label: "Observed Relative Frequency",
          data: [0.25, 0.25, 0.25, 0.25],
          backgroundColor: "#0284c7",
          borderRadius: 3,
        },
        {
          label: "Theoretical Null Expectation (p = 0.25)",
          data: [0.25, 0.25, 0.25, 0.25],
          backgroundColor: "rgba(100, 116, 139, 0.2)",
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 0,
          max: 0.6,
          grid: { color: gridColor },
          ticks: {
            font: fontMono,
            color: tickColor,
            callback: (v) => (v * 100).toFixed(0) + "%",
          },
          title: { display: true, text: "Frequency", font: fontMain, color: "#334155" },
        },
        x: {
          grid: { display: false },
          ticks: { font: fontMono, color: "#334155" },
        },
      },
      plugins: {
        legend: { labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 5. Pauli Error Syndrome Breakdown
  const ctxPauli = document.getElementById("pauliSyndromeChart").getContext("2d");
  charts.pauliSyndrome = new Chart(ctxPauli, {
    type: "doughnut",
    data: {
      labels: ["Identity (I)", "Bit-Flip (X)", "Bit+Phase (Y)", "Phase-Only (Z)"],
      datasets: [
        {
          data: [95, 2, 1, 2],
          backgroundColor: ["#059669", "#dc2626", "#d97706", "#7c3aed"],
          borderWidth: 2,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right", labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 6. Benchmark Intensity Sweep Chart
  const ctxBench = document.getElementById("benchmarkIntensityChart").getContext("2d");
  charts.benchmarkIntensity = new Chart(ctxBench, {
    type: "line",
    data: {
      labels: [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
      datasets: [],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
          title: { display: true, text: "Attack Injection Intensity (η)", font: fontMain, color: "#334155" },
        },
        y: {
          min: 0,
          max: 1.05,
          grid: { color: gridColor },
          ticks: {
            font: fontMono,
            color: tickColor,
            callback: (v) => (v * 100).toFixed(0) + "%",
          },
          title: { display: true, text: "Detection Probability P_D", font: fontMain, color: "#334155" },
        },
      },
      plugins: {
        legend: { position: "top", labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });

  // 7. Noise Degradation Chart
  const ctxNoise = document.getElementById("noiseDegradationChart").getContext("2d");
  const noiseVals = [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15];
  charts.noiseDegradation = new Chart(ctxNoise, {
    type: "line",
    data: {
      labels: noiseVals.map((p) => p.toFixed(2)),
      datasets: [
        {
          label: "Analytical QBER: Q(p) = 2p/3",
          data: noiseVals.map((p) => (2 * p) / 3),
          borderColor: "#dc2626",
          borderWidth: 2,
          pointRadius: 3,
          fill: false,
        },
        {
          label: "Theoretical CHSH: S(p) = 2√2(1 - 4p/3)",
          data: noiseVals.map((p) => Math.max(0, 2.8284 * (1 - (4 * p) / 3))),
          borderColor: "#1d4ed8",
          borderWidth: 2,
          pointRadius: 3,
          fill: false,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { font: fontMono, color: tickColor },
          title: { display: true, text: "Depolarizing Parameter (p)", font: fontMain, color: "#334155" },
        },
        y: {
          min: 0,
          max: 0.25,
          position: "left",
          grid: { color: gridColor },
          ticks: {
            font: fontMono,
            color: "#dc2626",
            callback: (v) => (v * 100).toFixed(1) + "%",
          },
          title: { display: true, text: "QBER", font: fontMain, color: "#dc2626" },
        },
        y1: {
          min: 0,
          max: 3.0,
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { font: fontMono, color: "#1d4ed8" },
          title: { display: true, text: "CHSH S", font: fontMain, color: "#1d4ed8" },
        },
      },
      plugins: {
        legend: { labels: { font: fontMain, color: "#0f172a" } },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Server-Sent Events (SSE) Stream
// ---------------------------------------------------------------------------
function initSSE() {
  let evtSource = null;
  try {
    evtSource = new EventSource("/api/stream");
  } catch (e) {
    return;
  }

  evtSource.onopen = () => {
    state.sseConnected = true;
  };

  evtSource.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "batch") {
        renderBatchData(msg.data);
      } else if (msg.type === "config_update") {
        updateConfigSliders(msg.data);
      }
    } catch (err) {
      console.warn("SSE parse error:", err);
    }
  };

  evtSource.onerror = () => {
    state.sseConnected = false;
  };
}

// ---------------------------------------------------------------------------
// Process & Render Batch Telemetry with Individual Datapoints
// ---------------------------------------------------------------------------
// Global animation reference
let activeTrialAnimationTimer = null;

// ---------------------------------------------------------------------------
// Process & Render Batch Telemetry with Sequential Calculation Animation
// ---------------------------------------------------------------------------
function renderBatchData(data) {
  const summ = data.batch_summary;
  const alerts = data.alerts || [];
  const trials = data.trials || [];

  state.latestTrials = trials;

  // Update static summary captions
  const runTag = document.getElementById("last-run-tag");
  runTag.textContent = `${summ.attack_type} (η = ${summ.intensity.toFixed(2)})`;
  document.getElementById("metric-qber-caption").textContent = `H₀ Null Baseline: ${(summ.qber_null * 100).toFixed(2)}% | Noise: ${(summ.noise_level * 100).toFixed(1)}%`;
  document.getElementById("metric-chsh-caption").textContent = `Samples: ${summ.chsh_samples} | Theory: 2.828 | Bell Bound: 2.000`;
  document.getElementById("metric-verify-caption").textContent = `Accepted: ${summ.n_trials - summ.n_errors} / ${summ.n_trials} trials`;
  document.getElementById("metric-alert-count").textContent = alerts.length;

  // Animate trial results calculation point-by-point onto graphs
  plotIndividualTrialDatapointsAnimated(trials, summ, alerts);
}

function plotIndividualTrialDatapointsAnimated(trials, summ, alerts) {
  if (!trials || trials.length === 0) return;

  // Cancel any existing running trial animation
  if (activeTrialAnimationTimer !== null) {
    clearInterval(activeTrialAnimationTimer);
    activeTrialAnimationTimer = null;
  }

  // Clear live charts for the new incoming batch
  charts.liveQber.data.labels = [];
  charts.liveQber.data.datasets[0].data = [];
  charts.liveQber.data.datasets[1].data = [];
  charts.liveQber.data.datasets[2].data = [];
  charts.liveQber.update('none');

  charts.liveChsh.data.labels = [];
  charts.liveChsh.data.datasets[0].data = [];
  charts.liveChsh.data.datasets[1].data = [];
  charts.liveChsh.data.datasets[2].data = [];
  charts.liveChsh.data.datasets[3].data = [];
  charts.liveChsh.update('none');

  const baseGlobalTrials = state.totalTrials;
  const baseGlobalAlerts = state.totalAlerts;

  const totalN = trials.length;
  // Calculate pace: target ~4 seconds total for full batch streaming (clamped 12ms to 40ms)
  const stepDelayMs = Math.max(12, Math.min(40, Math.round(4000 / totalN)));

  const labels = [];
  const runningQber = [];
  const trialScatterQber = [];
  const qberNullLine = [];

  const runningChsh = [];
  const trialScatterChsh = [];
  const tsirelsonLine = [];
  const classicalLine = [];

  let cumErrors = 0;
  const anglePairs = {
    "0,22.5": { sum: 0, count: 0 },
    "0,67.5": { sum: 0, count: 0 },
    "45,22.5": { sum: 0, count: 0 },
    "45,67.5": { sum: 0, count: 0 },
  };

  let currentIndex = 0;

  function renderStep() {
    if (currentIndex >= totalN) {
      clearInterval(activeTrialAnimationTimer);
      activeTrialAnimationTimer = null;

      // Finalize global totals
      state.totalTrials = baseGlobalTrials + totalN;
      state.totalAlerts = baseGlobalAlerts + alerts.length;
      document.getElementById("global-trial-count").textContent = state.totalTrials.toLocaleString();
      document.getElementById("global-alert-count").textContent = state.totalAlerts.toLocaleString();

      // Finalize metrics with exact summary values
      document.getElementById("metric-qber").textContent = `${(summ.qber * 100).toFixed(2)}%`;
      document.getElementById("metric-chsh").textContent = summ.chsh_S.toFixed(3);
      document.getElementById("metric-verify-rate").textContent = `${((1 - summ.qber) * 100).toFixed(1)}%`;

      // Render alerts and raw table
      if (alerts.length > 0) {
        prependAlertCards(alerts);
      }
      renderRawTrialsTable(trials);
      return;
    }

    const t = trials[currentIndex];
    const trialIdx = currentIndex + 1;
    labels.push(`#${trialIdx}`);

    // QBER calculation point
    if (t.is_error) cumErrors++;
    const currentQber = cumErrors / trialIdx;
    runningQber.push(currentQber);
    trialScatterQber.push({ x: trialIdx, y: t.is_error ? 1 : 0 });
    qberNullLine.push(summ.qber_null);

    // CHSH calculation point
    const prod = t.chsh_a_sign * t.chsh_b_sign;
    trialScatterChsh.push({ x: trialIdx, y: prod });

    const aDeg = Math.round((t.chsh_a_angle * 180) / Math.PI);
    const bDeg = (Math.round(((t.chsh_b_angle * 180) / Math.PI) * 10) / 10).toFixed(1);
    const angleKey = `${aDeg},${bDeg}`;

    if (anglePairs[angleKey]) {
      anglePairs[angleKey].sum += prod;
      anglePairs[angleKey].count++;
    }

    const e11 = anglePairs["0,22.5"].count > 0 ? anglePairs["0,22.5"].sum / anglePairs["0,22.5"].count : 0.707;
    const e12 = anglePairs["0,67.5"].count > 0 ? anglePairs["0,67.5"].sum / anglePairs["0,67.5"].count : -0.707;
    const e21 = anglePairs["45,22.5"].count > 0 ? anglePairs["45,22.5"].sum / anglePairs["45,22.5"].count : 0.707;
    const e22 = anglePairs["45,67.5"].count > 0 ? anglePairs["45,67.5"].sum / anglePairs["45,67.5"].count : 0.707;
    const currentS = Math.abs(e11 - e12 + e21 + e22);
    runningChsh.push(currentS);

    tsirelsonLine.push(2.8284);
    classicalLine.push(2.0);

    // Update QBER Chart dynamically
    charts.liveQber.data.labels = labels;
    charts.liveQber.data.datasets[0].data = runningQber;
    charts.liveQber.data.datasets[1].data = trialScatterQber;
    charts.liveQber.data.datasets[2].data = qberNullLine;
    charts.liveQber.update('none');

    // Update CHSH Chart dynamically
    charts.liveChsh.data.labels = labels;
    charts.liveChsh.data.datasets[0].data = runningChsh;
    charts.liveChsh.data.datasets[1].data = trialScatterChsh;
    charts.liveChsh.data.datasets[2].data = tsirelsonLine;
    charts.liveChsh.data.datasets[3].data = classicalLine;
    charts.liveChsh.update('none');

    // Update live global trial counter readout
    document.getElementById("global-trial-count").textContent = (baseGlobalTrials + trialIdx).toLocaleString();

    // Update KPI card values live as calculations stream in
    document.getElementById("metric-qber").textContent = `${(currentQber * 100).toFixed(2)}%`;
    document.getElementById("metric-chsh").textContent = currentS.toFixed(3);
    document.getElementById("metric-verify-rate").textContent = `${((1 - currentQber) * 100).toFixed(1)}%`;

    // Update physical distribution charts progressively
    if (trialIdx % 2 === 0 || trialIdx === totalN) {
      updatePhysicalDistributions(trials.slice(0, trialIdx));
    }

    currentIndex++;
  }

  // Start sequential calculation display loop
  renderStep();
  activeTrialAnimationTimer = setInterval(renderStep, stepDelayMs);
}

function updatePhysicalDistributions(trials) {
  if (!trials || trials.length === 0) return;

  const corrCounts = { "00": 0, "01": 0, "10": 0, "11": 0 };
  let pauliCounts = { I: 0, X: 0, Y: 0, Z: 0 };

  const anglePairs = {
    "0,22.5": { sum: 0, count: 0 },
    "0,67.5": { sum: 0, count: 0 },
    "45,22.5": { sum: 0, count: 0 },
    "45,67.5": { sum: 0, count: 0 },
  };

  trials.forEach((t) => {
    const key = `${t.m0}${t.m1}`;
    if (corrCounts[key] !== undefined) corrCounts[key]++;

    const p = t.pauli || "I";
    if (pauliCounts[p] !== undefined) pauliCounts[p]++;
    else pauliCounts["I"]++;

    const aDeg = Math.round((t.chsh_a_angle * 180) / Math.PI);
    const bDeg = (Math.round(((t.chsh_b_angle * 180) / Math.PI) * 10) / 10).toFixed(1);
    const angleKey = `${aDeg},${bDeg}`;
    if (anglePairs[angleKey]) {
      anglePairs[angleKey].sum += t.chsh_a_sign * t.chsh_b_sign;
      anglePairs[angleKey].count++;
    }
  });

  // Update Correction Chart
  const n = trials.length;
  charts.correctionDist.data.datasets[0].data = [
    corrCounts["00"] / n,
    corrCounts["01"] / n,
    corrCounts["10"] / n,
    corrCounts["11"] / n,
  ];
  charts.correctionDist.update();

  // Update Pauli Chart
  charts.pauliSyndrome.data.datasets[0].data = [
    pauliCounts.I,
    pauliCounts.X,
    pauliCounts.Y,
    pauliCounts.Z,
  ];
  charts.pauliSyndrome.update();

  // Update Angle Correlators Chart
  const e11 = anglePairs["0,22.5"].count > 0 ? anglePairs["0,22.5"].sum / anglePairs["0,22.5"].count : 0.707;
  const e12 = anglePairs["0,67.5"].count > 0 ? anglePairs["0,67.5"].sum / anglePairs["0,67.5"].count : -0.707;
  const e21 = anglePairs["45,22.5"].count > 0 ? anglePairs["45,22.5"].sum / anglePairs["45,22.5"].count : 0.707;
  const e22 = anglePairs["45,67.5"].count > 0 ? anglePairs["45,67.5"].sum / anglePairs["45,67.5"].count : 0.707;

  charts.angleCorrelator.data.datasets[0].data = [e11, e12, e21, e22];
  charts.angleCorrelator.update();
}

function prependAlertCards(alerts) {
  const container = document.getElementById("live-alert-container");
  const empty = container.querySelector(".empty-log-state");
  if (empty) empty.remove();

  alerts.forEach((a) => {
    const entry = document.createElement("div");
    entry.className = `log-entry severity-${a.severity}`;

    const timeStr = new Date(a.ts * 1000).toLocaleTimeString();
    entry.innerHTML = `
      <span class="log-entry-msg"><strong>[${escapeHtml(a.detector)}]</strong> ${escapeHtml(a.message)}</span>
      <span class="log-entry-meta">${timeStr} &bull; Trial #${a.trial_batch_end}</span>
    `;

    container.insertBefore(entry, container.firstChild);
  });

  while (container.children.length > 30) {
    container.removeChild(container.lastChild);
  }
}

function renderRawTrialsTable(trials) {
  const tbody = document.getElementById("raw-trials-tbody");
  const filter = document.getElementById("filter-error-only").value;

  tbody.innerHTML = "";
  if (!trials || trials.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center">No trials recorded.</td></tr>`;
    return;
  }

  const filtered = trials.filter((t) => {
    if (filter === "errors") return t.is_error;
    if (filter === "valid") return !t.is_error;
    return true;
  });

  const displayList = filtered.slice(0, 100);
  displayList.forEach((t) => {
    const tr = document.createElement("tr");
    const statusSpan = t.is_error
      ? `<span class="status-error">Error</span>`
      : `<span class="status-valid">Valid</span>`;

    const aDeg = `${Math.round((t.chsh_a_angle * 180) / Math.PI)}°`;
    const bDeg = `${((t.chsh_b_angle * 180) / Math.PI).toFixed(1)}°`;

    tr.innerHTML = `
      <td><code>#${t.id}</code></td>
      <td><strong>${t.message_bit !== undefined ? t.message_bit : (t.is_error ? 1 : 0)}</strong></td>
      <td>${t.received_bit !== undefined ? t.received_bit : (t.is_error ? 0 : 0)}</td>
      <td>${statusSpan}</td>
      <td><code>(${t.qotp_key_a || 0}, ${t.qotp_key_b || 0})</code></td>
      <td><code>(${t.m0}, ${t.m1})</code></td>
      <td>${aDeg}, ${bDeg}</td>
      <td>${t.chsh_a_sign > 0 ? "+1" : "-1"}, ${t.chsh_b_sign > 0 ? "+1" : "-1"}</td>
      <td><code>${t.pauli}</code></td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// REST API Execution Calls
// ---------------------------------------------------------------------------
async function runQuantumBatchFromModal(attackOverride = null) {
  const attackType = attackOverride || document.getElementById("modal-attack-type").value;
  const nTrials = parseInt(document.getElementById("modal-n-trials").value, 10) || 250;
  const intensity = parseFloat(document.getElementById("modal-slider-intensity").value) || 0.5;
  const noiseLevel = parseFloat(document.getElementById("modal-slider-noise").value) || 0.02;

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        n_trials: nTrials,
        attack_type: attackType,
        intensity: intensity,
        noise_level: noiseLevel,
      }),
    });
    const data = await res.json();
    if (!state.sseConnected) {
      renderBatchData(data);
    }
  } catch (err) {
    console.error("Simulation run error:", err);
  }
}

async function fetchInitialConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    state.config = data;
    updateConfigSliders(data);
  } catch (e) {
    console.error("Config fetch error:", e);
  }
}

function updateConfigSliders(cfg) {
  if (cfg.qber_alpha !== undefined) {
    document.getElementById("modal-slider-qber-alpha").value = cfg.qber_alpha;
    document.getElementById("modal-val-qber-alpha").textContent = Number(cfg.qber_alpha).toFixed(3);
  }
  if (cfg.chsh_alpha !== undefined) {
    document.getElementById("modal-slider-chsh-alpha").value = cfg.chsh_alpha;
    document.getElementById("modal-val-chsh-alpha").textContent = Number(cfg.chsh_alpha).toFixed(3);
  }
  if (cfg.pauli_alpha !== undefined) {
    document.getElementById("modal-slider-pauli-alpha").value = cfg.pauli_alpha;
    document.getElementById("modal-val-pauli-alpha").textContent = Number(cfg.pauli_alpha).toFixed(3);
  }
  if (cfg.corr_alpha !== undefined) {
    document.getElementById("modal-slider-corr-alpha").value = cfg.corr_alpha;
    document.getElementById("modal-val-corr-alpha").textContent = Number(cfg.corr_alpha).toFixed(3);
  }
}

async function fetchBenchmarkData() {
  try {
    const res = await fetch("/api/benchmark");
    if (!res.ok) return;
    const data = await res.json();
    renderBenchmarkCurves(data);
  } catch (err) {
    console.error("Benchmark load error:", err);
  }
}

function renderBenchmarkCurves(bench) {
  if (!bench || !bench.sweep) return;

  const attacks = ["IR", "EH", "PF", "CBM"];
  const colors = {
    IR: "#1d4ed8",
    EH: "#7c3aed",
    PF: "#dc2626",
    CBM: "#d97706",
  };

  const targetNoise = 0.02;
  const datasets = attacks.map((att) => {
    const filtered = bench.sweep
      .filter((cell) => cell.attack === att && Math.abs(cell.noise - targetNoise) < 1e-4)
      .sort((a, b) => a.intensity - b.intensity);

    return {
      label: `${att} Attack (Noise p = ${targetNoise})`,
      data: filtered.map((c) => c.detection_rate),
      borderColor: colors[att] || "#1d4ed8",
      backgroundColor: colors[att] || "#1d4ed8",
      borderWidth: 2,
      pointRadius: 4,
      fill: false,
      tension: 0.1,
    };
  });

  charts.benchmarkIntensity.data.datasets = datasets;
  charts.benchmarkIntensity.update();
}

// ---------------------------------------------------------------------------
// Event Handlers
// ---------------------------------------------------------------------------
function bindEventHandlers() {
  document.getElementById("btn-quick-run").addEventListener("click", () => {
    runQuantumBatchFromModal();
  });

  document.getElementById("btn-refresh-benchmark").addEventListener("click", () => {
    fetchBenchmarkData();
  });

  document.getElementById("filter-error-only").addEventListener("change", () => {
    renderRawTrialsTable(state.latestTrials);
  });
}

function escapeHtml(str) {
  if (typeof str !== "string") return str;
  return str.replace(/[&<>"']/g, (m) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[m]));
}
