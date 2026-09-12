import { api, Auth, showToast } from "../api.js";

let cachedUsers = [];
let rolePermissions = {};
let localCameras = [];
const ALL_PERMS = new Set();

export function initUsersPage() {
  const form = document.getElementById("createUserForm");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("newUsername").value.trim();
    const password = document.getElementById("newPassword").value;
    const role = document.getElementById("newRole").value;
    if (!username || username.length < 2) {
      showToast("Username required (min 2 characters)");
      return;
    }
    if (cachedUsers.some((u) => u.username.toLowerCase() === username.toLowerCase())) {
      showToast("Username already exists");
      return;
    }
    try {
      await api("/api/auth/users", {
        method: "POST",
        body: JSON.stringify({
          username, password, role,
          full_name: document.getElementById("newFullName")?.value?.trim() || "",
        }),
      });
      showToast(`User "${username}" created`);
      form.reset();
      loadUsers();
    } catch (ex) {
      showToast(ex.message || "Failed to create user");
    }
  });

  document.getElementById("editUserForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("editUsername").value;
    const perms = [...document.querySelectorAll("#editPermissionsList input:checked")].map((el) => el.value);
    const cameraIds = [...document.querySelectorAll("#editCameraAssign input:checked")].map((el) => parseInt(el.value, 10));
    try {
      await api(`/api/auth/users/${username}`, {
        method: "PUT",
        body: JSON.stringify({
          full_name: document.getElementById("editFullName").value.trim(),
          role: document.getElementById("editRole").value,
          active: document.getElementById("editActive").checked,
          permissions: perms,
        }),
      });
      await api(`/api/auth/users/${username}/cameras`, {
        method: "PUT",
        body: JSON.stringify({ camera_ids: cameraIds }),
      });
      document.getElementById("editUserDialog")?.close();
      showToast(`User "${username}" updated`);
      loadUsers();
    } catch (ex) {
      showToast(ex.message);
    }
  });

  document.getElementById("editUserCancel")?.addEventListener("click", () => {
    document.getElementById("editUserDialog")?.close();
  });

  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "users" && Auth.isAdmin()) loadUsers();
  });
}

