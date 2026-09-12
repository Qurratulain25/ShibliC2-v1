import { api, showToast } from "../api.js";
import { setKeyboardEnabled } from "../keyboard.js";
import { applyTheme } from "../theme.js";

export function initSettingsPage() {
  const saveDialog = document.getElementById("saveSettingsDialog");
  const settingsContent = document.getElementById("settingsContent");
  const settingsNav = document.getElementById("settingsNav");
  const searchInput = document.getElementById("settingsSearch");
  const noResults = document.getElementById("settingsNoResults");

  function showPane(paneId) {
    settingsNav?.querySelectorAll(".settings-nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.pane === paneId);
    });
    settingsContent?.querySelectorAll(".settings-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.dataset.pane === paneId);
    });
    settingsContent?.classList.remove("settings-search-mode");
    if (searchInput) searchInput.value = "";
    clearSearchFilter();
    if (noResults) noResults.classList.add("hidden");
  }

  function clearSearchFilter() {
    settingsContent?.querySelectorAll(".setting-row, .settings-pane").forEach((el) => {
      el.classList.remove("hidden-by-search");
    });
    settingsNav?.querySelectorAll(".settings-nav-item").forEach((btn) => {
      btn.classList.remove("hidden-by-search");
    });
  }

  function applySearch(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      settingsContent?.classList.remove("settings-search-mode");
      clearSearchFilter();
      if (noResults) noResults.classList.add("hidden");
      return;
    }

    settingsContent?.classList.add("settings-search-mode");
    let anyMatch = false;

    settingsContent?.querySelectorAll(".settings-pane").forEach((pane) => {
      let paneMatch = false;
      pane.querySelectorAll(".setting-row").forEach((row) => {
        const title = row.querySelector(".setting-title")?.textContent || "";
        const desc = row.querySelector(".setting-desc")?.textContent || "";
        const keywords = row.dataset.keywords || "";
        const match = `${title} ${desc} ${keywords}`.toLowerCase().includes(q);
        row.classList.toggle("hidden-by-search", !match);
        if (match) paneMatch = true;
      });
      pane.classList.toggle("hidden-by-search", !paneMatch);
      if (paneMatch) anyMatch = true;
      const navBtn = settingsNav?.querySelector(`[data-pane="${pane.dataset.pane}"]`);
      navBtn?.classList.toggle("hidden-by-search", !paneMatch);
    });

    if (noResults) noResults.classList.toggle("hidden", anyMatch);
  }

  settingsNav?.addEventListener("click", (e) => {
    const btn = e.target.closest(".settings-nav-item");
    if (!btn?.dataset.pane) return;
    showPane(btn.dataset.pane);
  });

  searchInput?.addEventListener("input", () => {
    clearTimeout(applySearch.timer);
    applySearch.timer = setTimeout(() => applySearch(searchInput.value), 120);
  });

  document.getElementById("resetSettingsBtn")?.addEventListener("click", async () => {
    if (!confirm("Reset settings to default? Recordings and users will not be deleted.")) return;
    try {
      await api("/api/settings/reset", { method: "POST" });
      showToast("Settings reset to default");
      loadSettings();
    } catch (ex) {
      showToast("Settings could not be saved.");
    }
  });

  document.getElementById("saveSettingsBtn")?.addEventListener("click", () => {
    saveDialog?.showModal();
  });

  document.getElementById("saveSettingsCancel")?.addEventListener("click", () => {
    saveDialog?.close();
  });

  document.getElementById("saveSettingsConfirm")?.addEventListener("click", async () => {
    saveDialog?.close();
    try {
      const patch = {
        recording_path: document.getElementById("settingRecPath").value,
        keyboard_enabled: document.getElementById("settingKeyboard").checked,
        default_page_size: parseInt(document.getElementById("settingPageSize").value, 10),
        app_port: parseInt(document.getElementById("settingAppPort").value, 10) || 8080,
        theme: document.getElementById("settingTheme").value,
        ptz_method: document.getElementById("settingPtzMethod").value,
        lrf_method: document.getElementById("settingLrfMethod").value,
        illuminator_method: document.getElementById("settingIllumMethod").value,
        ptz_systems: [
          { id: "ptz-1", label: document.getElementById("ptz1Label").value, default: true },
          { id: "ptz-2", label: document.getElementById("ptz2Label").value, default: false },
        ],
        service_urls: {
          core: document.getElementById("settingCoreUrl").value.trim(),
          controls: document.getElementById("settingControlsUrl").value.trim(),
          vss: document.getElementById("settingVssUrl").value.trim(),
        },
        device_drivers: {
          ptz: document.getElementById("driverPtz").value.trim(),
          lrf: document.getElementById("driverLrf").value.trim(),
          illumination: document.getElementById("driverIllum").value.trim(),
        },
        osd_config: {
          show_logo: document.getElementById("osdShowLogo").checked,
          show_telemetry: document.getElementById("osdShowTelemetry").checked,
          logo_text: document.getElementById("osdLogoText").value.trim() || "SHIBLI C2",
          custom_text: document.getElementById("osdCustomText").value.trim(),
          position: document.getElementById("osdPosition").value,
        },
        default_layout: document.getElementById("settingDefaultView").value,
      };
      await api("/api/settings", { method: "PUT", body: JSON.stringify(patch) });
      setKeyboardEnabled(patch.keyboard_enabled);
      applyTheme(patch.theme);
      showToast("Settings saved successfully.");
      loadSettings();
    } catch (ex) {
      showToast("Settings could not be saved.");
    }
  });

  saveDialog?.addEventListener("click", (e) => {
    if (e.target === saveDialog) saveDialog.close();
  });

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "settings") loadSettings();
  });
}

