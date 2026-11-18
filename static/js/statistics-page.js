const SVG_NS = "http://www.w3.org/2000/svg";

const SLICE_PALETTE = [
  "#2563eb",
  "#dc2626",
  "#ea580c",
  "#15803d",
  "#7e22ce",
  "#0e7490",
  "#be185d",
  "#4d7c0f",
  "#991b1b",
  "#1e40af",
  "#6d28d9",
  "#0f766e",
];

const CHART_META = [
  { key: "total", title: "해당 회차의 총점수 비율(명)" },
  { key: "problem1", title: "문제1 비율(명)" },
  { key: "problem2", title: "문제2 비율(명)" },
  { key: "problem3", title: "문제3 비율(명)" },
  { key: "problem4", title: "문제4 비율(명)" },
];

const SCORE_PARAM_KEYS = ["my", "jum0", "jum1", "jum2", "jum3"];
const numberFormat = new Intl.NumberFormat("ko-KR");

function darkenHex(hex, amount = 0.28) {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return "#1e293b";
  const r = Math.max(0, Math.round(parseInt(clean.slice(0, 2), 16) * (1 - amount)));
  const g = Math.max(0, Math.round(parseInt(clean.slice(2, 4), 16) * (1 - amount)));
  const b = Math.max(0, Math.round(parseInt(clean.slice(4, 6), 16) * (1 - amount)));
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

function formatBucketLabel(rawLabel) {
  const label = String(rawLabel ?? "").trim();
  if (!label) return "-";
  if (label.includes("점") || label.includes("미만")) return label;
  return `${label}점`;
}

function getQueryState() {
  const params = new URLSearchParams(window.location.search);
  const examId = (params.get("exam_id") || "sample_01").trim() || "sample_01";
  const scoreParams = {};
  for (const key of SCORE_PARAM_KEYS) {
    const raw = params.get(key);
    if (raw !== null && raw.trim() !== "" && Number.isFinite(Number(raw))) {
      scoreParams[key] = String(Math.trunc(Number(raw)));
    }
  }
  return { examId, scoreParams };
}

function buildStatisticsApiUrl(examId, scoreParams) {
  const query = new URLSearchParams();
  query.set("exam_id", examId);
  for (const key of SCORE_PARAM_KEYS) {
    if (scoreParams[key] !== undefined) {
      query.set(key, scoreParams[key]);
    }
  }
  return `/api/statistics?${query.toString()}`;
}

function updateBrowserUrl(examId, scoreParams) {
  const url = new URL(window.location.href);
  url.searchParams.set("exam_id", examId);
  for (const key of SCORE_PARAM_KEYS) {
    if (scoreParams[key] !== undefined) {
      url.searchParams.set(key, scoreParams[key]);
    }
  }
  window.history.replaceState(null, "", url.toString());
}

function createSvgElement(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function buildSliceArcPath(cx, cy, r, startAngle, endAngle) {
  const x1 = cx + Math.cos(startAngle) * r;
  const y1 = cy + Math.sin(startAngle) * r;
  const x2 = cx + Math.cos(endAngle) * r;
  const y2 = cy + Math.sin(endAngle) * r;
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  return `M ${cx.toFixed(2)} ${cy.toFixed(2)} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
}

function setStatus(message, isError = false) {
  const statusEl = document.getElementById("stats-status");
  if (!statusEl) return;
  if (!message) {
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.classList.remove("is-error");
    return;
  }
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("is-error", isError);
}

function updateKpiStrip(data, scoreParams) {
  const subtitleEl = document.getElementById("stats-exam-subtitle");
  const participantsEl = document.getElementById("kpi-participants");
  const averageEl = document.getElementById("kpi-average");
  const mySummaryEl = document.getElementById("kpi-my-summary");
  const myPill = mySummaryEl?.closest(".kpi-pill--my");

  if (subtitleEl) {
    subtitleEl.textContent = `선택 회차: ${data.exam_title} — 총점 및 문제별 점수 분포와 내 점수 위치를 확인할 수 있습니다.`;
  }
  if (participantsEl) {
    participantsEl.textContent = `${numberFormat.format(data.participant_count ?? 0)}명`;
  }
  if (averageEl) {
    averageEl.textContent = `${Number(data.average_score ?? 0).toFixed(2)}점`;
  }

  const myScores = data.my_scores;
  const hasUrlScore = Object.keys(scoreParams).length > 0;

  if (mySummaryEl && myPill) {
    if (myScores) {
      mySummaryEl.textContent = `총점 ${myScores.total}점 (문제1 ${myScores.problem1} · 문제2 ${myScores.problem2} · 문제3 ${myScores.problem3} · 문제4 ${myScores.problem4})`;
      myPill.classList.add("is-active");
    } else if (hasUrlScore) {
      const parts = [];
      if (scoreParams.my !== undefined) parts.push(`총점 ${scoreParams.my}점`);
      if (scoreParams.jum0 !== undefined) parts.push(`문제1 ${scoreParams.jum0}`);
      if (scoreParams.jum1 !== undefined) parts.push(`문제2 ${scoreParams.jum1}`);
      if (scoreParams.jum2 !== undefined) parts.push(`문제3 ${scoreParams.jum2}`);
      if (scoreParams.jum3 !== undefined) parts.push(`문제4 ${scoreParams.jum3}`);
      mySummaryEl.textContent = parts.join(" · ");
      myPill.classList.add("is-active");
    } else {
      mySummaryEl.textContent = "미지정 (채점 후 연동 시 강조 표시)";
      myPill.classList.remove("is-active");
    }
  }
}

function createAccessibleTable(key, title, buckets, totalCount) {
  const panel = document.createElement("div");
  panel.id = `table-panel-${key}`;
  panel.className = "table-panel is-collapsed";

  const wrapper = document.createElement("div");
  wrapper.className = "table-wrapper";
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-labelledby", `table-caption-${key}`);
  wrapper.setAttribute("tabindex", "-1");

  const table = document.createElement("table");
  table.className = "stats-table";

  const caption = document.createElement("caption");
  caption.id = `table-caption-${key}`;
  caption.textContent = `${title} 상세 분포표 (전체 ${numberFormat.format(totalCount)}명)`;
  table.appendChild(caption);

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const colTitle of ["점수 구간", "응시자 수(명)", "비율(%)", "비고"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = colTitle;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const bucket of buckets) {
    const tr = document.createElement("tr");
    if (bucket.is_my) {
      tr.className = "is-my-row";
    }

    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = formatBucketLabel(bucket.label);
    tr.appendChild(th);

    const tdCount = document.createElement("td");
    tdCount.textContent = `${numberFormat.format(bucket.count)}명`;
    tr.appendChild(tdCount);

    const tdPct = document.createElement("td");
    tdPct.textContent = `${Number(bucket.percent).toFixed(1)}%`;
    tr.appendChild(tdPct);

    const tdNote = document.createElement("td");
    tdNote.textContent = bucket.is_my ? "내 점수" : "-";
    tr.appendChild(tdNote);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  wrapper.appendChild(table);
  panel.appendChild(wrapper);
  return panel;
}

function renderChartCard(key, headingText, series) {
  const container = document.getElementById(`chart-body-${key}`);
  if (!container) return;

  container.replaceChildren();
  const buckets = Array.isArray(series?.buckets) ? series.buckets : [];
  const totalCount = buckets.reduce((acc, b) => acc + (Number(b.count) || 0), 0);

  const figure = document.createElement("figure");
  figure.className = "chart-figure";

  const stage = document.createElement("div");
  stage.className = "pie-stage";

  const tooltip = document.createElement("div");
  tooltip.className = "pie-tooltip";
  tooltip.hidden = true;
  stage.appendChild(tooltip);

  const svg = createSvgElement("svg", {
    class: "pie-svg",
    role: "img",
    viewBox: "0 0 320 260",
    "aria-labelledby": `svg-title-${key}`,
    "aria-describedby": `svg-desc-${key}`,
  });

  const svgTitle = createSvgElement("title", { id: `svg-title-${key}` });
  svgTitle.textContent = headingText;
  svg.appendChild(svgTitle);

  const svgDesc = createSvgElement("desc", { id: `svg-desc-${key}` });
  const myBucket = buckets.find((b) => b.is_my);
  const summaryDesc = myBucket
    ? `전체 ${numberFormat.format(totalCount)}명 중 내 점수 구간은 ${formatBucketLabel(myBucket.label)}(${numberFormat.format(myBucket.count)}명, ${Number(myBucket.percent).toFixed(1)}%)입니다.`
    : `전체 ${numberFormat.format(totalCount)}명의 점수 구간별 분포 차트입니다.`;
  svgDesc.textContent = summaryDesc;
  svg.appendChild(svgDesc);

  const cx = 160;
  const cy = 126;
  const radius = 98;
  const explodeDist = 12;
  const depthOffset = 7;

  const sliceGroupsByIdx = new Map();
  const legendButtonsByIdx = new Map();

  const readout = document.createElement("div");
  readout.className = "chart-active-readout";
  readout.setAttribute("aria-live", "polite");
  const defaultReadoutText = myBucket
    ? `내 점수 구간: ${formatBucketLabel(myBucket.label)} — ${numberFormat.format(myBucket.count)}명 (${Number(myBucket.percent).toFixed(1)}%)`
    : "차트 조각 또는 범례 항목에 마우스를 올리거나 포커스하면 상세 수치를 확인할 수 있습니다.";
  readout.textContent = defaultReadoutText;

  const setActiveBucket = (activeIdx) => {
    for (const [idx, group] of sliceGroupsByIdx.entries()) {
      group.classList.toggle("is-active", idx === activeIdx);
    }
    for (const [idx, btn] of legendButtonsByIdx.entries()) {
      btn.classList.toggle("is-active", idx === activeIdx);
    }

    if (activeIdx === null || !buckets[activeIdx]) {
      tooltip.hidden = true;
      readout.textContent = defaultReadoutText;
      return;
    }

    const bucket = buckets[activeIdx];
    const label = formatBucketLabel(bucket.label);
    const pctText = `${Number(bucket.percent).toFixed(1)}%`;
    const countText = `${numberFormat.format(bucket.count)}명`;
    const myTag = bucket.is_my ? " [내 점수]" : "";
    tooltip.textContent = `${label}${myTag}: ${countText} (${pctText})`;
    tooltip.hidden = false;
    readout.textContent = `선택 구간: ${label}${myTag} — ${countText} (${pctText})`;
  };

  if (totalCount === 0) {
    const emptyCircle = createSvgElement("circle", {
      cx,
      cy,
      r: radius,
      class: "pie-empty-circle",
    });
    const emptyText = createSvgElement("text", {
      x: cx,
      y: cy,
      class: "pie-empty-text",
    });
    emptyText.textContent = "응시 데이터 없음";
    svg.appendChild(emptyCircle);
    svg.appendChild(emptyText);
  } else {
    const rimLayer = createSvgElement("g", { class: "pie-rim-layer" });
    const faceLayer = createSvgElement("g", { class: "pie-face-layer" });
    const myLayer = createSvgElement("g", { class: "pie-my-layer" });

    let currentAngle = -Math.PI / 2;

    buckets.forEach((bucket, idx) => {
      const count = Number(bucket.count) || 0;
      if (count <= 0) return;

      const fraction = count / totalCount;
      const sweep = fraction * Math.PI * 2;
      const startAngle = currentAngle;
      const endAngle = currentAngle + sweep;
      const midAngle = startAngle + sweep / 2;
      currentAngle = endAngle;

      const color = SLICE_PALETTE[idx % SLICE_PALETTE.length];
      const rimColor = darkenHex(color, 0.3);
      const offset = bucket.is_my ? explodeDist : 0;
      const dx = Math.cos(midAngle) * offset;
      const dy = Math.sin(midAngle) * offset;

      const isFullCircle = fraction >= 0.9999;

      const createShape = (fillColor, isRim) => {
        if (isFullCircle) {
          return createSvgElement("circle", {
            cx,
            cy,
            r: radius,
            fill: fillColor,
            class: isRim ? "pie-slice-rim" : "pie-slice-path",
          });
        }
        return createSvgElement("path", {
          d: buildSliceArcPath(cx, cy, radius, startAngle, endAngle),
          fill: fillColor,
          class: isRim ? "pie-slice-rim" : "pie-slice-path",
        });
      };

      const rimShape = createShape(rimColor, true);
      rimShape.setAttribute("transform", `translate(${dx.toFixed(2)}, ${(dy + depthOffset).toFixed(2)})`);

      const faceGroup = createSvgElement("g", {
        class: bucket.is_my ? "pie-slice-group is-my" : "pie-slice-group",
        transform: `translate(${dx.toFixed(2)}, ${dy.toFixed(2)})`,
        "data-bucket-idx": idx,
      });

      faceGroup.appendChild(createShape(color, false));

      if (sweep >= (22 * Math.PI) / 180 || isFullCircle) {
        const labelRadius = isFullCircle ? 0 : radius * 0.64;
        const lx = cx + Math.cos(midAngle) * labelRadius;
        const ly = cy + Math.sin(midAngle) * labelRadius;
        const textEl = createSvgElement("text", {
          x: lx.toFixed(2),
          y: ly.toFixed(2),
          class: "pie-slice-label",
        });
        textEl.textContent = `${Number(bucket.percent).toFixed(1)}%`;
        faceGroup.appendChild(textEl);
      }

      faceGroup.addEventListener("pointerenter", () => setActiveBucket(idx));
      faceGroup.addEventListener("pointerleave", () => setActiveBucket(null));
      faceGroup.addEventListener("click", () => setActiveBucket(idx));

      sliceGroupsByIdx.set(idx, faceGroup);

      if (bucket.is_my) {
        myLayer.appendChild(rimShape);
        myLayer.appendChild(faceGroup);
      } else {
        rimLayer.appendChild(rimShape);
        faceLayer.appendChild(faceGroup);
      }
    });

    svg.appendChild(rimLayer);
    svg.appendChild(faceLayer);
    svg.appendChild(myLayer);
  }

  stage.appendChild(svg);
  figure.appendChild(stage);

  const legend = document.createElement("ul");
  legend.className = "chart-legend";
  legend.setAttribute("aria-label", `${headingText} 범례`);

  buckets.forEach((bucket, idx) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = bucket.is_my ? "legend-btn is-my" : "legend-btn";
    btn.dataset.bucketIdx = String(idx);

    const dot = document.createElement("span");
    dot.className = "legend-dot";
    dot.style.backgroundColor = SLICE_PALETTE[idx % SLICE_PALETTE.length];
    dot.setAttribute("aria-hidden", "true");
    btn.appendChild(dot);

    const labelWrap = document.createElement("span");
    labelWrap.className = "legend-label-wrap";

    const labelText = document.createElement("span");
    labelText.textContent = formatBucketLabel(bucket.label);
    labelWrap.appendChild(labelText);

    if (bucket.is_my) {
      const myBadge = document.createElement("span");
      myBadge.className = "legend-my-tag";
      myBadge.textContent = "[내 점수]";
      labelWrap.appendChild(myBadge);
    }

    btn.appendChild(labelWrap);

    const stats = document.createElement("span");
    stats.className = "legend-stats";
    stats.textContent = `${numberFormat.format(bucket.count)}명 (${Number(bucket.percent).toFixed(1)}%)`;
    btn.appendChild(stats);

    btn.addEventListener("mouseenter", () => setActiveBucket(idx));
    btn.addEventListener("mouseleave", () => setActiveBucket(null));
    btn.addEventListener("focus", () => setActiveBucket(idx));
    btn.addEventListener("blur", () => setActiveBucket(null));
    btn.addEventListener("click", () => setActiveBucket(idx));

    legendButtonsByIdx.set(idx, btn);
    li.appendChild(btn);
    legend.appendChild(li);
  });

  figure.appendChild(legend);
  container.appendChild(figure);
  container.appendChild(readout);

  const tablePanel = createAccessibleTable(key, headingText, buckets, totalCount);
  container.appendChild(tablePanel);

  // Sync toggle button state if user had previously expanded this card's table
  const toggleBtn = document.querySelector(`.table-toggle-btn[data-target="table-panel-${key}"]`);
  if (toggleBtn) {
    const isExpanded = toggleBtn.getAttribute("aria-expanded") === "true";
    tablePanel.classList.toggle("is-collapsed", !isExpanded);
    const wrapper = tablePanel.querySelector(".table-wrapper");
    if (wrapper) {
      wrapper.setAttribute("tabindex", isExpanded ? "0" : "-1");
    }
  }
}

function initTableToggleButtons() {
  const buttons = document.querySelectorAll(".table-toggle-btn");
  for (const btn of buttons) {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.target;
      if (!targetId) return;
      const panel = document.getElementById(targetId);
      if (!panel) return;

      const nextExpanded = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(nextExpanded));
      btn.textContent = nextExpanded ? "데이터 표 숨기기" : "데이터 표 보기";
      panel.classList.toggle("is-collapsed", !nextExpanded);

      const wrapper = panel.querySelector(".table-wrapper");
      if (wrapper) {
        wrapper.setAttribute("tabindex", nextExpanded ? "0" : "-1");
      }
    });
  }
}

async function loadExams(selectedExamId) {
  const selectEl = document.getElementById("stats-exam-select");
  if (!selectEl) return selectedExamId;

  try {
    const response = await fetch("/api/exams", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const exams = Array.isArray(payload.exams) ? payload.exams : [];
    if (exams.length === 0) return selectedExamId;

    selectEl.replaceChildren();
    let hasSelected = false;

    for (const exam of exams) {
      const option = document.createElement("option");
      option.value = exam.exam_id;
      option.textContent = exam.available === false ? `${exam.title} (준비 중)` : exam.title;
      if (exam.exam_id === selectedExamId) {
        option.selected = true;
        hasSelected = true;
      }
      selectEl.appendChild(option);
    }

    if (!hasSelected && exams[0]) {
      selectEl.value = exams[0].exam_id;
      return exams[0].exam_id;
    }
    return selectEl.value || selectedExamId;
  } catch (err) {
    console.warn("회차 목록을 불러오지 못했습니다:", err);
    return selectedExamId;
  }
}

async function loadAndRenderStatistics(examId, scoreParams) {
  setStatus("통계 데이터를 불러오는 중입니다...");
  const apiUrl = buildStatisticsApiUrl(examId, scoreParams);

  try {
    const response = await fetch(apiUrl, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`통계 조회 실패 (HTTP ${response.status})`);
    }
    const data = await response.json();

    updateKpiStrip(data, scoreParams);

    const charts = data.charts || {};
    for (const meta of CHART_META) {
      renderChartCard(meta.key, meta.title, charts[meta.key]);
    }

    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("통계 데이터를 불러오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initTableToggleButtons();

  const state = getQueryState();
  let currentExamId = await loadExams(state.examId);
  await loadAndRenderStatistics(currentExamId, state.scoreParams);

  const selectEl = document.getElementById("stats-exam-select");
  const filterForm = document.getElementById("stats-filter-form");

  const handleExamSwitch = async (nextExamId) => {
    if (!nextExamId) return;
    currentExamId = nextExamId;
    updateBrowserUrl(currentExamId, state.scoreParams);
    await loadAndRenderStatistics(currentExamId, state.scoreParams);
  };

  if (selectEl) {
    selectEl.addEventListener("change", () => {
      handleExamSwitch(selectEl.value);
    });
  }

  if (filterForm) {
    filterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const chosen = selectEl?.value || currentExamId;
      handleExamSwitch(chosen);
    });
  }

  let hasInitialAuthRendered = false;
  document.addEventListener("comlicense:authchange", () => {
    if (!hasInitialAuthRendered) {
      hasInitialAuthRendered = true;
      if (Object.keys(state.scoreParams).length === 0) {
        loadAndRenderStatistics(currentExamId, state.scoreParams);
      }
      return;
    }
    if (Object.keys(state.scoreParams).length === 0) {
      loadAndRenderStatistics(currentExamId, state.scoreParams);
    }
  });
});
