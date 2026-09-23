import { api, showToast } from "../api.js";

let editingId = null;
const testStatus = {};
let wizardStep = 1;
const WIZARD_STEPS = 5;
let camerasCache = [];
let listBound = false;

function cameraPayload() {
  return {
    name: document.getElementById("camName").value.trim(),
    camera_type: document.getElementById("camType").value,
    ip_address: document.getElementById("camIp").value.trim(),
    rtsp_url: document.getElementById("camRtsp").value.trim(),
    onvif_port: parseInt(document.getElementById("camOnvif").value, 10) || 80,
    username: document.getElementById("camUser").value.trim(),
    password: document.getElementById("camPass").value,
    ptz_mapping: document.getElementById("camPtz").value,
    camera_group: document.getElementById("camGroup").value.trim(),
    enabled: document.getElementById("camEnabled").checked,
    connection_mode: document.getElementById("camConnectionMode")?.value || "lan",
  };
}

function payloadFromCamera(cam, overrides = {}) {
  return {
    name: cam.name,
    camera_type: cam.cameraType,
    ip_address: cam.ipAddress || "",
    rtsp_url: cam.rtspUrl || "",
    onvif_port: cam.onvifPort || 80,
    username: cam.username || "",
    password: "",
    ptz_mapping: cam.ptzMapping || "none",
    camera_group: cam.cameraGroup || "",
    enabled: cam.enabled,
    connection_mode: cam.connectionMode || "lan",
    ...overrides,
  };
}

function setTestResult(text, kind) {
  const resultEl = document.getElementById("cameraTestResult");
  if (!resultEl) return;
  resultEl.textContent = text || "";
  resultEl.classList.toggle("is-ok", kind === "ok");
  resultEl.classList.toggle("is-bad", kind === "bad");
}

function syncEnabledLabel() {
  const on = Boolean(document.getElementById("camEnabled")?.checked);
  const lab = document.getElementById("camEnabledLabel");
  if (lab) lab.textContent = on ? "Enabled" : "Disabled";
}

function setFormTitle(mode, name) {
  const title = document.getElementById("cameraFormTitle");
  if (!title) return;
  title.textContent = mode === "edit" && name ? `Edit Camera — ${name}` : "Add Camera";
}

function focusCameraName() {
  document.querySelector("#page-cameras .page-body")?.scrollTo({ top: 0, behavior: "smooth" });
  document.getElementById("camName")?.focus();
}

function clearForm() {
  editingId = null;
  const editId = document.getElementById("cameraEditId");
  if (editId) editId.value = "";
  setFormTitle("add");
  document.getElementById("saveCameraBtn").textContent = "Save Camera";
  document.getElementById("cameraForm").reset();
  document.getElementById("camOnvif").value = "80";
  document.getElementById("camEnabled").checked = true;
  const legacyOpt = document.getElementById("camModeLegacyOpt");
  if (legacyOpt) legacyOpt.hidden = true;
  const modeSel = document.getElementById("camConnectionMode");
  if (modeSel) modeSel.value = "lan";
  setTestResult("", "");
  syncEnabledLabel();
}

function openAddCamera() {
  clearForm();
  focusCameraName();
}

function isSharedDeploy() {
  return document.getElementById("wizDeployType")?.value === "shared";
}

