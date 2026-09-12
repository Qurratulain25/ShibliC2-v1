import { api, Auth, showToast } from "./api.js";

const DEFAULT_MAP = {
  w: "ptz_up", s: "ptz_down", a: "ptz_left", d: "ptz_right",
  q: "ptz_up_left", e: "ptz_up_right", z: "ptz_down_left", c: "ptz_down_right",
  "+": "zoom_in", "=": "zoom_in", "-": "zoom_out",
  r: "toggle_record", f: "fullscreen",
  " ": "ptz_stop", "1": "ptz_system_1", "2": "ptz_system_2", escape: "exit_fullscreen",
};

const HOLD_ACTIONS = new Set([
  "ptz_up", "ptz_down", "ptz_left", "ptz_right",
  "ptz_up_left", "ptz_up_right", "ptz_down_left", "ptz_down_right",
  "zoom_in", "zoom_out",
]);

let enabled = true;
let keyMap = { ...DEFAULT_MAP };
let onAction = null;
const held = new Set();

export function initKeyboard(handler) {
  onAction = handler;
  loadMap();
  document.addEventListener("keydown", handleKeyDown);
  document.addEventListener("keyup", handleKeyUp);
  window.addEventListener("blur", releaseAll);
}

async function loadMap() {
  try {
    const res = await api("/api/settings");
    enabled = res.settings?.keyboard_enabled !== false;
    keyMap = { ...DEFAULT_MAP, ...(res.settings?.keyboard_map || {}) };
  } catch {
    enabled = true;
  }
}

function handleKeyDown(e) {
  if (!Auth.isLoggedIn() || !Auth.canControl()) return;
  if (!enabled) return;
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase();
  const action = keyMap[key];
  if (!action) return;
  e.preventDefault();
  if (HOLD_ACTIONS.has(action)) {
    if (held.has(action)) return;
    held.add(action);
    onAction?.(action, "down");
    return;
  }
  onAction?.(action, "tap");
  showToast(`Key: ${action}`);
}

function handleKeyUp(e) {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase();
  const action = keyMap[key];
  if (!action || !HOLD_ACTIONS.has(action)) return;
  if (!held.has(action)) return;
  held.delete(action);
  onAction?.(action, "up");
}

function releaseAll() {
  for (const action of [...held]) {
    held.delete(action);
    onAction?.(action, "up");
  }
}

export function setKeyboardEnabled(on) {
  enabled = on;
}
