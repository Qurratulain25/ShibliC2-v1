import { api, Auth, showToast } from "./api.js";
import { initAuth, bindLogout, connectionModeLabel, currentConnectionMode, switchConnectionMode } from "./auth.js";
import { initRouter } from "./router.js";
import { initRecordingsPage } from "./pages/recordings.js";
import { initCamerasPage } from "./pages/cameras.js";
import { initUsersPage } from "./pages/users.js";
import { initSettingsPage } from "./pages/settings.js";
import { initAuditPage } from "./pages/audit.js";
import { initTheme, toggleTheme, bindPasswordToggles } from "./theme.js";
import { initKeyboard } from "./keyboard.js";
import { connectGo2Rtc, stopAllGo2Rtc, stopGo2Rtc } from "./webrtc.js";
import { initDragZoom } from "./drag-zoom.js";

const state = {
  ptzMode: "abs",
  ptzSpeed: "medium",
  selectedIntensity: "med",
  activePtz: "ptz-1",
  activeCameraId: "",
  cameras: [],
  localCameras: [],
  layout: "day_thermal",
  customMaxChannel: null,
  mapping: null,
  serviceStatus: null,
  controlsOnline: false,
  hwSimulate: false,
  vssOnline: false,
  recordingMode: "off",
  recordingStartedAt: null,
  streamStatus: { day: "none", thermal: "none" },
  ptzTarget: "both",
  ptzLabels: {},
  customPanels: [],
  osdConfig: {
    show_telemetry: true,
    show_logo: true,
    logo_text: "SHIBLI C2",
    custom_text: "",
    position: "bottom-left",
  },
  go2rtc: null,
  dayZoom: 1,
  thermalZoom: 1,
  lrfContinuous: false,
  dayAutoFocus: false,
  thermalAutoFocus: false,
  autoPan: false,
  ptzTelemetry: { azimuth: 0, elevation: 0, zoom: 1 },
};

const RECORD_LABELS = {
  off: "Record Off",
  ch1: "Record Day",
  ch2: "Record Thermal",
  both: "Record Both",
};

const LEGACY_LAYOUT_MAP = {
  single: "day_full",
  dual: "day_thermal",
  triple: "day_thermal",
  quad: "custom",
  quad6: "custom",
  grid9: "custom",
  grid16: "custom",
};

function normalizeLayout(layout) {
  return LEGACY_LAYOUT_MAP[layout] || layout || "day_thermal";
}

async function refreshHardwareState() {
  try {
    const [boot, local] = await Promise.all([
      api("/api/backend/bootstrap").catch(() => ({})),
      api("/api/cameras/local").catch(() => ({ cameras: [] })),
    ]);
    state.cameras = boot.cameras || [];
    state.localCameras = local.cameras || [];
    state.controlsOnline = Boolean(boot.mapping?.controlsOnline ?? boot.controlsCameras?.length);
    if (!state.activeCameraId && state.cameras[0]) {
      state.activeCameraId = state.cameras[0].controlsId || "";
    }
    await bindLocalCameraStreams();
    populatePtzSelect();
    highlightPtzPanels();
    state.hardwareCacheAt = Date.now();
  } catch { /* offline */ }
}

let hardwareRefreshPromise = null;
async function ensureHardwareState(maxAgeMs = 10000) {
  if (state.hardwareCacheAt && Date.now() - state.hardwareCacheAt < maxAgeMs) return;
  if (!hardwareRefreshPromise) {
    hardwareRefreshPromise = refreshHardwareState().finally(() => {
      hardwareRefreshPromise = null;
    });
  }
  await hardwareRefreshPromise;
}

function hasCameraConfigured() {
  return Boolean(state.activeCameraId)
    || state.localCameras.some((c) => c.enabled)
    || state.cameras.length > 0;
}

async function refreshControlsOnline() {
  try {
    const st = await api("/api/backend/status");
    state.controlsOnline = Boolean(st.controls?.online);
    state.vssOnline = Boolean(st.vss?.online);
    state.coreOnline = Boolean(st.core?.online);
  } catch {
    state.controlsOnline = false;
    state.vssOnline = false;
    state.coreOnline = false;
  }
}

function ptzCanMove() {
  return Auth.canControl() && (state.hwSimulate || state.controlsOnline || hasCameraConfigured());
}

function ptzRequestBody(direction) {
  return {
    direction,
    speed: state.ptzSpeed,
    mode: state.ptzMode,
    ptz_id: state.activePtz,
    ...cameraPayload(),
  };
}

async function warmPtzCamera() {
  if (!ptzCanMove()) return;
  resolveActiveCameraFromPtz();
  try {
    await api("/api/ptz/warm", { method: "POST", body: JSON.stringify(ptzRequestBody("stop")) });
  } catch { /* optional */ }
}

async function hardwareReady() {
  await refreshControlsOnline();
  await ensureHardwareState();
  resolveActiveCameraFromPtz();
  if (!Auth.canControl()) {
    showToast("View-only mode (VIEWER role)");
    return false;
  }
  if (!state.hwSimulate && !hasCameraConfigured()) {
    showToast("No PTZ device mapped.");
    return false;
  }
  if (!state.controlsOnline && !state.hwSimulate) {
    showToast("Hardware controls offline — start the controls service.");
    return false;
  }
  return true;
}

async function runHardwareAction(label, fn) {
  if (!Auth.canControl()) {
    showToast("View-only mode (VIEWER role)");
    return;
  }
  await refreshControlsOnline();
  await ensureHardwareState();
  resolveActiveCameraFromPtz();
  if (!state.hwSimulate && !hasCameraConfigured()) {
    showToast("No PTZ device mapped.");
    return;
  }
  if (!state.controlsOnline && !state.hwSimulate) {
    showToast("Hardware controls offline — start the controls service.");
    return;
  }
  try {
    const res = await fn();
    if (res && res.ok === false) {
      throw new Error(res.error || `${label} failed`);
    }
    const tag = res?.simulated || res?.fallback ? " (simulated)" : "";
    showToast(`${label} — command sent${tag}.`);
  } catch (ex) {
    showToast(`Command failed: ${ex.message || label}`);
  }
}

function isSharedPtzHead(ptzId) {
  const mapped = state.localCameras.filter((c) => c.enabled && c.ptzMapping === ptzId);
  const types = new Set(mapped.map((c) => (c.cameraType || "").toLowerCase()));
  return mapped.length >= 2 && types.has("day") && types.has("thermal");
}

function updatePtzHeadUi(ptzId) {
  const shared = isSharedPtzHead(ptzId);
  document.getElementById("ptzTargetRow")?.classList.toggle("hidden", !shared);
  document.getElementById("ptzHeadLabel")?.classList.toggle("hidden", !shared);
}

function highlightPtzPanels() {
  const ptz = state.activePtz;
  const dayPanel = document.getElementById("dayPanel");
  const thermalPanel = document.getElementById("thermalPanel");
  const mapped = state.localCameras.filter((c) => c.enabled && c.ptzMapping === ptz);
  const shared = isSharedPtzHead(ptz);
  updatePtzHeadUi(ptz);

  if (shared && state.ptzTarget === "both") {
    dayPanel?.classList.add("ptz-active");
    thermalPanel?.classList.add("ptz-active");
    return;
  }
  const dayMatch = mapped.some((c) => (c.cameraType || "").toLowerCase() === "day");
  const thermalMatch = mapped.some((c) => (c.cameraType || "").toLowerCase() === "thermal");
  dayPanel?.classList.toggle("ptz-active", dayMatch && (state.ptzTarget === "day" || !shared));
  thermalPanel?.classList.toggle("ptz-active", thermalMatch && (state.ptzTarget === "thermal" || !shared));
}

