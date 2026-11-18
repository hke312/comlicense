function createEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

function attachLightDismissFallback(dialog) {
  if ("closedBy" in HTMLDialogElement.prototype) return;
  const isOutside = (e) => {
    const r = dialog.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  let pressedOutside = false;
  dialog.addEventListener("pointerdown", (e) => {
    pressedOutside = isOutside(e);
  });
  dialog.addEventListener("pointerup", (e) => {
    if (pressedOutside && isOutside(e)) {
      dialog.close("backdrop");
    }
    pressedOutside = false;
  });
}

function setStatus(message, isError = false) {
  const el = document.getElementById("history-status");
  if (!el) return;
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("is-error");
    return;
  }
  el.hidden = false;
  el.textContent = message;
  el.classList.toggle("is-error", isError);
}

function updateKpi(summary) {
  const attemptsEl = document.getElementById("kpi-attempts");
  const passRateEl = document.getElementById("kpi-pass-rate");
  const bestEl = document.getElementById("kpi-best-score");
  const avgEl = document.getElementById("kpi-avg-score");

  if (!summary) {
    if (attemptsEl) attemptsEl.textContent = "-";
    if (passRateEl) passRateEl.textContent = "-";
    if (bestEl) bestEl.textContent = "-";
    if (avgEl) avgEl.textContent = "-";
    return;
  }

  if (attemptsEl) attemptsEl.textContent = `${summary.total_attempts}회`;
  if (passRateEl) passRateEl.textContent = `${summary.pass_count}회 (${Number(summary.pass_rate).toFixed(1)}%)`;
  if (bestEl) bestEl.textContent = `${summary.best_score}점`;
  if (avgEl) avgEl.textContent = `${Number(summary.average_score).toFixed(1)}점`;
}

function openDeductionDialog(item) {
  const dialog = document.getElementById("deduction-detail-dialog");
  const title = document.getElementById("deduction-dialog-title");
  const body = document.getElementById("deduction-dialog-body");
  if (!dialog || !title || !body) return;

  title.textContent = `${item.exam_title || item.exam_id} — 총점 ${item.scores.total}점 (${item.passed ? "합격" : "불합격"})`;
  body.replaceChildren();

  body.append(
    createEl(
      "p",
      "page-subtitle",
      `채점일시: ${item.created_at} · 기본 ${item.scores.problem1}/20 · 계산 ${item.scores.problem2}/40 · 분석 ${item.scores.problem3}/20 · 기타 ${item.scores.problem4}/20`
    )
  );

  const deductions = Array.isArray(item.deductions) ? item.deductions : [];
  if (deductions.length === 0) {
    body.append(createEl("p", null, "감점 내역이 없습니다! 모든 작업을 정확하게 수행했습니다."));
  } else {
    const list = createEl("ul", "detail-list");
    for (const d of deductions) {
      const li = createEl("li", "detail-item");
      const head = createEl("div", "detail-item-head");
      head.append(
        createEl("span", "detail-item-title", `[문제${d.problem_no}] ${d.task_name}`),
        createEl("span", "detail-item-pts", d.deduction > 0 ? `-${d.deduction}점` : "0점")
      );
      li.append(head, createEl("p", "detail-item-desc", d.detail));
      list.append(li);
    }
    body.append(list);
  }

  dialog.showModal();
}

