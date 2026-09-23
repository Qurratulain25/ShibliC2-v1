const TRACKING_UI_ENDPOINT = "/api/v1.1/tracking/ui";
const TRACKING_RESET_ENDPOINT = "/api/v1.1/tracking/mock/reset";

const VISIBLE_TRACK_STATES = new Set(["ACTIVE", "REACQUIRED"]);
const STATUS_POLL_MS = 400;

const state = {
  loaded: false,
  running: false,
  busy: false,
  videoUrl: null,
  selectedFile: null,
  selectedFollowId: null,
  tracks: [],
  tracksByFrame: new Map(),
  videoFps: 30,
  sessionId: null,
  sessionUrls: null,
  processingReady: false,
  processGeneration: 0,
  alertedIds: new Set(),
  audioContext: null,
};

function showMessage(message) {
  const el = document.getElementById("trackingMessage");
  if (el) el.textContent = message || "";
}

function formatFileSize(bytes) {
  const b = Number(bytes);
  if (!Number.isFinite(b) || b <= 0) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`;
  return `${(b / 1073741824).toFixed(1)} GB`;
}

function formatMediaDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds)));
  if (!Number.isFinite(s)) return "";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function updateFileMeta(file) {
  const name = document.getElementById("trackingFileName");
  const info = document.getElementById("trackingFileInfo");
  if (name) name.textContent = file?.name || "No file selected";
  if (info) info.textContent = file ? formatFileSize(file.size) : "";
}

function refreshFileDuration() {
  const video = getVideo();
  const info = document.getElementById("trackingFileInfo");
  if (!info || !video) return;
  const parts = [];
  if (Number.isFinite(video.duration) && video.duration > 0) {
    parts.push(formatMediaDuration(video.duration));
  }
  if (state.selectedFile) {
    const size = formatFileSize(state.selectedFile.size);
    if (size) parts.push(size);
  }
  info.textContent = parts.join(" · ");
}

function renderTrackTable(tracks) {
  const body = document.getElementById("trackingResultsBody");
  if (!body) return;
  const rows = currentVisibleTracks(tracks);
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="4" class="tracking-lab-muted">${
      state.processingReady ? "No tracked objects in this frame." : "No tracking results yet."
    }</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((track) => {
    const confidence = Number(track.confidence);
    const confText = Number.isFinite(confidence) ? confidence.toFixed(2) : "—";
    return `<tr>
      <td>${track.track_id ?? "—"}</td>
      <td>${String(track.class_name || "—")}</td>
      <td>${confText}</td>
      <td>${String(track.state || "—")}</td>
    </tr>`;
  }).join("");
}

function getVideo() {
  return document.getElementById("trackingVideo");
}

function getCanvas() {
  return document.getElementById("trackingOverlay");
}

function isVisibleTrack(track) {
  return Boolean(track) && VISIBLE_TRACK_STATES.has(track.state);
}

function currentVisibleTracks(tracks) {
  return (tracks || []).filter(isVisibleTrack);
}

function canSelectFollow(track) {
  return isVisibleTrack(track);
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function operatorOverlayLabel(track) {
  return String(track?.class_name || "").toUpperCase();
}

function operatorThreatStatus(tracks) {
  const hasDrone = currentVisibleTracks(tracks).some(
    (track) => track.class_name === "drone"
  );

  return hasDrone ? "DRONE DETECTED" : "NO THREAT";
}

function operatorPtzLabel(following, command) {
  const text = String(command || "STOP").trim().toUpperCase();

  if (!text || text === "STOP") {
    return following ? "FOLLOWING TARGET" : "STOPPED";
  }

  return text;
}

function setPlaybackEnabled(enabled) {
  const video = getVideo();

  if (video) {
    video.controls = Boolean(enabled);
  }
}

function setThreatStatus(tracks) {
  const card = document.getElementById("trackingThreatCard");
  const label = document.getElementById("trackingThreatStatus");
  const status = operatorThreatStatus(tracks);
  const alert = status === "DRONE DETECTED";

  if (label) {
    label.textContent = alert ? "⚠ DRONE DETECTED" : "✓ NO THREAT";
  }

  if (card) {
    card.classList.toggle("is-alert", alert);
    card.classList.toggle("is-clear", !alert);
  }
}

function renderFollowControls() {
  const start = document.getElementById("trackingFollowTarget");
  const active = document.getElementById("trackingFollowActive");
  const canFollow = (
    state.processingReady
    && currentVisibleTracks(state.tracks).some(canSelectFollow)
  );
  const following = Boolean(state.selectedFollowId);

  if (start) {
    start.hidden = following || !canFollow;
  }

  if (active) {
    active.hidden = !following;
  }
}

function formatAlertClock() {
  const now = new Date();

  return [
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join(":");
}

function appendAlertLog() {
  const log = document.getElementById("trackingAlertLog");

  if (!log) {
    return;
  }

  const line = `${formatAlertClock()}  Drone detected`;

  if (log.dataset.empty !== "false") {
    log.textContent = line;
    log.dataset.empty = "false";
  } else {
    log.textContent = `${log.textContent}\n${line}`;
  }
}

function clearAlertLog() {
  const log = document.getElementById("trackingAlertLog");

  if (log) {
    log.textContent = "No events";
    log.dataset.empty = "true";
  }
}

function ensureAudioContext() {
  const AudioContextClass =
    window.AudioContext || window.webkitAudioContext;

  if (!AudioContextClass) {
    return null;
  }

  if (!state.audioContext) {
    state.audioContext = new AudioContextClass();
  }

  if (state.audioContext.state === "suspended") {
    state.audioContext.resume().catch(() => {});
  }

  return state.audioContext;
}

function playDroneAlertSound() {
  const context = ensureAudioContext();

  if (!context) {
    return;
  }

  const oscillator = context.createOscillator();
  const gain = context.createGain();

  oscillator.type = "square";
  oscillator.frequency.value = 880;
  gain.gain.value = 0.05;
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.16);
}

function resetAlertState() {
  state.alertedIds.clear();
  clearAlertLog();
  setThreatStatus([]);
}

function processDroneAlerts(tracks) {
  const visible = currentVisibleTracks(tracks).filter((track) => (
    track.class_name === "drone"
  ));

  setThreatStatus(tracks);

  for (const track of visible) {
    if (state.alertedIds.has(track.track_id)) {
      continue;
    }

    state.alertedIds.add(track.track_id);
    appendAlertLog();
    playDroneAlertSound();
  }
}

async function updateFollowPanel() {
  const command = document.getElementById("trackingPtzCommand");

  if (!command) {
    return;
  }

  renderFollowControls();

  try {
    const video = getVideo();
    const frameWidth = video?.videoWidth || 0;
    const frameHeight = video?.videoHeight || 0;

    if (!frameWidth || !frameHeight) {
      command.textContent = operatorPtzLabel(
        Boolean(state.selectedFollowId),
        "STOP"
      );
      return;
    }

    const response = await fetch(
      `/api/v1.1/tracking/follow/ptz?frame_width=${frameWidth}&frame_height=${frameHeight}`
    );

    if (!response.ok) {
      throw new Error(`PTZ endpoint returned ${response.status}`);
    }

    const result = await response.json();

    if (result.track_id != null) {
      state.selectedFollowId = result.track_id;
    }

    command.textContent = operatorPtzLabel(
      Boolean(state.selectedFollowId),
      result.command
    );
    renderFollowControls();
  } catch (error) {
    command.textContent = operatorPtzLabel(
      Boolean(state.selectedFollowId),
      "STOP"
    );
  }
}

async function selectFollowTarget(trackId) {
  const target = state.tracks.find(
    (track) => track.track_id === trackId
  );

  if (!target || !canSelectFollow(target)) {
    return;
  }

  try {
    const response = await fetch(
      `/api/v1.1/tracking/follow/${trackId}`,
      { method: "POST" }
    );

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Could not follow the target.");
    }

    const result = await response.json();
    state.selectedFollowId = result.active_follow_id;
    await updateFollowPanel();
    drawOverlay();
  } catch (error) {
    showMessage(error.message || "Could not follow the target.");
  }
}

async function followAvailableTarget() {
  const target = currentVisibleTracks(state.tracks).find((track) => (
    track.class_name === "drone"
  )) || currentVisibleTracks(state.tracks)[0];

  if (!target) {
    return;
  }

  await selectFollowTarget(target.track_id);
}

async function stopFollow() {
  try {
    await fetch("/api/v1.1/tracking/follow", { method: "DELETE" });
  } catch {
    // Best-effort clear.
  }

  state.selectedFollowId = null;
  await updateFollowPanel();
  drawOverlay();
}

function clearCanvas() {
  const canvas = getCanvas();
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function setupCanvas() {
  const video = getVideo();
  const canvas = getCanvas();

  if (!video || !canvas) {
    return;
  }

  if (!video.videoWidth || !video.videoHeight) {
    clearCanvas();
    return;
  }

  const stage = canvas.parentElement;

  if (!stage) {
    return;
  }

  const rect = stage.getBoundingClientRect();

  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));

  drawOverlay();
}

function drawOverlay() {
  const video = getVideo();
  const canvas = getCanvas();

  if (!video || !canvas) {
    return;
  }

  if (
    !state.processingReady
    || !video.videoWidth
    || !video.videoHeight
    || !canvas.width
    || !canvas.height
  ) {
    clearCanvas();
    return;
  }

  const ctx = canvas.getContext("2d");

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  const scale = Math.min(
    canvas.width / sourceWidth,
    canvas.height / sourceHeight
  );
  const displayedWidth = sourceWidth * scale;
  const displayedHeight = sourceHeight * scale;
  const offsetX = (canvas.width - displayedWidth) / 2;
  const offsetY = (canvas.height - displayedHeight) / 2;

  for (const track of currentVisibleTracks(state.tracks)) {
    const [sourceX1, sourceY1, sourceX2, sourceY2] = track.bbox;
    const x1 = offsetX + sourceX1 * scale;
    const y1 = offsetY + sourceY1 * scale;
    const x2 = offsetX + sourceX2 * scale;
    const y2 = offsetY + sourceY2 * scale;
    const selected = track.track_id === state.selectedFollowId;
    const label = operatorOverlayLabel(track);

    ctx.save();
    ctx.lineWidth = selected ? 4 : 3;
    ctx.strokeStyle = selected ? "#ffd84d" : "#45d483";
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

    ctx.font = "800 16px Segoe UI, sans-serif";
    const metrics = ctx.measureText(label);
    const labelHeight = 26;

    ctx.fillStyle = "rgba(0,0,0,.72)";
    ctx.fillRect(
      x1,
      Math.max(0, y1 - labelHeight),
      metrics.width + 16,
      labelHeight
    );
    ctx.fillStyle = selected ? "#ffd84d" : "#ffffff";
    ctx.fillText(label, x1 + 8, Math.max(18, y1 - 8));
    ctx.restore();
  }
}

async function loadProcessedTracks(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("Could not load tracking results.");
  }

  const records = await response.json();

  if (!Array.isArray(records)) {
    throw new Error("Tracking results are not ready.");
  }

  state.tracksByFrame = new Map();
  resetAlertState();

  for (const record of records) {
    const frame = Number(record.frame);

    if (!Number.isFinite(frame)) {
      continue;
    }

    if (!state.tracksByFrame.has(frame)) {
      state.tracksByFrame.set(frame, []);
    }

    state.tracksByFrame.get(frame).push(record);
  }

  return records;
}

function setControlAvailability() {
  const start = document.getElementById("trackingStart");
  const stop = document.getElementById("trackingStop");
  const hasFile = Boolean(state.selectedFile);

  if (start) {
    start.disabled = !hasFile || state.busy || state.running;
    start.textContent = state.processingReady ? "Play Result" : "Start Tracking";
  }

  if (stop) {
    stop.disabled = !state.running && !state.busy;
  }
}

async function resetTracking() {
  const video = getVideo();

  state.processGeneration += 1;
  state.running = false;
  state.selectedFollowId = null;
  state.tracks = [];
  state.tracksByFrame = new Map();
  state.processingReady = false;
  state.sessionId = null;
  state.sessionUrls = null;
  resetAlertState();
  setTrackingOutputsEnabled(false);
  setPlaybackEnabled(false);
  state.busy = false;
  updateProcessPanel({ status: "READY", percent: 0 });
  renderTrackTable([]);

  if (video) {
    video.pause();
    video.currentTime = 0;
  }

  try {
    await fetch("/api/v1.1/tracking/follow", { method: "DELETE" });
    await fetch(TRACKING_RESET_ENDPOINT, { method: "POST" });
  } catch {
    // Best-effort reset.
  }

  processDroneAlerts([]);
  renderFollowControls();
  await updateFollowPanel();
  clearCanvas();
  setControlAvailability();
  showMessage("");
}

async function beginProcessing(file) {
  const video = getVideo();

  if (!video || !file) {
    showMessage("Choose a video first.");
    return;
  }

  const generation = ++state.processGeneration;

  try {
    ensureAudioContext();
    resetAlertState();
    setTrackingOutputsEnabled(false);
    setPlaybackEnabled(false);
    state.busy = true;
    state.processingReady = false;
    state.running = false;
    state.tracksByFrame = new Map();
    state.tracks = [];
    state.selectedFollowId = null;
    clearCanvas();
    setControlAvailability();

    video.pause();
    video.currentTime = 0;

    const result = await processUploadedVideo(file);

    if (generation !== state.processGeneration) {
      return;
    }

    state.sessionId = result.session_id;
    state.sessionUrls = result.urls || {};
    state.videoFps = Number(result.fps || 30);
    video.dataset.fps = String(state.videoFps);
    updateProcessPanel(result);

    const ready = await pollSessionUntilReady(
      result.session_id,
      generation
    );

    if (generation !== state.processGeneration) {
      return;
    }

    const urls = ready.urls || state.sessionUrls || {};

    await loadProcessedTracks(urls.json);

    state.processingReady = true;
    state.busy = false;
    state.videoFps = Number(ready.fps || state.videoFps);
    video.dataset.fps = String(state.videoFps);
    video.pause();
    video.currentTime = 0;
    setPlaybackEnabled(true);
    updateProcessPanel({ ...ready, status: "COMPLETED" });
    setTrackingOutputsEnabled(true);
    enableExportButtons(urls);
    setControlAvailability();
    setupCanvas();
    updateTracksForCurrentFrame();
    showMessage("");
  } catch (error) {
    if (generation !== state.processGeneration) {
      return;
    }

    state.processingReady = false;
    state.busy = false;
    setPlaybackEnabled(false);
    setControlAvailability();
    updateProcessPanel({
      status: "FAILED",
      percent: 0,
      error: error.message,
    });
    showMessage(error.message || "Unable to process video");
  }
}

async function startPlayback() {
  const video = getVideo();

  if (!video) {
    return;
  }

  if (!state.processingReady) {
    showMessage("Wait until the video is ready.");
    return;
  }

  try {
    ensureAudioContext();
    await video.play();
    state.running = true;
    setControlAvailability();
  } catch (error) {
    showMessage("Could not play the video.");
  }
}

function stopTracking() {
  const video = getVideo();

  if (state.busy && !state.processingReady) {
    state.processGeneration += 1;
    state.busy = false;
    updateProcessPanel({ status: "STOPPED", percent: 0 });
    showMessage("Processing stopped.");
    setControlAvailability();
    return;
  }

  state.running = false;
  video?.pause();
  setControlAvailability();
}

function bindTrackingPage() {
  if (state.loaded) return;
  state.loaded = true;

  const video = getVideo();
  const input = document.getElementById("trackingVideoInput");

  bindProcessedVideoSync();
  setPlaybackEnabled(false);

  input?.addEventListener("change", () => {
    const file = input.files?.[0];

    if (!file) return;

    if (state.videoUrl) {
      URL.revokeObjectURL(state.videoUrl);
    }

    state.selectedFile = file;
    state.processGeneration += 1;
    state.processingReady = false;
    state.running = false;
    state.busy = false;
    state.sessionId = null;
    state.sessionUrls = null;
    state.tracks = [];
    state.tracksByFrame = new Map();
    state.videoUrl = URL.createObjectURL(file);
    video.src = state.videoUrl;
    video.dataset.fps = "30";
    video.pause();
    document.getElementById("trackingEmptyState")?.classList.add("hidden");
    updateFileMeta(file);
    setTrackingOutputsEnabled(false);
    setPlaybackEnabled(false);
    clearCanvas();
    renderTrackTable([]);
    updateProcessPanel({ status: "READY", percent: 0 });
    setControlAvailability();
    video.load();
  });

  video?.addEventListener("loadedmetadata", () => {
    setupCanvas();
    video.pause();
    refreshFileDuration();
    if (!state.processingReady) {
      video.currentTime = 0;
    }
  });

  video?.addEventListener("play", () => {
    if (!state.processingReady) {
      video.pause();
      return;
    }

    state.running = true;
    setControlAvailability();
    requestAnimationFrame(syncTracksWhilePlaying);
  });

  video?.addEventListener("ended", () => {
    stopTracking();
  });

  document.getElementById("trackingStart")?.addEventListener(
    "click",
    () => {
      if (state.processingReady) {
        startPlayback();
        return;
      }
      if (state.selectedFile) {
        beginProcessing(state.selectedFile);
      } else {
        showMessage("Choose a video first.");
      }
    }
  );
  document.getElementById("trackingStop")?.addEventListener(
    "click",
    stopTracking
  );
  document.getElementById("trackingReset")?.addEventListener(
    "click",
    resetTracking
  );
  document.getElementById("trackingFollowTarget")?.addEventListener(
    "click",
    () => {
      followAvailableTarget().catch((error) => {
        showMessage(error.message);
      });
    }
  );
  document.getElementById("trackingStopFollow")?.addEventListener(
    "click",
    () => {
      stopFollow().catch((error) => {
        showMessage(error.message);
      });
    }
  );

  document.getElementById("trackingExportVideo")?.addEventListener(
    "click",
    () => {
      exportAnnotatedMp4().catch((error) => {
        showMessage(error.message);
      });
    }
  );
  document.getElementById("trackingExportJson")?.addEventListener(
    "click",
    (event) => {
      const url = event.currentTarget.dataset.url;
      if (url) downloadUrl(url, "tracks.json");
    }
  );
  document.getElementById("trackingExportCsv")?.addEventListener(
    "click",
    (event) => {
      const url = event.currentTarget.dataset.url;
      if (url) downloadUrl(url, "tracks.csv");
    }
  );

  window.addEventListener("resize", setupCanvas);
}

async function ensureTrackingPage() {
  loadTrackingStyles();
  let page = document.getElementById("page-tracking");

  if (!page) {
    const response = await fetch(TRACKING_UI_ENDPOINT);

    if (!response.ok) {
      throw new Error("Could not load tracking.");
    }

    const html = await response.text();
    const workspace = document.querySelector(".workspace");

    if (!workspace) {
      throw new Error("Workspace not found.");
    }

    workspace.insertAdjacentHTML("beforeend", html);
    page = document.getElementById("page-tracking");
  }

  page?.classList.remove("hidden");
  bindTrackingPage();
}

async function handlePageChange(event) {
  if (event.detail !== "tracking") return;

  try {
    await ensureTrackingPage();
  } catch (error) {
    console.error(error);
    showMessage(error.message || "Could not open tracking.");
  }
}

function loadTrackingStyles() {
  if (document.getElementById("tracking-v1-1-styles")) return;

  const link = document.createElement("link");
  link.id = "tracking-v1-1-styles";
  link.rel = "stylesheet";
  link.href = "/api/v1.1/tracking/assets/tracking.css?v=20260922-lab";
  document.head.appendChild(link);
}

window.addEventListener("shibli:page", handlePageChange);

window.addEventListener("shibli:logged-out", () => {
  if (state.videoUrl) {
    URL.revokeObjectURL(state.videoUrl);
  }

  state.videoUrl = null;
  state.selectedFile = null;
  state.running = false;
  state.busy = false;
  state.loaded = false;
  state.tracks = [];
  state.tracksByFrame.clear();
  state.sessionId = null;
  state.alertedIds.clear();
  state.processingReady = false;
});

async function processUploadedVideo(file) {
  const sensorSelect = document.getElementById("trackingSensor");
  const sensor = sensorSelect?.value;

  if (!sensor) {
    throw new Error("Select RGB / Day or Thermal.");
  }

  const formData = new FormData();
  formData.append("video", file);
  formData.append("modality", sensor);

  updateProcessPanel({
    status: "QUEUED",
    percent: 0,
  });

  const response = await fetch(
    "/api/v1.1/tracking/process",
    {
      method: "POST",
      body: formData,
    }
  );

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not process the video.");
  }

  return response.json();
}

function setTrackingOutputsEnabled(enabled) {
  [
    "trackingExportVideo",
    "trackingExportJson",
    "trackingExportCsv",
  ].forEach((id) => {
    const button = document.getElementById(id);

    if (button) {
      button.disabled = !enabled;
    }
  });

  renderFollowControls();
}

function updateProcessPanel(status) {
  const label = document.getElementById("trackingProcessStatus");
  const percent = document.getElementById("trackingProcessPercent");
  const fill = document.getElementById("trackingProcessBarFill");
  const value = Number(status.percent || 0);
  const name = String(status.status || "READY").toUpperCase();

  let text = "READY";

  if (name === "QUEUED" || name === "PROCESSING") {
    text = "PROCESSING";
  } else if (name === "FAILED") {
    text = "FAILED";
  } else if (name === "STOPPED") {
    text = "STOPPED";
  } else if (name === "COMPLETED") {
    text = "COMPLETED";
  } else if (name === "READY") {
    text = state.processingReady ? "COMPLETED" : "READY";
  }

  if (label) {
    label.textContent = text;
  }

  if (percent) {
    if (name === "QUEUED" || name === "PROCESSING") {
      percent.textContent = Number.isFinite(value) ? `${value}%` : "";
    } else if (name === "COMPLETED" || (name === "READY" && state.processingReady)) {
      percent.textContent = "100%";
    } else {
      percent.textContent = "";
    }
  }

  if (fill) {
    let width = Math.max(0, Math.min(100, value));
    if (name === "READY" && !state.processingReady) width = 0;
    if (name === "COMPLETED" || (name === "READY" && state.processingReady)) width = 100;
    fill.style.width = `${width}%`;
  }
}

async function pollSessionUntilReady(sessionId, generation) {
  const statusUrl = `/api/v1.1/tracking/session/${sessionId}/status`;

  while (generation === state.processGeneration) {
    const response = await fetch(statusUrl);

    if (!response.ok) {
      throw new Error("Could not read processing status.");
    }

    const status = await response.json();
    updateProcessPanel(status);

    if (status.status === "READY") {
      return status;
    }

    if (status.status === "FAILED") {
      throw new Error(
        status.error || "Processing failed."
      );
    }

    await sleep(STATUS_POLL_MS);
  }

  throw new Error("Processing cancelled.");
}

function enableExportButtons(urls) {
  const jsonButton = document.getElementById("trackingExportJson");
  const csvButton = document.getElementById("trackingExportCsv");
  const videoButton = document.getElementById("trackingExportVideo");

  if (jsonButton) {
    jsonButton.disabled = false;
    jsonButton.dataset.url = urls.json;
  }

  if (csvButton) {
    csvButton.disabled = false;
    csvButton.dataset.url = urls.csv;
  }

  if (videoButton) {
    videoButton.disabled = false;
  }
}

async function exportAnnotatedMp4() {
  if (!state.sessionId) {
    throw new Error("Tracking results are not ready.");
  }

  const response = await fetch(
    `/api/v1.1/tracking/session/${state.sessionId}/export/mp4`,
    { method: "POST" }
  );

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not export the video.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  downloadUrl(url, "annotated.mp4");
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function downloadUrl(url, filename) {
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  link.target = "_blank";

  document.body.appendChild(link);
  link.click();
  link.remove();
}

function getCurrentVideoFrame() {
  const video = getVideo();

  if (!video) {
    return 0;
  }

  const fps = Number(video.dataset.fps) || state.videoFps || 30;

  return Math.max(0, Math.floor(video.currentTime * fps));
}

function updateTracksForCurrentFrame() {
  if (!state.processingReady || !state.tracksByFrame.size) {
    state.tracks = [];
    processDroneAlerts([]);
    renderFollowControls();
    renderTrackTable([]);
    clearCanvas();
    return;
  }

  const frame = getCurrentVideoFrame();
  const frameRecords = state.tracksByFrame.get(frame) || [];

  state.tracks = currentVisibleTracks(frameRecords);
  processDroneAlerts(state.tracks);
  renderTrackTable(state.tracks);
  updateFollowPanel();
  drawOverlay();
}

function bindProcessedVideoSync() {
  const video = getVideo();

  if (!video) {
    return;
  }

  video.addEventListener("timeupdate", updateTracksForCurrentFrame);
  video.addEventListener("seeked", updateTracksForCurrentFrame);
  video.addEventListener("pause", updateTracksForCurrentFrame);
}

function syncTracksWhilePlaying() {
  const video = getVideo();

  if (!video || video.paused || video.ended) {
    return;
  }

  updateTracksForCurrentFrame();
  requestAnimationFrame(syncTracksWhilePlaying);
}
