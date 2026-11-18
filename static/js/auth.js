const AUTH_LOGIN_ID_RE = /^[a-zA-Z0-9_.-]{3,30}$/;
const AUTH_PHONE_RE = /^(?:010|011|016|017|018|019)\d{7,8}$/;
const AUTH_TEACHER_RE = /^[a-zA-Z0-9_.-]{2,30}$/;

const authState = {
  initialized: false,
  authenticated: false,
  student: null,
};

function hasPiiPattern(value) {
  const trimmed = value.trim();
  if (trimmed.includes("@")) return "이메일 형식(@)은 사용할 수 없습니다.";
  const digits = trimmed.replace(/[-\s]/g, "");
  if (AUTH_PHONE_RE.test(digits)) return "전화번호 형식은 사용할 수 없습니다.";
  return "";
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function attachLightDismissFallback(dialog) {
  if ("closedBy" in HTMLDialogElement.prototype) return;
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

function createPasswordField({ id, name, labelText, autocomplete, enterkeyhint, hintText, errorId }) {
  const wrap = el("div", "auth-field");
  const label = el("label", "auth-label", labelText);
  label.htmlFor = id;
  label.append(el("span", "req-mark", " *"));

  const pwWrap = el("div", "auth-password-wrap");
  const input = document.createElement("input");
  input.type = "password";
  input.id = id;
  input.name = name;
  input.className = "auth-input";
  input.autocomplete = autocomplete;
  input.enterKeyHint = enterkeyhint;
  input.required = true;
  input.minLength = 8;
  input.maxLength = 72;
  input.dataset.error = errorId;

  const toggleWarnId = `${id}-toggle-warn`;
  const toggleWarn = el("span", "visually-hidden", "주의: 화면에 비밀번호가 표시됩니다.");
  toggleWarn.id = toggleWarnId;

  const toggleBtn = el("button", "pw-toggle-btn", "보기");
  toggleBtn.type = "button";
  toggleBtn.setAttribute("aria-pressed", "false");
  toggleBtn.setAttribute("aria-label", "비밀번호 표시");
  toggleBtn.setAttribute("aria-describedby", toggleWarnId);

  toggleBtn.addEventListener("click", () => {
    const nextShown = input.type === "password";
    input.type = nextShown ? "text" : "password";
    toggleBtn.setAttribute("aria-pressed", String(nextShown));
    toggleBtn.setAttribute("aria-label", nextShown ? "비밀번호 숨기기" : "비밀번호 표시");
    toggleBtn.textContent = nextShown ? "숨김" : "보기";
  });

  pwWrap.append(input, toggleBtn, toggleWarn);
  wrap.append(label, pwWrap);

  if (hintText) {
    const hintId = `${id}-hint`;
    const hint = el("span", "auth-hint", hintText);
    hint.id = hintId;
    input.setAttribute("aria-describedby", hintId);
    wrap.append(hint);
  }

  const errorEl = el("span", "auth-error");
  errorEl.id = errorId;
  errorEl.hidden = true;
  wrap.append(errorEl);

  return { wrap, input };
}

function createTextField({
  id,
  name,
  labelText,
  required = true,
  autocomplete,
  autocorrect = "off",
  autocapitalize = "none",
  spellcheck = false,
  enterkeyhint = "next",
  minlength,
  maxlength = 30,
  placeholder = "",
  hintText = "",
  errorId,
  autofocus = false,
}) {
  const wrap = el("div", "auth-field");
  const label = el("label", "auth-label", labelText);
  label.htmlFor = id;
  if (required) {
    label.append(el("span", "req-mark", " *"));
  }

  const input = document.createElement("input");
  input.type = "text";
  input.id = id;
  input.name = name;
  input.className = "auth-input";
  if (required) input.required = true;
  if (autocomplete) input.autocomplete = autocomplete;
  if (autocorrect) input.setAttribute("autocorrect", autocorrect);
  if (autocapitalize) input.setAttribute("autocapitalize", autocapitalize);
  input.spellcheck = spellcheck;
  input.enterKeyHint = enterkeyhint;
  if (minlength !== undefined) input.minLength = minlength;
  input.maxLength = maxlength;
  if (placeholder) input.placeholder = placeholder;
  if (autofocus) input.autofocus = true;
  input.dataset.error = errorId;

  wrap.append(label, input);

  if (hintText) {
    const hintId = `${id}-hint`;
    const hint = el("span", "auth-hint", hintText);
    hint.id = hintId;
    input.setAttribute("aria-describedby", hintId);
    wrap.append(hint);
  }

  const errorEl = el("span", "auth-error");
  errorEl.id = errorId;
  errorEl.hidden = true;
  wrap.append(errorEl);

  return { wrap, input };
}

function attachFormValidation(form, validateFieldFn) {
  const interacted = new WeakSet();

  const syncField = (input, forceShow) => {
    const msg = validateFieldFn(input);
    input.setCustomValidity(msg);
    const errorEl = input.dataset.error ? document.getElementById(input.dataset.error) : null;
    const showError = Boolean(msg) && (forceShow || interacted.has(input));

    if (showError) {
      if (errorEl) {
        errorEl.textContent = msg;
        errorEl.hidden = false;
      }
      input.setAttribute("aria-invalid", "true");
      input.classList.add("user-invalid-fallback");
      return false;
    }

    if (errorEl) {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
    input.setAttribute("aria-invalid", "false");
    input.classList.remove("user-invalid-fallback");
    return !msg;
  };

  form.addEventListener(
    "blur",
    (e) => {
      const target = e.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (target.value !== "" || interacted.has(target)) {
        interacted.add(target);
        syncField(target, true);
      }
    },
    true
  );

  form.addEventListener("input", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLInputElement)) return;
    interacted.add(target);
    if (target.getAttribute("aria-invalid") === "true") {
      syncField(target, true);
    }
  });

  return {
    validateAll: () => {
      const inputs = [...form.querySelectorAll("input")];
      let firstInvalid = null;
      for (const input of inputs) {
        interacted.add(input);
        const ok = syncField(input, true);
        if (!ok && !firstInvalid) firstInvalid = input;
      }
      if (firstInvalid) {
        firstInvalid.focus();
        return false;
      }
      return true;
    },
    resetValidation: () => {
      for (const input of form.querySelectorAll("input")) {
        input.setCustomValidity("");
        input.setAttribute("aria-invalid", "false");
        input.classList.remove("user-invalid-fallback");
        const errorEl = input.dataset.error ? document.getElementById(input.dataset.error) : null;
        if (errorEl) {
          errorEl.textContent = "";
          errorEl.hidden = true;
        }
      }
    },
  };
}

