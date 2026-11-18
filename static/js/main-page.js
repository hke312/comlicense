const NOTICE_DISMISSED_KEY = "comlicense_notice_dismissed";
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTS = new Set([".xlsx", ".xlsm"]);

const LECTURE_GUIDE_MODULES = [
  {
    badge: "[문제1] 기본작업 (20점)",
    desc: "고급 필터 조건식 작성, 조건부 서식 수식, 시트 보호·페이지 설정 핵심 정리",
    anchor: "/criteria#basic-tasks",
  },
  {
    badge: "[문제2] 계산작업 (40점)",
    desc: "VLOOKUP·INDEX/MATCH·SUMIFS·IFERROR·DATE·TEXT 등 빈출 함수 조합 풀이",
    anchor: "/criteria#calc-tasks",
  },
  {
    badge: "[문제3] 분석작업 (20점)",
    desc: "피벗 테이블 행/열/값 요약, 부분합 정렬 및 목표값 찾기·데이터 표 실습",
    anchor: "/criteria#analysis-tasks",
  },
  {
    badge: "[문제4] 기타작업 (20점)",
    desc: "차트 데이터 범위·제목·레이블 편집 및 매크로 기록·단추 연결 실수 방지",
    anchor: "/criteria#etc-tasks",
  },
];

const state = {
  exams: new Map(),
  selectedExamId: "sample_01",
  lastScores: null,
  droppedFile: null,
};

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function getFileExtension(filename) {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.slice(idx).toLowerCase() : "";
}

function createEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

