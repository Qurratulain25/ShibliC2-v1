import { Auth, showToast } from "./api.js";

const PAGES = ["dashboard", "recordings", "cameras", "users", "audit", "settings"];

export function initRouter() {
  window.addEventListener("hashchange", () => navigate(location.hash.slice(1) || "dashboard"));

  document.getElementById("sidebar")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".module-item[data-page]");
    if (!btn) return;
    if (btn.classList.contains("disabled")) {
      showToast(btn.dataset.phase ? `Available in Phase ${btn.dataset.phase}` : "Unavailable");
      return;
    }
    if (btn.dataset.adminOnly === "true" && !Auth.isAdmin()) {
      showToast("Administrator access required");
      return;
    }
    document.getElementById("appShell")?.classList.remove("sidebar-open");
    location.hash = btn.dataset.page;
  });

  navigate(location.hash.slice(1) || "dashboard");
}

function navigate(page) {
  if (!PAGES.includes(page)) page = "dashboard";
  if (page === "users" && !Auth.isAdmin()) page = "dashboard";
  if (page === "audit" && !Auth.isAdmin()) page = "dashboard";

  document.querySelectorAll(".page-view").forEach((el) => el.classList.add("hidden"));
  document.getElementById(`page-${page}`)?.classList.remove("hidden");

  document.querySelectorAll(".module-item[data-page]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === page);
  });

  const topbarControls = document.getElementById("dashboardToolbar");
  if (topbarControls) {
    const onDashboard = page === "dashboard";
    topbarControls.classList.toggle("hidden", !onDashboard);
    topbarControls.setAttribute("aria-hidden", onDashboard ? "false" : "true");
  }

  window.dispatchEvent(new CustomEvent("shibli:page", { detail: page }));
}

export function getPage() {
  return location.hash.slice(1) || "dashboard";
}
