import { api } from "../api.js";

export function initAuditPage() {
  window.addEventListener("shibli:page", (e) => {
    if (e.detail === "audit") loadAudit();
  });
}

async function loadAudit() {
  const tbody = document.getElementById("auditList");
  tbody.innerHTML = "<tr><td colspan='6'>Loading...</td></tr>";
  try {
    const res = await api("/api/audit-logs?limit=200");
    tbody.innerHTML = res.logs.map((l) => `<tr>
      <td>${l.created_at || "—"}</td>
      <td>${l.username || "—"}</td>
      <td>${l.role_name || "—"}</td>
      <td>${l.action}</td>
      <td>${l.module || "—"}</td>
      <td>${l.success ? "OK" : "FAIL"} · ${l.detail || ""}</td>
    </tr>`).join("");
  } catch (ex) {
    tbody.innerHTML = `<tr><td colspan='6'>${ex.message}</td></tr>`;
  }
}