/* ---------- Accessible Validation & ARIA Sync ---------- */
function setupValidationAnnouncer(form) {
  const announcer = document.createElement("div");
  announcer.setAttribute("aria-live", "polite");
  announcer.className = "visually-hidden";
  document.body.append(announcer);

  let announceTimer = 0;
  let announcedField = null;
  const interacted = new WeakSet();
  const announced = new WeakSet();

  const spokenText = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll('[aria-hidden="true"]').forEach((n) => n.remove());
    return copy.textContent.replace(/\s+/g, " ").trim();
  };

  const linkError = (el, shown) => {
    const errorId = el.dataset.error;
    if (!errorId) return;
    const ids = (el.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter((id) => id && id !== errorId);
    if (shown) ids.push(errorId);
    if (ids.length > 0) el.setAttribute("aria-describedby", ids.join(" "));
    else el.removeAttribute("aria-describedby");
  };

  const announceError = (el) => {
    const errorEl = el.dataset.error ? document.getElementById(el.dataset.error) : null;
    if (!errorEl) return;
    const labelText = el.labels?.[0] ? `${spokenText(el.labels[0])}: ` : "";
    clearTimeout(announceTimer);
    announcer.textContent = "";
    announcedField = el;
    announceTimer = window.setTimeout(() => {
      announcer.textContent = `${labelText}${errorEl.textContent.trim()}`;
    }, 500);
  };

  const validateControl = (el) => {
    if (el.id === "teacher-id") {
      const trimmed = el.value.trim();
      if (trimmed.includes("@")) {
        el.setCustomValidity("이메일 형식은 사용할 수 없습니다.");
      } else {
        el.setCustomValidity("");
      }
    } else if (el.id === "student-nickname") {
      const trimmed = el.value.trim();
      if (!trimmed) {
        el.setCustomValidity("학생 닉네임을 입력해 주세요.");
      } else if (trimmed.includes("@")) {
        el.setCustomValidity("이메일 형식은 사용할 수 없습니다.");
      } else {
        el.setCustomValidity("");
      }
    } else if (el.id === "excel-file") {
      const file = el.files?.[0] || state.droppedFile;
      if (!file) {
        el.setCustomValidity("채점할 .xlsx 또는 .xlsm 파일을 선택해 주세요.");
      } else {
        const ext = getFileExtension(file.name);
        if (!ALLOWED_EXTS.has(ext)) {
          el.setCustomValidity("지원하지 않는 파일 형식입니다. .xlsx 또는 .xlsm 파일만 업로드해 주세요.");
        } else if (file.size === 0) {
          el.setCustomValidity("빈 파일은 채점할 수 없습니다.");
        } else if (file.size > MAX_FILE_BYTES) {
          el.setCustomValidity("파일 크기가 20MB 제한을 초과했습니다.");
        } else {
          el.setCustomValidity("");
        }
      }
    }
    return el.validity.valid;
  };

  const syncField = (el, { forceShow = false, announce = false } = {}) => {
    if (!el?.matches?.("input, select, textarea")) return true;
    const isValid = validateControl(el);
    const shouldShow = forceShow || interacted.has(el);

    const errorEl = el.dataset.error ? document.getElementById(el.dataset.error) : null;

    if (!isValid && shouldShow) {
      if (errorEl) {
        errorEl.textContent = el.validationMessage;
        errorEl.hidden = false;
      }
      el.setAttribute("aria-invalid", "true");
      el.classList.add("user-invalid-fallback");
      el.classList.remove("user-valid-fallback");
      if (el.id === "excel-file") {
        document.getElementById("file-dropzone")?.classList.add("is-invalid");
      }
      linkError(el, true);
      if (announce && !announced.has(el)) {
        announceError(el);
        announced.add(el);
      }
      return false;
    }

    if (errorEl) errorEl.hidden = true;
    el.setAttribute("aria-invalid", "false");
    el.classList.remove("user-invalid-fallback");
    if (shouldShow && isValid) {
      el.classList.add("user-valid-fallback");
    } else {
      el.classList.remove("user-valid-fallback");
    }
    if (el.id === "excel-file") {
      document.getElementById("file-dropzone")?.classList.remove("is-invalid");
    }
    linkError(el, false);
    announced.delete(el);
    if (announcedField === el) {
      clearTimeout(announceTimer);
      announcer.textContent = "";
    }
    return isValid;
  };

  form.querySelectorAll("input, select, textarea").forEach((el) => {
    el.setAttribute("aria-invalid", "false");
  });

  form.addEventListener(
    "blur",
    (e) => {
      const target = e.target;
      if (!target?.matches?.("input, select, textarea")) return;
      if (target.value !== "" || interacted.has(target)) {
        interacted.add(target);
        syncField(target, { forceShow: true, announce: true });
      }
    },
    true
  );

  form.addEventListener("input", (e) => {
    const target = e.target;
    if (!target?.matches?.("input, select, textarea")) return;
    interacted.add(target);
    if (target.getAttribute("aria-invalid") === "true") {
      syncField(target, { forceShow: true, announce: false });
    }
  });

  form.addEventListener("change", (e) => {
    const target = e.target;
    if (!target?.matches?.("input, select, textarea")) return;
    interacted.add(target);
    syncField(target, { forceShow: true, announce: true });
  });

  return {
    validateAll: () => {
      const controls = [...form.querySelectorAll("select, input")];
      let firstInvalid = null;
      for (const control of controls) {
        interacted.add(control);
        const ok = syncField(control, { forceShow: true, announce: false });
        if (!ok && !firstInvalid) {
          firstInvalid = control;
        }
      }
      if (firstInvalid) {
        firstInvalid.focus();
        announceError(firstInvalid);
        return false;
      }
      return true;
    },
    syncFileField: () => {
      const fileInput = document.getElementById("excel-file");
      if (fileInput) {
        interacted.add(fileInput);
        return syncField(fileInput, { forceShow: true, announce: true });
      }
      return false;
    },
  };
}

/* ---------- Notice Banner ---------- */
function initNoticeBanner() {
  const banner = document.getElementById("notice-banner");
  const dismissBtn = document.getElementById("dismiss-notice-btn");
  if (!banner || !dismissBtn) return;

  try {
    if (sessionStorage.getItem(NOTICE_DISMISSED_KEY) === "1") {
      banner.hidden = true;
    }
  } catch {
    // Ignore storage access errors
  }

  dismissBtn.addEventListener("click", () => {
    banner.hidden = true;
    try {
      sessionStorage.setItem(NOTICE_DISMISSED_KEY, "1");
    } catch {
      // Ignore storage access errors
    }
  });
}

