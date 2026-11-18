const PASS_THRESHOLD = 70;

const PASS_ICON_PATH = "M20 6L9 17l-5-5";
const FAIL_ICON_PATH = "M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z";

function initScoreSimulator() {
  const form = document.getElementById("simulator-form");
  if (!form) return;

  const basic1El = document.getElementById("sim-basic1");
  const basic2El = document.getElementById("sim-basic2");
  const basic3El = document.getElementById("sim-basic3");
  const calcEl = document.getElementById("sim-calc");
  const analysisEl = document.getElementById("sim-analysis");
  const macroEl = document.getElementById("sim-macro");
  const chartEl = document.getElementById("sim-chart");

  const valBasic1 = document.getElementById("val-basic1");
  const valBasic2 = document.getElementById("val-basic2");
  const valBasic3 = document.getElementById("val-basic3");
  const valCalc = document.getElementById("val-calc");
  const valAnalysis = document.getElementById("val-analysis");
  const valMacro = document.getElementById("val-macro");
  const valChart = document.getElementById("val-chart");

  const statusCard = document.getElementById("sim-status-card");
  const totalScoreEl = document.getElementById("sim-total-score");
  const verdictBadgeEl = document.getElementById("sim-verdict-badge");
  const verdictTextEl = document.getElementById("sim-verdict-text");
  const gapTextEl = document.getElementById("sim-gap-text");
  const meterFillEl = document.getElementById("sim-meter-fill");
  const liveRegionEl = document.getElementById("sim-live-region");

  const sumBasicEl = document.getElementById("sum-basic");
  const sumCalcEl = document.getElementById("sum-calc");
  const sumAnalysisEl = document.getElementById("sum-analysis");
  const sumEtcEl = document.getElementById("sum-etc");

  const presetPassBtn = document.getElementById("preset-pass");
  const presetPerfectBtn = document.getElementById("preset-perfect");
  const presetResetBtn = document.getElementById("preset-reset");

  const stepButtons = Array.from(form.querySelectorAll(".step-btn"));
  const rangeInputs = [basic2El, calcEl, analysisEl, macroEl, chartEl].filter(Boolean);

  let announceTimer = null;

  const updateRangeVisuals = (rangeEl) => {
    const min = Number(rangeEl.min || 0);
    const max = Number(rangeEl.max || 100);
    const val = Number(rangeEl.value || 0);
    const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
    rangeEl.style.setProperty("--range-progress", `${pct}%`);
  };

  const syncStepperDisabledStates = () => {
    for (const btn of stepButtons) {
      const targetId = btn.dataset.stepTarget;
      const delta = Number(btn.dataset.stepDelta || 0);
      const target = targetId ? document.getElementById(targetId) : null;
      if (!target) continue;

      const min = Number(target.min || 0);
      const max = Number(target.max || 0);
      const val = Number(target.value || 0);
      btn.disabled = (delta < 0 && val <= min) || (delta > 0 && val >= max);
    }
  };

  const renderVerdictIcon = (isPass) => {
    const svg = verdictBadgeEl?.querySelector("svg");
    const path = svg?.querySelector("path");
    if (path) {
      path.setAttribute("d", isPass ? PASS_ICON_PATH : FAIL_ICON_PATH);
    }
  };

  const announceSummary = (total, isPass, gapMessage) => {
    if (!liveRegionEl) return;
    liveRegionEl.textContent = `예상 총점 ${total}점, ${isPass ? "합격" : "불합격"}. ${gapMessage}.`;
  };

  const recalculate = ({ immediateAnnounce = false } = {}) => {
    const basic1Score = basic1El?.checked ? 5 : 0;
    const basic2Count = Number(basic2El?.value || 0);
    const basic2Score = basic2Count * 2;
    const basic3Score = basic3El?.checked ? 5 : 0;

    const calcCount = Number(calcEl?.value || 0);
    const calcScore = calcCount * 8;

    const analysisCount = Number(analysisEl?.value || 0);
    const analysisScore = analysisCount * 10;

    const macroScore = Number(macroEl?.value || 0);
    const chartCount = Number(chartEl?.value || 0);
    const chartScore = chartCount * 2;

    const basicTotal = basic1Score + basic2Score + basic3Score;
    const etcTotal = macroScore + chartScore;
    const total = basicTotal + calcScore + analysisScore + etcTotal;
    const isPass = total >= PASS_THRESHOLD;

    if (valBasic1) valBasic1.textContent = `${basic1Score} / 5점`;
    if (valBasic2) valBasic2.textContent = `${basic2Count}문제 · ${basic2Score} / 10점`;
    if (valBasic3) valBasic3.textContent = `${basic3Score} / 5점`;
    if (valCalc) valCalc.textContent = `${calcCount}문제 · ${calcScore} / 40점`;
    if (valAnalysis) valAnalysis.textContent = `${analysisCount}문제 · ${analysisScore} / 20점`;
    if (valMacro) valMacro.textContent = `${macroScore} / 10점`;
    if (valChart) valChart.textContent = `${chartCount}문항 · ${chartScore} / 10점`;

    if (sumBasicEl) sumBasicEl.textContent = `${basicTotal} / 20점`;
    if (sumCalcEl) sumCalcEl.textContent = `${calcScore} / 40점`;
    if (sumAnalysisEl) sumAnalysisEl.textContent = `${analysisScore} / 20점`;
    if (sumEtcEl) sumEtcEl.textContent = `${etcTotal} / 20점`;

    if (totalScoreEl) totalScoreEl.textContent = String(total);
    if (statusCard) statusCard.dataset.status = isPass ? "pass" : "fail";
    if (verdictTextEl) verdictTextEl.textContent = isPass ? "합격" : "불합격";
    renderVerdictIcon(isPass);

    let gapMessage = "";
    if (total === PASS_THRESHOLD) {
      gapMessage = "합격 기준(70점)을 정확히 충족했습니다";
    } else if (isPass) {
      gapMessage = `합격 기준(70점)보다 ${total - PASS_THRESHOLD}점 여유`;
    } else {
      gapMessage = `합격까지 ${PASS_THRESHOLD - total}점 부족`;
    }

    if (gapTextEl) gapTextEl.textContent = gapMessage;
    if (meterFillEl) meterFillEl.style.inlineSize = `${Math.min(100, Math.max(0, total))}%`;

    for (const rangeEl of rangeInputs) {
      updateRangeVisuals(rangeEl);
    }
    syncStepperDisabledStates();

    if (announceTimer) {
      window.clearTimeout(announceTimer);
      announceTimer = null;
    }

    if (immediateAnnounce) {
      announceSummary(total, isPass, gapMessage);
    } else {
      announceTimer = window.setTimeout(() => {
        announceSummary(total, isPass, gapMessage);
        announceTimer = null;
      }, 260);
    }
  };

  const applyPreset = (preset) => {
    if (basic1El) basic1El.checked = preset.basic1;
    if (basic2El) basic2El.value = String(preset.basic2);
    if (basic3El) basic3El.checked = preset.basic3;
    if (calcEl) calcEl.value = String(preset.calc);
    if (analysisEl) analysisEl.value = String(preset.analysis);
    if (macroEl) macroEl.value = String(preset.macro);
    if (chartEl) chartEl.value = String(preset.chart);
    recalculate({ immediateAnnounce: true });
  };

  form.addEventListener("input", (event) => {
    const isCheckbox = event.target instanceof HTMLInputElement && event.target.type === "checkbox";
    recalculate({ immediateAnnounce: isCheckbox });
  });

  form.addEventListener("click", (event) => {
    const btn = event.target instanceof Element ? event.target.closest(".step-btn") : null;
    if (!btn) return;

    const targetId = btn.dataset.stepTarget;
    const delta = Number(btn.dataset.stepDelta || 0);
    const input = targetId ? document.getElementById(targetId) : null;
    if (!(input instanceof HTMLInputElement)) return;

    const min = Number(input.min || 0);
    const max = Number(input.max || 100);
    const next = Math.min(max, Math.max(min, Number(input.value || 0) + delta));
    if (next !== Number(input.value)) {
      input.value = String(next);
      recalculate({ immediateAnnounce: true });
    }
  });

  presetPassBtn?.addEventListener("click", () => {
    applyPreset({
      basic1: true,
      basic2: 4,
      basic3: true,
      calc: 3,
      analysis: 1,
      macro: 10,
      chart: 4,
    });
  });

  presetPerfectBtn?.addEventListener("click", () => {
    applyPreset({
      basic1: true,
      basic2: 5,
      basic3: true,
      calc: 5,
      analysis: 2,
      macro: 10,
      chart: 5,
    });
  });

  presetResetBtn?.addEventListener("click", () => {
    applyPreset({
      basic1: false,
      basic2: 0,
      basic3: false,
      calc: 0,
      analysis: 0,
      macro: 0,
      chart: 0,
    });
  });

  recalculate({ immediateAnnounce: false });
}