function showWizardStep(step) {
  wizardStep = step;
  document.querySelectorAll(".onboarding-step").forEach((el) => {
    el.classList.toggle("hidden", parseInt(el.dataset.step, 10) !== step);
  });
  document.getElementById("onboardingStepLabel").textContent = `Step ${step} of ${WIZARD_STEPS}`;
  document.getElementById("onboardingBack").disabled = step === 1;
  document.getElementById("onboardingNext").classList.toggle("hidden", step === WIZARD_STEPS);
  document.getElementById("onboardingFinish").classList.toggle("hidden", step !== WIZARD_STEPS);
  document.getElementById("onboardingTest").classList.toggle("hidden", step < 4);
  if (step === 3) {
    const shared = isSharedDeploy();
    document.getElementById("wizThermalHint")?.classList.toggle("hidden", !shared);
    document.getElementById("wizThermalPtzWrap")?.classList.toggle("hidden", shared);
    if (shared) {
      document.getElementById("wizThermalIp").value = document.getElementById("wizDayIp").value;
      document.getElementById("wizThermalOnvif").value = document.getElementById("wizDayOnvif").value;
      document.getElementById("wizThermalUser").value = document.getElementById("wizDayUser").value;
    }
  }
  if (step === WIZARD_STEPS) {
    document.getElementById("wizReview").textContent = buildWizardReview();
  }
}

function buildWizardReview() {
  const shared = isSharedDeploy();
  const lines = [
    `Deployment: ${shared ? "Shared PTZ head" : "Separate devices"}`,
    "",
    "Day camera:",
    `  Name: ${document.getElementById("wizDayName").value}`,
    `  IP: ${document.getElementById("wizDayIp").value}`,
    `  RTSP: ${document.getElementById("wizDayRtsp").value}`,
    `  PTZ: ${document.getElementById("wizDayPtz").value}`,
  ];
  if (shared || document.getElementById("wizThermalName").value.trim()) {
    lines.push("", "Thermal camera:", `  Name: ${document.getElementById("wizThermalName").value || "(same device)"}`,
      `  IP: ${shared ? document.getElementById("wizDayIp").value : document.getElementById("wizThermalIp").value}`,
      `  RTSP: ${document.getElementById("wizThermalRtsp").value}`,
      `  PTZ: ${shared ? document.getElementById("wizDayPtz").value : document.getElementById("wizThermalPtz").value}`);
  }
  const group = document.getElementById("wizGroup").value.trim();
  if (group) lines.push("", `Group: ${group}`);
  return lines.join("\n");
}

function wizardCameraPayloads() {
  const shared = isSharedDeploy();
  const group = document.getElementById("wizGroup").value.trim() || (shared ? "main-ptz-head" : "");
  const day = {
    name: document.getElementById("wizDayName").value.trim(),
    camera_type: "Day",
    ip_address: document.getElementById("wizDayIp").value.trim(),
    rtsp_url: document.getElementById("wizDayRtsp").value.trim(),
    onvif_port: parseInt(document.getElementById("wizDayOnvif").value, 10) || 80,
    username: document.getElementById("wizDayUser").value.trim(),
    password: document.getElementById("wizDayPass").value,
    ptz_mapping: document.getElementById("wizDayPtz").value,
    camera_group: group,
    enabled: true,
    connection_mode: document.getElementById("wizConnectionMode")?.value || "lan",
  };
  const payloads = [day];
  const thermalName = document.getElementById("wizThermalName").value.trim();
  const thermalRtsp = document.getElementById("wizThermalRtsp").value.trim();
  if (shared || thermalName || thermalRtsp) {
    payloads.push({
      name: thermalName || `${day.name} Thermal`,
      camera_type: "Thermal",
      ip_address: shared ? day.ip_address : document.getElementById("wizThermalIp").value.trim(),
      rtsp_url: thermalRtsp,
      onvif_port: shared ? day.onvif_port : parseInt(document.getElementById("wizThermalOnvif").value, 10) || 80,
      username: shared ? day.username : document.getElementById("wizThermalUser").value.trim(),
      password: shared ? day.password : document.getElementById("wizThermalPass").value,
      ptz_mapping: shared ? day.ptz_mapping : document.getElementById("wizThermalPtz").value,
      camera_group: group,
      enabled: true,
      connection_mode: day.connection_mode,
    });
  }
  return payloads;
}

