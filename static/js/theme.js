import { api } from "./api.js";

const THEME_KEY = "shibli_theme";

const PW_EYE_SHOW = `<svg class="pw-eye-show" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>`;
const PW_EYE_HIDE = `<svg class="pw-eye-hide" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M17.94 17.94A10.94 10.94 0 0112 20c-7 0-11-8-11-8a21.77 21.77 0 014.06-5.94M9.9 4.24A10.94 10.94 0 0112 4c7 0 11 8 11 8a21.8 21.8 0 01-5.06 6.94"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;

export function applyTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  const btn = document.getElementById("themeToggle");
  if (btn) btn.textContent = t === "light" ? "☀" : "☾";
}

export async function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  let theme = stored || "dark";
  if (!stored) {
    try {
      const res = await api("/api/settings");
      if (res.settings?.theme) theme = res.settings.theme;
    } catch {
      /* pre-login: localStorage only */
    }
  }
  applyTheme(theme);
}

export async function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ theme: next }) });
  } catch {
    /* saved locally */
  }
}

export function bindPasswordToggles() {
  document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
    if (!btn.querySelector(".pw-eye-show")) {
      btn.innerHTML = `${PW_EYE_SHOW}${PW_EYE_HIDE}`;
    }
    btn.addEventListener("click", () => {
      const id = btn.dataset.passwordToggle;
      const input = document.getElementById(id);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("is-visible", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
}
