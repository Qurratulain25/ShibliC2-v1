const MIN_BOX_PX = 20;
const MIN_DRAG_PX = 12;

function getFrameMetrics(frame) {
  const rect = frame.getBoundingClientRect();
  return { rect, w: rect.width, h: rect.height };
}

export function initDragZoom(handlers = {}) {
  const { onRegionZoom, onDragZoom, onReset } = handlers;

  document.querySelectorAll("[data-drag-zoom]").forEach((frame) => {
    const channel = frame.dataset.dragZoom;
    const layer = frame.querySelector(".drag-zoom-layer");
    if (!layer) return;

    const selectEl = document.createElement("div");
    selectEl.className = "zoom-select-rect hidden";
    layer.appendChild(selectEl);

    let active = false;
    let startX = 0;
    let startY = 0;
    let pointerId = null;

    const clearSelect = () => {
      selectEl.classList.add("hidden");
      selectEl.style.width = "0";
      selectEl.style.height = "0";
    };

    const updateSelect = (x, y, w, h) => {
      selectEl.classList.remove("hidden");
      selectEl.style.left = `${x}px`;
      selectEl.style.top = `${y}px`;
      selectEl.style.width = `${Math.max(0, w)}px`;
      selectEl.style.height = `${Math.max(0, h)}px`;
    };

    layer.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const { rect } = getFrameMetrics(frame);
      active = true;
      pointerId = e.pointerId;
      startX = e.clientX - rect.left;
      startY = e.clientY - rect.top;
      layer.setPointerCapture(e.pointerId);
      clearSelect();
      e.preventDefault();
    });

    layer.addEventListener("pointermove", (e) => {
      if (!active || e.pointerId !== pointerId) return;
      const { rect, w, h } = getFrameMetrics(frame);
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const left = Math.max(0, Math.min(startX, x));
      const top = Math.max(0, Math.min(startY, y));
      const width = Math.min(w - left, Math.abs(x - startX));
      const height = Math.min(h - top, Math.abs(y - startY));
      updateSelect(left, top, width, height);
    });

    const finish = (e) => {
      if (!active || e.pointerId !== pointerId) return;
      active = false;
      layer.releasePointerCapture(e.pointerId);
      pointerId = null;

      const { rect, w, h } = getFrameMetrics(frame);
      const endX = e.clientX - rect.left;
      const endY = e.clientY - rect.top;
      const dx = endX - startX;
      const dy = endY - startY;
      const boxW = Math.abs(dx);
      const boxH = Math.abs(dy);

      clearSelect();

      if (boxW < MIN_BOX_PX && boxH < MIN_BOX_PX) return;

      if (boxW < MIN_BOX_PX * 2 && boxH < MIN_BOX_PX * 2 && Math.abs(dy) > MIN_DRAG_PX && Math.abs(dy) > Math.abs(dx)) {
        onDragZoom?.(channel, dy < 0 ? "in" : "out");
        return;
      }

      const left = Math.max(0, Math.min(startX, endX));
      const top = Math.max(0, Math.min(startY, endY));
      const width = Math.min(w - left, boxW);
      const height = Math.min(h - top, boxH);
      if (width < MIN_BOX_PX || height < MIN_BOX_PX) return;

      const cx = (left + width / 2) / w;
      const cy = (top + height / 2) / h;
      const scale = Math.min(w / width, h / height, 8);
      onRegionZoom?.(channel, { cx, cy, scale, left, top, width, height, frameW: w, frameH: h });
    };

    layer.addEventListener("pointerup", finish);
    layer.addEventListener("pointercancel", finish);

    layer.addEventListener("dblclick", (e) => {
      e.preventDefault();
      onReset?.(channel);
    });
  });
}