function openOnboardingWizard() {
  const dlg = document.getElementById("cameraOnboardingDialog");
  document.getElementById("cameraOnboardingForm")?.reset();
  document.getElementById("wizDayOnvif").value = "80";
  document.getElementById("wizThermalOnvif").value = "80";
  document.getElementById("wizTestResult").textContent = "";
  showWizardStep(1);
  dlg?.showModal();
}

async function testWizardCameras() {
  const resultEl = document.getElementById("wizTestResult");
  resultEl.textContent = "Testing…";
  const payloads = wizardCameraPayloads();
  const messages = [];
  for (const payload of payloads) {
    if (!payload.rtsp_url) {
      messages.push(`${payload.name}: RTSP URL required.`);
      continue;
    }
    try {
      const res = await api("/api/cameras/local/test", { method: "POST", body: JSON.stringify(payload) });
      messages.push(`${payload.name}: ${res.message || (res.ok ? "OK" : "Failed")}`);
    } catch (ex) {
      messages.push(`${payload.name}: ${ex.message}`);
    }
  }
  resultEl.textContent = messages.join(" · ");
  showToast(messages[messages.length - 1] || "Test complete");
}

async function finishWizard(e) {
  e.preventDefault();
  const payloads = wizardCameraPayloads();
  if (!payloads[0]?.name) {
    showToast("Day camera name is required");
    showWizardStep(2);
    return;
  }
  try {
    for (const payload of payloads) {
      await api("/api/cameras/local", { method: "POST", body: JSON.stringify(payload) });
    }
    try {
      const sync = await api("/api/backend/sync", { method: "POST" });
      if (sync.synced?.length) {
        showToast(`Saved ${payloads.length} camera(s) and synced ${sync.synced.length} to Controls`);
      } else if (sync.error) {
        showToast(sync.error);
      } else {
        showToast(`Saved ${payloads.length} camera(s). Sync when Hardware Controls is online.`);
      }
    } catch {
      showToast(`Saved ${payloads.length} camera(s) locally.`);
    }
    document.getElementById("cameraOnboardingDialog")?.close();
    loadCameras();
    window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
  } catch (ex) {
    showToast(ex.message || "Failed to save cameras");
  }
}

