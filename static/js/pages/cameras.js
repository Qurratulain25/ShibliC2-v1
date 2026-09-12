import { api, showToast } from "../api.js";

let editingId = null;
const testStatus = {};
let wizardStep = 1;
const WIZARD_STEPS = 5;

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

function clearForm() {
  editingId = null;
  document.getElementById("cameraEditId").value = "";
  document.getElementById("cameraFormTitle").textContent = "Add Camera";
  document.getElementById("saveCameraBtn").textContent = "Save Camera";
  document.getElementById("disableCameraBtn")?.classList.add("hidden");
  document.getElementById("cameraForm").reset();
  document.getElementById("camOnvif").value = "80";
  document.getElementById("camEnabled").checked = true;
  const legacyOpt = document.getElementById("camModeLegacyOpt");
  if (legacyOpt) legacyOpt.hidden = true;
  const modeSel = document.getElementById("camConnectionMode");
  if (modeSel) modeSel.value = "lan";
  document.getElementById("cameraTestResult").textContent = "";
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
  document.getElementById("startOnboardingBtn")?.addEventListener("click", openOnboardingWizard);
  document.getElementById("startOnboardingEmpty")?.addEventListener("click", openOnboardingWizard);
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
    const resultEl = document.getElementById("cameraTestResult");
    resultEl.textContent = "Testing…";
    try {
      const res = await api("/api/cameras/local/test", {
        method: "POST",
        body: JSON.stringify(cameraPayload()),
      });
      resultEl.textContent = res.message || (res.ok ? "OK" : "Failed");
      if (editingId) testStatus[editingId] = res.ok ? "Online" : "Offline";
      showToast(res.message);
      loadCameras();
    } catch (ex) {
      resultEl.textContent = ex.message;
      showToast(ex.message);
    }
  });

  document.getElementById("disableCameraBtn")?.addEventListener("click", async () => {
    if (!editingId) return;
    if (!confirm("Disable this camera?")) return;
    const payload = { ...cameraPayload(), enabled: false };
    await api(`/api/cameras/local/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
    showToast("Camera disabled");
    clearForm();
    loadCameras();
    window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
  });

  document.getElementById("clearCameraForm")?.addEventListener("click", clearForm);

  document.getElementById("syncCamerasBtn")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/backend/sync", { method: "POST" });
      if (res.synced?.length) {
        showToast(`Sync success: ${res.synced.length} camera(s) registered in Hardware Controls`);
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

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "cameras") loadCameras();
  });
  if (location.hash.replace("#", "") === "cameras") loadCameras();
}

function withTimeout(promise, ms = 8000) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error("Request timed out")), ms)),
  ]);
}

async function loadCameras() {
  const list = document.getElementById("camerasList");
  const controls = document.getElementById("controlsStatus");
  const empty = document.getElementById("camerasEmpty");
  if (!list) return;

      list.innerHTML = "<tr><td colspan='8'>Loading…</td></tr>";
  try {
    // Local DB only — never block the page on Core/controls
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
      list.innerHTML = "<tr><td colspan='8'>Permission required: manage-cameras. Sign out and sign in again.</td></tr>";
      if (controls) controls.textContent = "—";
      return;
    }

    const local = localRes.cameras || [];
    empty?.classList.toggle("hidden", local.length > 0);

    if (!local.length) {
      list.innerHTML = "<tr><td colspan='8' class='muted'>No cameras yet — use the form above or Add Camera Wizard. (OK without hardware attached.)</td></tr>";
    } else {
      renderCameraRows(local);
    }

    if (controls) controls.textContent = `Local: ${local.length} configured`;
    // Optional hardware status — ignore failures / timeouts
    withTimeout(api("/api/backend/status").catch(() => ({})), 2000)
      .then((st) => {
        const online = Boolean(st.controls?.online);
        if (controls) {
          controls.textContent = `Local: ${local.length} configured · Hardware Controls: ${online ? "ready" : "offline (OK without camera)"}`;
        }
      })
      .catch(() => {
        if (controls) controls.textContent = `Local: ${local.length} configured · Hardware: unknown`;
      });
  } catch (ex) {
    list.innerHTML = `<tr><td colspan='8'>${esc(ex.message)} — form above still works for adding cameras.</td></tr>`;
    empty?.classList.remove("hidden");
    if (controls) controls.textContent = "Status unavailable";
  }
}

function renderCameraRows(local) {
  const list = document.getElementById("camerasList");
  list.innerHTML = local.map((c) => {
      const status = testStatus[c.id] || (c.enabled ? "Configured" : "Disabled");
      const statusClass = status === "Online" ? "online" : status === "Offline" ? "offline" : "";
      const modeLabel = c.connectionMode === "lan" ? "LAN" : c.connectionMode === "ip" ? "IP / Online" : "Unassigned";
      return `<tr>
      <td>${esc(c.name)}</td>
      <td>${esc(c.cameraType)}</td>
      <td>${esc(modeLabel)}</td>
      <td>${esc(c.ipAddress || "—")}</td>
      <td class="mono">${esc(shortRtsp(c.rtspUrl))}</td>
      <td>${esc(c.ptzMapping)}</td>
      <td><span class="${statusClass}">${status}</span></td>
      <td class="actions-cell">
        <button type="button" class="mini" data-edit="${c.id}">Edit</button>
        <button type="button" class="mini" data-test="${c.id}">Test</button>
        <button type="button" class="mini danger" data-del="${c.id}">Delete</button>
      </td>
    </tr>`;
    }).join("");

  list.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => editCamera(local, parseInt(btn.dataset.edit, 10)));
    });

    list.querySelectorAll("[data-test]").forEach((btn) => {
      btn.addEventListener("click", () => testCameraRow(local, parseInt(btn.dataset.test, 10)));
    });

    list.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this camera configuration?")) return;
        await api(`/api/cameras/local/${btn.dataset.del}`, { method: "DELETE" });
        showToast("Camera deleted");
        loadCameras();
        window.dispatchEvent(new CustomEvent("shibli:cameras-changed"));
      });
    });
}

function editCamera(local, id) {
  const cam = local.find((x) => x.id === id);
  if (!cam) return;
  editingId = cam.id;
  document.getElementById("cameraFormTitle").textContent = `Edit Camera: ${cam.name}`;
  document.getElementById("saveCameraBtn").textContent = "Update Camera";
  document.getElementById("disableCameraBtn")?.classList.remove("hidden");
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
  document.querySelector("#page-cameras .page-body")?.scrollTo({ top: 0, behavior: "smooth" });
}

async function testCameraRow(local, id) {
  const cam = local.find((x) => x.id === id);
  if (!cam) return;
  editCamera(local, id);
  document.getElementById("testCameraBtn")?.click();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function shortRtsp(url) {
  if (!url) return "—";
  const redacted = String(url).replace(/\/\/[^@/?#]+@/, "//***@");
  return redacted.length > 48 ? `${redacted.slice(0, 45)}…` : redacted;
}