async function loadUsers() {
  const tbody = document.getElementById("usersList");
  tbody.innerHTML = "<tr><td colspan='6'>Loading…</td></tr>";
  try {
    const [res, rolesRes, camsRes] = await Promise.all([
      api("/api/auth/users"),
      api("/api/auth/role-permissions"),
      api("/api/cameras/local?include_all=true").catch(() => ({ cameras: [] })),
    ]);
    cachedUsers = res.users || [];
    rolePermissions = rolesRes.roles || {};
    localCameras = camsRes.cameras || [];
    Object.values(rolePermissions).forEach((p) => p.forEach((x) => ALL_PERMS.add(x)));
    renderGroupedRolePermissions();

    tbody.innerHTML = cachedUsers
      .map((u) => {
        const isAdmin = u.username === "admin";
        const actions = isAdmin
          ? "—"
          : `<button type="button" class="mini" data-edit="${u.username}">Edit</button>
             <button type="button" class="mini" data-reset="${u.username}">Reset pwd</button>
             <button type="button" class="mini danger" data-disable="${u.username}">Disable</button>
             <button type="button" class="mini danger" data-delete="${u.username}">Delete</button>`;
        const controlNote = u.roleName === "VIEWER" ? " <span class='muted'>(no PTZ)</span>" : "";
        return `<tr>
          <td>${esc(u.username)}</td>
          <td>${esc(u.fullName || "—")}</td>
          <td>${esc(u.roleName)}${controlNote}</td>
          <td>${u.active === false ? "Inactive" : "Active"}</td>
          <td>${new Date(u.createdAt).toLocaleDateString()}</td>
          <td class="actions-cell">${actions}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => openEditDialog(btn.dataset.edit));
    });
    tbody.querySelectorAll("[data-disable]").forEach((btn) => {
      btn.addEventListener("click", () => disableUser(btn.dataset.disable));
    });
    tbody.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", () => deleteUser(btn.dataset.delete));
    });
    tbody.querySelectorAll("[data-reset]").forEach((btn) => {
      btn.addEventListener("click", () => resetPassword(btn.dataset.reset));
    });
  } catch (ex) {
    tbody.innerHTML = `<tr><td colspan='6'>${esc(ex.message)}</td></tr>`;
  }
}

const PERM_LABELS = {
  "get-streams": "View live cameras",
  "manage-cameras": "Add, edit, disable, and delete cameras",
  "add-stream": "Test camera connection",
  "control-camera": "Control PTZ movement",
  "control-ptz": "Use zoom, focus, and presets",
  "manage-recordings": "Start/stop recording, view, play, export, and rename recordings",
  "delete-recordings": "Delete recordings",
  "manage-layouts": "Change view mode and create custom layout",
  "register-user": "Create user",
  "get-users": "View users",
  "get-roles": "View roles",
  "manage-users": "Manage users",
  "edit-user": "Edit user",
  "delete-user": "Delete user",
  "manage-settings": "View and edit settings",
  "reset-settings": "Reset settings",
  "view-audit-logs": "View audit logs",
};

const PERM_GROUPS = {
  "Dashboard Access": ["get-streams"],
  "Camera Access": ["manage-cameras", "add-stream"],
  "PTZ & Hardware Controls": ["control-camera", "control-ptz"],
  "Recording Controls": ["manage-recordings", "delete-recordings"],
  "Layout Controls": ["manage-layouts"],
  "User Management": ["register-user", "get-users", "get-roles", "manage-users", "edit-user", "delete-user"],
  "System Administration": ["manage-settings", "reset-settings", "view-audit-logs"],
};

function permLabel(p) {
  return PERM_LABELS[p] || p;
}

function renderPermissionCheckboxes(container, userPerms) {
  const userSet = new Set(userPerms || []);
  const assigned = new Set();
  let html = "";
  for (const [group, perms] of Object.entries(PERM_GROUPS)) {
    const items = perms.filter((p) => ALL_PERMS.has(p));
    if (!items.length) continue;
    html += `<fieldset class="perm-group"><legend>${esc(group)}</legend>`;
    html += items.map((p) => {
      assigned.add(p);
      return `<label><input type="checkbox" value="${p}" ${userSet.has(p) ? "checked" : ""} /> ${esc(permLabel(p))}</label>`;
    }).join("");
    html += "</fieldset>";
  }
  const other = [...ALL_PERMS].filter((p) => !assigned.has(p)).sort();
  if (other.length) {
    html += `<fieldset class="perm-group"><legend>Other</legend>`;
    html += other.map((p) =>
      `<label><input type="checkbox" value="${p}" ${userSet.has(p) ? "checked" : ""} /> ${esc(permLabel(p))}</label>`
    ).join("");
    html += "</fieldset>";
  }
  container.innerHTML = html;
}

function renderGroupedRolePermissions() {
  const el = document.getElementById("rolePermissionsTable");
  if (!el) return;
  el.innerHTML = Object.entries(rolePermissions).map(([role, perms]) => {
    const grouped = Object.entries(PERM_GROUPS).map(([name, keys]) => {
      const hit = keys.filter((k) => perms.includes(k));
      return hit.length ? `<div><strong>${esc(name)}</strong>: ${hit.map((k) => esc(permLabel(k))).join(", ")}</div>` : "";
    }).filter(Boolean).join("");
    return `<div class="role-row"><strong>${esc(role)}</strong><div>${grouped || esc(perms.join(", "))}</div></div>`;
  }).join("");
}

function openEditDialog(username) {
  const user = cachedUsers.find((u) => u.username === username);
  if (!user) return;
  document.getElementById("editUsername").value = username;
  document.getElementById("editFullName").value = user.fullName || "";
  document.getElementById("editRole").value = user.roleName;
  document.getElementById("editActive").checked = user.active !== false;

  const permList = document.getElementById("editPermissionsList");
  renderPermissionCheckboxes(permList, user.permissions || []);

  const camAssign = document.getElementById("editCameraAssign");
  const assigned = new Set(user.cameraIds || []);
  camAssign.innerHTML = localCameras.length
    ? localCameras.map((c) => {
      const type = (c.cameraType || "Camera").replace(/^./, (ch) => ch.toUpperCase());
      const label = c.name && c.name !== String(c.id) ? `${c.name} — ${type}` : `Camera ${c.id} — ${type}`;
      return `<label><input type="checkbox" value="${c.id}" ${assigned.has(c.id) ? "checked" : ""} /> ${esc(label)}</label>`;
    }).join("")
    : "<p class='muted'>No cameras configured — add cameras first</p>";

  document.getElementById("editUserDialog")?.showModal();
}

async function disableUser(username) {
  if (!confirm(`Disable user ${username}?`)) return;
  try {
    await api(`/api/auth/users/${username}/disable`, { method: "POST" });
    showToast(`User ${username} disabled`);
    loadUsers();
  } catch (ex) {
    showToast(ex.message);
  }
}

async function deleteUser(username) {
  if (!confirm(`Delete (deactivate) user ${username}?`)) return;
  try {
    await api(`/api/auth/users/${username}`, { method: "DELETE" });
    showToast(`User ${username} deleted`);
    loadUsers();
  } catch (ex) {
    showToast(ex.message);
  }
}

async function resetPassword(username) {
  const pwd = prompt(`New password for ${username}:`);
  if (!pwd) return;
  try {
    await api(`/api/auth/users/${username}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password: pwd }),
    });
    showToast(`Password reset for ${username}`);
  } catch (ex) {
    showToast(ex.message);
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