export function initCamerasPage() {
  document.getElementById("addCameraBtn")?.addEventListener("click", openAddCamera);
  document.getElementById("startOnboardingBtn")?.addEventListener("click", openOnboardingWizard);
  document.getElementById("startOnboardingEmpty")?.addEventListener("click", openAddCamera);
  document.getElementById("onboardingClose")?.addEventListener("click", () => {
    document.getElementById("cameraOnboardingDialog")?.close();
  });
  document.getElementById("onboardingBack")?.addEventListener("click", () => {
    if (wizardStep > 1) showWizardStep(wizardStep - 1);
  });
  document.getElementById("onboardingNext")?.addEventListener("click", () => {
    if (wizardStep === 2 && !document.getElementById("wizDayName").value.trim()) {
      showToast("Enter a day camera name");
      return;
    }
    if (wizardStep < WIZARD_STEPS) showWizardStep(wizardStep + 1);
  });
  document.getElementById("onboardingTest")?.addEventListener("click", testWizardCameras);
  document.getElementById("cameraOnboardingForm")?.addEventListener("submit", finishWizard);
  document.getElementById("camEnabled")?.addEventListener("change", syncEnabledLabel);

  document.getElementById("cameraForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = cameraPayload();
    if (!payload.name) {
      showToast("Camera name required");
      return;
    }
    try {
      let res;
      if (editingId) {
        res = await api(`/api/cameras/local/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
        showToast(`Camera "${payload.name}" updated`);
      } else {
        res = await api("/api/cameras/local", { method: "POST", body: JSON.stringify(payload) });
        showToast(`Camera "${payload.name}" added`);
      }
      if (res.sync?.synced?.length) {
        showToast(`Synced ${res.sync.synced.length} camera(s) to hardware controls`);
      } else if (res.sync?.error) {
        showToast(res.sync.error);
      }
      clearForm();
      loadCameras();
      window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
    } catch (ex) {
      showToast(ex.message);
    }
  });

  document.getElementById("testCameraBtn")?.addEventListener("click", async () => {
    setTestResult("Testing…", "");
    try {
      const res = await api("/api/cameras/local/test", {
        method: "POST",
        body: JSON.stringify(cameraPayload()),
      });
      const ok = Boolean(res.ok);
      const message = res.message || (ok ? "Connection successful" : "Unable to connect to camera");
      setTestResult(message, ok ? "ok" : "bad");
      if (editingId) testStatus[editingId] = ok ? "Online" : "Offline";
      showToast(message);
      loadCameras();
    } catch (ex) {
      setTestResult(ex.message, "bad");
      showToast(ex.message);
    }
  });

  document.getElementById("clearCameraForm")?.addEventListener("click", () => {
    clearForm();
    focusCameraName();
  });

  document.getElementById("syncCamerasBtn")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/backend/sync", { method: "POST" });
      if (res.synced?.length) {
        showToast(`Sync successful: ${res.synced.length} camera(s) registered in Hardware Controls`);
      } else if (res.error) {
        showToast(res.error);
      } else if (res.errors?.length) {
        showToast(`Sync issue: ${res.errors[0]}`);
      } else {
        showToast("Sync complete — no new cameras mapped.");
      }
      loadCameras();
    } catch (ex) {
      showToast(ex.message || "Sync failed — run ./scripts/start-controls.sh first.");
    }
  });

  document.getElementById("cameraSearch")?.addEventListener("input", renderFilteredCameras);
  document.getElementById("cameraTypeFilter")?.addEventListener("change", renderFilteredCameras);
  document.getElementById("cameraStatusFilter")?.addEventListener("change", renderFilteredCameras);

  if (!listBound) {
    document.getElementById("camerasList")?.addEventListener("click", onCameraListClick);
    listBound = true;
  }

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "cameras") loadCameras();
  });
  syncEnabledLabel();
  if (location.hash.replace("#", "") === "cameras") loadCameras();
}

function withTimeout(promise, ms = 8000) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error("Request timed out")), ms)),
  ]);
}

function cameraStatusOf(cam) {
  if (!cam.enabled) return "disabled";
  const tested = testStatus[cam.id];
  if (tested === "Online") return "online";
  if (tested === "Offline") return "offline";
  return "unknown";
}

function statusLabel(status) {
  return { online: "ONLINE", offline: "OFFLINE", disabled: "DISABLED", unknown: "UNKNOWN" }[status] || "UNKNOWN";
}

function protocolLabel(cam) {
  const parts = [];
  if (cam.hasRtsp || cam.rtspUrl) parts.push("RTSP");
  if (cam.username || cam.hasPassword) parts.push("ONVIF");
  return parts.join(" / ") || "—";
}

function safeAddress(cam) {
  if (cam.ipAddress) return cam.ipAddress;
  const rtsp = String(cam.rtspUrl || "");
  if (!rtsp) return "—";
  try {
    const host = new URL(rtsp.replace(/^rtsp/i, "http")).hostname;
    return host || "—";
  } catch {
    return "—";
  }
}

function typeKind(cam) {
  const t = String(cam.cameraType || "").toLowerCase();
  if (t === "thermal") return "thermal";
  if (t === "day") return "day";
  return "other";
}

function ptzLabel(mapping) {
  if (mapping === "ptz-1") return "PTZ 1";
  if (mapping === "ptz-2") return "PTZ 2";
  return "—";
}

function listMessage(text) {
  return `<tr><td colspan="7" class="cam-list-msg">${text}</td></tr>`;
}

function filteredCameras() {
  const q = (document.getElementById("cameraSearch")?.value || "").trim().toLowerCase();
  const type = document.getElementById("cameraTypeFilter")?.value || "";
  const status = document.getElementById("cameraStatusFilter")?.value || "";
  return camerasCache.filter((cam) => {
    if (type && cam.cameraType !== type) return false;
    if (status && cameraStatusOf(cam) !== status) return false;
    if (!q) return true;
    const hay = [cam.name, cam.cameraType, cam.ipAddress, cam.cameraGroup, protocolLabel(cam), ptzLabel(cam.ptzMapping)]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}

async function loadCameras() {
  const list = document.getElementById("camerasList");
  const controls = document.getElementById("controlsStatus");
  const empty = document.getElementById("camerasEmpty");
  if (!list) return;

  list.innerHTML = listMessage("Loading…");
  try {
    const localRes = await withTimeout(
      api("/api/cameras/local?include_all=true").catch((ex) => {
        if (ex.status === 403 || String(ex.message).includes("403") || String(ex.message).includes("permission")) {
          return { cameras: [], permissionError: true };
        }
        throw ex;
      }),
      4000,
    );

    if (localRes.permissionError) {
      camerasCache = [];
      empty?.classList.add("hidden");
      list.innerHTML = listMessage("Permission required: manage-cameras. Sign out and sign in again.");
      if (controls) controls.textContent = "—";
      return;
    }

    camerasCache = localRes.cameras || [];
    empty?.classList.toggle("hidden", camerasCache.length > 0);
    renderFilteredCameras();

    if (controls) controls.textContent = `Local: ${camerasCache.length} configured`;
    withTimeout(api("/api/backend/status").catch(() => ({})), 2000)
      .then((st) => {
        const online = Boolean(st.controls?.online);
        if (controls) {
          controls.textContent = `Local: ${camerasCache.length} configured · Hardware Controls: ${online ? "ready" : "offline"}`;
        }
      })
      .catch(() => {
        if (controls) controls.textContent = `Local: ${camerasCache.length} configured · Hardware: unknown`;
      });
  } catch (ex) {
    camerasCache = [];
    empty?.classList.remove("hidden");
    list.innerHTML = listMessage(esc(ex.message));
    if (controls) controls.textContent = "Status unavailable";
  }
}

function renderFilteredCameras() {
  const list = document.getElementById("camerasList");
  const empty = document.getElementById("camerasEmpty");
  if (!list) return;
  if (!camerasCache.length) {
    list.innerHTML = "";
    empty?.classList.remove("hidden");
    return;
  }
  empty?.classList.add("hidden");
  const visible = filteredCameras();
  if (!visible.length) {
    list.innerHTML = listMessage("No cameras match the current search or filters.");
    return;
  }
  renderCameraRows(visible);
}

function renderCameraRows(local) {
  const list = document.getElementById("camerasList");
  list.innerHTML = local.map((c) => {
    const status = cameraStatusOf(c);
    const kind = typeKind(c);
    const typeClass = kind === "thermal" ? "is-thermal" : kind === "day" ? "is-day" : "";
    const typeText = kind === "thermal" ? "THERMAL" : kind === "day" ? "DAY" : esc(c.cameraType || "OTHER");
    const toggleLabel = c.enabled ? "Disable" : "Enable";
    const group = String(c.cameraGroup || "").trim();
    return `<tr class="${c.enabled ? "" : "is-disabled"}" data-camera-id="${c.id}">
      <td>
        <div class="cam-name">
          <strong>${esc(c.name)}</strong>
          ${group ? `<span>${esc(group)}</span>` : ""}
        </div>
      </td>
      <td><span class="cam-type ${typeClass}"><span class="cam-type-dot" aria-hidden="true"></span>${typeText}</span></td>
      <td>${esc(protocolLabel(c))}</td>
      <td>${esc(safeAddress(c))}</td>
      <td>${esc(ptzLabel(c.ptzMapping))}</td>
      <td><span class="camera-status-pill is-${status}">${statusLabel(status)}</span></td>
      <td>
        <div class="camera-row-actions">
          <button type="button" class="mini" data-action="edit" data-id="${c.id}">Edit</button>
          <button type="button" class="mini" data-action="test" data-id="${c.id}">Test</button>
          <button type="button" class="mini" data-action="toggle" data-id="${c.id}">${toggleLabel}</button>
          <button type="button" class="mini danger" data-action="delete" data-id="${c.id}">Delete</button>
        </div>
      </td>
    </tr>`;
  }).join("");
}

function onCameraListClick(e) {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = parseInt(btn.dataset.id, 10);
  const action = btn.dataset.action;
  if (action === "edit") editCamera(camerasCache, id);
  else if (action === "test") testCameraRow(camerasCache, id);
  else if (action === "delete") deleteCamera(id);
  else if (action === "toggle") toggleCameraEnabled(id);
}

function editCamera(local, id) {
  const cam = local.find((x) => x.id === id);
  if (!cam) return;
  editingId = cam.id;
  document.getElementById("cameraEditId").value = String(cam.id);
  setFormTitle("edit", cam.name);
  document.getElementById("saveCameraBtn").textContent = "Save Camera";
  document.getElementById("camName").value = cam.name;
  document.getElementById("camType").value = cam.cameraType;
  document.getElementById("camIp").value = cam.ipAddress;
  document.getElementById("camRtsp").value = cam.rtspUrl;
  document.getElementById("camOnvif").value = cam.onvifPort || 80;
  document.getElementById("camUser").value = cam.username || "";
  document.getElementById("camPass").value = "";
  document.getElementById("camPtz").value = cam.ptzMapping || "none";
  document.getElementById("camGroup").value = cam.cameraGroup || "";
  document.getElementById("camEnabled").checked = cam.enabled;
  const modeSel = document.getElementById("camConnectionMode");
  const legacyOpt = document.getElementById("camModeLegacyOpt");
  const mode = cam.connectionMode || "legacy";
  if (legacyOpt) legacyOpt.hidden = mode !== "legacy";
  if (modeSel) modeSel.value = mode === "ip" ? "ip" : mode === "lan" ? "lan" : "legacy";
  setTestResult("", "");
  syncEnabledLabel();
  focusCameraName();
}

async function testCameraRow(local, id) {
  const cam = local.find((x) => x.id === id);
  if (!cam) return;
  try {
    showToast("Testing connection…");
    const res = await api("/api/cameras/local/test", {
      method: "POST",
      body: JSON.stringify(payloadFromCamera(cam)),
    });
    const ok = Boolean(res.ok);
    testStatus[id] = ok ? "Online" : "Offline";
    const message = res.message || (ok ? "Connection successful" : "Unable to connect to camera");
    showToast(message);
    renderFilteredCameras();
  } catch (ex) {
    testStatus[id] = "Offline";
    showToast(ex.message || "Unable to connect to camera");
    renderFilteredCameras();
  }
}

async function toggleCameraEnabled(id) {
  const cam = camerasCache.find((x) => x.id === id);
  if (!cam) return;
  const next = !cam.enabled;
  if (!next && !confirm("Disable this camera?")) return;
  try {
    await api(`/api/cameras/local/${id}`, {
      method: "PUT",
      body: JSON.stringify(payloadFromCamera(cam, { enabled: next, password: "" })),
    });
    showToast(next ? "Camera enabled" : "Camera disabled");
    if (editingId === id) {
      document.getElementById("camEnabled").checked = next;
      syncEnabledLabel();
    }
    loadCameras();
    window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
  } catch (ex) {
    showToast(ex.message || "Unable to update camera");
  }
}

async function deleteCamera(id) {
  if (!confirm("Delete this camera configuration?")) return;
  await api(`/api/cameras/local/${id}`, { method: "DELETE" });
  showToast("Camera deleted");
  if (editingId === id) clearForm();
  loadCameras();
  window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
