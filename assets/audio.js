// Audio plumbing: mic capture with voice-activity detection, WAV encoding for
// the /chat endpoint, device enumeration for the settings panel, and amplitude
// taps that drive the orb.

const RATE_LIMIT_DB = 0.00001;

export function rms(buf) {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

// Perceptual-ish scaling so the orb responds to speech rather than to peaks.
export function toLevel(r) {
  const db = 20 * Math.log10(Math.max(r, RATE_LIMIT_DB));
  return Math.max(0, Math.min(1, (db + 60) / 45));
}

let ctx = null;
export function audioContext() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

export function encodeWavPcm16(mono, sampleRate) {
  const dataSize = mono.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  let p = 0;
  const u32 = (v) => { view.setUint32(p, v, true); p += 4; };
  const u16 = (v) => { view.setUint16(p, v, true); p += 2; };
  const str = (s) => { for (let i = 0; i < s.length; i++) view.setUint8(p++, s.charCodeAt(i)); };
  str("RIFF"); u32(36 + dataSize); str("WAVE");
  str("fmt "); u32(16); u16(1); u16(1); u32(sampleRate);
  u32(sampleRate * 2); u16(2); u16(16);
  str("data"); u32(dataSize);
  for (let i = 0; i < mono.length; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(p, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    p += 2;
  }
  return buffer;
}

export async function listInputs() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "audioinput");
  } catch {
    return [];
  }
}

export function micConstraints(deviceId) {
  return {
    audio: {
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      channelCount: 1,
      echoCancellation: true,   // keeps the TTS reply out of the next turn
      noiseSuppression: true,
      autoGainControl: true,
    },
  };
}

/**
 * Open the mic and stream amplitude to `onLevel`. Returns a handle with
 * `stop()`. Used both by the conversation loop and the settings mic test.
 */
export async function openMic({ deviceId, onLevel, onChunk }) {
  const stream = await navigator.mediaDevices.getUserMedia(micConstraints(deviceId));
  const ac = audioContext();
  const source = ac.createMediaStreamSource(stream);
  const processor = ac.createScriptProcessor(2048, 1, 1);
  // ScriptProcessor only runs while connected to the graph, but we must not
  // hear ourselves — so route it through a silent gain into the destination.
  const mute = ac.createGain();
  mute.gain.value = 0;

  processor.onaudioprocess = (e) => {
    const buf = e.inputBuffer.getChannelData(0);
    if (onChunk) onChunk(new Float32Array(buf));
    if (onLevel) onLevel(toLevel(rms(buf)), rms(buf));
  };
  source.connect(processor);
  processor.connect(mute);
  mute.connect(ac.destination);

  return {
    sampleRate: ac.sampleRate,
    stop() {
      try { processor.disconnect(); } catch {}
      try { mute.disconnect(); } catch {}
      try { source.disconnect(); } catch {}
      try { stream.getTracks().forEach((t) => t.stop()); } catch {}
      processor.onaudioprocess = null;
    },
  };
}

/**
 * Record one utterance, ending on silence.
 *
 * Resolves with a WAV Blob, or null if the caller aborted or nobody spoke.
 * This is what makes hands-free mode possible: without it an auto-started
 * recording would never know when to stop.
 */
export function recordUtterance({
  deviceId,
  onLevel,
  signal,
  onSpeechStart,
  onProgress,
  partialMs = 900,
  startThreshold = 0.55,
  endThreshold = 0.42,
  silenceMs = 1100,
  leadInMs = 9000,
  maxMs = 30000,
}) {
  return new Promise(async (resolve, reject) => {
    let mic;
    const chunks = [];
    let speaking = false;
    let lastVoice = performance.now();
    const started = performance.now();
    let done = false;
    let timer = null;
    let lastPartial = 0;

    // Encode everything captured so far. Re-encoding the whole buffer each
    // time is O(n), but n is a few seconds of speech, so it stays cheap and
    // it lets the server transcribe a self-contained WAV every time.
    const snapshot = () => {
      const total = chunks.reduce((n, c) => n + c.length, 0);
      if (!total) return null;
      const mono = new Float32Array(total);
      let off = 0;
      for (const c of chunks) { mono.set(c, off); off += c.length; }
      return new Blob([encodeWavPcm16(mono, mic?.sampleRate || 48000)], { type: "audio/wav" });
    };

    const finish = (ok) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      signal?.removeEventListener("abort", onAbort);
      const sr = mic?.sampleRate || 48000;
      mic?.stop();
      if (!ok || !chunks.length) return resolve(null);
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const mono = new Float32Array(total);
      let off = 0;
      for (const c of chunks) { mono.set(c, off); off += c.length; }
      resolve(new Blob([encodeWavPcm16(mono, sr)], { type: "audio/wav" }));
    };

    const onAbort = () => finish(false);
    signal?.addEventListener("abort", onAbort);

    try {
      mic = await openMic({
        deviceId,
        onChunk: (c) => chunks.push(c),
        onLevel: (level, raw) => {
          onLevel?.(level);
          const now = performance.now();
          if (level > startThreshold) {
            if (!speaking) { speaking = true; onSpeechStart?.(); }
            lastVoice = now;
          } else if (speaking && level > endThreshold) {
            lastVoice = now; // still trailing off, not silence yet
          }
        },
      });
    } catch (err) {
      signal?.removeEventListener("abort", onAbort);
      return reject(err);
    }

    timer = setInterval(() => {
      const now = performance.now();
      // Stream what we have so far so the UI can show it being heard.
      if (onProgress && speaking && now - lastPartial > partialMs) {
        lastPartial = now;
        const blob = snapshot();
        if (blob) onProgress(blob);
      }
      if (speaking && now - lastVoice > silenceMs) finish(true);
      else if (!speaking && now - started > leadInMs) finish(false);
      else if (now - started > maxMs) finish(true);
    }, 80);
  });
}

/** Tap an <audio> element so the orb can react to the spoken reply. */
export function analysePlayback(audioEl, onLevel) {
  const ac = audioContext();
  let src;
  try {
    src = ac.createMediaElementSource(audioEl);
  } catch {
    return () => {};
  }
  const analyser = ac.createAnalyser();
  analyser.fftSize = 512;
  src.connect(analyser);
  analyser.connect(ac.destination);
  const data = new Float32Array(analyser.fftSize);
  let raf = 0;
  const loop = () => {
    raf = requestAnimationFrame(loop);
    analyser.getFloatTimeDomainData(data);
    onLevel(toLevel(rms(data)));
  };
  loop();
  return () => {
    cancelAnimationFrame(raf);
    try { src.disconnect(); analyser.disconnect(); } catch {}
  };
}