function resolveActiveCameraFromPtz() {
  const sel = document.getElementById("ptzSelect");
  const opt = sel?.selectedOptions?.[0];
  if (opt?.dataset?.ptz) {
    state.activePtz = opt.dataset.ptz;
    const selectedCam = state.localCameras.find((c) => {
      const cid = c.ipAddress ? `${c.ipAddress}:${c.onvifPort || 80}` : c.ptzMapping;
      return cid === opt.value;
    });
    const camType = (selectedCam?.cameraType || "").toLowerCase();
    if (camType === "day" || camType === "thermal") state.ptzTarget = camType;
  } else if (sel?.value && !sel.value.includes(":") && !sel.value.includes(".")) {
    state.activePtz = sel.value;
  }
  if (opt?.value && (opt.value.includes(":") || opt.value.includes("."))) {
    state.activeCameraId = opt.value;
    highlightPtzPanels();
    return;
  }
  const ptzVal = state.activePtz;
  const mapped = state.localCameras.filter((c) => c.enabled && c.ptzMapping === ptzVal);
  let pick = mapped[0];
  if (isSharedPtzHead(ptzVal)) {
    if (state.ptzTarget === "day") {
      pick = mapped.find((c) => (c.cameraType || "").toLowerCase() === "day") || pick;
    } else if (state.ptzTarget === "thermal") {
      pick = mapped.find((c) => (c.cameraType || "").toLowerCase() === "thermal") || pick;
    } else {
      pick = mapped.find((c) => (c.cameraType || "").toLowerCase() === "day") || pick;
    }
  }
  if (pick?.ipAddress) {
    state.activeCameraId = `${pick.ipAddress}:${pick.onvifPort || 80}`;
  } else {
    const bootCam = state.cameras.find((c) => c.controlsId);
    if (bootCam?.controlsId) state.activeCameraId = bootCam.controlsId;
  }
  highlightPtzPanels();
  document.querySelectorAll("[data-ptz-target]").forEach((b) => {
    b.classList.toggle("active", b.dataset.ptzTarget === state.ptzTarget);
  });
}

const ICONS = {
  grid: "▦", film: "▻", gear: "⚙", camera: "◉", users: "👤", audit: "📋",
  brain: "AI", map: "◇", radar: "◎",
};

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

function isRecordingChannel(mode, btnMode) {
  if (mode === "off") return false;
  if (btnMode === mode) return true;
  return mode === "both" && (btnMode === "ch1" || btnMode === "ch2");
}

function updateRecordingUi(mode) {
  document.querySelectorAll("[data-record]").forEach((btn) => {
    const btnMode = btn.dataset.record;
    btn.classList.toggle("active", btnMode === mode);
    btn.classList.toggle("recording-on", isRecordingChannel(mode, btnMode));
  });
  const showing = mode !== "off";
  document.getElementById("recordingStatus")?.classList.toggle("hidden", !showing);
  document.getElementById("dashboardToolbar")?.classList.toggle("is-recording", showing);
  if (!showing) {
    const timerEl = document.getElementById("recordingTimer");
    if (timerEl) timerEl.textContent = "00:00:00";
  }
}

function updateClock() {
  const el = document.getElementById("clock");
  if (el) el.textContent = new Date().toLocaleTimeString([], { hour12: false });
  const timerEl = document.getElementById("recordingTimer");
  if (timerEl && state.recordingMode !== "off" && state.recordingStartedAt) {
    timerEl.textContent = formatElapsed(Date.now() - state.recordingStartedAt);
  }
}

function renderModules(modules) {
  const nav = document.getElementById("moduleNav");
  if (!nav) return;
  nav.innerHTML = "";

  modules.forEach((mod) => {
    if (mod.admin_only && !Auth.isAdmin()) return;
    if (!mod.available) return;
    const btn = document.createElement("button");
    btn.className = "module-item";
    btn.dataset.page = mod.id;
    btn.dataset.phase = mod.phase;
    if (mod.admin_only) btn.dataset.adminOnly = "true";
    if (mod.id === "dashboard") btn.classList.add("active");
    btn.innerHTML = `<span class="icon">${ICONS[mod.icon] || "•"}</span><span>${mod.label}</span>`;
    nav.appendChild(btn);
  });
}

function cameraPayload() {
  const base = state.activeCameraId ? { camera_id: state.activeCameraId } : {};
  const target = state.ptzTarget === "day" || state.ptzTarget === "thermal" || state.ptzTarget === "both"
    ? state.ptzTarget
    : "both";
  return { ...base, ptz_id: state.activePtz, ptz_target: target };
}

function cameraForChannel(channel) {
  const want = (channel || "").toLowerCase();
  if (want !== "day" && want !== "thermal") return null;
  const typed = state.localCameras.filter(
    (c) => c.enabled && (c.cameraType || "").toLowerCase() === want && c.ipAddress
  );
  const onPtz = typed.filter((c) => c.ptzMapping === state.activePtz);
  return onPtz[0] || typed[0] || null;
}

function cameraPayloadForChannel(channel) {
  const payload = { ...cameraPayload() };
  const want = (channel || "").toLowerCase();
  if (want !== "day" && want !== "thermal") return payload;
  payload.channel = want;
  payload.ptz_target = want;
  const cam = cameraForChannel(want);
  if (cam?.ipAddress) {
    payload.camera_id = `${cam.ipAddress}:${cam.onvifPort || 80}`;
  }
  return payload;
}

async function loadBackendMapping() {
  try {
    const [boot, localRes] = await Promise.all([
      api("/api/backend/bootstrap"),
      api("/api/cameras/local").catch(() => ({ cameras: [] })),
    ]);
    state.localCameras = localRes.cameras || [];
    state.mapping = boot.mapping;
    state.cameras = boot.cameras || [];
    populatePtzSelect();

    const day = state.cameras[0];
    await bindLocalCameraStreams();

    updateMappingBanner(boot);

    if (boot.mapping?.needsSync && Auth.canControl()) {
      try {
        const sync = await api("/api/backend/sync", { method: "POST" });
        if (sync.synced?.length) {
          showToast(`Auto-synced ${sync.synced.length} camera(s) to hardware controls`);
          await refreshHardwareState();
        } else if (sync.error) {
          showToast(sync.error);
        }
      } catch (ex) {
        showToast(ex.message || "Camera sync failed — check SHIBLI-controls is running.");
      }
    }
    state.controlsOnline = Boolean(boot.mapping?.controlsOnline ?? boot.controlsCameras?.length);
    if (state.controlsOnline) warmPtzCamera();
  } catch (ex) {
    console.warn("backend mapping", ex);
    updateMappingBanner(null);
  }
}

function applyServiceStatus(services, mapping, camerasMapped) {
  const svc = services || state.serviceStatus || {};
  const m = mapping || state.mapping || {};
  const controlsOn = svc.controls?.online ?? m.controlsOnline ?? false;
  const localCount = m.localConfigured ?? camerasMapped ?? 0;
  const enabledCount = state.localCameras.filter((c) => c.enabled).length || localCount;
  const camerasConnected = enabledCount > 0 && (
    state.streamStatus.day === "live" || state.streamStatus.thermal === "live" || enabledCount > 0
  );

  const setChip = (id, text, on) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.textContent !== text) el.textContent = text;
    el.classList.toggle("online", on);
    el.classList.toggle("offline", !on);
  };
  const camText = camerasConnected ? `Cams: ${enabledCount}` : "Cams: Off";
  const hwText = state.hwSimulate
    ? "HW: Simulate"
    : (controlsOn ? "HW: Online" : "HW: Offline");
  if (
    camText === state._chipCamText
    && hwText === state._chipHwText
    && controlsOn === state.controlsOnline
    && state.hwSimulate === state._chipSim
  ) {
    return;
  }
  state._chipCamText = camText;
  state._chipHwText = hwText;
  state._chipSim = state.hwSimulate;
  setChip("chipCamStatus", camText, camerasConnected);
  setChip("chipHwStatus", hwText, controlsOn || state.hwSimulate);

  const statusEl = document.getElementById("systemStatusText");
  if (statusEl) {
    statusEl.textContent = "App Ready";
    statusEl.title = camerasConnected
      ? `${enabledCount} camera(s) configured`
      : "No cameras connected — add cameras on Cameras page";
  }

  state.controlsOnline = controlsOn;
  state.vssOnline = Boolean(svc.vss?.online ?? m.vssOnline);
  updateHwOfflineNote();

  const recLabel = RECORD_LABELS[state.recordingMode] || "Recording Ready";
}

function updateMappingBanner(boot) {
  const el = document.getElementById("mappingBanner");
  if (!el) return;
  el.classList.add("hidden");
  el.setAttribute("aria-hidden", "true");
  if (!boot) return;
  state.mapping = boot.mapping || null;
  if (boot.services) state.serviceStatus = boot.services;
  applyServiceStatus(boot.services, boot.mapping, boot.mapping?.localConfigured);
}