/* ---------- File Dropzone ---------- */
function initFileDropzone(validator) {
  const dropzone = document.getElementById("file-dropzone");
  const fileInput = document.getElementById("excel-file");
  const filenameEl = document.getElementById("selected-file-name");
  const statusEl = document.getElementById("file-validation-status");
  if (!dropzone || !fileInput || !filenameEl || !statusEl) return;

  const updateFileUI = (file) => {
    if (!file) {
      filenameEl.textContent = "선택된 파일 없음";
      dropzone.classList.remove("has-file");
      statusEl.textContent = "";
      return;
    }

    const ext = getFileExtension(file.name);
    filenameEl.textContent = `${file.name} (${formatFileSize(file.size)})`;

    if (!ALLOWED_EXTS.has(ext) || file.size === 0 || file.size > MAX_FILE_BYTES) {
      dropzone.classList.remove("has-file");
      statusEl.textContent = "";
    } else {
      dropzone.classList.add("has-file");
      statusEl.textContent = `업로드 준비 완료: ${file.name}`;
    }
    validator.syncFileField();
  };

  fileInput.addEventListener("change", () => {
    state.droppedFile = null;
    updateFileUI(fileInput.files?.[0] || null);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "dragend"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("is-dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove("is-dragover");

    const file = e.dataTransfer?.files?.[0];
    if (!file) return;

    state.droppedFile = file;
    try {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      state.droppedFile = null;
    } catch {
      // Keep fallback in state.droppedFile when browser restricts fileInput.files assignment
    }
    updateFileUI(file);
  });
}

/* ---------- Stats Link & Exam Metadata UI ---------- */
function updateStatsLink() {
  const statsLink = document.getElementById("stats-link");
  if (!statsLink) return;

  const params = new URLSearchParams();
  params.set("exam_id", state.selectedExamId);

  if (state.lastScores && state.lastScores.examId === state.selectedExamId) {
    const s = state.lastScores.scores;
    params.set("my", String(s.total));
    params.set("jum0", String(s.problem1));
    params.set("jum1", String(s.problem2));
    params.set("jum2", String(s.problem3));
    params.set("jum3", String(s.problem4));
  }

  statsLink.href = `/statistics?${params.toString()}`;
}

function updateSelectedExamUI(examId) {
  state.selectedExamId = examId;
  const exam = state.exams.get(examId);

  const viewProblemBtn = document.getElementById("view-problem-btn");
  if (viewProblemBtn) {
    viewProblemBtn.href = `/api/exams/${encodeURIComponent(examId)}/problem-sheet`;
  }

  const downloadBtn = document.getElementById("download-exam-btn");
  if (downloadBtn) {
    downloadBtn.href = `/api/exams/${encodeURIComponent(examId)}/download`;
  }

  const badge = document.getElementById("exam-type-badge");
  const desc = document.getElementById("exam-description-hint");
  if (exam && badge && desc) {
    badge.textContent = exam.is_sample ? "대표 기출" : "모의고사";
    desc.textContent = exam.description
      ? `${exam.description} — 문제지 보기 또는 해당회차 다운(문제지+실습파일 ZIP)으로 바로 풀이할 수 있습니다.`
      : "해당회차 다운 시 문제지(HTML)와 실습 파일(.xlsm)이 함께 ZIP으로 내려받아집니다.";
  }

  updateStatsLink();
}

/* ---------- API Loaders ---------- */
async function loadExams() {
  const select = document.getElementById("exam-select");
  if (!select) return;

  const urlExamId = new URLSearchParams(window.location.search).get("exam_id");

  try {
    const res = await fetch("/api/exams");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const exams = Array.isArray(data.exams) ? data.exams : [];

    if (exams.length === 0) return;

    state.exams.clear();
    select.replaceChildren();

    for (const exam of exams) {
      state.exams.set(exam.exam_id, exam);
      const option = document.createElement("option");
      option.value = exam.exam_id;
      option.textContent = exam.title;
      select.append(option);
    }

    const initialId =
      urlExamId && state.exams.has(urlExamId) ? urlExamId : exams[0].exam_id;
    select.value = initialId;
    updateSelectedExamUI(initialId);
  } catch (err) {
    console.error("Failed to load exam catalog:", err);
  }
}

function applySummary(summary) {
  const countEl = document.getElementById("participant-count");
  const avgEl = document.getElementById("average-score");
  const waitEl = document.getElementById("waiting-count");

  if (countEl) {
    countEl.textContent = Number(summary.participant_count || 0).toLocaleString("ko-KR");
  }
  if (avgEl) {
    avgEl.textContent = Number(summary.average_score || 0).toFixed(2);
  }
  if (waitEl) {
    waitEl.textContent = String(summary.waiting_count ?? 0);
  }
}

async function fetchSummary(examId) {
  try {
    const res = await fetch(`/api/summary?exam_id=${encodeURIComponent(examId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applySummary(data);
  } catch (err) {
    console.error("Failed to fetch summary:", err);
  }
}

function renderRankingList(container, items, { isTeacher }) {
  container.replaceChildren();

  if (!items || items.length === 0) {
    container.append(createEl("p", "ranking-loading", "아직 등록된 순위 데이터가 없습니다."));
    return;
  }

  const list = createEl("ol", "ranking-list");
  list.setAttribute(
    "aria-label",
    isTeacher ? "선생님 누적점수 순위 목록" : "학생 누적점수 순위 목록"
  );

  for (const item of items) {
    const rank = Number(item.rank) || 0;
    const rawScore = isTeacher ? Number(item.average_score) : Number(item.score);
    const clampedPct = Math.max(0, Math.min(100, rawScore));
    const displayName = isTeacher
      ? `${item.masked_teacher_id} (${item.student_count}명)`
      : item.masked_nickname;
    const scoreText = isTeacher ? `${rawScore.toFixed(1)}점` : `${rawScore}점`;

    const li = createEl("li", `ranking-row rank-${rank <= 3 ? rank : "other"}`);

    const rankEl = createEl("span", "ranking-rank", `${rank}`);
    const nameEl = createEl("span", "ranking-name", displayName);
    nameEl.title = displayName;

    const trackEl = createEl("div", "ranking-track");
    trackEl.setAttribute("aria-hidden", "true");
    const barEl = createEl("div", "ranking-bar");
    barEl.style.inlineSize = `${clampedPct}%`;
    trackEl.append(barEl);

    const scoreEl = createEl("span", "ranking-score", scoreText);

    li.append(rankEl, nameEl, trackEl, scoreEl);
    list.append(li);
  }

  const axis = createEl("div", "ranking-axis");
  axis.setAttribute("aria-hidden", "true");
  const ticks = createEl("div", "ranking-axis-ticks");
  for (const tick of ["0", "20", "40", "60", "80", "100"]) {
    ticks.append(createEl("span", null, tick));
  }
  axis.append(ticks);

  container.append(list, axis);
}

async function fetchRankings(examId) {
  const studentContainer = document.getElementById("student-ranking-chart");
  const teacherContainer = document.getElementById("teacher-ranking-chart");
  if (!studentContainer || !teacherContainer) return;

  try {
    const res = await fetch(`/api/rankings?exam_id=${encodeURIComponent(examId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderRankingList(studentContainer, data.students || [], { isTeacher: false });
    renderRankingList(teacherContainer, data.teachers || [], { isTeacher: true });
  } catch (err) {
    console.error("Failed to fetch rankings:", err);
    studentContainer.replaceChildren(
      createEl("p", "ranking-loading", "학생 순위 데이터를 불러오지 못했습니다.")
    );
    teacherContainer.replaceChildren(
      createEl("p", "ranking-loading", "선생님 순위 데이터를 불러오지 못했습니다.")
    );
  }
}

/* ---------- Grading Results Rendering ---------- */
function renderGradeResult(data) {
  const { scores, max_scores: maxScores, deductions, passed, pass_threshold: threshold } = data;

  const p1 = document.getElementById("score-p1");
  const p2 = document.getElementById("score-p2");
  const p3 = document.getElementById("score-p3");
  const p4 = document.getElementById("score-p4");
  const total = document.getElementById("score-total");
  const pill = document.getElementById("pass-status-pill");
  const meta = document.getElementById("graded-meta");

  if (p1) p1.textContent = `${scores.problem1} / ${maxScores.problem1}`;
  if (p2) p2.textContent = `${scores.problem2} / ${maxScores.problem2}`;
  if (p3) p3.textContent = `${scores.problem3} / ${maxScores.problem3}`;
  if (p4) p4.textContent = `${scores.problem4} / ${maxScores.problem4}`;
  if (total) total.textContent = `${scores.total} 점`;

  if (pill) {
    pill.classList.remove("is-neutral", "is-pass", "is-fail");
    if (passed) {
      pill.classList.add("is-pass");
      pill.textContent = `합격 (${threshold}점 이상)`;
    } else {
      pill.classList.add("is-fail");
      pill.textContent = `불합격 (${threshold}점 미만)`;
    }
  }

  if (meta) {
    meta.textContent = `${data.student_nickname} · ${data.graded_at}`;
  }

  const tbody = document.getElementById("deduction-tbody");
  if (tbody) {
    tbody.replaceChildren();

    if (!deductions || deductions.length === 0) {
      const tr = createEl("tr", "perfect-row");
      const td = createEl(
        "td",
        null,
        "감점 내역이 없습니다! 모든 작업을 정확하게 수행했습니다."
      );
      td.colSpan = 4;
      tr.append(td);
      tbody.append(tr);
    } else {
      for (const item of deductions) {
        const tr = document.createElement("tr");

        const th = createEl("th", null, `문제${item.problem_no}`);
        th.setAttribute("scope", "row");

        const taskTd = createEl("td", null, item.task_name);
        const deductionTd = createEl(
          "td",
          "deduction-val",
          item.deduction > 0 ? `-${item.deduction}점` : "0점"
        );
        const detailTd = createEl("td", null, item.detail);

        tr.append(th, taskTd, deductionTd, detailTd);
        tbody.append(tr);
      }
    }
  }

  if (data.summary) {
    applySummary(data.summary);
  }

  state.lastScores = {
    examId: data.exam_id,
    scores,
  };
  updateStatsLink();
}

/* ---------- Form Submission ---------- */
function initGradingForm(validator) {
  const form = document.getElementById("grading-form");
  const submitBtn = document.getElementById("grade-submit-btn");
  const statusEl = document.getElementById("grading-status");
  const examSelect = document.getElementById("exam-select");
  const fileInput = document.getElementById("excel-file");
  if (!form || !submitBtn || !statusEl || !examSelect || !fileInput) return;

  examSelect.addEventListener("change", () => {
    const nextExamId = examSelect.value;
    updateSelectedExamUI(nextExamId);
    fetchSummary(nextExamId);
    fetchRankings(nextExamId);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!validator.validateAll()) {
      statusEl.className = "grading-status is-error";
      statusEl.textContent = "필수 입력 항목과 업로드 파일을 확인해 주세요.";
      return;
    }

    const file = fileInput.files?.[0] || state.droppedFile;
    if (!file) return;

    const formData = new FormData();
    formData.append("exam_id", examSelect.value);
    formData.append("teacher_id", document.getElementById("teacher-id").value.trim());
    formData.append("student_nickname", document.getElementById("student-nickname").value.trim());
    formData.append("file", file);

    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    statusEl.className = "grading-status";
    statusEl.textContent = "답안 파일을 채점 중입니다. 잠시만 기다려 주세요...";

    try {
      const res = await fetch("/api/grade", {
        method: "POST",
        body: formData,
      });

      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload.detail || `채점 요청이 실패했습니다 (HTTP ${res.status}).`);
      }

      renderGradeResult(payload);
      statusEl.className = "grading-status is-success";
      statusEl.textContent = `채점이 완료되었습니다. 총점 ${payload.scores.total}점 (${
        payload.passed ? "합격" : "불합격"
      })`;
      if (payload.student_id) {
        const histLink = createEl("a", null, " · 내 점수 이력 보기");
        histLink.href = "/history";
        statusEl.append(histLink);
      }

      await fetchRankings(payload.exam_id);
    } catch (err) {
      statusEl.className = "grading-status is-error";
      statusEl.textContent = err instanceof Error ? err.message : "채점 중 오류가 발생했습니다.";
    } finally {
      submitBtn.disabled = false;
      submitBtn.removeAttribute("aria-busy");
    }
  });
}

/* ---------- Video Lecture Modal (<dialog>) ---------- */
function initVideoModal() {
  const openBtn = document.getElementById("video-modal-btn");
  const dialog = document.getElementById("video-dialog");
  const closeX = document.getElementById("video-dialog-close-x");
  const titleEl = document.getElementById("video-dialog-title");
  const bodyEl = document.getElementById("video-dialog-body");
  if (!openBtn || !dialog || !closeX || !titleEl || !bodyEl) return;

  const populateModal = () => {
    const exam = state.exams.get(state.selectedExamId);
    const examTitle = exam ? exam.title : "선택한 회차";

    titleEl.textContent = `${examTitle} — 동영상 강좌 및 풀이 가이드`;
    bodyEl.replaceChildren();

    const summary = createEl(
      "p",
      "dialog-round-summary",
      `${examTitle}의 작업별 핵심 풀이 포인트와 감점 방지 가이드를 확인하세요.`
    );
    bodyEl.append(summary);

    const list = createEl("ul", "lecture-list");
    for (const item of LECTURE_GUIDE_MODULES) {
      const li = createEl("li", "lecture-item");
      const info = createEl("div", "lecture-info");
      info.append(
        createEl("span", "lecture-title", item.badge),
        createEl("span", "lecture-desc", item.desc)
      );

      const link = createEl("a", "btn btn-secondary btn-compact", "기준 보기");
      link.href = item.anchor;

      li.append(info, link);
      list.append(li);
    }
    bodyEl.append(list);
  };

  openBtn.addEventListener("click", () => {
    populateModal();
    dialog.showModal();
  });

  closeX.addEventListener("click", () => {
    dialog.close("close");
  });

  dialog.addEventListener("close", () => {
    dialog.returnValue = "";
  });

  // Light-dismiss fallback for browsers without <dialog closedby="any">
  if (!("closedBy" in HTMLDialogElement.prototype)) {
    const isOutside = (e) => {
      const rect = dialog.getBoundingClientRect();
      return (
        e.clientX < rect.left ||
        e.clientX > rect.right ||
        e.clientY < rect.top ||
        e.clientY > rect.bottom
      );
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
}

/* ---------- Auth State Integration ---------- */
function syncHomeAuthUI(authDetail) {
  const strip = document.getElementById("auth-inline-strip");
  const nickInput = document.getElementById("student-nickname");
  const teacherInput = document.getElementById("teacher-id");
  if (!strip) return;

  strip.replaceChildren();
  const authenticated = Boolean(authDetail?.authenticated && authDetail?.student);
  const student = authDetail?.student;

  if (authenticated && student) {
    strip.classList.add("is-authenticated");
    strip.append(
      createEl(
        "span",
        "auth-inline-text",
        `로그인됨: ${student.display_nickname} — 채점 시 내 이력에 자동 기록됩니다.`
      )
    );
    const link = createEl("a", "btn btn-secondary btn-sm", "내 점수 이력");
    link.href = "/history";
    strip.append(link);

    if (nickInput && !nickInput.value.trim()) {
      nickInput.value = student.display_nickname;
    }
    if (teacherInput && !teacherInput.value.trim() && student.default_teacher_code) {
      teacherInput.value = student.default_teacher_code;
    }
  } else {
    strip.classList.remove("is-authenticated");
    strip.append(
      createEl(
        "span",
        "auth-inline-text",
        "로그인하면 채점 점수가 내 이력에 자동 기록됩니다."
      )
    );
    const btn = createEl("button", "btn btn-secondary btn-sm", "로그인 / 가입");
    btn.type = "button";
    btn.id = "inline-login-btn";
    btn.addEventListener("click", () => {
      window.comlicenseAuth?.openModal("login");
    });
    strip.append(btn);
  }
}

/* ---------- Boot ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  initNoticeBanner();

  document.getElementById("inline-login-btn")?.addEventListener("click", () => {
    window.comlicenseAuth?.openModal("login");
  });
  document.addEventListener("comlicense:authchange", (e) => {
    syncHomeAuthUI(e.detail);
  });
  if (window.comlicenseAuth?.getState().initialized) {
    syncHomeAuthUI(window.comlicenseAuth.getState());
  }

  const form = document.getElementById("grading-form");
  if (form) {
    const validator = setupValidationAnnouncer(form);
    initFileDropzone(validator);
    initGradingForm(validator);
  }

  document.getElementById("print-btn")?.addEventListener("click", () => {
    window.print();
  });

  initVideoModal();

  await loadExams();
  await Promise.all([
    fetchSummary(state.selectedExamId),
    fetchRankings(state.selectedExamId),
  ]);
});
