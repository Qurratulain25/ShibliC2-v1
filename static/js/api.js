export const Auth = {
  token: localStorage.getItem("shibli_token") || "",
  user: JSON.parse(localStorage.getItem("shibli_user") || "null"),

  setSession(token, user) {
    this.token = token;
    this.user = user;
    localStorage.setItem("shibli_token", token);
    localStorage.setItem("shibli_user", JSON.stringify(user));
  },

  clear() {
    this.token = "";
    this.user = null;
    localStorage.removeItem("shibli_token");
    localStorage.removeItem("shibli_user");
  },

  isLoggedIn() {
    return Boolean(this.token);
  },

  isAdmin() {
    return this.user?.roleName === "ADMINISTRATOR";
  },

  canControl() {
    return this.user?.permissions?.includes("control-camera");
  },
};

export async function api(path, options = {}) {
  const { skipAuthRedirect, ...fetchOptions } = options;
  const headers = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers || {}),
  };
  if (Auth.token) headers.Authorization = `Bearer ${Auth.token}`;
  let response;
  try {
    response = await fetch(path, { ...fetchOptions, headers });
  } catch {
    const err = new Error("Network unavailable");
    err.code = "NETWORK";
    throw err;
  }
  if (response.status === 401) {
    if (!skipAuthRedirect && !api._sessionCleared) {
      api._sessionCleared = true;
      Auth.clear();
      window.dispatchEvent(new CustomEvent("shibli:session-expired"));
      setTimeout(() => { api._sessionCleared = false; }, 2000);
    }
    const err = new Error("Session expired");
    err.status = 401;
    throw err;
  }
  if (!response.ok) {
    let msg = response.statusText;
    try {
      const body = await response.json();
      const detail = body.detail ?? body.error;
      if (Array.isArray(detail)) {
        msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      } else if (detail) {
        msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      } else {
        msg = JSON.stringify(body);
      }
    } catch {
      try { msg = await response.text(); } catch { /* keep statusText */ }
    }
    const err = new Error(msg);
    err.status = response.status;
    throw err;
  }
  if (response.status === 204) return null;
  return response.json();
}

export function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2000);
}
