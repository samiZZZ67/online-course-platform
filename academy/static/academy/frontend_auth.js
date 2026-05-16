(function () {
  const state = {
    authenticated: false,
    user: null,
    session: null,
    accessToken: null,
    pendingSignupRole: "student",
    forceInstructorSignup: false,
    enrollments: {},
    dashboardTab: "overview"
  };

  let progressSyncTimer = null;
  const CUSTOM_COURSES_STORAGE_KEY = "skillforge-custom-courses";
  const THUMBNAIL_OVERRIDES_STORAGE_KEY = "skillforge-course-thumbnails";

  function appState() {
    return window.SkillForgeApp && window.SkillForgeApp.state ? window.SkillForgeApp.state : null;
  }

  function hasCapability(name) {
    return !!(state.user && state.user.capabilities && state.user.capabilities[name]);
  }

  function ensureSkillForgeState() {
    const skillState = appState();
    if (!skillState) {
      return;
    }
    if (!skillState.enrollments) {
      skillState.enrollments = {};
    }
    skillState.currentUser = state.user;
    skillState.isAuthenticated = state.authenticated;
    skillState.enrollments = state.enrollments;
    skillState.dashboardTab = state.dashboardTab;
  }

  function isInstructorUser() {
    return hasCapability("canCreateCourses") || !!(state.user && (state.user.role === "instructor" || state.user.role === "admin"));
  }

  function safeToast(title, message, tone) {
    if (typeof window.showToast === "function") {
      window.showToast(title, message, tone);
    }
  }

  function setInlineStatus(type, message) {
    if (typeof window.setInlineStatus === "function") {
      window.setInlineStatus("authStatus", type, message);
      return;
    }
    const host = document.getElementById("authStatus");
    if (!host) {
      return;
    }
    host.textContent = message;
    host.style.color = type === "error" ? "var(--danger)" : "var(--success)";
  }

  function getNavAuthButtons() {
    const actions = document.querySelector(".nav-actions");
    if (!actions) {
      return {};
    }
    const buttons = Array.from(actions.querySelectorAll("button"));
    return {
      actions: actions,
      signIn: buttons.find(function (button) { return button.textContent.indexOf("Sign In") >= 0; }) || null,
      getStarted: buttons.find(function (button) { return button.textContent.indexOf("Get Started") >= 0; }) || null
    };
  }

  function getInstructorNavLink() {
    return Array.from(document.querySelectorAll(".nav-links .nav-link")).find(function (button) {
      return button.textContent.trim() === "Instructor";
    }) || null;
  }

  function removeBridgeButtons() {
    const existing = document.querySelectorAll("[data-auth-bridge]");
    existing.forEach(function (node) {
      node.remove();
    });
  }

  function shouldAttachAccessToken(url) {
    return !!state.accessToken && url.indexOf("/api/") === 0 && url !== "/api/auth/refresh";
  }

  function getCookie(name) {
    const pattern = new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)");
    const match = document.cookie.match(pattern);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function getCsrfToken() {
    return getCookie("csrftoken");
  }

  function isUnsafeMethod(method) {
    return ["POST", "PUT", "PATCH", "DELETE"].indexOf(String(method || "GET").toUpperCase()) >= 0;
  }

  function canRetryWithRefresh(url) {
    if (url !== "/api/auth/me" && !state.session && !state.authenticated) {
      return false;
    }
    if (url === "/api/auth/refresh") {
      return false;
    }
    if (url === "/api/auth/login" || url === "/api/auth/signup") {
      return false;
    }
    if (url.indexOf("/api/auth/password/") === 0 || url.indexOf("/api/auth/oauth/") === 0) {
      return false;
    }
    return url.indexOf("/api/") === 0;
  }

  async function performJsonRequest(url, options) {
    const init = Object.assign(
      {
        credentials: "same-origin",
        headers: {}
      },
      options || {}
    );
    init.headers = Object.assign({}, init.headers || {});
    if (shouldAttachAccessToken(url) && !init.headers.Authorization) {
      init.headers.Authorization = "Bearer " + state.accessToken;
    }
    if (init.body && !(typeof window !== "undefined" && init.body instanceof window.FormData) && !init.headers["Content-Type"]) {
      init.headers["Content-Type"] = "application/json";
    }
    if (isUnsafeMethod(init.method)) {
      const csrfToken = getCsrfToken();
      if (csrfToken && !init.headers["X-CSRFToken"]) {
        init.headers["X-CSRFToken"] = csrfToken;
      }
    }
    const response = await fetch(url, init);
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    return { response: response, data: data };
  }

  async function refreshAccessSession(options) {
    const settings = options || {};
    const result = await performJsonRequest("/api/auth/refresh", { method: "POST" });
    if (result.response.ok && result.data.user) {
      setAuthState(result.data);
      return true;
    }
    if (!settings.preserveState) {
      clearAuthState();
    }
    return false;
  }

  async function requestJson(url, options) {
    const init = Object.assign({}, options || {});
    const skipAuthRetry = !!init.skipAuthRetry;
    delete init.skipAuthRetry;
    const result = await performJsonRequest(url, init);
    if (result.response.status === 401 && !skipAuthRetry && canRetryWithRefresh(url)) {
      const refreshed = await refreshAccessSession({ preserveState: false });
      if (refreshed) {
        return requestJson(url, Object.assign({}, options || {}, { skipAuthRetry: true }));
      }
    }
    return result;
  }

  function shouldUseGetForAction(type, endpoint) {
    const actionType = String(type || "");
    return actionType.indexOf(".fetch") >= 0 || actionType.indexOf(".download") >= 0 || String(endpoint || "").indexOf("?") >= 0;
  }

  async function appApiRequest(type, payload, endpoint) {
    const action = {
      type: type,
      payload: payload,
      endpoint: endpoint,
      timestamp: new Date().toISOString()
    };
    const app = window.SkillForgeApp;
    if (app && Array.isArray(app.actionQueue)) {
      app.actionQueue.push(action);
    }
    window.dispatchEvent(new CustomEvent("skillforge:action", { detail: action }));
    if (!endpoint || String(endpoint).indexOf("/api/") !== 0) {
      return { ok: true, queued: true, action: action, data: {} };
    }

    const isForm = typeof window !== "undefined" && payload instanceof window.FormData;
    const useGet = shouldUseGetForAction(type, endpoint);
    let url = endpoint;
    const init = { method: useGet ? "GET" : "POST" };
    if (useGet && payload && !isForm) {
      const params = new URLSearchParams();
      Object.keys(payload).forEach(function (key) {
        const value = payload[key];
        if (value !== undefined && value !== null && value !== "") {
          params.set(key, String(value));
        }
      });
      const query = params.toString();
      if (query) {
        url += (url.indexOf("?") >= 0 ? "&" : "?") + query;
      }
    } else if (isForm) {
      init.body = payload;
    } else {
      init.body = JSON.stringify(payload || {});
    }
    const result = await requestJson(url, init);
    return {
      ok: result.response.ok,
      response: result.response,
      data: result.data,
      action: action
    };
  }

  function readStorageJson(key, fallback) {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeStorageJson(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      return;
    }
  }

  function replaceStoredCustomCourses(courses) {
    writeStorageJson(
      CUSTOM_COURSES_STORAGE_KEY,
      (courses || []).filter(function (course) {
        return !!(course && course.id);
      })
    );
  }

  function persistCustomCourseSnapshot(course) {
    if (!course || !course.id || !course.isCustom) {
      return;
    }
    const stored = readStorageJson(CUSTOM_COURSES_STORAGE_KEY, []).filter(function (item) {
      return item && item.id !== course.id;
    });
    stored.push(course);
    replaceStoredCustomCourses(stored);
  }

  function updateThumbnailOverrides(courseId, inputValue) {
    const skillState = appState();
    const overrides = skillState && skillState.thumbnailOverrides
      ? Object.assign({}, skillState.thumbnailOverrides)
      : Object.assign({}, readStorageJson(THUMBNAIL_OVERRIDES_STORAGE_KEY, {}));
    if (inputValue) {
      overrides[courseId] = inputValue;
    } else {
      delete overrides[courseId];
    }
    if (skillState) {
      skillState.thumbnailOverrides = overrides;
    }
    writeStorageJson(THUMBNAIL_OVERRIDES_STORAGE_KEY, overrides);
  }

  function getThumbnailOverrideValue(courseId) {
    const skillState = appState();
    if (skillState && skillState.thumbnailOverrides && skillState.thumbnailOverrides[courseId]) {
      return skillState.thumbnailOverrides[courseId];
    }
    const stored = readStorageJson(THUMBNAIL_OVERRIDES_STORAGE_KEY, {});
    return stored[courseId] || "";
  }

  function registerServerCourse(course, options) {
    if (!course || !course.id || typeof window.registerCourse !== "function") {
      return;
    }
    window.registerCourse(course);
    if (!options || options.persist !== false) {
      persistCustomCourseSnapshot(course);
    }
  }

  async function syncCourseCatalog(options) {
    if (typeof window.registerCourse !== "function") {
      return { response: { ok: false }, data: {} };
    }
    const result = await requestJson("/api/courses", { method: "GET" });
    if (result.response.ok && Array.isArray(result.data.courses)) {
      result.data.courses.forEach(function (course) {
        registerServerCourse(course, { persist: false });
      });
      replaceStoredCustomCourses(
        result.data.courses.filter(function (course) {
          return !!(course && course.isCustom);
        })
      );
      if (!options || options.refresh !== false) {
        if (typeof window.refreshCourseSurfaces === "function") {
          window.refreshCourseSurfaces();
        } else if (typeof window.renderInstructorCourseStudio === "function") {
          window.renderInstructorCourseStudio();
        }
      }
    }
    return result;
  }

  async function persistInstructorCourse(coursePayload) {
    const result = await requestJson("/api/instructor/courses", {
      method: "POST",
      body: JSON.stringify({ course: coursePayload })
    });
    if (result.response.ok && result.data.course) {
      registerServerCourse(result.data.course);
      if (typeof window.syncInstructorEditorFromSavedCourse === "function") {
        window.syncInstructorEditorFromSavedCourse(result.data.course);
      }
    }
    return result;
  }

  async function persistInstructorAsset(courseId, file, lessonId) {
    const body = new window.FormData();
    body.append("courseId", courseId);
    body.append("file", file);
    if (lessonId) {
      body.append("lessonId", lessonId);
    }
    const result = await requestJson("/api/instructor/courses/assets", {
      method: "POST",
      body: body
    });
    if (result.response.ok && result.data.course) {
      registerServerCourse(result.data.course);
      if (typeof window.syncInstructorEditorFromSavedCourse === "function") {
        window.syncInstructorEditorFromSavedCourse(result.data.course);
      }
    }
    return result;
  }

  function upsertEnrollment(enrollment) {
    if (!enrollment || !enrollment.courseId) {
      return;
    }
    state.enrollments[enrollment.courseId] = enrollment;
    ensureSkillForgeState();
  }

  function replaceEnrollments(items) {
    const next = {};
    (items || []).forEach(function (item) {
      if (item && item.courseId) {
        next[item.courseId] = item;
      }
    });
    state.enrollments = next;
    ensureSkillForgeState();
  }

  function updateInstructorAccessUi() {
    const instructorLink = getInstructorNavLink();
    if (!instructorLink) {
      return;
    }
    instructorLink.classList.toggle("hidden", !isInstructorUser());
  }

  function renderNavAuth() {
    const parts = getNavAuthButtons();
    if (!parts.actions) {
      updateInstructorAccessUi();
      return;
    }

    removeBridgeButtons();
    updateInstructorAccessUi();

    if (state.authenticated && state.user) {
      if (parts.signIn) {
        parts.signIn.classList.add("hidden");
      }
      if (parts.getStarted) {
        parts.getStarted.classList.add("hidden");
      }

      const accountChip = document.createElement("span");
      accountChip.dataset.authBridge = "user";
      accountChip.className = "btn btn-ghost btn-sm";
      accountChip.textContent = state.user.firstName || state.user.email;

      const logoutButton = document.createElement("button");
      logoutButton.type = "button";
      logoutButton.dataset.authBridge = "logout";
      logoutButton.className = "btn btn-primary btn-sm";
      logoutButton.textContent = "Log Out";
      logoutButton.addEventListener("click", handleLogout);

      parts.actions.appendChild(accountChip);
      parts.actions.appendChild(logoutButton);
      return;
    }

    if (parts.signIn) {
      parts.signIn.classList.remove("hidden");
    }
    if (parts.getStarted) {
      parts.getStarted.classList.remove("hidden");
    }

    const instructorButton = document.createElement("button");
    instructorButton.type = "button";
    instructorButton.dataset.authBridge = "become-instructor";
    instructorButton.className = "btn btn-ghost btn-sm";
    instructorButton.textContent = "Become Instructor";
    instructorButton.addEventListener("click", handleBecomeInstructor);
    parts.actions.appendChild(instructorButton);
  }

  function updateDashboardStats() {
    const cards = document.querySelectorAll("#view-dashboard .stat-card");
    const profile = state.user && state.user.studentProfile ? state.user.studentProfile : null;
    if (!cards.length || !profile) {
      return;
    }
    if (cards[0]) {
      const value = cards[0].querySelector(".stat-num");
      if (value) {
        value.textContent = String(profile.currentCourses || 0);
      }
    }
    if (cards[1]) {
      const value = cards[1].querySelector(".stat-num");
      if (value) {
        value.textContent = String(Math.max(0, Math.round((profile.totalLearningMinutes || 0) / 60))) + "h";
      }
    }
    if (cards[3]) {
      const value = cards[3].querySelector(".stat-num");
      if (value) {
        value.textContent = String(profile.learningStreakDays || 0);
      }
    }
  }

  function updateDashboardHeaders() {
    const userName = state.user ? (state.user.firstName || state.user.username || state.user.email) : "Learner";
    const dashboardTitle = document.querySelector("#view-dashboard .dash-title");
    if (dashboardTitle) {
      dashboardTitle.textContent = "Welcome back, " + userName + "!";
    }
    const instructorTitle = document.querySelector("#view-instructor .dash-title");
    if (instructorTitle && isInstructorUser()) {
      instructorTitle.textContent = state.user.firstName && state.user.lastName
        ? state.user.firstName + " " + state.user.lastName
        : userName;
    }
  }

  function hydrateEnrollmentCards() {
    document.querySelectorAll("#view-dashboard .enrolled-card").forEach(function (card) {
      const title = card.querySelector(".enrolled-title") ? card.querySelector(".enrolled-title").textContent : "";
      const course = typeof window.matchCourseByTitle === "function" ? window.matchCourseByTitle(title) : null;
      if (!course) {
        return;
      }
      const enrollment = state.enrollments[course.id];
      const fill = card.querySelector(".enrolled-progress-fill");
      const label = card.querySelector(".enrolled-progress-label");
      if (!fill || !label) {
        return;
      }
      if (enrollment) {
        fill.style.width = String(enrollment.progressPercent || 0) + "%";
        label.innerHTML = "<span>" + ((enrollment.progressPercent || 0) >= 100 ? "Completed" : "In progress") + "</span><span style=\"color:var(--gold)\">" + String(enrollment.progressPercent || 0) + "%</span>";
      } else if (state.authenticated) {
        fill.style.width = "0%";
        label.innerHTML = "<span>Not enrolled yet</span><span style=\"color:var(--text3)\">0%</span>";
      }
    });
  }

  function hydrateCourseDetailEnrollmentState() {
    const skillState = appState();
    const courseId = skillState ? skillState.selectedCourseId : null;
    const button = document.querySelector("#view-detail .sidebar-btn");
    if (!button || !courseId) {
      return;
    }
    button.textContent = state.enrollments[courseId] ? "Continue Learning ->" : "Start Learning ->";
  }

  function hydrateDashboardProgress() {
    updateDashboardHeaders();
    updateDashboardStats();
    hydrateEnrollmentCards();
    hydrateCourseDetailEnrollmentState();
  }

  function getDashboardPanels() {
    const main = document.querySelector("#view-dashboard .dashboard-main");
    if (!main) {
      return [];
    }
    const stats = main.querySelector(".stats-grid");
    const sections = main.querySelectorAll(":scope > .dash-section");
    const splitGrid = Array.from(main.children).find(function (child) {
      return child.getAttribute && (child.getAttribute("style") || "").indexOf("grid-template-columns:1fr 1fr") >= 0;
    });
    return [
      { element: stats, tabs: ["overview", "progress"] },
      { element: sections[0] || null, tabs: ["overview", "courses", "progress"] },
      { element: splitGrid || null, tabs: ["overview", "progress"] },
      { element: sections[1] || null, tabs: ["overview", "certs"] }
    ];
  }

  function applyDashboardTab(tab) {
    const normalized = ["overview", "courses", "progress", "certs"].indexOf(tab) >= 0 ? tab : "overview";
    state.dashboardTab = normalized;
    ensureSkillForgeState();
    localStorage.setItem("skillforge-dashboard-tab", normalized);
    getDashboardPanels().forEach(function (panel) {
      if (!panel.element) {
        return;
      }
      panel.element.classList.toggle("hidden", panel.tabs.indexOf(normalized) === -1);
    });
  }

  function setDashboardActive(element) {
    const container = element ? element.closest(".sidebar-nav") : null;
    if (!container) {
      return;
    }
    container.querySelectorAll(".sidebar-nav-link").forEach(function (button) {
      button.classList.remove("active");
    });
    element.classList.add("active");
  }

  async function restoreDashboardTab() {
    let tab = localStorage.getItem("skillforge-dashboard-tab") || "overview";
    if (state.authenticated) {
      const result = await requestJson("/api/dashboard/tab", { method: "GET" });
      if (result.response.ok && result.data.selection && result.data.selection.tab) {
        tab = result.data.selection.tab;
      }
    }
    const button = Array.from(document.querySelectorAll("#view-dashboard .sidebar-nav-link")).find(function (candidate) {
      const handler = candidate.getAttribute("onclick") || "";
      return handler.indexOf("'" + tab + "'") >= 0;
    });
    if (button) {
      setDashboardActive(button);
    }
    applyDashboardTab(tab);
  }

  async function loadEnrollments(courseId) {
    if (!state.authenticated) {
      state.enrollments = {};
      ensureSkillForgeState();
      hydrateDashboardProgress();
      return { response: { ok: false }, data: {} };
    }
    const url = courseId ? "/api/enrollments?courseId=" + encodeURIComponent(courseId) : "/api/enrollments";
    const result = await requestJson(url, { method: "GET" });
    if (result.response.ok && Array.isArray(result.data.enrollments)) {
      if (courseId) {
        result.data.enrollments.forEach(upsertEnrollment);
      } else {
        replaceEnrollments(result.data.enrollments);
      }
      hydrateDashboardProgress();
      applyCurrentPlayerProgress();
    }
    return result;
  }

  function applyCurrentPlayerProgress() {
    const skillState = appState();
    if (!skillState || !skillState.selectedCourseId) {
      return;
    }
    const enrollment = state.enrollments[skillState.selectedCourseId];
    if (!enrollment || typeof enrollment.progressPercent !== "number") {
      return;
    }
    skillState.playerProgress = enrollment.progressPercent;
    if (skillState.view === "player" && typeof window.renderPlayer === "function") {
      window.renderPlayer();
    }
  }

  async function saveEnrollmentProgress(courseId, progressPercent) {
    if (!state.authenticated || !courseId) {
      return;
    }
    const skillState = appState();
    const lessonId = skillState ? skillState.selectedLessonId : "";
    const positionKey = skillState && lessonId ? courseId + ":" + lessonId : "";
    const positionSeconds = skillState && positionKey && skillState.mediaPositions ? (skillState.mediaPositions[positionKey] || 0) : 0;
    const result = await requestJson("/api/enrollments/progress", {
      method: "POST",
      body: JSON.stringify({ courseId: courseId, lessonId: lessonId, progressPercent: progressPercent, positionSeconds: positionSeconds })
    });
    if (result.response.ok && result.data.enrollment) {
      upsertEnrollment(result.data.enrollment);
      hydrateDashboardProgress();
    }
  }

  function scheduleProgressSync() {
    const skillState = appState();
    if (!skillState || !skillState.selectedCourseId) {
      return;
    }
    window.clearTimeout(progressSyncTimer);
    progressSyncTimer = window.setTimeout(function () {
      saveEnrollmentProgress(skillState.selectedCourseId, skillState.playerProgress || 0);
    }, 180);
  }

  function setAuthState(payload) {
    state.authenticated = !!(payload && payload.user);
    state.user = payload && payload.user ? payload.user : null;
    state.session = payload && payload.session ? payload.session : null;
    state.accessToken = state.authenticated ? ((payload && (payload.accessToken || payload.token)) || state.accessToken) : null;
    if (!state.authenticated) {
      state.enrollments = {};
    }
    ensureSkillForgeState();
    renderNavAuth();
    hydrateDashboardProgress();
  }

  function clearAuthState() {
    state.pendingSignupRole = "student";
    state.forceInstructorSignup = false;
    state.accessToken = null;
    state.enrollments = {};
    setAuthState({ user: null, session: null });
  }

  function decorateAuthForm() {
    const form = document.getElementById("authDynamicForm");
    if (!form) {
      return;
    }
    const mode = form.dataset.mode || "login";
    const existingHint = form.querySelector('[data-auth-bridge="signup-role-hint"]');
    const existingRole = form.querySelector('input[name="role"][data-auth-bridge="signup-role"]');

    if (mode !== "signup") {
      if (existingHint) {
        existingHint.remove();
      }
      if (existingRole) {
        existingRole.remove();
      }
      return;
    }

    let roleField = existingRole;
    if (!roleField) {
      roleField = document.createElement("input");
      roleField.type = "hidden";
      roleField.name = "role";
      roleField.dataset.authBridge = "signup-role";
      form.appendChild(roleField);
    }
    roleField.value = state.pendingSignupRole;

    let hint = existingHint;
    if (!hint) {
      hint = document.createElement("div");
      hint.dataset.authBridge = "signup-role-hint";
      hint.className = "inline-status success";
      const divider = form.querySelector(".form-divider");
      if (divider) {
        divider.insertAdjacentElement("afterend", hint);
      } else {
        form.insertAdjacentElement("afterbegin", hint);
      }
    }

    const submitButton = form.querySelector('button[type="submit"]');
    if (state.pendingSignupRole === "instructor") {
      hint.textContent = "Instructor signup enabled. This account can open the instructor dashboard and manage courses.";
      if (submitButton) {
        submitButton.textContent = "Create Instructor Account ->";
      }
    } else {
      hint.textContent = "Student signup enabled. This account is for learning, progress, and enrollments.";
      if (submitButton) {
        submitButton.textContent = "Create Account ->";
      }
    }
  }

  function handleBecomeInstructor() {
    state.pendingSignupRole = "instructor";
    state.forceInstructorSignup = true;
    if (typeof window.openModal === "function") {
      window.openModal("signup");
    }
    window.setTimeout(decorateAuthForm, 0);
  }

  async function refreshAuthState() {
    await syncCourseCatalog();
    const restored = await refreshAccessSession({ preserveState: false });
    if (restored) {
      await loadEnrollments();
      await restoreDashboardTab();
      return true;
    }
    applyDashboardTab("overview");
    return false;
  }

  async function handleAuthSubmitBridge(form) {
    const submitButton = form.querySelector('button[type="submit"]');
    const payload = Object.fromEntries(new FormData(form).entries());
    const mode = form.dataset.mode || "login";

    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Saving...";
    }
    setInlineStatus("success", "Connecting to Django authentication...");

    const result = await requestJson(form.dataset.endpoint, {
      method: "POST",
      body: JSON.stringify(payload)
    });

    if (!result.response.ok) {
      setInlineStatus("error", result.data.message || "Unable to complete authentication.");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = mode === "login"
          ? "Sign In ->"
          : (state.pendingSignupRole === "instructor" ? "Create Instructor Account ->" : "Create Account ->");
      }
      return;
    }

    if (result.data.twoFactorRequired) {
      const promptText = result.data.otpCode
        ? "Enter the 6-digit verification code from your email. Dev code: " + result.data.otpCode
        : "Enter the 6-digit verification code from your email.";
      setInlineStatus("success", "Verification required. Enter the code to finish signing in.");
      const enteredCode = window.prompt(promptText, "");
      if (!enteredCode) {
        setInlineStatus("error", "A verification code is required to finish signing in.");
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Sign In ->";
        }
        return;
      }
      const verifyResult = await requestJson("/api/auth/2fa/verify", {
        method: "POST",
        body: JSON.stringify({
          challengeId: result.data.challengeId,
          code: enteredCode.trim()
        })
      });
      if (!verifyResult.response.ok) {
        setInlineStatus("error", verifyResult.data.message || "Unable to verify the sign-in code.");
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Sign In ->";
        }
        return;
      }
      result.data = verifyResult.data;
    }

    setAuthState(result.data);
    state.forceInstructorSignup = false;
    state.pendingSignupRole = "student";
    await loadEnrollments();
    await restoreDashboardTab();
    setInlineStatus("success", mode === "login" ? "Signed in successfully." : "Account created successfully.");
    if (typeof window.closeModal === "function") {
      window.closeModal();
    }
    if (typeof window.showView === "function") {
      if (result.data.user && (result.data.user.role === "instructor" || result.data.user.role === "admin")) {
        window.showView("instructor");
      } else {
        window.showView(mode === "login" ? "dashboard" : "courses");
      }
    }
    safeToast(
      mode === "login" ? "Signed in" : "Account created",
      mode === "login"
        ? "Your session is now active."
        : (result.data.user && result.data.user.role === "instructor"
          ? "Your instructor account was created and can now manage courses."
          : "Your account was created and signed in."),
      "success"
    );
    if (result.data.verificationRequired) {
      safeToast("Verification needed", "A verification email was prepared for this account.", "success");
    }
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = mode === "login" ? "Sign In ->" : "Create Account ->";
    }
  }

  async function handleLogout() {
    const logoutButton = document.querySelector('[data-auth-bridge="logout"]');
    if (logoutButton) {
      logoutButton.disabled = true;
      logoutButton.textContent = "Logging out...";
    }

    const result = await requestJson("/api/auth/logout", {
      method: "POST",
      body: JSON.stringify({})
    });

    clearAuthState();
    if (typeof window.showView === "function") {
      window.showView("home");
    }
    safeToast("Logged out", "Your session has been closed.", result.response.ok ? "success" : "error");
  }

  async function handleOAuthBridge(provider) {
    if (provider !== "google") {
      return;
    }
    const result = await requestJson("/api/auth/oauth/start", {
      method: "POST",
      body: JSON.stringify({ provider: provider })
    });
    if (!result.response.ok) {
      safeToast("OAuth unavailable", result.data.message || "Unable to start OAuth.", "error");
      return;
    }
    safeToast("OAuth ready", "Google sign-in start payload was generated by the backend.", "success");
    if (result.data.authorizationUrl) {
      window.open(result.data.authorizationUrl, "_blank", "noopener,noreferrer");
    }
  }

  function interceptAuthSubmit(event) {
    const form = event.target;
    if (!form || form.id !== "authDynamicForm") {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    handleAuthSubmitBridge(form);
  }

  function wrapModalHelpers() {
    if (typeof window.openModal === "function") {
      const originalOpenModal = window.openModal;
      window.openModal = function (type) {
        if (type === "signup" && !state.forceInstructorSignup) {
          state.pendingSignupRole = "student";
        }
        if (type === "login") {
          state.pendingSignupRole = "student";
          state.forceInstructorSignup = false;
        }
        const result = originalOpenModal.apply(this, arguments);
        window.setTimeout(decorateAuthForm, 0);
        return result;
      };
    }

    if (typeof window.switchTab === "function") {
      const originalSwitchTab = window.switchTab;
      window.switchTab = function (element, type) {
        if (type === "signup" && !state.forceInstructorSignup) {
          state.pendingSignupRole = "student";
        }
        if (type === "login") {
          state.pendingSignupRole = "student";
          state.forceInstructorSignup = false;
        }
        const result = originalSwitchTab.apply(this, arguments);
        window.setTimeout(decorateAuthForm, 0);
        return result;
      };
    }

    if (typeof window.closeModal === "function") {
      const originalCloseModal = window.closeModal;
      window.closeModal = function () {
        const result = originalCloseModal.apply(this, arguments);
        state.forceInstructorSignup = false;
        state.pendingSignupRole = "student";
        return result;
      };
    }
  }

  function wrapViewGuards() {
    if (typeof window.showView === "function") {
      const originalShowView = window.showView;
      window.showView = function (view) {
        if (view === "instructor" && !isInstructorUser()) {
          safeToast("Instructor access only", "Only instructor accounts can open the course studio.", "error");
          if (state.authenticated) {
            originalShowView.call(this, "dashboard", Object.assign({}, arguments[1] || {}, { replace: true }));
          }
          if (!state.authenticated) {
            handleBecomeInstructor();
          }
          return;
        }

        const result = originalShowView.apply(this, arguments);
        if (view === "dashboard") {
          hydrateDashboardProgress();
          restoreDashboardTab();
          loadEnrollments();
        }
        if (view === "detail") {
          hydrateCourseDetailEnrollmentState();
          loadEnrollments(appState() ? appState().selectedCourseId : null);
        }
        if (view === "player") {
          loadEnrollments(appState() ? appState().selectedCourseId : null);
        }
        if (view === "instructor") {
          updateDashboardHeaders();
        }
        return result;
      };
    }
  }

  function wrapDashboardTabs() {
    window.setDashTab = function (element, tab) {
      if (element) {
        setDashboardActive(element);
      }
      applyDashboardTab(tab);
      if (state.authenticated) {
        requestJson("/api/dashboard/tab", {
          method: "POST",
          body: JSON.stringify({ tab: tab })
        });
      }
    };
  }

  function wrapProgressAndEnrollmentFlows() {
    if (typeof window.startEnrollment === "function") {
      window.startEnrollment = async function (courseId) {
        const course = typeof window.getCourse === "function" ? window.getCourse(courseId) : null;
        if (!state.authenticated) {
          safeToast("Sign in required", "Please sign in before enrolling in a course.", "error");
          if (typeof window.openModal === "function") {
            window.openModal("login");
          }
          return;
        }
        const result = await requestJson("/api/enrollments", {
          method: "POST",
          body: JSON.stringify({ courseId: courseId })
        });
        if (!result.response.ok) {
          safeToast("Enrollment failed", result.data.message || "Unable to enroll in this course right now.", "error");
          return;
        }
        upsertEnrollment(result.data.enrollment);
        hydrateDashboardProgress();
        safeToast("Enrollment saved", course ? course.title + " is now in your learning dashboard." : "Your course enrollment is now active.", "success");
        if (typeof window.openPlayerForCourse === "function") {
          window.openPlayerForCourse(courseId);
        }
      };
    }

    if (typeof window.openPlayerForCourse === "function") {
      const originalOpenPlayerForCourse = window.openPlayerForCourse;
      window.openPlayerForCourse = async function (courseId, lessonId) {
        const result = originalOpenPlayerForCourse.apply(this, arguments);
        await loadEnrollments(courseId);
        applyCurrentPlayerProgress();
        return result;
      };
    }

    if (typeof window.updatePlayerProgress === "function") {
      const originalUpdatePlayerProgress = window.updatePlayerProgress;
      window.updatePlayerProgress = function () {
        const result = originalUpdatePlayerProgress.apply(this, arguments);
        scheduleProgressSync();
        return result;
      };
    }

    if (typeof window.selectLesson === "function") {
      const originalSelectLesson = window.selectLesson;
      window.selectLesson = function () {
        const result = originalSelectLesson.apply(this, arguments);
        scheduleProgressSync();
        return result;
      };
    }

    if (typeof window.changeLesson === "function") {
      const originalChangeLesson = window.changeLesson;
      window.changeLesson = function () {
        const result = originalChangeLesson.apply(this, arguments);
        scheduleProgressSync();
        return result;
      };
    }
  }

  function wrapInstructorActions() {
    if (typeof window.toggleCourseComposer === "function") {
      const originalToggleCourseComposer = window.toggleCourseComposer;
      window.toggleCourseComposer = function () {
        if (!isInstructorUser()) {
          safeToast("Instructor access only", "Only instructor accounts can open the course composer.", "error");
          return;
        }
        return originalToggleCourseComposer.apply(this, arguments);
      };
    }

    if (typeof window.handleCreateCourseSubmit === "function") {
      window.handleCreateCourseSubmit = async function (event) {
        if (!isInstructorUser()) {
          if (event && typeof event.preventDefault === "function") {
            event.preventDefault();
          }
          safeToast("Instructor access only", "Only instructor accounts can create courses.", "error");
          return;
        }
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }
        const form = event && event.currentTarget ? event.currentTarget : null;
        if (!form) {
          return;
        }
        const submitButton = form.querySelector('button[type="submit"]');
        const formData = Object.fromEntries(new FormData(form).entries());
        const payload = {
          title: String(formData.title || "").trim(),
          cat: String(formData.category || "ai").trim(),
          instructor: String(formData.instructor || "").trim(),
          price: String(formData.price || "").trim(),
          hours: String(formData.hours || "").trim(),
          lessons: String(formData.lessons || "").trim(),
          level: String(formData.level || "Beginner").trim(),
          thumbnail: String(formData.thumbnail || "").trim(),
          overview: String(formData.overview || "").trim()
        };
        if (!payload.title || !payload.instructor || !payload.overview) {
          safeToast("Course not created", "Title, instructor, and overview are required.", "error");
          return;
        }
        if (submitButton) {
          submitButton.disabled = true;
          submitButton.textContent = "Saving...";
        }
        const result = await requestJson("/api/instructor/courses", {
          method: "POST",
          body: JSON.stringify({ course: payload })
        });
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Create Course";
        }
        if (!result.response.ok || !result.data.course) {
          safeToast("Course not created", result.data.message || "Unable to save this course right now.", "error");
          return;
        }
        registerServerCourse(result.data.course);
        if (typeof window.syncInstructorEditorFromSavedCourse === "function") {
          window.syncInstructorEditorFromSavedCourse(result.data.course);
        }
        const skillState = appState();
        if (skillState) {
          skillState.selectedCourseId = result.data.course.id;
          skillState.instructorComposerOpen = false;
        }
        if (typeof window.openInstructorCourseEditor === "function") {
          window.openInstructorCourseEditor(result.data.course.id);
        }
        form.reset();
        if (typeof window.refreshCourseSurfaces === "function") {
          window.refreshCourseSurfaces();
        }
        safeToast("Course saved", result.data.course.title + " is now in the live catalog.", "success");
        return result;
      };
    }

    if (typeof window.applyCourseThumbnail === "function") {
      window.applyCourseThumbnail = async function (courseId) {
        if (!isInstructorUser()) {
          safeToast("Instructor access only", "Only instructor accounts can update course thumbnails.", "error");
          return;
        }
        const course = typeof window.getCourse === "function" ? window.getCourse(courseId) : null;
        const input = document.getElementById("thumbnail-input-" + courseId);
        if (!course || !input) {
          return;
        }
        const inputValue = input.value.trim();
        const previousOverrideValue = getThumbnailOverrideValue(courseId);
        const computedThumbnail = inputValue || (
          typeof window.createCourseThumbnailData === "function"
            ? window.createCourseThumbnailData(course)
            : course.thumbnail
        );
        const previousThumbnail = course.thumbnail;
        course.thumbnail = computedThumbnail;
        updateThumbnailOverrides(courseId, inputValue);
        if (typeof window.refreshCourseSurfaces === "function") {
          window.refreshCourseSurfaces();
        }
        const result = await requestJson("/api/instructor/courses/thumbnail", {
          method: "POST",
          body: JSON.stringify({ courseId: courseId, thumbnail: computedThumbnail || "" })
        });
        if (!result.response.ok || !result.data.course) {
          course.thumbnail = previousThumbnail;
          updateThumbnailOverrides(courseId, previousOverrideValue);
          if (inputValue !== previousOverrideValue && input) {
            input.value = previousOverrideValue;
          }
          if (typeof window.refreshCourseSurfaces === "function") {
            window.refreshCourseSurfaces();
          }
          safeToast("Thumbnail not saved", result.data.message || "Unable to update this thumbnail right now.", "error");
          return;
        }
        registerServerCourse(result.data.course);
        if (typeof window.syncInstructorEditorFromSavedCourse === "function") {
          window.syncInstructorEditorFromSavedCourse(result.data.course);
        }
        course.thumbnail = result.data.course.thumbnail;
        updateThumbnailOverrides(courseId, inputValue);
        if (typeof window.refreshCourseSurfaces === "function") {
          window.refreshCourseSurfaces();
        }
        safeToast(inputValue ? "Thumbnail updated" : "Thumbnail reset", "The course card now uses the saved backend thumbnail.", "success");
        return result;
      };
    }
  }

  function installOverrides() {
    document.addEventListener("submit", interceptAuthSubmit, true);
    if (window.SkillForgeApp) {
      window.SkillForgeApp.request = appApiRequest;
    }
    window.startOAuth = handleOAuthBridge;
    window.saveInstructorCourseDraftBridge = persistInstructorCourse;
    window.uploadInstructorCourseAssetBridge = persistInstructorAsset;
    window.handleAuthSubmit = function (event) {
      event.preventDefault();
      handleAuthSubmitBridge(event.currentTarget);
    };
    wrapModalHelpers();
    wrapViewGuards();
    wrapDashboardTabs();
    wrapProgressAndEnrollmentFlows();
    wrapInstructorActions();
  }

  async function init() {
    ensureSkillForgeState();
    installOverrides();
    applyDashboardTab(localStorage.getItem("skillforge-dashboard-tab") || "overview");
    decorateAuthForm();
    await refreshAuthState();
    const skillState = appState();
    if (skillState && skillState.view === "instructor" && !isInstructorUser() && typeof window.showView === "function") {
      window.showView(state.authenticated ? "dashboard" : "home", { replace: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      init();
    }, { once: true });
  } else {
    init();
  }
})();