function handleKeyboardAction(action, phase = "tap") {
  const dirMap = {
    ptz_up: "up",
    ptz_down: "down",
    ptz_left: "left",
    ptz_right: "right",
    ptz_up_left: "up_left",
    ptz_up_right: "up_right",
    ptz_down_left: "down_left",
    ptz_down_right: "down_right",
  };
  if (dirMap[action] || action === "zoom_in" || action === "zoom_out") {
    const selector = dirMap[action]
      ? `[data-ptz="${dirMap[action]}"]`
      : `.lens-stack [data-lens="${action}"]`;
    const btn = document.querySelector(selector);
    if (!btn) return;
    if (phase === "down") btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    else if (phase === "up") btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    else btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    return;
  }
  const map = {
    ptz_stop: () => document.querySelector('[data-ptz="stop"]')?.click(),
    ptz_home: () => document.querySelector('[data-ptz="home"]')?.click(),
    fullscreen: () => document.getElementById("fullscreenBtn")?.click(),
    exit_fullscreen: () => { if (document.fullscreenElement) document.exitFullscreen(); },
    ptz_system_1: () => { const s = document.getElementById("ptzSelect"); if (s?.options[0]) { s.selectedIndex = 0; s.dispatchEvent(new Event("change")); } },
    ptz_system_2: () => { const s = document.getElementById("ptzSelect"); if (s?.options[1]) { s.selectedIndex = 1; s.dispatchEvent(new Event("change")); } },
    toggle_record: () => document.querySelector('[data-record="both"]')?.click(),
  };
  map[action]?.();
}

async function loadConfig() {
  const [cfg, modData] = await Promise.all([api("/api/config"), api("/api/modules")]);
  document.title = cfg.system_name || "SHIBLI C2";
  document.getElementById("systemName").textContent = cfg.system_name || "SHIBLI C2";

  state.ptzLabels = {};
  (cfg.ptz_systems || []).forEach((ptz) => {
    state.ptzLabels[ptz.id] = ptz.label;
    if (ptz.default) state.activePtz = ptz.id;
  });

  renderModules(modData.modules || []);

  if (cfg.streams?.day_camera) attachStream("day", cfg.streams.day_camera);
  if (cfg.streams?.thermal) attachStream("thermal", cfg.streams.thermal);

  await bindLocalCameraStreams();
  await loadBackendMapping();
}

function ptzSystemLabel(ptzId) {
  if (state.ptzLabels?.[ptzId]) return state.ptzLabels[ptzId];
  const n = String(ptzId || "").replace(/^ptz-/, "");
  return n ? `PTZ ${n}` : "PTZ";
}

function populatePtzSelect() {
  const sel = document.getElementById("ptzSelect");
  if (!sel) return;
  const targets = state.localCameras.filter((c) => c.enabled && c.ptzMapping && c.ptzMapping !== "none");
  const prev = sel.value;
  sel.innerHTML = "";
  if (!targets.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No PTZ device mapped.";
    sel.appendChild(opt);
    return;
  }
  targets.forEach((cam) => {
    const opt = document.createElement("option");
    const controlsId = cam.ipAddress ? `${cam.ipAddress}:${cam.onvifPort || 80}` : cam.ptzMapping;
    opt.value = controlsId;
    opt.dataset.ptz = cam.ptzMapping;
    opt.textContent = `${ptzSystemLabel(cam.ptzMapping)} - ${cam.name || cam.cameraType || "Camera"}`;
    sel.appendChild(opt);
  });
  const restore = [...sel.options].find((o) => o.value === prev);
  if (restore) {
    sel.value = prev;
  } else {
    const dayOpt = [...sel.options].find((o) => /day/i.test(o.textContent));
    if (dayOpt) sel.value = dayOpt.value;
  }
  resolveActiveCameraFromPtz();
}

function setStreamStatus(channel, status, message) {
  state.streamStatus[channel] = status;
  const label = document.getElementById(channel === "thermal" ? "thermalStatusLabel" : "dayStatusLabel");
  const video = document.getElementById(channel === "thermal" ? "thermalStream" : "dayStream");
  const placeholder = document.querySelector(channel === "thermal" ? ".thermal-placeholder" : ".day-placeholder");
  if (!label) return;
  label.textContent = message;
  if (status === "live") {
    video?.classList.remove("hidden");
    if (placeholder) placeholder.style.display = "none";
  } else {
    video?.classList.add("hidden");
    if (placeholder) placeholder.style.display = "";
  }
  applyServiceStatus(state.serviceStatus, state.mapping, state.localCameras.filter((c) => c.enabled).length);
}

function setGridLayout(count) {
  const n = parseInt(count, 10);
  document.querySelectorAll(".grid-segmented [data-grid]").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.grid, 10) === n);
  });
  const matrix = document.getElementById("videoMatrix");
  if (!matrix) return;
  matrix.querySelectorAll(".grid-slot-empty").forEach((el) => el.remove());
  ["grid-layout-4", "grid-layout-9", "grid-layout-16"].forEach((c) => matrix.classList.remove(c));

  if (n === 1) {
    setLayout("day_full");
    return;
  }
  setLayout("custom");
  matrix.classList.add(`grid-layout-${n}`);
  const slots = Math.max(0, n - 2);
  for (let i = 0; i < slots; i += 1) {
    const slot = document.createElement("div");
    slot.className = "grid-slot-empty panel";
    slot.textContent = `Panel ${i + 3}`;
    matrix.appendChild(slot);
  }
}

async function pollPtzStatus() {
  if (!Auth.isLoggedIn()) return;
  if (state.hwSimulate) return; // local telemetry already updated by simulate commands
  if (!state.controlsOnline) return;
  try {
    const cam = state.activeCameraId || "";
    const q = cam ? `?camera_id=${encodeURIComponent(cam)}` : "";
    const tel = await api(`/api/ptz/status${q}`);
    state.ptzTelemetry = tel;
  } catch {
    /* offline */
  }
}

async function pollSystemDiag() {
  if (!Auth.isLoggedIn()) return;
  try {
    const d = await api("/api/diag");
    const setDot = (id, on) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("online", Boolean(on));
    };
    setDot("diagGo2rtc", d.go2rtc?.online);
    setDot("diagDay", d.day_camera?.reachable);
    setDot("diagThermal", d.thermal_camera?.reachable);
    setDot("diagLrf", d.lrf?.online);
    setDot("diagHw", d.controls?.online);
    if (d.storage?.low && !state._storageWarned) {
      state._storageWarned = true;
      showToast(`Storage low: ${d.storage.free_gb} GB free`);
    }
    if (!d.storage?.low) state._storageWarned = false;
  } catch {
    /* ignore */
  }
}

async function pollLrfDistance() {
  if (!state.lrfContinuous || !Auth.isLoggedIn()) return;
  try {
    const res = await api("/api/lrf/distance");
    if (res.range_m != null) {
      const rangeInput = document.getElementById("rangeInput");
      if (rangeInput) rangeInput.value = `${res.range_m} m`;
    }
  } catch {
    /* ignore */
  }
}

function applyChannelZoom(channel, scale, cx = 0.5, cy = 0.5) {
  const videoId = channel === "thermal" ? "thermalStream" : "dayStream";
  const video = document.getElementById(videoId);
  if (!video) return;
  const key = channel === "thermal" ? "thermalZoom" : "dayZoom";
  const z = Math.max(1, Math.min(8, scale));
  state[key] = z;
  if (z <= 1.001) {
    video.style.transform = "";
    video.style.transformOrigin = "";
    return;
  }
  video.style.transformOrigin = `${(cx * 100).toFixed(1)}% ${(cy * 100).toFixed(1)}%`;
  video.style.transform = `scale(${z.toFixed(3)})`;
}

function resetChannelZoom(channel) {
  applyChannelZoom(channel, 1);
  api("/api/ptz/lens", {
    method: "POST",
    body: JSON.stringify({ action: "zoom_out", ptz_id: state.activePtz, ...cameraPayload() }),
  }).catch(() => {});
}

function applyThermalZoom(direction) {
  const z = state.thermalZoom || 1;
  const next = direction === "in" ? Math.min(8, z * 1.12) : Math.max(1, z / 1.12);
  applyChannelZoom("thermal", next);
  api("/api/ptz/lens", {
    method: "POST",
    body: JSON.stringify({ action: direction === "in" ? "zoom_in" : "zoom_out", ptz_id: state.activePtz, ...cameraPayload() }),
  }).catch(() => {});
}

function applyDayZoom(direction) {
  const z = state.dayZoom || 1;
  const next = direction === "in" ? Math.min(8, z * 1.12) : Math.max(1, z / 1.12);
  applyChannelZoom("day", next);
  api("/api/ptz/lens", {
    method: "POST",
    body: JSON.stringify({ action: direction === "in" ? "zoom_in" : "zoom_out", ptz_id: state.activePtz, ...cameraPayload() }),
  }).catch(() => {});
}