function buildAuthDialog() {
  let existing = document.getElementById("auth-dialog");
  if (existing) return existing;

  const dialog = document.createElement("dialog");
  dialog.id = "auth-dialog";
  dialog.className = "auth-dialog";
  dialog.setAttribute("closedby", "any");
  dialog.setAttribute("aria-labelledby", "auth-dialog-title");

  const panel = el("div", "auth-dialog-panel");
  const header = el("div", "auth-dialog-header");
  const title = el("h2", "auth-dialog-title", "학생 로그인");
  title.id = "auth-dialog-title";

  const closeBtn = el("button", "auth-dialog-close");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "로그인 창 닫기");
  closeBtn.append(el("span", null, "×"));
  closeBtn.firstElementChild.setAttribute("aria-hidden", "true");
  closeBtn.addEventListener("click", () => dialog.close("close"));

  header.append(title, closeBtn);

  const tabs = el("div", "auth-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "인증 방식 선택");

  const loginTabBtn = el("button", "auth-tab-btn", "로그인");
  loginTabBtn.type = "button";
  loginTabBtn.id = "auth-tab-login";
  loginTabBtn.setAttribute("role", "tab");
  loginTabBtn.setAttribute("aria-selected", "true");

  const signupTabBtn = el("button", "auth-tab-btn", "회원가입");
  signupTabBtn.type = "button";
  signupTabBtn.id = "auth-tab-signup";
  signupTabBtn.setAttribute("role", "tab");
  signupTabBtn.setAttribute("aria-selected", "false");

  tabs.append(loginTabBtn, signupTabBtn);

  const body = el("div", "auth-dialog-body");
  const privacyNote = el(
    "p",
    "auth-privacy-note",
    "개인정보 보호를 위해 이메일, 전화번호, 실명은 수집하지 않습니다. 학습용 아이디와 닉네임으로 이용해 주세요."
  );

  const statusEl = el("div", "auth-status");
  statusEl.id = "auth-dialog-status";
  statusEl.setAttribute("role", "status");
  statusEl.setAttribute("aria-live", "polite");

  // Sign-in form
  const signinForm = document.createElement("form");
  signinForm.id = "auth-signin-form";
  signinForm.className = "auth-form";
  signinForm.method = "post";
  signinForm.noValidate = true;
  signinForm.setAttribute("aria-labelledby", "auth-tab-login");

  const inIdField = createTextField({
    id: "auth-login-id",
    name: "login_id",
    labelText: "학생 아이디",
    autocomplete: "username",
    enterkeyhint: "next",
    minlength: 3,
    maxlength: 30,
    placeholder: "예: study_user01",
    errorId: "auth-login-id-err",
    autofocus: true,
  });
  const inPwField = createPasswordField({
    id: "auth-login-pw",
    name: "password",
    labelText: "비밀번호",
    autocomplete: "current-password",
    enterkeyhint: "done",
    errorId: "auth-login-pw-err",
  });
  const signinSubmit = el("button", "btn btn-primary", "로그인");
  signinSubmit.type = "submit";
  signinForm.append(inIdField.wrap, inPwField.wrap, signinSubmit);

  // Sign-up form
  const signupForm = document.createElement("form");
  signupForm.id = "auth-signup-form";
  signupForm.className = "auth-form";
  signupForm.method = "post";
  signupForm.noValidate = true;
  signupForm.hidden = true;
  signupForm.setAttribute("aria-labelledby", "auth-tab-signup");

  const upIdField = createTextField({
    id: "auth-reg-id",
    name: "login_id",
    labelText: "사용할 아이디",
    autocomplete: "username",
    enterkeyhint: "next",
    minlength: 3,
    maxlength: 30,
    placeholder: "예: excel_master01",
    hintText: "영문·숫자·._- 3~30자 (이메일·전화번호 금지)",
    errorId: "auth-reg-id-err",
  });
  const upPwField = createPasswordField({
    id: "auth-reg-pw",
    name: "password",
    labelText: "비밀번호",
    autocomplete: "new-password",
    enterkeyhint: "next",
    hintText: "8자 이상 입력 (한 번만 입력합니다)",
    errorId: "auth-reg-pw-err",
  });
  const upNickField = createTextField({
    id: "auth-reg-nick",
    name: "display_nickname",
    labelText: "학생 닉네임",
    autocomplete: "nickname",
    autocorrect: "on",
    autocapitalize: "none",
    spellcheck: false,
    enterkeyhint: "next",
    minlength: 1,
    maxlength: 30,
    placeholder: "예: 코딩거북이",
    hintText: "1~30자 별명 (실명 대신 닉네임을 입력하세요)",
    errorId: "auth-reg-nick-err",
  });
  const upTeacherField = createTextField({
    id: "auth-reg-teacher",
    name: "default_teacher_code",
    labelText: "담당 선생님/반 코드 (선택)",
    required: false,
    enterkeyhint: "done",
    maxlength: 30,
    placeholder: "예: teacher01",
    hintText: "없으면 비워두셔도 됩니다",
    errorId: "auth-reg-teacher-err",
  });
  const signupSubmit = el("button", "btn btn-primary", "회원가입");
  signupSubmit.type = "submit";
  signupForm.append(
    upIdField.wrap,
    upPwField.wrap,
    upNickField.wrap,
    upTeacherField.wrap,
    signupSubmit
  );

  body.append(privacyNote, signinForm, signupForm, statusEl);
  panel.append(header, tabs, body);
  dialog.append(panel);
  document.body.append(dialog);

  attachLightDismissFallback(dialog);

  const signinValidator = attachFormValidation(signinForm, (input) => {
    const val = input.value.trim();
    if (input.id === "auth-login-id") {
      if (!val) return "아이디를 입력해 주세요.";
      if (!AUTH_LOGIN_ID_RE.test(val)) return "아이디는 3~30자 영문·숫자·._-만 가능합니다.";
    } else if (input.id === "auth-login-pw") {
      if (!input.value) return "비밀번호를 입력해 주세요.";
      if (input.value.length < 8) return "비밀번호는 8자 이상이어야 합니다.";
    }
    return "";
  });

  const signupValidator = attachFormValidation(signupForm, (input) => {
    const val = input.value.trim();
    if (input.id === "auth-reg-id") {
      if (!val) return "사용할 아이디를 입력해 주세요.";
      const pii = hasPiiPattern(val);
      if (pii) return pii;
      if (!AUTH_LOGIN_ID_RE.test(val)) return "영문·숫자·._- 3~30자로 입력해 주세요.";
    } else if (input.id === "auth-reg-pw") {
      if (!input.value) return "비밀번호를 입력해 주세요.";
      if (input.value.length < 8) return "비밀번호는 8자 이상으로 설정해 주세요.";
    } else if (input.id === "auth-reg-nick") {
      if (!val) return "학생 닉네임을 입력해 주세요.";
      const pii = hasPiiPattern(val);
      if (pii) return pii;
    } else if (input.id === "auth-reg-teacher" && val) {
      const pii = hasPiiPattern(val);
      if (pii) return pii;
      if (!AUTH_TEACHER_RE.test(val)) return "선생님 코드는 2~30자 영문·숫자·._-만 가능합니다.";
    }
    return "";
  });

  const switchMode = (mode) => {
    const isSignup = mode === "signup";
    title.textContent = isSignup ? "학생 회원가입" : "학생 로그인";
    loginTabBtn.setAttribute("aria-selected", String(!isSignup));
    signupTabBtn.setAttribute("aria-selected", String(isSignup));
    signinForm.hidden = isSignup;
    signupForm.hidden = !isSignup;
    statusEl.className = "auth-status";
    statusEl.textContent = "";
    signinValidator.resetValidation();
    signupValidator.resetValidation();
    if (dialog.open) {
      (isSignup ? upIdField.input : inIdField.input).focus();
    }
  };

  loginTabBtn.addEventListener("click", () => switchMode("login"));
  signupTabBtn.addEventListener("click", () => switchMode("signup"));

  dialog.addEventListener("close", () => {
    dialog.returnValue = "";
    statusEl.textContent = "";
    statusEl.className = "auth-status";
  });

  signinForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!signinValidator.validateAll()) return;

    signinSubmit.disabled = true;
    statusEl.className = "auth-status";
    statusEl.textContent = "로그인 확인 중입니다...";

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          login_id: inIdField.input.value.trim(),
          password: inPwField.input.value,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "로그인에 실패했습니다.");
      }

      setAuthState(true, data.student);
      signinForm.reset();
      dialog.close("login");
    } catch (err) {
      statusEl.className = "auth-status is-error";
      statusEl.textContent = err instanceof Error ? err.message : "로그인 중 오류가 발생했습니다.";
    } finally {
      signinSubmit.disabled = false;
    }
  });

  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!signupValidator.validateAll()) return;

    signupSubmit.disabled = true;
    statusEl.className = "auth-status";
    statusEl.textContent = "계정을 생성하고 있습니다...";

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          login_id: upIdField.input.value.trim(),
          password: upPwField.input.value,
          display_nickname: upNickField.input.value.trim(),
          default_teacher_code: upTeacherField.input.value.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail[0]?.msg || "입력 값을 확인해 주세요."
          : data.detail || "회원가입에 실패했습니다.";
        throw new Error(detail);
      }

      setAuthState(true, data.student);
      signupForm.reset();
      dialog.close("signup");
    } catch (err) {
      statusEl.className = "auth-status is-error";
      statusEl.textContent = err instanceof Error ? err.message : "회원가입 중 오류가 발생했습니다.";
    } finally {
      signupSubmit.disabled = false;
    }
  });

  dialog._switchMode = switchMode;
  return dialog;
}

