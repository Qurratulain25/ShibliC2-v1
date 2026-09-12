import { api, Auth, showToast } from "../api.js";

let state = { page: 1, pageSize: 20, sort: "date_desc", search: "", totalPages: 1 };
let activeRecording = null;

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

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "recordings") loadRecordings();
  });
}

async function loadRecordings() {
  const list = document.getElementById("recordingsList");
  const stats = document.getElementById("recordingsStats");
  const pager = document.getElementById("recordingsPager");
  list.innerHTML = "<tr><td colspan='9'>Loading...</td></tr>";
  try {
    const q = new URLSearchParams({
      search: state.search, sort: state.sort, page: state.page, page_size: state.pageSize,
    });
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

    stats.textContent = `${local.total ?? rows.length} recording(s) · Storage: ${(await api("/api/recordings/local/storage-path")).path}`;

    if (!rows.length) {
      list.innerHTML = "<tr><td colspan='9'>No recordings found</td></tr>";
    } else {
      list.innerHTML = rows.map((r) => renderRow(r)).join("");
      bindRowActions();
    }
    state.totalPages = Math.max(1, Math.ceil((local.total || rows.length) / state.pageSize));
    if (pager) pager.textContent = `Page ${state.page} / ${state.totalPages}`;
    document.getElementById("recNext").disabled = state.page >= state.totalPages;
  } catch (ex) {
    list.innerHTML = `<tr><td colspan='9'>${ex.message}</td></tr>`;
  }
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
  return `${(b / 1048576).toFixed(1)} MB`;
}

function renderRow(r) {
  const canDelete = Auth.user?.permissions?.includes("delete-recordings");
  const canRename = Auth.user?.permissions?.includes("manage-recordings");
  const play = r.id
    ? (isPlaceholder(r)
      ? `<button type="button" class="mini" disabled title="Recording empty or still in progress — stop recording first">Play</button>`
      : `<button type="button" class="mini" data-play="${r.id}" data-size="${r.fileSizeBytes || 0}">Play</button>`)
    : "";
  const dl = r.id ? `<button type="button" class="mini" data-export="${r.id}">Export</button>` : "";
  const ren = canRename && r.id ? `<button type="button" class="mini" data-rename="${r.id}">Rename</button>` : "";
  const del = canDelete && r.id ? `<button type="button" class="mini danger" data-del="${r.id}">Delete</button>` : "";
  const dt = r.recordedAt ? new Date(r.recordedAt) : null;
  return `<tr>
    <td>${r.fileName || "—"}</td>
    <td>${r.cameraName || "—"}</td>
    <td>${r.cameraId || "—"}</td>
    <td>${dt ? dt.toLocaleDateString() : "—"}</td>
    <td>${dt ? dt.toLocaleTimeString() : "—"}</td>
    <td>${r.duration != null ? r.duration + "s" : "—"}</td>
    <td>${fmtSize(r.fileSizeBytes)}</td>
    <td>${r.recordingType || "—"}</td>
    <td>${r.recordedBy || "—"} ${play}${dl}${ren}${del}</td>
  </tr>`;
}

function bindRowActions() {
  document.querySelectorAll("[data-export]").forEach((btn) => {
    btn.addEventListener("click", () => exportRecording(btn.dataset.export));
  });
  document.querySelectorAll("[data-play]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const size = parseInt(btn.dataset.size || "0", 10);
      const id = btn.dataset.play;
      const row = btn.closest("tr");
      const fileName = row?.children[0]?.textContent || "Recording";
      const cameraName = row?.children[1]?.textContent || "—";
      const date = row?.children[3]?.textContent || "";
      const time = row?.children[4]?.textContent || "";
      if (size < 1024) {
        openPlayerUnavailable(fileName, cameraName, date, time);
        return;
      }
      await openPlayer(id, fileName, cameraName, date, time);
    });
  });
  document.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this recording?")) return;
      await api(`/api/recordings/local/${btn.dataset.del}`, { method: "DELETE" });
      showToast("Recording deleted");
      loadRecordings();
    });
  });
  document.querySelectorAll("[data-rename]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = prompt("New file name:");
      if (!name) return;
      await api(`/api/recordings/local/${btn.dataset.rename}/rename`, {
        method: "PUT", body: JSON.stringify({ file_name: name }),
      });
      loadRecordings();
    });
  });
}

async function exportRecording(id) {
  const res = await fetch(`/api/recordings/local/${id}/file`, {
    headers: { Authorization: `Bearer ${Auth.token}` },
  });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "recording.mp4";
  a.click();
}

function openPlayerUnavailable(fileName, cameraName, date, time) {
  const dialog = document.getElementById("recordingPlayerDialog");
  document.getElementById("recPlayerTitle").textContent = fileName;
  document.getElementById("recPlayerMeta").textContent = `${cameraName} · ${date} ${time}`;
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
  document.getElementById("recPlayerMeta").textContent = `${cameraName} · ${date} ${time}`;
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