function sendPtzNudgeFromRegion(cx, cy) {
  const panX = cx - 0.5;
  const panY = cy - 0.5;
  if (Math.abs(panX) < 0.08 && Math.abs(panY) < 0.08) return;
  let direction = "right";
  if (Math.abs(panY) > Math.abs(panX)) direction = panY < 0 ? "up" : "down";
  else direction = panX < 0 ? "left" : "right";
  api("/api/ptz/move", {
    method: "POST",
    body: JSON.stringify({ direction, speed: state.ptzSpeed, mode: "rel", ptz_id: state.activePtz, ...cameraPayload() }),
  }).catch(() => {});
}

let autoPanTimer = null;
const PATROL_DIRS = ["right", "right", "down", "left", "left", "up"];
let patrolIdx = 0;

async function toggleAutoPan() {
  const btn = document.getElementById("autoPanBtn");
  state.autoPan = !state.autoPan;
  btn?.classList.toggle("active", state.autoPan);
  try {
    await api("/api/ptz/auto-pan", {
      method: "POST",
      body: JSON.stringify({ enabled: state.autoPan, speed: state.ptzSpeed, ...cameraPayload() }),
    });
  } catch (ex) {
    showToast(ex.message || "Auto-pan failed");
    state.autoPan = !state.autoPan;
    btn?.classList.toggle("active", state.autoPan);
    return;
  }
  if (autoPanTimer) {
    clearInterval(autoPanTimer);
    autoPanTimer = null;
  }
  if (state.autoPan) {
    showToast("Auto-pan patrol started");
    autoPanTimer = setInterval(() => {
      const direction = PATROL_DIRS[patrolIdx % PATROL_DIRS.length];
      patrolIdx += 1;
      api("/api/ptz/move", {
        method: "POST",
        body: JSON.stringify({ direction, speed: state.ptzSpeed, mode: "rel", ptz_id: state.activePtz, ...cameraPayload() }),
      }).catch(() => {});
    }, 2200);
  } else {
    patrolIdx = 0;
    api("/api/ptz/move", {
      method: "POST",
      body: JSON.stringify({ direction: "stop", speed: state.ptzSpeed, mode: state.ptzMode, ptz_id: state.activePtz, ...cameraPayload() }),
    }).catch(() => {});
    showToast("Auto-pan stopped");
  }
}

async function loadGo2RtcConfig() {
  try {
    const cfg = await api("/api/go2rtc/config");
    state.go2rtc = cfg;
    return cfg;
  } catch {
    state.go2rtc = null;
    return null;
  }
}

async function attachStream(channel, url) {
  const videoId = channel === "thermal" ? "thermalStream" : "dayStream";
  const video = document.getElementById(videoId);
  if (!video) return;

  setStreamStatus(channel, "connecting", "Connecting…");
  const cfg = state.go2rtc?.online ? state.go2rtc : await loadGo2RtcConfig();

  if (cfg?.online && cfg?.enabled) {
    const streamId = cfg.streams?.[channel];
    try {
      await connectGo2Rtc(streamId, video, cfg.api_url, (connState) => {
        if (connState === "connected") setStreamStatus(channel, "live", "");
      });
      setStreamStatus(channel, "live", "");
      return;
    } catch (ex) {
      console.warn("WebRTC connect failed", channel, ex);
    }
  }

  if (url && (url.includes("/mjpeg") || url.endsWith(".mjpg") || url.includes("multipart"))) {
    video.src = url;
    video.classList.remove("hidden");
    video.onloadeddata = () => setStreamStatus(channel, "live", "");
    video.onerror = () => setStreamStatus(channel, "error", "Stream not reachable");
    return;
  }

  if (url) {
    setStreamStatus(channel, "error", "Start go2rtc: ./scripts/start-go2rtc.sh");
  } else {
    setStreamStatus(channel, "none", "No camera saved · go2rtc offline");
  }
}

async function bindLocalCameraStreams() {
  const dayCam = state.localCameras.find((c) => c.enabled && (c.cameraType || "").toLowerCase() === "day");
  const thermalCam = state.localCameras.find((c) => c.enabled && (c.cameraType || "").toLowerCase() === "thermal");
  const cfg = state.go2rtc?.online ? state.go2rtc : await loadGo2RtcConfig();
  if (dayCam && (dayCam.hasRtsp || dayCam.rtspUrl)) attachStream("day", dayCam.rtspUrl || "configured");
  else {
    stopChannel("day");
    setStreamStatus("day", "none", "No camera for this connection mode");
  }
  if (thermalCam && (thermalCam.hasRtsp || thermalCam.rtspUrl)) attachStream("thermal", thermalCam.rtspUrl || "configured");
  else {
    stopChannel("thermal");
    setStreamStatus("thermal", "none", "No camera for this connection mode");
  }
  populateCustomCameraSelect();
}

function stopChannel(channel) {
  const videoId = channel === "thermal" ? "thermalStream" : "dayStream";
  const video = document.getElementById(videoId);
  if (video) stopGo2Rtc(video);
}

function populateCustomCameraSelect() {
  const sel = document.getElementById("customCamSelect");
  if (!sel) return;
  const cams = state.localCameras.filter((c) => c.enabled);
  sel.innerHTML = cams.length
    ? cams.map((c) => `<option value="${c.id}">${c.name} (${c.cameraType})</option>`).join("")
    : "<option value=''>No cameras configured</option>";
}

function setRecordingMode(mode, opts = {}) {
  const next = mode || "off";
  const prev = state.recordingMode;
  if (prev !== next) {
    if (next !== "off" && prev === "off") {
      state.recordingStartedAt = Date.now();
    } else if (next === "off") {
      state.recordingStartedAt = null;
    }
    state.recordingMode = next;
    applyServiceStatus(state.serviceStatus, state.mapping, state.localCameras.filter((c) => c.enabled).length);
  } else if (opts.fromServer && next !== "off" && !state.recordingStartedAt) {
    state.recordingStartedAt = Date.now();
  }
  updateRecordingUi(next);
}

function channelLabel(channel) {
  return channel === "thermal" ? "Thermal" : "Day";
}

function panelDisplayName(cam, channel) {
  return `${cam.name} — ${channelLabel(channel)}`;
}

function updateCustomEmptyState() {
  const empty = document.getElementById("customEmptyState");
  if (!empty) return;
  const count = document.querySelectorAll("#videoMatrix .video-panel.extra").length;
  const show = state.layout === "custom" && count === 0;
  empty.classList.toggle("hidden", !show);
  empty.setAttribute("aria-hidden", show ? "false" : "true");
}

function updateHwOfflineNote() {
  const note = document.getElementById("hwOfflineNote");
  if (!note) return;
  const show = !state.controlsOnline && !state.hwSimulate;
  note.classList.toggle("hidden", !show);
}

function countVisiblePanels() {
  if (state.layout === "custom") {
    return document.querySelectorAll("#videoMatrix .video-panel.extra").length;
  }
  return [...document.querySelectorAll("#videoMatrix .video-panel:not(.extra)")].filter(
    (p) => !p.classList.contains("hidden"),
  ).length;
}

function applyAutoGridLayout() {
  const matrix = document.getElementById("videoMatrix");
  if (!matrix || state.layout !== "custom") {
    updateCustomEmptyState();
    return;
  }
  const classes = ["auto-arrange-1", "auto-arrange-2", "auto-arrange-3", "auto-arrange-4", "auto-arrange-6", "auto-arrange-9", "auto-arrange-16"];
  matrix.classList.remove(...classes);
  const count = countVisiblePanels();
  if (!count) {
    updateCustomEmptyState();
    return;
  }
  const cls = count <= 1 ? "auto-arrange-1"
    : count === 2 ? "auto-arrange-2"
      : count === 3 ? "auto-arrange-3"
        : count === 4 ? "auto-arrange-4"
          : count <= 6 ? "auto-arrange-6"
            : count <= 9 ? "auto-arrange-9"
              : "auto-arrange-16";
  matrix.classList.add(cls);
  updateCustomEmptyState();
}