function initFaqAccordion() {
  const accordion = document.getElementById("faq-accordion");
  const toggleAllBtn = document.getElementById("faq-toggle-all");
  if (!accordion) return;

  const triggers = Array.from(accordion.querySelectorAll(".faq-trigger"));

  const setPanelState = (trigger, expanded) => {
    const panelId = trigger.getAttribute("aria-controls");
    const panel = panelId ? document.getElementById(panelId) : null;
    trigger.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (panel) {
      panel.hidden = expanded ? false : "until-found";
    }
  };

  const syncToggleAllButton = () => {
    if (!toggleAllBtn || triggers.length === 0) return;
    const allExpanded = triggers.every((btn) => btn.getAttribute("aria-expanded") === "true");
    toggleAllBtn.setAttribute("aria-expanded", allExpanded ? "true" : "false");
    toggleAllBtn.textContent = allExpanded ? "모두 접기" : "모두 펼치기";
  };

  accordion.addEventListener("click", (event) => {
    const trigger = event.target instanceof Element ? event.target.closest(".faq-trigger") : null;
    if (!trigger) return;

    const currentlyExpanded = trigger.getAttribute("aria-expanded") === "true";
    setPanelState(trigger, !currentlyExpanded);
    syncToggleAllButton();
  });

  toggleAllBtn?.addEventListener("click", () => {
    const allExpanded = toggleAllBtn.getAttribute("aria-expanded") === "true";
    const nextState = !allExpanded;
    for (const trigger of triggers) {
      setPanelState(trigger, nextState);
    }
    syncToggleAllButton();
  });

  // Sync ARIA state when browser find-in-page reveals hidden="until-found" panels
  document.addEventListener("beforematch", (event) => {
    const panel = event.target instanceof Element ? event.target.closest(".faq-panel") : null;
    if (!panel || !accordion.contains(panel)) return;

    const trigger = accordion.querySelector(`[aria-controls="${CSS.escape(panel.id)}"]`);
    if (trigger) {
      trigger.setAttribute("aria-expanded", "true");
      syncToggleAllButton();
    }
  });

  syncToggleAllButton();
}

document.addEventListener("DOMContentLoaded", () => {
  initScoreSimulator();
  initFaqAccordion();
});