function renderSubmissionsTable(submissions) {
  const tbody = document.getElementById("history-tbody");
  const countBadge = document.getElementById("history-count-badge");
  if (!tbody) return;

  tbody.replaceChildren();
  if (countBadge) countBadge.textContent = `${submissions.length}건`;

  if (!submissions || submissions.length === 0) {
    const tr = createEl("tr", "empty-row");
    const td = createEl("td", null, "아직 기록된 채점 이력이 없습니다. 홈 화면에서 답안을 채점해 보세요.");
    td.colSpan = 8;
    tr.append(td);
    tbody.append(tr);
    return;
  }

  for (const item of submissions) {
    const tr = document.createElement("tr");

    const th = createEl("th", null, item.created_at);
    th.scope = "row";

    const examTd = createEl("td", null, item.exam_title || item.exam_id);

    const totalTd = createEl("td", null, `${item.scores.total}점`);
    const pill = createEl(
      "span",
      item.passed ? "verdict-pill is-pass" : "verdict-pill is-fail",
      item.passed ? "합격" : "불합격"
    );
    totalTd.append(pill);

    const p1Td = createEl("td", null, `${item.scores.problem1}`);
    const p2Td = createEl("td", null, `${item.scores.problem2}`);
    const p3Td = createEl("td", null, `${item.scores.problem3}`);
    const p4Td = createEl("td", null, `${item.scores.problem4}`);

    const actionTd = document.createElement("td");
    const btn = createEl("button", "btn btn-secondary btn-detail", `감점 (${item.deductions?.length || 0})`);
    btn.type = "button";
    btn.addEventListener("click", () => openDeductionDialog(item));
    actionTd.append(btn);

    tr.append(th, examTd, totalTd, p1Td, p2Td, p3Td, p4Td, actionTd);
    tbody.append(tr);
  }
}

async function loadExamsFilter() {
  const select = document.getElementById("history-exam-select");
  if (!select) return;
  try {
    const res = await fetch("/api/exams", { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    const exams = Array.isArray(data.exams) ? data.exams : [];
    for (const exam of exams) {
      const opt = document.createElement("option");
      opt.value = exam.exam_id;
      opt.textContent = exam.title;
      select.append(opt);
    }
  } catch {
    // Keep default all-exams option
  }
}

async function loadMySubmissions() {
  const select = document.getElementById("history-exam-select");
  const examId = select ? select.value.trim() : "";
  const query = examId ? `?exam_id=${encodeURIComponent(examId)}` : "";

  setStatus("채점 이력을 불러오는 중입니다...");
  try {
    const res = await fetch(`/api/my/submissions${query}`, {
      headers: { Accept: "application/json" },
    });
    if (res.status === 401) {
      renderLoggedOutView();
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `이력 조회 실패 (HTTP ${res.status})`);
    }
    updateKpi(data.summary);
    renderSubmissionsTable(data.submissions || []);
    setStatus("");
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "이력을 불러오지 못했습니다.", true);
  }
}

function renderLoggedOutView() {
  const gate = document.getElementById("history-guest-gate");
  const records = document.getElementById("history-records-section");
  const subtitle = document.getElementById("history-subtitle");
  if (gate) gate.hidden = false;
  if (records) records.hidden = true;
  if (subtitle) {
    subtitle.textContent = "로그인한 학생 계정으로 제출한 회차별 점수 추이와 감점 내역을 확인할 수 있습니다.";
  }
  updateKpi(null);
}

function renderLoggedInView(student) {
  const gate = document.getElementById("history-guest-gate");
  const records = document.getElementById("history-records-section");
  const subtitle = document.getElementById("history-subtitle");
  if (gate) gate.hidden = true;
  if (records) records.hidden = false;
  if (subtitle && student) {
    subtitle.textContent = `${student.display_nickname} (${student.login_id}) 학생의 회차별 채점 기록입니다.`;
  }
  loadMySubmissions();
}

function syncHistoryAuth(detail) {
  if (detail?.authenticated && detail?.student) {
    renderLoggedInView(detail.student);
  } else {
    renderLoggedOutView();
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const detailDialog = document.getElementById("deduction-detail-dialog");
  const closeX = document.getElementById("deduction-dialog-close-x");
  if (detailDialog) {
    attachLightDismissFallback(detailDialog);
    detailDialog.addEventListener("close", () => {
      detailDialog.returnValue = "";
    });
  }
  closeX?.addEventListener("click", () => detailDialog?.close("close"));

  document.getElementById("guest-login-btn")?.addEventListener("click", () => {
    window.comlicenseAuth?.openModal("login");
  });
  document.getElementById("guest-signup-btn")?.addEventListener("click", () => {
    window.comlicenseAuth?.openModal("signup");
  });

  document.getElementById("history-filter-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    loadMySubmissions();
  });

  await loadExamsFilter();

  document.addEventListener("comlicense:authchange", (e) => {
    syncHistoryAuth(e.detail);
  });

  if (window.comlicenseAuth?.getState().initialized) {
    syncHistoryAuth(window.comlicenseAuth.getState());
  }
});