function bindCustomPanel(article, cam, channel) {
  const img = article.querySelector("img");
  const streamUrl = channel === "thermal"
    ? (cam.thermalRtspUrl || cam.rtspUrl)
    : cam.rtspUrl;
  const placeholder = article.querySelector(".placeholder-label");
  if (streamUrl && img) {
    img.onload = () => { article.querySelector(".placeholder").style.display = "none"; img.classList.remove("hidden"); };
    img.onerror = () => { placeholder.textContent = "Camera configured, stream not reachable"; };
    img.src = streamUrl;
  } else {
    placeholder.textContent = "No camera connected";
  }
  article.querySelector("[data-remove-extra]")?.addEventListener("click", () => {
    article.remove();
    applyAutoGridLayout();
    showToast("Panel removed");
  });
  article.querySelector("[data-shot-extra]")?.addEventListener("click", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0a1016";
    ctx.fillRect(0, 0, 1280, 720);
    if (img && !img.classList.contains("hidden") && img.complete && img.naturalWidth) {
      ctx.drawImage(img, 0, 0, 1280, 720);
    } else {
      ctx.fillStyle = "#8b9aab";
      ctx.font = "22px Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No stream — placeholder capture", 640, 360);
    }
    canvas.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `shibli_${cam.name}_${channel}_${new Date().toISOString().replace(/[:.]/g, "-")}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast("Screenshot saved");
    }, "image/png");
  });
  article.querySelector("[data-min-extra]")?.addEventListener("click", () => {
    article.classList.add("minimized");
    article.classList.remove("maximized");
    showToast("Panel minimized");
  });
  article.querySelector("[data-max-extra]")?.addEventListener("click", () => {
    const isMax = article.classList.contains("maximized");
    document.querySelectorAll("#videoMatrix .video-panel.extra").forEach((p) => {
      p.classList.remove("maximized", "minimized");
    });
    if (!isMax) {
      article.classList.add("maximized");
      showToast("Panel maximized");
    } else {
      showToast("Panel restored");
    }
  });
}

function addCustomPanel(cam, channel) {
  const matrix = document.getElementById("videoMatrix");
  const article = document.createElement("article");
  article.className = "panel video-panel extra";
  article.dataset.channel = channel;
  article.dataset.cameraId = String(cam.id);
  const title = panelDisplayName(cam, channel);
  article.innerHTML = `<header class="panel-title">
      <span><span class="live-dot${channel === "thermal" ? " thermal" : ""}"></span> ${title}</span>
      <span class="panel-actions">
        <button type="button" class="mini shot-btn" data-shot-extra title="Screenshot">📷</button>
        <button type="button" class="mini min-btn" data-min-extra title="Minimize">⊟</button>
        <button type="button" class="mini max-btn" data-max-extra title="Maximize">⛶</button>
        <button type="button" class="mini danger" data-remove-extra title="Remove">✕</button>
      </span>
    </header>
    <div class="video-frame${channel === "thermal" ? " thermal-frame" : ""}">
      <img class="stream hidden" alt="${title}" />
      <div class="placeholder${channel === "thermal" ? " thermal-placeholder" : " day-placeholder"}">
        ${channel === "thermal" ? "<div class=\"crosshair\"></div>" : ""}
        <div class="placeholder-label">Connecting…</div>
      </div>
    </div>`;
  matrix.appendChild(article);
  bindCustomPanel(article, cam, channel);
  applyAutoGridLayout();
}

function resetCustomPanels() {
  document.getElementById("dayPanel")?.classList.remove("maximized", "minimized");
  document.getElementById("thermalPanel")?.classList.remove("maximized", "minimized");
}

function captureScreenshot(channel) {
  const video = document.getElementById(channel === "thermal" ? "thermalStream" : "dayStream");
  const canvas = document.createElement("canvas");
  const w = 1280;
  const h = 720;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#0a1016";
  ctx.fillRect(0, 0, w, h);
  if (video && !video.classList.contains("hidden") && video.videoWidth) {
    ctx.drawImage(video, 0, 0, w, h);
  } else {
    ctx.fillStyle = "#8b9aab";
    ctx.font = "22px Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No stream — placeholder capture", w / 2, h / 2);
  }
  canvas.toBlob((blob) => {
    if (!blob) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `shibli_${channel}_${new Date().toISOString().replace(/[:.]/g, "-")}.png`;
    a.click();
    URL.revokeObjectURL(a.href);
    showToast(`${channel} screenshot saved`);
  }, "image/png");
}

function toggleCustomMaximize(channel) {
  const dayPanel = document.getElementById("dayPanel");
  const thermalPanel = document.getElementById("thermalPanel");
  const isMax = (channel === "day" && dayPanel?.classList.contains("maximized"))
    || (channel === "thermal" && thermalPanel?.classList.contains("maximized"));
  if (isMax) {
    resetCustomPanels();
    state.customMaxChannel = null;
    return;
  }
  if (channel === "day") {
    dayPanel?.classList.add("maximized");
    dayPanel?.classList.remove("minimized");
    thermalPanel?.classList.add("minimized");
    thermalPanel?.classList.remove("maximized");
  } else {
    thermalPanel?.classList.add("maximized");
    thermalPanel?.classList.remove("minimized");
    dayPanel?.classList.add("minimized");
    dayPanel?.classList.remove("maximized");
  }
  state.customMaxChannel = channel;
}

function setLayout(layout) {
  const next = normalizeLayout(layout || state.layout || "day_thermal");
  state.layout = next;
  const cameraZone = document.getElementById("cameraZone");
  const dayPanel = document.getElementById("dayPanel");
  const thermalPanel = document.getElementById("thermalPanel");
  const customBar = document.getElementById("customLayoutBar");

  if (cameraZone) {
    cameraZone.className = `camera-zone layout-${next}`;
  }

  document.querySelectorAll("#videoMatrix .video-panel.extra").forEach((el) => el.remove());
  resetCustomPanels();

  if (next === "custom") {
    dayPanel?.classList.add("hidden");
    thermalPanel?.classList.add("hidden");
    customBar?.classList.remove("hidden");
    customBar?.setAttribute("aria-hidden", "false");
  } else {
    customBar?.classList.add("hidden");
    customBar?.setAttribute("aria-hidden", "true");
    dayPanel?.classList.remove("hidden");
    thermalPanel?.classList.remove("hidden");
    if (next === "day_full") {
      thermalPanel?.classList.add("hidden");
    } else if (next === "thermal_full") {
      dayPanel?.classList.add("hidden");
    }
  }

  applyAutoGridLayout();
  document.querySelectorAll(".layout-segmented [data-layout]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.layout === next);
  });
}

function updateHud(hw, osdEnabled, osdConfig) {
  const cfg = osdConfig || state.osdConfig || {};
  const tel = { ...(hw.telemetry || {}), ...state.ptzTelemetry };
  const lrf = hw.lrf || {};
  const telLine = `AZ ${tel.azimuth ?? "—"}° · EL ${tel.elevation ?? "—"}° · RNG ${lrf.range_m ? `${lrf.range_m}m` : "—"}`;
  if (telLine !== state._lastHudLine) {
    state._lastHudLine = telLine;
    document.getElementById("telemetryLine").textContent = telLine;
  }
  const cmd = hw.last_command || "Ready";
  if (cmd !== state._lastCmdLine) {
    state._lastCmdLine = cmd;
    document.getElementById("commandLine").textContent = cmd;
  }
  const pos = cfg.position || "bottom-left";
  const lines = [];
  if (cfg.show_logo !== false && cfg.logo_text) lines.push(cfg.logo_text);
  if (cfg.show_telemetry !== false) lines.push(telLine);
  if (cfg.custom_text) lines.push(cfg.custom_text);
  const overlayText = lines.join("\n");
  ["dayHud", "thermalHud"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `hud-overlay hud-${pos}`;
    el.textContent = osdEnabled ? overlayText : "";
  });
}

function applyRefreshStatus(status) {
  if (status.services && Object.keys(status.services).length) {
    state.serviceStatus = status.services;
  }
  const version = status.version || "v1.0";
  if (version !== state._lastVersion) {
    state._lastVersion = version;
    document.getElementById("versionTag").textContent = version;
  }

  applyServiceStatus(state.serviceStatus, state.mapping, status.cameras_mapped);
  setRecordingMode(status.recording || "off", { fromServer: true });
  if (status.layout) {
    const normalized = normalizeLayout(status.layout);
    if (normalized !== state.layout) setLayout(normalized);
  }

  const osd = Boolean(status.osd_enabled);
  if (osd !== state._lastOsd) {
    state._lastOsd = osd;
    document.body.classList.toggle("osd-on", osd);
    document.getElementById("osdToggle").checked = osd;
    document.getElementById("osdLabel").textContent = osd ? "On" : "Off";
  }
  if (status.osd_config) {
    state.osdConfig = status.osd_config;
  }

  const hw = status.hardware || {};
  if (hw.lrf) {
    const rangeVal = hw.lrf.range_m ? `${hw.lrf.range_m} m` : "—";
    const rangeInput = document.getElementById("rangeInput");
    if (rangeInput && rangeInput.value !== rangeVal) rangeInput.value = rangeVal;
    const cx = hw.lrf.cursor?.x ?? "—";
    const cy = hw.lrf.cursor?.y ?? "—";
    const cursorX = document.getElementById("cursorX");
    const cursorY = document.getElementById("cursorY");
    if (cursorX && cursorX.textContent !== String(cx)) cursorX.textContent = cx;
    if (cursorY && cursorY.textContent !== String(cy)) cursorY.textContent = cy;
  }
  if (hw.illumination) {
    const illumOn = Boolean(hw.illumination.enabled);
    const illumToggle = document.getElementById("illumToggle");
    if (illumToggle && illumToggle.checked !== illumOn) illumToggle.checked = illumOn;
    const src = hw.illumination.source || "ir";
    const beam = hw.illumination.beam || "narrow";
    const illumSource = document.getElementById("illumSource");
    const beamMode = document.getElementById("beamMode");
    if (illumSource && illumSource.value !== src) illumSource.value = src;
    if (beamMode && beamMode.value !== beam) beamMode.value = beam;
    const intensity = hw.illumination.intensity || "med";
    if (intensity !== state.selectedIntensity) {
      state.selectedIntensity = intensity;
      document.querySelectorAll("[data-intensity]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.intensity === intensity);
      });
    }
    const brEl = document.getElementById("illumBrightnessVal");
    const fovEl = document.getElementById("illumFovVal");
    if (brEl && hw.illumination.brightness != null) brEl.textContent = `${hw.illumination.brightness}%`;
    if (fovEl && hw.illumination.fov != null) fovEl.textContent = `${hw.illumination.fov}°`;
  }
  if (hw.focus) {
    state.dayAutoFocus = Boolean(hw.focus.day_auto);
    state.thermalAutoFocus = Boolean(hw.focus.thermal_auto);
    document.getElementById("dayAfcBtn")?.classList.toggle("active", state.dayAutoFocus);
    document.getElementById("thermalAfcBtn")?.classList.toggle("active", state.thermalAutoFocus);
    document.querySelectorAll('[data-lens][data-channel="thermal"]').forEach((b) => {
      b.disabled = state.thermalAutoFocus && String(b.dataset.lens || "").startsWith("focus");
    });
    document.querySelectorAll('[data-lens][data-channel="day"], .lens-stack [data-lens]').forEach((b) => {
      if (String(b.dataset.lens || "").startsWith("focus")) b.disabled = state.dayAutoFocus;
    });
  }
  if (hw.thermal) {
    const pol = hw.thermal.polarity || "white_hot";
    document.querySelectorAll("[data-polarity]").forEach((b) => {
      b.classList.toggle("active", b.dataset.polarity === pol);
    });
    const tb = document.getElementById("thermalBrightness");
    const tc = document.getElementById("thermalContrast");
    if (tb && hw.thermal.brightness != null) tb.value = hw.thermal.brightness;
    if (tc && hw.thermal.contrast != null) tc.value = hw.thermal.contrast;
    const tbVal = document.getElementById("thermalBrightnessVal");
    const tcVal = document.getElementById("thermalContrastVal");
    if (tbVal && hw.thermal.brightness != null) tbVal.textContent = `${hw.thermal.brightness}`;
    if (tcVal && hw.thermal.contrast != null) tcVal.textContent = `${hw.thermal.contrast}`;
  }
  if (hw.auxiliary) {
    document.getElementById("wiperBtn")?.classList.toggle("active", hw.auxiliary.wiper);
    document.getElementById("heaterBtn")?.classList.toggle("active", hw.auxiliary.heater);
    document.getElementById("nucBtn")?.classList.toggle("active", hw.auxiliary.nuc);
    document.getElementById("agcBtn")?.classList.toggle("active", hw.auxiliary.agc);
  }
  if (status.storage) {
    const storageLine = `Storage ${status.storage.free_gb}/${status.storage.total_gb} GB free`;
    const storageEl = document.getElementById("storageLine");
    if (storageEl && storageEl.textContent !== storageLine) storageEl.textContent = storageLine;
  }
  updateHud(hw, osd, state.osdConfig);
}

let statusPending = null;
let statusRaf = 0;
function scheduleRefreshStatus(data) {
  statusPending = data;
  if (statusRaf) return;
  statusRaf = requestAnimationFrame(() => {
    statusRaf = 0;
    const payload = statusPending;
    statusPending = null;
    if (payload) applyRefreshStatus(payload);
  });
}

function updateConnectionChip() {
  const chip = document.getElementById("connectionModeChip");
  if (chip) chip.textContent = `Connection: ${connectionModeLabel(currentConnectionMode())}`;
}

async function refreshStatus(data = null) {
  const status = data || await api("/api/status");
  applyRefreshStatus(status);
}

function bindDashboard() {
  updateConnectionChip();
  document.getElementById("connectionModeChip")?.addEventListener("click", async () => {
    const next = currentConnectionMode() === "ip" ? "lan" : "ip";
    try {
      stopAllGo2Rtc();
      await switchConnectionMode(next);
      updateConnectionChip();
      state.hardwareCacheAt = 0;
      await refreshHardwareState();
      await loadGo2RtcConfig();
      await bindLocalCameraStreams();
      showToast(`Connection: ${connectionModeLabel(next)}`);
    } catch (ex) {
      showToast(ex.message || "Could not switch connection mode");
    }
  });

  if (!Auth.canControl()) {
    document.querySelectorAll("[data-ptz],[data-lens],[data-preset],[data-quick],[data-intensity],#measureBtn")
      .forEach((el) => { el.disabled = true; });
    showToast("View-only mode (VIEWER role)");
  }

  document.getElementById("ptzSelect")?.addEventListener("change", () => {
    resolveActiveCameraFromPtz();
  });

  document.querySelectorAll("[data-ptz-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.ptzTarget = btn.dataset.ptzTarget;
      document.querySelectorAll("[data-ptz-target]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      resolveActiveCameraFromPtz();
      showToast(`PTZ target: ${btn.dataset.ptzTarget}`);
    });
  });

  window.addEventListener("shibli:cameras-changed", async () => {
    await refreshHardwareState();
    await bindLocalCameraStreams();
    populatePtzSelect();
    resolveActiveCameraFromPtz();
  });

  document.querySelectorAll("[data-shot]").forEach((btn) => {
    btn.addEventListener("click", () => captureScreenshot(btn.dataset.shot));
  });

  document.querySelectorAll("[data-max]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (state.layout !== "custom") {
        try {
          await api("/api/layout", { method: "POST", body: JSON.stringify({ layout: "custom" }) });
          setLayout("custom");
        } catch (ex) {
          setLayout("custom");
        }
      }
      toggleCustomMaximize(btn.dataset.max);
    });
  });

  document.querySelectorAll("[data-min]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const channel = btn.dataset.min;
      const panel = document.getElementById(channel === "thermal" ? "thermalPanel" : "dayPanel");
      panel?.classList.add("minimized");
      panel?.classList.remove("maximized");
      showToast(`${channel === "thermal" ? "Thermal" : "Day"} panel minimized`);
    });
  });

  document.getElementById("customAddPanel")?.addEventListener("click", () => {
    const camId = parseInt(document.getElementById("customCamSelect")?.value || "", 10);
    const channel = document.getElementById("customChannelSelect")?.value || "day";
    const cam = state.localCameras.find((c) => c.id === camId);
    if (!cam) {
      showToast("Select a camera to add.");
      return;
    }
    addCustomPanel(cam, channel);
    showToast(`Added ${panelDisplayName(cam, channel)}`);
  });

  document.getElementById("customResetLayout")?.addEventListener("click", async () => {
    document.querySelectorAll("#videoMatrix .video-panel.extra").forEach((el) => el.remove());
    resetCustomPanels();
    try {
      await api("/api/layout", { method: "POST", body: JSON.stringify({ layout: "day_thermal" }) });
    } catch { /* offline */ }
    setLayout("day_thermal");
    showToast("Layout reset.");
  });

  document.querySelectorAll("[data-record]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const mode = btn.dataset.record;
      setRecordingMode(mode);
      try {
        await api("/api/recording", { method: "POST", body: JSON.stringify({ mode }) });
        const label = RECORD_LABELS[mode] || "Recording updated";
        showToast(mode === "off" ? "Recording stopped — files saved" : `${label} — recording to data/recordings/`);
      } catch (ex) {
        showToast(ex.message);
      }
    });
  });

  document.querySelectorAll(".layout-segmented [data-layout]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const layout = btn.dataset.layout;
      setLayout(layout);
      try {
        await api("/api/layout", { method: "POST", body: JSON.stringify({ layout }) });
        showToast(`Layout: ${btn.textContent.trim()}`);
      } catch (ex) {
        showToast(ex.message || "Layout saved locally");
      }
    });
  });

  document.getElementById("osdToggle")?.addEventListener("change", async (e) => {
    const on = e.target.checked;
    document.getElementById("osdLabel").textContent = on ? "On" : "Off";
    try {
      await api("/api/osd", { method: "POST", body: JSON.stringify({ enabled: on }) });
      showToast(`OSD ${on ? "on" : "off"}`);
    } catch (ex) {
      showToast(ex.message);
      e.target.checked = !on;
      document.getElementById("osdLabel").textContent = e.target.checked ? "On" : "Off";
    }
  });

  document.getElementById("hwSelfTestBtn")?.addEventListener("click", async () => {
    const out = document.getElementById("hwSelfTestOut");
    if (out) {
      out.classList.remove("hidden");
      out.textContent = "Running self-test…";
    }
    try {
      const res = await api("/api/hardware/self-test", { method: "POST" });
      const lines = (res.checks || []).map((c) => `${c.ok ? "OK" : "—"} ${c.label}: ${c.detail}`);
      if (out) {
        out.textContent = `Self-test ${res.passed}/${res.total}\n${lines.join("\n")}\n\n${res.hint || ""}`;
      }
      showToast(`Self-test: ${res.passed}/${res.total} checks passed`);
    } catch (ex) {
      if (out) out.textContent = ex.message || "Self-test failed";
      showToast(ex.message || "Self-test failed");
    }
  });

  document.querySelectorAll("[data-ptz]").forEach((btn) => {
    const direction = btn.dataset.ptz;
    if (direction === "stop") {
      btn.addEventListener("click", () => runHardwareAction("PTZ stop", () =>
        api("/api/ptz/stop", {
          method: "POST",
          body: JSON.stringify({
            direction: "stop",
            speed: state.ptzSpeed,
            mode: state.ptzMode,
            ptz_id: state.activePtz,
            ...cameraPayload(),
          }),
        })
      ));
      return;
    }
    if (direction === "home") {
      btn.addEventListener("click", () => runHardwareAction("PTZ home", () =>
        api("/api/ptz/move", {
          method: "POST",
          body: JSON.stringify({
            direction: "home",
            speed: state.ptzSpeed,
            mode: state.ptzMode,
            ptz_id: state.activePtz,
            ...cameraPayload(),
          }),
        })
      ));
      return;
    }
    const sendPtzStart = (dir) => api("/api/ptz/start", {
      method: "POST",
      body: JSON.stringify(ptzRequestBody(dir)),
    });
    const sendPtzStop = () => api("/api/ptz/stop", {
      method: "POST",
      body: JSON.stringify(ptzRequestBody("stop")),
    }).catch(() => {});
    let moving = false;
    const start = () => {
      if (!ptzCanMove()) {
        if (!state.controlsOnline && !state.hwSimulate) {
          showToast("Hardware controls offline — start the controls service");
        }
        return;
      }
      if (moving) return;
      moving = true;
      resolveActiveCameraFromPtz();
      sendPtzStart(direction).catch((ex) => {
        moving = false;
        showToast(`PTZ failed: ${ex.message || direction}`);
      });
    };
    const stop = () => {
      if (!moving) return;
      moving = false;
      sendPtzStop();
    };
    btn.addEventListener("mousedown", (e) => { e.preventDefault(); start(); });
    btn.addEventListener("mouseup", stop);
    btn.addEventListener("mouseleave", stop);
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); start(); }, { passive: false });
    btn.addEventListener("touchend", stop);
    btn.addEventListener("touchcancel", stop);
  });

  function bindHold(btn, startFn, stopFn) {
    let moving = false;
    const start = (e) => {
      e.preventDefault();
      if (moving) return;
      if (!ptzCanMove()) {
        if (!state.controlsOnline && !state.hwSimulate) showToast("Hardware controls offline — start the controls service");
        return;
      }
      moving = true;
      resolveActiveCameraFromPtz();
      Promise.resolve(startFn()).catch((ex) => {
        moving = false;
        showToast(ex.message || "Command failed");
      });
    };
    const stop = () => {
      if (!moving) return;
      moving = false;
      Promise.resolve(stopFn()).catch(() => {});
    };
    btn.addEventListener("mousedown", start);
    btn.addEventListener("mouseup", stop);
    btn.addEventListener("mouseleave", stop);
    btn.addEventListener("touchstart", start, { passive: false });
    btn.addEventListener("touchend", stop);
    btn.addEventListener("touchcancel", stop);
  }

  document.querySelectorAll("[data-lens]").forEach((btn) => {
    const action = btn.dataset.lens;
    const channel = btn.dataset.channel || "";
    const extra = () => (channel ? cameraPayloadForChannel(channel) : cameraPayload());
    if (action === "zoom_in" || action === "zoom_out") {
      bindHold(
        btn,
        () => api("/api/ptz/start", { method: "POST", body: JSON.stringify({ ...ptzRequestBody(action), ...extra() }) }),
        () => api("/api/ptz/stop", { method: "POST", body: JSON.stringify({ ...ptzRequestBody("stop"), ...extra() }) }),
      );
      return;
    }
    if (action === "focus_plus" || action === "focus_minus") {
      const direction = action === "focus_minus" ? "near" : "far";
      const ch = channel || "day";
      bindHold(
        btn,
        () => api("/api/ptz/focus/start", { method: "POST", body: JSON.stringify({ direction, channel: ch, ...extra() }) }),
        () => api("/api/ptz/focus/stop", { method: "POST", body: JSON.stringify({ direction, channel: ch, ...extra() }) }),
      );
    }
  });

  document.getElementById("ptzSpeed")?.addEventListener("change", (e) => {
    state.ptzSpeed = e.target.value;
    runHardwareAction("PTZ speed", () =>
      api("/api/ptz/speed", { method: "POST", body: JSON.stringify({ speed: state.ptzSpeed, ...cameraPayload() }) })
    );
  });

  document.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.ptzMode = btn.dataset.mode;
      document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b === btn));
    });
  });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => runHardwareAction(`Preset ${btn.dataset.preset}`, () =>
      api(`/api/ptz/preset/${btn.dataset.preset}`, {
        method: "POST",
        body: JSON.stringify({ preset: document.getElementById("presetSelect").value, ptz_id: state.activePtz, ...cameraPayload() }),
      })
    ));
  });

  document.getElementById("measureBtn")?.addEventListener("click", () => runHardwareAction("LRF measure", async () => {
    state.lrfContinuous = false;
    const result = await api("/api/lrf/measure", {
      method: "POST",
      body: JSON.stringify({ mode: "single", ...cameraPayload() }),
    });
    if (result.ok === false) {
      document.getElementById("rangeInput").value = "—";
      throw new Error(result.error || "LRF measurement failed");
    }
    document.getElementById("rangeInput").value = result.range_m != null ? `${result.range_m} m` : "—";
    document.getElementById("cursorX").textContent = result.cursor.x;
    document.getElementById("cursorY").textContent = result.cursor.y;
  }));

  document.getElementById("lrfContBtn")?.addEventListener("click", () => runHardwareAction("LRF continuous", async () => {
    await api("/api/lrf/continuous/start", {
      method: "POST",
      body: JSON.stringify({ mode: "continuous", ...cameraPayload() }),
    });
    state.lrfContinuous = true;
    document.getElementById("lrfMode").value = "continuous";
    showToast("LRF continuous — polling range");
  }));

  document.getElementById("lrfStopBtn")?.addEventListener("click", () => runHardwareAction("LRF stop", async () => {
    await api("/api/lrf/continuous/stop", { method: "POST" });
    state.lrfContinuous = false;
    document.getElementById("rangeInput").value = "—";
    showToast("LRF stopped");
  }));

  document.getElementById("dayAfcBtn")?.addEventListener("click", () => {
    const next = !state.dayAutoFocus;
    runHardwareAction(next ? "Day auto focus on" : "Day auto focus off", async () => {
      const res = await api("/api/ptz/focus/mode", {
        method: "POST",
        body: JSON.stringify({ auto: next, channel: "day", ...cameraPayloadForChannel("day") }),
      });
      if (res.ok === false) throw new Error(res.error || "Day autofocus failed");
      state.dayAutoFocus = next;
      document.getElementById("dayAfcBtn")?.classList.toggle("active", next);
    });
  });

  document.getElementById("thermalAfcBtn")?.addEventListener("click", () => {
    const next = !state.thermalAutoFocus;
    runHardwareAction(next ? "Thermal auto focus on" : "Thermal auto focus off", async () => {
      const res = await api("/api/ptz/focus/mode", {
        method: "POST",
        body: JSON.stringify({ auto: next, channel: "thermal", ...cameraPayloadForChannel("thermal") }),
      });
      if (res.ok === false) throw new Error(res.error || "Thermal autofocus failed");
      state.thermalAutoFocus = next;
      document.getElementById("thermalAfcBtn")?.classList.toggle("active", next);
    });
  });

  document.querySelectorAll("[data-thermal-zoom]").forEach((btn) => {
    btn.addEventListener("click", () => applyThermalZoom(btn.dataset.thermalZoom));
  });

  document.querySelectorAll(".grid-segmented [data-grid]").forEach((btn) => {
    btn.addEventListener("click", () => setGridLayout(btn.dataset.grid));
  });

  const sendIllum = (patch, label) => runHardwareAction(label || "Illumination", async () => {
    const res = await api("/api/illumination", { method: "POST", body: JSON.stringify({ ...patch, ...cameraPayload() }) });
    const ill = res?.illumination || {};
    const brightness = res?.brightness ?? ill.brightness;
    const fov = res?.fov ?? ill.fov;
    const brEl = document.getElementById("illumBrightnessVal");
    const fovEl = document.getElementById("illumFovVal");
    if (brEl && brightness != null) brEl.textContent = `${brightness}%`;
    if (fovEl && fov != null) fovEl.textContent = `${fov}°`;
    return res;
  });
  document.getElementById("illumToggle")?.addEventListener("change", (e) => sendIllum({ enabled: e.target.checked }, "Illumination"));
  document.getElementById("illumSource")?.addEventListener("change", (e) => sendIllum({ source: e.target.value }));
  document.getElementById("beamMode")?.addEventListener("change", (e) => sendIllum({ beam: e.target.value }));
  document.querySelectorAll("[data-intensity]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.selectedIntensity = btn.dataset.intensity;
      document.querySelectorAll("[data-intensity]").forEach((b) => b.classList.toggle("active", b === btn));
      await sendIllum({ intensity: state.selectedIntensity });
    });
  });
  document.getElementById("illumBrightUp")?.addEventListener("click", () => sendIllum({ bump: "brightness_up" }, "IR brighter"));
  document.getElementById("illumBrightDown")?.addEventListener("click", () => sendIllum({ bump: "brightness_down" }, "IR dimmer"));
  document.getElementById("illumFovUp")?.addEventListener("click", () => sendIllum({ bump: "fov_up" }, "IR FOV wider"));
  document.getElementById("illumFovDown")?.addEventListener("click", () => sendIllum({ bump: "fov_down" }, "IR FOV narrower"));
  document.getElementById("illumFovReset")?.addEventListener("click", () => sendIllum({ fov_action: "reset" }, "IR FOV reset"));

  const sendThermal = (patch, label) => runHardwareAction(label || "Thermal", () =>
    api("/api/thermal/image", { method: "POST", body: JSON.stringify({ ...patch, ...cameraPayloadForChannel("thermal") }) })
  );
  document.querySelectorAll("[data-polarity]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-polarity]").forEach((b) => b.classList.toggle("active", b === btn));
      sendThermal({ polarity: btn.dataset.polarity }, "Polarity");
    });
  });
  const bindThermalSlider = (id, valId, field, label) => {
    const input = document.getElementById(id);
    const val = document.getElementById(valId);
    input?.addEventListener("input", () => { if (val) val.textContent = input.value; });
    input?.addEventListener("change", () => sendThermal({ [field]: parseInt(input.value, 10) }, label));
  };
  bindThermalSlider("thermalBrightness", "thermalBrightnessVal", "brightness", "Thermal brightness");
  bindThermalSlider("thermalContrast", "thermalContrastVal", "contrast", "Thermal contrast");

  document.querySelectorAll("[data-quick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const [group, action] = btn.dataset.quick.split(":");
      runHardwareAction(`${group} ${action}`, () =>
        api("/api/quick", { method: "POST", body: JSON.stringify({ group, action }) })
      );
    });
  });

  document.getElementById("fullscreenBtn")?.addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
        showToast("Fullscreen on");
      } else {
        await document.exitFullscreen();
        showToast("Fullscreen off");
      }
    } catch {
      showToast("Fullscreen not available in this browser");
    }
  });

  document.getElementById("menuToggle")?.addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("appShell")?.classList.toggle("sidebar-open");
  });
  document.addEventListener("click", (e) => {
    const shell = document.getElementById("appShell");
    const sidebar = document.getElementById("sidebar");
    if (!shell?.classList.contains("sidebar-open")) return;
    if (sidebar?.contains(e.target) || e.target.closest("#menuToggle")) return;
    shell.classList.remove("sidebar-open");
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.getElementById("appShell")?.classList.remove("sidebar-open");
  });

  document.getElementById("autoPanBtn")?.addEventListener("click", () => {
    runHardwareAction("Auto-pan", toggleAutoPan);
  });

  initDragZoom({
    onRegionZoom(channel, { cx, cy, scale }) {
      applyChannelZoom(channel, scale, cx, cy);
      sendPtzNudgeFromRegion(cx, cy);
      if (scale > 1.15) {
        api("/api/ptz/lens", {
          method: "POST",
          body: JSON.stringify({ action: "zoom_in", ptz_id: state.activePtz, ...cameraPayload() }),
        }).catch(() => {});
      }
    },
    onDragZoom(channel, direction) {
      if (channel === "thermal") applyThermalZoom(direction);
      else applyDayZoom(direction);
    },
    onReset(channel) {
      resetChannelZoom(channel);
      showToast(`${channel === "thermal" ? "Thermal" : "Day"} zoom reset`);
    },
  });
}

let wsReconnectTimer = null;
let wsBackoffMs = 2000;

function startSocket() {
  if (!Auth.isLoggedIn()) return;
  clearTimeout(wsReconnectTimer);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/status?token=${encodeURIComponent(Auth.token)}`);
  ws.onmessage = (e) => {
    try {
      scheduleRefreshStatus(JSON.parse(e.data));
    } catch (err) {
      console.error(err);
    }
  };
  ws.onopen = () => { wsBackoffMs = 2000; };
  ws.onclose = () => {
    if (!Auth.isLoggedIn()) return;
    wsReconnectTimer = setTimeout(startSocket, wsBackoffMs);
    wsBackoffMs = Math.min(wsBackoffMs * 1.5, 15000);
  };
}

