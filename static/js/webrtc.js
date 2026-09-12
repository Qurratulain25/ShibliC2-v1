/** go2rtc WebRTC playback — low-latency streams in browser */
const activePlayers = new Map();

export async function connectGo2Rtc(streamSrc, videoEl, apiBase, onState) {
  if (!streamSrc || !videoEl || !apiBase) return null;
  stopGo2Rtc(videoEl);

  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  });
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });

  pc.ontrack = (ev) => {
    if (ev.streams?.[0] && videoEl.srcObject !== ev.streams[0]) {
      videoEl.srcObject = ev.streams[0];
      videoEl.play().catch(() => {});
    }
  };

  pc.onconnectionstatechange = () => {
    onState?.(pc.connectionState);
    if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
      const entry = activePlayers.get(videoEl);
      if (!entry) return;
      if (entry.retryTimer) clearTimeout(entry.retryTimer);
      const delay = Math.min((entry.retryDelay || 5000) * 1.6, 30000);
      entry.retryDelay = delay;
      entry.retryTimer = setTimeout(() => {
        connectGo2Rtc(streamSrc, videoEl, apiBase, onState);
      }, delay);
    }
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  const response = await fetch(
    `${apiBase}/api/webrtc?src=${encodeURIComponent(streamSrc)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: offer.sdp,
    },
  );
  if (!response.ok) throw new Error(`WebRTC negotiate failed (${response.status})`);
  const answerSdp = await response.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

  activePlayers.set(videoEl, { pc, streamSrc, apiBase, onState, retryDelay: 5000 });
  return pc;
}

export function stopGo2Rtc(videoEl) {
  const entry = activePlayers.get(videoEl);
  if (!entry) return;
  if (entry.retryTimer) clearTimeout(entry.retryTimer);
  try {
    entry.pc.close();
  } catch {
    /* ignore */
  }
  activePlayers.delete(videoEl);
  if (videoEl) {
    videoEl.srcObject = null;
  }
}

export function stopAllGo2Rtc() {
  [...activePlayers.keys()].forEach((el) => stopGo2Rtc(el));
}