function renderHeaderAuthControls() {
  const container = document.getElementById("auth-header-controls");
  if (!container) return;

  container.replaceChildren();

  if (authState.authenticated && authState.student) {
    const badge = el("span", "auth-user-badge", `${authState.student.display_nickname}`);
    badge.title = `아이디: ${authState.student.login_id}`;

    const historyLink = el("a", "auth-header-btn", "내 이력");
    historyLink.href = "/history";

    const logoutBtn = el("button", "auth-header-btn", "로그아웃");
    logoutBtn.type = "button";
    logoutBtn.addEventListener("click", () => {
      logout();
    });

    container.append(badge, historyLink, logoutBtn);
  } else {
    const loginBtn = el("button", "auth-header-btn auth-header-btn--primary", "로그인 / 가입");
    loginBtn.type = "button";
    loginBtn.addEventListener("click", () => {
      openAuthModal("login");
    });
    container.append(loginBtn);
  }
}

function setAuthState(authenticated, student) {
  authState.initialized = true;
  authState.authenticated = Boolean(authenticated && student);
  authState.student = authState.authenticated ? student : null;
  renderHeaderAuthControls();

  document.dispatchEvent(
    new CustomEvent("comlicense:authchange", {
      detail: {
        authenticated: authState.authenticated,
        student: authState.student,
      },
    })
  );
}

export function openAuthModal(mode = "login") {
  const dialog = buildAuthDialog();
  if (typeof dialog._switchMode === "function") {
    dialog._switchMode(mode);
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

export async function refreshAuthState() {
  try {
    const res = await fetch("/api/auth/me", { headers: { Accept: "application/json" } });
    if (!res.ok) {
      setAuthState(false, null);
      return authState;
    }
    const data = await res.json();
    setAuthState(Boolean(data.authenticated), data.student || null);
  } catch {
    setAuthState(false, null);
  }
  return authState;
}

export async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {
    // Ignore network errors and clear client auth state
  }
  setAuthState(false, null);
}

export function getAuthState() {
  return {
    initialized: authState.initialized,
    authenticated: authState.authenticated,
    student: authState.student,
  };
}

window.comlicenseAuth = {
  openModal: openAuthModal,
  refresh: refreshAuthState,
  logout,
  getState: getAuthState,
};

document.addEventListener("DOMContentLoaded", () => {
  buildAuthDialog();
  refreshAuthState();
});