let booted = false;

async function bootApp() {
  if (booted) return;
  booted = true;

  bindLogout();
  initRouter();
  initRecordingsPage();
  initCamerasPage();
  initUsersPage();
  initAuditPage();
  initSettingsPage();
  bindDashboard();
  initKeyboard(handleKeyboardAction);
  updateClock();
  setInterval(updateClock, 1000);
  setInterval(pollPtzStatus, 5000);
  setInterval(pollSystemDiag, 15000);
  setInterval(pollLrfDistance, 500);
  try {
    await loadConfig();
    await loadGo2RtcConfig();
    state.hwSimulate = false;
    updateHwOfflineNote();
    updateConnectionChip();
    await refreshStatus();
  } catch (ex) {
    console.warn("boot partial (offline?)", ex);
  }
  startSocket();
  document.getElementById("appShell")?.classList.add("ready");
  showToast("SHIBLI C2 ready");
}

async function main() {
  bindPasswordToggles();
  await initTheme();
  const loggedIn = await initAuth();
  if (loggedIn) await bootApp();
  window.addEventListener("shibli:logged-in", () => bootApp());
  window.addEventListener("shibli:logged-out", () => {
    booted = false;
    clearTimeout(wsReconnectTimer);
    stopAllGo2Rtc();
  });
  document.getElementById("themeToggle")?.addEventListener("click", () => toggleTheme());
}

main().catch((err) => {
  console.error(err);
  showToast("Startup error");
});
