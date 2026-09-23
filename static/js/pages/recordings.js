import { api, Auth, showToast } from "../api.js";

let state = { page: 1, pageSize: 20, sort: "date_desc", search: "", dateFrom: "", totalPages: 1, total: 0 };
let activeRecording = null;
let loadedRows = [];
let listBound = false;
let playerBound = false;

export function initRecordingsPage() {
  document.getElementById("recSearch")?.addEventListener("input", (e) => {
    state.search = e.target.value;
    state.page = 1;
    loadRecordings();
  });
  document.getElementById("recSort")?.addEventListener("change", (e) => {
    state.sort = e.target.value;
    loadRecordings();
  });
  document.getElementById("recPageSize")?.addEventListener("change", (e) => {
    state.pageSize = parseInt(e.target.value, 10);
    state.page = 1;
    loadRecordings();
  });
  document.getElementById("recDateFrom")?.addEventListener("change", (e) => {
    state.dateFrom = e.target.value || "";
    state.page = 1;
    loadRecordings();
  });
  document.getElementById("recCameraFilter")?.addEventListener("change", renderVisibleRows);
  document.getElementById("recChannelFilter")?.addEventListener("change", renderVisibleRows);
  document.getElementById("recClearFilters")?.addEventListener("click", clearFilters);
  document.getElementById("recEmptyClear")?.addEventListener("click", clearFilters);
  document.getElementById("recRefresh")?.addEventListener("click", loadRecordings);
  document.getElementById("recPrev")?.addEventListener("click", () => {
    if (state.page > 1) { state.page--; loadRecordings(); }
  });
  document.getElementById("recNext")?.addEventListener("click", () => {
    if (state.page < state.totalPages) { state.page++; loadRecordings(); }
  });

  const dialog = document.getElementById("recordingPlayerDialog");
  const close = () => {
    dialog?.close();
    const v = document.getElementById("recordingPlayer");
    if (v) { v.pause(); v.removeAttribute("src"); v.load(); }
    activeRecording = null;
  };
  if (!playerBound) {
    document.getElementById("recPlayerClose")?.addEventListener("click", close);
    dialog?.addEventListener("click", (e) => { if (e.target === dialog) close(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dialog?.open) close();
    });
    document.getElementById("recPlayerExport")?.addEventListener("click", () => {
      if (activeRecording?.id) exportRecording(activeRecording.id);
    });
    document.getElementById("recPlayerDelete")?.addEventListener("click", async () => {
      if (!activeRecording?.id) return;
      if (!confirm("Delete this recording?")) return;
      await api(`/api/recordings/local/${activeRecording.id}`, { method: "DELETE" });
      close();
      showToast("Recording deleted");
      loadRecordings();
    });
    playerBound = true;
  }

  if (!listBound) {
    document.getElementById("recordingsList")?.addEventListener("click", onRecordingsListClick);
    document.getElementById("recordingsPager")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-page]");
      if (!btn) return;
      const page = parseInt(btn.dataset.page, 10);
      if (!page || page === state.page) return;
      state.page = page;
      loadRecordings();
    });
    listBound = true;
  }

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "recordings") loadRecordings();
  });
  if (location.hash.replace("#", "") === "recordings") loadRecordings();
}

function filtersActive() {
  return Boolean(
    (state.search || "").trim()
    || state.dateFrom
    || document.getElementById("recCameraFilter")?.value
    || document.getElementById("recChannelFilter")?.value,
  );
}

function clearFilters() {
  state.search = "";
  state.dateFrom = "";
  state.page = 1;
  const search = document.getElementById("recSearch");
  if (search) search.value = "";
  const date = document.getElementById("recDateFrom");
  if (date) date.value = "";
  const cam = document.getElementById("recCameraFilter");
  if (cam) cam.value = "";
  const ch = document.getElementById("recChannelFilter");
  if (ch) ch.value = "";
  loadRecordings();
}

function listMessage(text) {
  return `<tr><td colspan="7" class="rec-list-msg">${text}</td></tr>`;
}

