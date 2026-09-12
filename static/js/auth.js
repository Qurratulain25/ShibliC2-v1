import { api, Auth, showToast } from "./api.js";

const MODE_KEY = "shibli_connection_mode";

function readSavedMode() {
  try {
    const saved = localStorage.getItem(MODE_KEY);
    return saved === "ip" ? "ip" : "lan";
  } catch {
    return "lan";
  }
}

function saveMode(mode) {
  try {
    localStorage.setItem(MODE_KEY, mode === "ip" ? "ip" : "lan");
  } catch { /* ignore */ }
}

function selectedLoginMode() {
  return document.getElementById("modeIpBtn")?.classList.contains("active") ? "ip" : "lan";
}

function setLoginMode(mode) {
  const lan = document.getElementById("modeLanBtn");
  const ip = document.getElementById("modeIpBtn");
  const isIp = mode === "ip";
  lan?.classList.toggle("active", !isIp);
  ip?.classList.toggle("active", isIp);
  lan?.setAttribute("aria-pressed", String(!isIp));
  ip?.setAttribute("aria-pressed", String(isIp));
}

export function connectionModeLabel(mode) {
  return mode === "ip" ? "IP / Online" : "LAN";
}

export function currentConnectionMode() {
  return Auth.user?.connectionMode || readSavedMode();
}

export async function initAuth() {
  const loginScreen = document.getElementById("loginScreen");
  const appShell = document.getElementById("appShell");
  const loginForm = document.getElementById("loginForm");
  const forgotForm = document.getElementById("forgotPasswordForm");

  window.addEventListener("shibli:session-expired", () => {
    loginScreen?.classList.remove("hidden");
    appShell?.classList.add("hidden");
    const err = document.getElementById("loginError");
    if (err) err.textContent = "Session expired — please sign in again.";
  });

  const setup = await fetch("/api/auth/setup-required")
    .then((r) => (r.ok ? r.json() : { setupRequired: false }))
    .catch(() => ({ setupRequired: false }));
  const title = document.getElementById("loginTitle");
  const submitBtn = document.getElementById("loginSubmit");

  if (setup.setupRequired) {
    title.textContent = "Create Administrator Account";
    submitBtn.textContent = "Create Admin & Login";
    document.getElementById("forgotPasswordBtn")?.classList.add("hidden");
  }

  document.getElementById("loginUser")?.setAttribute("value", "");
  document.getElementById("loginPass")?.setAttribute("value", "");
  setLoginMode(readSavedMode());
  document.getElementById("modeLanBtn")?.addEventListener("click", () => setLoginMode("lan"));
  document.getElementById("modeIpBtn")?.addEventListener("click", () => setLoginMode("ip"));

  document.getElementById("forgotPasswordBtn")?.addEventListener("click", () => {
    loginForm?.classList.add("hidden");
    forgotForm?.classList.remove("hidden");
    document.getElementById("forgotError").textContent = "";
  });

  document.getElementById("backToLoginBtn")?.addEventListener("click", () => {
    forgotForm?.classList.add("hidden");
    loginForm?.classList.remove("hidden");
  });

  forgotForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("forgotError");
    err.textContent = "";
    try {
      await api("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({
          username: document.getElementById("forgotUser").value.trim(),
          recovery_code: document.getElementById("forgotCode").value.trim(),
          new_password: document.getElementById("forgotNewPass").value,
        }),
        skipAuthRedirect: true,
      });
      showToast("Password reset — sign in with your new password");
      forgotForm.classList.add("hidden");
      loginForm.classList.remove("hidden");
      forgotForm.reset();
    } catch (ex) {
      err.textContent = ex.message || "Reset failed";
      if (String(ex.message).includes("500") || String(ex.message).toLowerCase().includes("server")) {
        err.textContent += " — restart SHIBLI C2 (scripts/restart-shibli.ps1) and try again.";
      }
    }
  });

  if (Auth.isLoggedIn()) {
    try {
      const res = await api("/api/auth/verify", { skipAuthRedirect: true });
      if (res?.user) Auth.setSession(Auth.token, res.user);
      loginScreen.classList.add("hidden");
      appShell.classList.remove("hidden");
      updateUserBadge();
      return true;
    } catch (ex) {
      if (ex.status === 401) {
        Auth.clear();
      } else {
        loginScreen.classList.add("hidden");
        appShell.classList.remove("hidden");
        updateUserBadge();
        return true;
      }
    }
  }

  loginScreen.classList.remove("hidden");
  appShell.classList.add("hidden");

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("loginUser").value.trim();
    const password = document.getElementById("loginPass").value;
    const err = document.getElementById("loginError");
    err.textContent = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in…";
    try {
      if (setup.setupRequired) {
        await api("/api/auth/create-first-admin", {
          method: "POST",
          body: JSON.stringify({ username, password }),
          skipAuthRedirect: true,
        });
      }
      const result = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username,
          password,
          connection_mode: selectedLoginMode(),
        }),
        skipAuthRedirect: true,
      });
      const mode = result.connectionMode || result.user?.connectionMode || selectedLoginMode();
      Auth.setSession(result.accessToken, { ...result.user, connectionMode: mode });
      saveMode(mode);
      loginScreen.classList.add("hidden");
      appShell.classList.remove("hidden");
      updateUserBadge();
      showToast(`Welcome, ${result.user.username}`);
      window.dispatchEvent(new CustomEvent("shibli:logged-in"));
    } catch (ex) {
      err.textContent = ex.message || "Invalid username or password";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = setup.setupRequired ? "Create Admin & Login" : "LOGIN";
    }
  });

  return false;
}

function updateUserBadge() {
  const el = document.getElementById("userBadge");
  if (el && Auth.user) {
    const full = `${Auth.user.username} · ${Auth.user.roleName}`;
    el.textContent = Auth.user.username;
    el.title = full;
    el.setAttribute("aria-label", full);
  }
}

export async function switchConnectionMode(mode) {
  const result = await api("/api/auth/connection-mode", {
    method: "POST",
    body: JSON.stringify({ connection_mode: mode }),
  });
  const next = result.connectionMode || mode;
  Auth.setSession(result.accessToken, { ...(result.user || Auth.user), connectionMode: next });
  saveMode(next);
  return next;
}

export function bindLogout() {
  document.getElementById("logoutBtn")?.addEventListener("click", async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch { /* session may already be invalid */ }
    Auth.clear();
    window.dispatchEvent(new CustomEvent("shibli:logged-out"));
    document.getElementById("appShell")?.classList.add("hidden");
    document.getElementById("loginScreen")?.classList.remove("hidden");
    document.getElementById("loginError").textContent = "";
    document.getElementById("loginForm")?.reset();
    setLoginMode(readSavedMode());
  });
}
