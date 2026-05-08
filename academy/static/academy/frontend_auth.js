(function () {
  const state = {
    authenticated: false,
    user: null,
    session: null
  };

  function setAuthState(payload) {
    state.authenticated = !!(payload && payload.user);
    state.user = payload && payload.user ? payload.user : null;
    state.session = payload && payload.session ? payload.session : null;
    if (window.SkillForgeApp && window.SkillForgeApp.state) {
      window.SkillForgeApp.state.currentUser = state.user;
      window.SkillForgeApp.state.isAuthenticated = state.authenticated;
    }
    renderNavAuth();
  }

  function clearAuthState() {
    setAuthState({ user: null, session: null });
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
      signIn: buttons.find((button) => button.textContent.indexOf("Sign In") >= 0) || null,
      getStarted: buttons.find((button) => button.textContent.indexOf("Get Started") >= 0) || null
    };
  }

  function removeBridgeButtons() {
    const existing = document.querySelectorAll("[data-auth-bridge]");
    existing.forEach((node) => node.remove());
  }

  function renderNavAuth() {
    const parts = getNavAuthButtons();
    if (!parts.actions) {
      return;
    }

    removeBridgeButtons();

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
  }

  async function requestJson(url, options) {
    const init = Object.assign(
      {
        credentials: "same-origin",
        headers: {}
      },
      options || {}
    );
    if (init.body && !init.headers["Content-Type"]) {
      init.headers["Content-Type"] = "application/json";
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

  async function refreshAuthState() {
    const result = await requestJson("/api/auth/me", { method: "GET" });
    if (result.response.ok && result.data.authenticated) {
      setAuthState(result.data);
      return true;
    }
    clearAuthState();
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
        submitButton.textContent = mode === "login" ? "Sign In ->" : "Create Account ->";
      }
      return;
    }

    setAuthState(result.data);
    setInlineStatus("success", mode === "login" ? "Signed in successfully." : "Account created successfully.");
    if (typeof window.closeModal === "function") {
      window.closeModal();
    }
    if (typeof window.showView === "function") {
      window.showView(mode === "login" ? "dashboard" : "courses");
    }
    safeToast(
      mode === "login" ? "Signed in" : "Account created",
      mode === "login" ? "Your session is now active." : "Your account was created and signed in.",
      "success"
    );
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

  function installOverrides() {
    document.addEventListener("submit", interceptAuthSubmit, true);
    window.startOAuth = handleOAuthBridge;
    window.handleAuthSubmit = function (event) {
      event.preventDefault();
      handleAuthSubmitBridge(event.currentTarget);
    };
  }

  function init() {
    installOverrides();
    refreshAuthState();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