async function loadSettings() {
  const backend = document.getElementById("backendStatus");
  const cfg = document.getElementById("configPreview");
  const dbPath = document.getElementById("dbPathDisplay");
  try {
    const [status, settingsRes, config] = await Promise.all([
      api("/api/backend/status"),
      api("/api/settings"),
      api("/api/config"),
    ]);
    const s = settingsRes.settings;
    const urls = s.service_urls || {};
    backend.innerHTML = Object.entries(status)
      .map(([k, v]) => {
        const label = { core: "Core Service", controls: "Controls Service", vss: "VSS Service" }[k] || k;
        return `<div class="status-row"><span>${label}</span><span class="${v.online ? "online" : "offline"}">${v.online ? "Online" : "Offline"}</span><code>${v.url || ""}</code></div>`;
      })
      .join("");
    cfg.textContent = JSON.stringify(config, null, 2);
    if (dbPath) {
      dbPath.textContent = settingsRes.database?.path || "—";
      dbPath.title = settingsRes.database?.encrypted ? "SQLCipher encrypted" : "Plain SQLite";
    }
    document.getElementById("settingRecPath").value = s.recording_path || "";
    document.getElementById("settingKeyboard").checked = s.keyboard_enabled !== false;
    document.getElementById("settingPageSize").value = s.default_page_size || 20;
    document.getElementById("settingAppPort").value = s.app_port || 8080;
    document.getElementById("settingTheme").value = s.theme || localStorage.getItem("shibli_theme") || "dark";
    document.getElementById("settingPtzMethod").value = s.ptz_method || "onvif";
    document.getElementById("settingLrfMethod").value = s.lrf_method || "none";
    document.getElementById("settingIllumMethod").value = s.illuminator_method || "none";
    setKeyboardEnabled(s.keyboard_enabled !== false);
    document.getElementById("settingCoreUrl").value = urls.core || "http://127.0.0.1:3000";
    document.getElementById("settingControlsUrl").value = urls.controls || "http://127.0.0.1:8001";
    document.getElementById("settingVssUrl").value = urls.vss || "http://127.0.0.1:8000";
    const drivers = s.device_drivers || {};
    document.getElementById("driverPtz").value = drivers.ptz || "shibli_controls";
    document.getElementById("driverLrf").value = drivers.lrf || "shibli_controls";
    document.getElementById("driverIllum").value = drivers.illumination || "shibli_controls";
    const ptz = s.ptz_systems || [];
    document.getElementById("ptz1Label").value = ptz[0]?.label || "PTZ 1 - Day Camera";
    document.getElementById("ptz2Label").value = ptz[1]?.label || "PTZ 2 - Thermal Camera";
    const osd = s.osd_config || {};
    document.getElementById("osdShowLogo").checked = osd.show_logo !== false;
    document.getElementById("osdShowTelemetry").checked = osd.show_telemetry !== false;
    document.getElementById("osdLogoText").value = osd.logo_text || "SHIBLI C2";
    document.getElementById("osdCustomText").value = osd.custom_text || "";
    document.getElementById("osdPosition").value = osd.position || "bottom-left";
    const defaultView = document.getElementById("settingDefaultView");
    if (defaultView) defaultView.value = s.default_layout || "day_thermal";
  } catch (ex) {
    if (backend) backend.textContent = ex.message;
  }
}