async function loadRecordings() {
  const list = document.getElementById("recordingsList");
  const stats = document.getElementById("recordingsStats");
  if (!list) return;
  list.innerHTML = listMessage("Loading recordings...");
  try {
    const q = new URLSearchParams({
      search: state.search, sort: state.sort, page: state.page, page_size: state.pageSize,
    });
    if (state.dateFrom) {
      q.set("date_from", state.dateFrom);
      q.set("date_to", state.dateFrom);
    }
    const local = await api(`/api/recordings/local?${q}`);
    let rows = local.items || [];

    try {
      const core = await api("/api/backend/recordings");
      if (core.ok && core.data?.recordings) {
        const extra = flattenCore(core.data.recordings);
        const ids = new Set(rows.map((r) => r.fileName));
        extra.forEach((r) => { if (!ids.has(r.fileName)) rows.push(r); });
      }
    } catch { /* core offline */ }

    loadedRows = rows;
    state.total = local.total ?? rows.length;
    state.totalPages = Math.max(1, Math.ceil((state.total || rows.length) / state.pageSize));
    if (state.page > state.totalPages) state.page = state.totalPages;

    populateCameraFilter(rows);
    renderVisibleRows();
    renderPager();

    if (stats) {
      stats.textContent = `${state.total} recording(s)`;
      api("/api/recordings/local/storage-path")
        .then((st) => {
          if (st?.path) stats.textContent = `${state.total} recording(s) · Storage: ${st.path}`;
        })
        .catch(() => {});
    }
  } catch (ex) {
    loadedRows = [];
    state.total = 0;
    list.innerHTML = listMessage(`Unable to load recordings. ${esc(ex.message || "")}`.trim());
    showEmpty(false);
    const range = document.getElementById("recordingsRange");
    if (range) range.textContent = "Showing 0–0 of 0 recordings";
    if (stats) stats.textContent = "Status unavailable";
    showToast(ex.message || "Unable to load recordings.");
  }
}

function populateCameraFilter(rows) {
  const sel = document.getElementById("recCameraFilter");
  if (!sel) return;
  const current = sel.value;
  const names = [...new Set(rows.map((r) => r.cameraName).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  sel.innerHTML = `<option value="">All Cameras</option>${names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")}`;
  if (current && names.includes(current)) sel.value = current;
}

function visibleRows() {
  const cam = document.getElementById("recCameraFilter")?.value || "";
  const ch = document.getElementById("recChannelFilter")?.value || "";
  return loadedRows.filter((r) => {
    if (cam && r.cameraName !== cam) return false;
    if (ch && channelKind(r) !== ch) return false;
    return true;
  });
}

function renderVisibleRows() {
  const list = document.getElementById("recordingsList");
  if (!list) return;
  const rows = visibleRows();
  const filtered = filtersActive();
  if (!loadedRows.length) {
    list.innerHTML = "";
    showEmpty(true, filtered);
    updateRange(0);
    return;
  }
  if (!rows.length) {
    list.innerHTML = "";
    showEmpty(true, true);
    updateRange(0);
    return;
  }
  showEmpty(false);
  list.innerHTML = rows.map((r) => renderRow(r)).join("");
  updateRange(rows.length);
}

function showEmpty(show, filtered = false) {
  const empty = document.getElementById("recordingsEmpty");
  const detail = document.getElementById("recordingsEmptyDetail");
  const clearBtn = document.getElementById("recEmptyClear");
  const title = empty?.querySelector(".rec-empty-title");
  empty?.classList.toggle("hidden", !show);
  if (!show) return;
  if (title) title.textContent = filtered ? "No recordings match the selected filters." : "No recordings found";
  if (detail) detail.textContent = filtered ? "Try a different search, camera, channel, or date." : "Recorded surveillance footage will appear here.";
  clearBtn?.classList.toggle("hidden", !filtered);
}

function updateRange(visibleCount) {
  const range = document.getElementById("recordingsRange");
  if (!range) return;
  if (!state.total || !visibleCount) {
    range.textContent = `Showing 0–0 of ${state.total} recordings`;
    return;
  }
  const start = (state.page - 1) * state.pageSize + 1;
  const end = (state.page - 1) * state.pageSize + visibleCount;
  range.textContent = `Showing ${start}–${end} of ${state.total} recordings`;
}

function renderPager() {
  const pager = document.getElementById("recordingsPager");
  const prev = document.getElementById("recPrev");
  const next = document.getElementById("recNext");
  if (prev) prev.disabled = state.page <= 1;
  if (next) next.disabled = state.page >= state.totalPages;
  if (!pager) return;
  const total = state.totalPages;
  const cur = state.page;
  const pages = [];
  const windowSize = 5;
  let from = Math.max(1, cur - 2);
  let to = Math.min(total, from + windowSize - 1);
  from = Math.max(1, to - windowSize + 1);
  for (let i = from; i <= to; i += 1) pages.push(i);
  pager.innerHTML = pages.map((p) => (
    `<button type="button" class="mini rec-page-btn${p === cur ? " is-active" : ""}" data-page="${p}">${p}</button>`
  )).join("");
}

function flattenCore(data) {
  if (!Array.isArray(data)) return [];
  if (data[0]?.segments) {
    return data.flatMap((g) => (g.segments || []).map((s) => ({
      id: s.id, fileName: s.fileName || s.file_name, cameraName: g.cameraName,
      cameraId: g.cameraId, recordedAt: s.startTime, duration: s.duration,
      fileSizeBytes: s.fileSize, recordingType: s.status || "Event", recordedBy: "—",
    })));
  }
  return data.map((r) => ({
    id: r.id, fileName: r.fileName || r.file_name, cameraName: r.cameraName,
    cameraId: r.cameraId, recordedAt: r.date, duration: r.duration,
    fileSizeBytes: r.fileSize, recordingType: r.status || "Manual", recordedBy: "—",
  }));
}

function isPlaceholder(r) {
  return !r.fileSizeBytes || r.fileSizeBytes < 4096;
}

function fmtSize(b) {
  if (!b) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`;
  return `${(b / 1073741824).toFixed(1)} GB`;
}

function fmtDuration(sec) {
  if (sec == null || sec === "") return "—";
  const s = Math.max(0, Math.round(Number(sec)));
  if (!Number.isFinite(s)) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function shortName(name) {
  const raw = String(name || "").replace(/\\/g, "/");
  const base = raw.split("/").pop() || raw;
  return base || "—";
}

function channelKind(r) {
  const s = `${r.cameraName || ""} ${r.cameraId || ""}`.toLowerCase();
  if (s.includes("thermal")) return "thermal";
  if (s.includes("day")) return "day";
  return "";
}

function channelLabel(r) {
  const kind = channelKind(r);
  if (kind === "thermal") return { kind, text: "THERMAL" };
  if (kind === "day") return { kind, text: "DAY" };
  return { kind: "", text: r.cameraId || "—" };
}

function formatStamp(iso) {
  if (!iso) return { date: "—", time: "" };
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return { date: String(iso), time: "" };
  return {
    date: dt.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }),
    time: dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  };
}

function renderRow(r) {
  const canDelete = Auth.user?.permissions?.includes("delete-recordings");
  const canRename = Auth.user?.permissions?.includes("manage-recordings");
  const play = r.id
    ? (isPlaceholder(r)
      ? `<button type="button" class="mini" disabled title="Recording empty or still in progress — stop recording first">Play</button>`
      : `<button type="button" class="mini rec-action-play" data-action="play" data-id="${r.id}">Play</button>`)
    : "";
  const dl = r.id ? `<button type="button" class="mini rec-action-export" data-action="export" data-id="${r.id}">Export</button>` : "";
  const ren = canRename && r.id ? `<button type="button" class="mini" data-action="rename" data-id="${r.id}">Rename</button>` : "";
  const del = canDelete && r.id ? `<button type="button" class="mini danger" data-action="delete" data-id="${r.id}">Delete</button>` : "";
  const stamp = formatStamp(r.recordedAt);
  const ch = channelLabel(r);
  const typeBits = [r.recordingType, r.recordedBy].filter((x) => x && x !== "—");
  const secondary = typeBits.length ? `<span>${esc(typeBits.join(" · "))}</span>` : "";
  return `<tr data-id="${r.id || ""}">
    <td>
      <div class="rec-name">
        <strong title="${esc(r.fileName || "")}">${esc(shortName(r.fileName))}</strong>
        ${secondary}
      </div>
    </td>
    <td>${esc(r.cameraName || "—")}</td>
    <td><span class="rec-channel ${ch.kind ? `is-${ch.kind}` : ""}"><span class="rec-channel-dot" aria-hidden="true"></span>${esc(ch.text)}</span></td>
    <td>
      <div class="rec-stamp">
        <strong>${esc(stamp.date)}</strong>
        <span>${esc(stamp.time)}</span>
      </div>
    </td>
    <td>${esc(fmtDuration(r.duration))}</td>
    <td>${esc(fmtSize(r.fileSizeBytes))}</td>
    <td>
      <div class="rec-row-actions">${play}${dl}${ren}${del}</div>
    </td>
  </tr>`;
}

function onRecordingsListClick(e) {
  const btn = e.target.closest("button[data-action]");
  if (!btn || btn.disabled) return;
  const id = btn.dataset.id;
  const action = btn.dataset.action;
  const rec = loadedRows.find((r) => String(r.id) === String(id));
  if (action === "export") exportRecording(id);
  else if (action === "play") playRecording(rec || { id });
  else if (action === "delete") deleteRecording(id);
  else if (action === "rename") renameRecording(id);
}

async function playRecording(r) {
  const stamp = formatStamp(r.recordedAt);
  const fileName = shortName(r.fileName);
  const cameraName = r.cameraName || "—";
  if ((r.fileSizeBytes || 0) < 1024) {
    openPlayerUnavailable(fileName, cameraName, stamp.date, stamp.time);
    return;
  }
  await openPlayer(r.id, fileName, cameraName, stamp.date, stamp.time);
}

async function deleteRecording(id) {
  if (!confirm("Delete this recording?")) return;
  await api(`/api/recordings/local/${id}`, { method: "DELETE" });
  showToast("Recording deleted");
  loadRecordings();
}

async function renameRecording(id) {
  const name = prompt("New file name:");
  if (!name) return;
  await api(`/api/recordings/local/${id}/rename`, {
    method: "PUT", body: JSON.stringify({ file_name: name }),
  });
  loadRecordings();
}

async function exportRecording(id) {
  const rec = loadedRows.find((r) => String(r.id) === String(id));
  const res = await fetch(`/api/recordings/local/${id}/file`, {
    headers: { Authorization: `Bearer ${Auth.token}` },
  });
  if (!res.ok) {
    showToast("Unable to export recording.");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = shortName(rec?.fileName) || "recording.mp4";
  a.click();
}

function openPlayerUnavailable(fileName, cameraName, date, time) {
  const dialog = document.getElementById("recordingPlayerDialog");
  document.getElementById("recPlayerTitle").textContent = fileName;
  document.getElementById("recPlayerMeta").textContent = `${cameraName} · ${date} ${time}`.trim();
  const v = document.getElementById("recordingPlayer");
  v.classList.add("hidden");
  const msg = document.getElementById("recPlayerUnavailable") || (() => {
    const p = document.createElement("p");
    p.id = "recPlayerUnavailable";
    p.className = "rec-unavailable";
    v.parentNode.insertBefore(p, v.nextSibling);
    return p;
  })();
  msg.textContent = "Preview unavailable until real camera stream is recorded.";
  msg.classList.remove("hidden");
  document.getElementById("recPlayerDelete")?.classList.add("hidden");
  activeRecording = null;
  dialog?.showModal();
}

async function openPlayer(id, fileName, cameraName, date, time) {
  const dialog = document.getElementById("recordingPlayerDialog");
  document.getElementById("recPlayerTitle").textContent = fileName;
  document.getElementById("recPlayerMeta").textContent = `${cameraName} · ${date} ${time}`.trim();
  const unavail = document.getElementById("recPlayerUnavailable");
  if (unavail) unavail.classList.add("hidden");
  const v = document.getElementById("recordingPlayer");
  v.classList.remove("hidden");
  const res = await fetch(`/api/recordings/local/${id}/file`, {
    headers: { Authorization: `Bearer ${Auth.token}` },
  });
  if (!res.ok) {
    openPlayerUnavailable(fileName, cameraName, date, time);
    return;
  }
  v.src = URL.createObjectURL(await res.blob());
  const canDelete = Auth.user?.permissions?.includes("delete-recordings");
  document.getElementById("recPlayerDelete")?.classList.toggle("hidden", !canDelete);
  activeRecording = { id, fileName, cameraName };
  dialog?.showModal();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
