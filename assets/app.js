import { createOrb } from "./orb.js";
import {
  recordUtterance, analysePlayback, openMic, listInputs, audioContext,
} from "./audio.js";

const API_URL = "http://localhost:5173";
const LS_MIC = "ova.micDeviceId";
// Must match recordUtterance's startThreshold so the meter marker is honest.
const SPEECH_THRESHOLD = 0.55;

const $ = (id) => document.getElementById(id);
const streamEl = $("stream");
const orbWrap = $("orbWrap");
const banner = $("keyBanner");
const sheet = $("sheet");
const scrim = $("scrim");
const keyInput = $("keyInput");
const saveNote = $("saveNote");
const micSelect = $("micSelect");
const meterFill = $("meterFill");
const meterNote = $("meterNote");
const talkBtn = $("talkBtn");
const talkLabel = $("talkLabel");

let state = "loading";       // loading | idle | listening | thinking | speaking
let hasApiKey = false;
let micDeviceId = localStorage.getItem(LS_MIC) || "";
let turnAbort = null;
let conversing = false;
let currentAudio = null;
let stopPlaybackTap = null;
let thinkingTurn = null;
let liveTurn = null;         // the partial transcript while you speak
let partialBusy = false;

/* ------------------------------------------------------------------- orb */
const orb = createOrb($("orb"));
if (!orb) document.body.classList.add("no-webgl");

/* ----------------------------------------------------------------- state */
// The orb and the single button carry all the state now — there is no text
// under the orb. Anything the user needs in words goes into the stream.
function setState(next) {
  state = next;
  document.body.dataset.state = next;
  orb?.setState(next);
  orbWrap.classList.toggle("disabled", next === "loading" || next === "thinking");
  talkBtn.disabled = next === "loading";
  talkBtn.classList.toggle("on", conversing);
  talkLabel.textContent =
    next === "loading" ? "Warming up…" : conversing ? "Stop" : "Start";
}

/* ------------------------------------------------------------- transcript */
// Newest turn sits at the bottom at full strength; older ones lose opacity and
// gain blur as they climb, until the container's gradient mask erases them.
const FADE = [1, 0.42, 0.2, 0.09, 0.04];

function restack() {
  const turns = [...streamEl.children];
  for (let i = turns.length - 1, depth = 0; i >= 0; i--, depth++) {
    const el = turns[i];
    el.style.opacity = String(FADE[depth] ?? 0);
    el.style.filter = depth === 0 ? "none" : `blur(${Math.min(depth * 0.9, 3.5)}px)`;
    if (depth > 6) el.remove();
  }
}

function addTurn(who, content, kind) {
  const wrap = document.createElement("div");
  wrap.className = `turn ${kind}`;
  if (who) {
    const label = document.createElement("div");
    label.className = "who";
    label.textContent = who;
    wrap.appendChild(label);
  }
  const say = document.createElement("div");
  say.className = "say";
  if (typeof content === "string") say.textContent = content;
  else say.appendChild(content);
  wrap.appendChild(say);
  streamEl.appendChild(wrap);
  restack();
  return wrap;
}

function showThinking() {
  const dots = document.createElement("span");
  dots.className = "thinking";
  dots.innerHTML = "<span></span><span></span><span></span>";
  thinkingTurn = addTurn("Assistant", dots, "assistant");
}
function clearThinking() { thinkingTurn?.remove(); thinkingTurn = null; restack(); }
function addNote(text, isError) { addTurn(null, text, `note${isError ? " error" : ""}`); }

/* --------------------------------------------------- live partial results */
function showLive(text) {
  if (!text) return;
  if (!liveTurn) liveTurn = addTurn("You", text, "you live");
  else liveTurn.querySelector(".say").textContent = text;
}
function clearLive() { liveTurn?.remove(); liveTurn = null; restack(); }

/**
 * Transcribe the audio captured so far so the user can watch their words land.
 * Fire-and-forget: a dropped or failed partial must never disturb the turn,
 * and only one is ever in flight so slow ASR can't queue up a backlog.
 */
async function sendPartial(blob, signal) {
  if (partialBusy || signal?.aborted) return;
  partialBusy = true;
  try {
    const res = await fetch(`${API_URL}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "audio/wav" },
      body: blob,
      signal,
    });
    if (res.ok) {
      const { transcript } = await res.json();
      if (!signal?.aborted) showLive(transcript);
    }
  } catch {
    /* partials are best-effort */
  } finally {
    partialBusy = false;
  }
}

/* -------------------------------------------------------------- settings */
function setKeyState(has) {
  hasApiKey = has;
  banner.classList.toggle("show", !has);
}

async function loadSettings() {
  try {
    const res = await fetch(`${API_URL}/settings`);
    if (!res.ok) return false;
    const s = await res.json();
    setKeyState(Boolean(s.has_api_key));
    $("factModel").textContent = s.model || "—";
    $("factHost").textContent = s.host || "—";
    $("factProfile").textContent = s.profile || "—";
    $("version").textContent = s.build
      ? `Version ${s.version} · build ${s.build}`
      : `Version ${s.version}`;
    if (s.has_api_key) {
      keyInput.placeholder = s.api_key_from_env
        ? `From environment (${s.api_key_hint})`
        : `Saved (${s.api_key_hint})`;
    }
    return true;
  } catch {
    return false;
  }
}

function openSheet() { sheet.classList.add("open"); scrim.classList.add("open"); refreshDevices(); }
function closeSheet() { sheet.classList.remove("open"); scrim.classList.remove("open"); stopMicTest(); }

$("settingsBtn").addEventListener("click", openSheet);
$("bannerAction").addEventListener("click", openSheet);
$("closeSheet").addEventListener("click", closeSheet);
scrim.addEventListener("click", closeSheet);

$("revealBtn").addEventListener("click", (e) => {
  const showing = keyInput.type === "text";
  keyInput.type = showing ? "password" : "text";
  e.currentTarget.textContent = showing ? "Show" : "Hide";
});

$("saveKey").addEventListener("click", async () => {
  const btn = $("saveKey");
  btn.disabled = true;
  saveNote.className = "save-note";
  saveNote.textContent = "Saving…";
  try {
    const res = await fetch(`${API_URL}/settings/api-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: keyInput.value.trim() }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    setKeyState(Boolean(s.has_api_key));
    keyInput.value = "";
    keyInput.placeholder = s.has_api_key ? `Saved (${s.api_key_hint})` : "Paste your OLLAMA_API_KEY";
    saveNote.className = "save-note ok";
    saveNote.textContent = s.has_api_key ? "Key saved. Ready to reply." : "Key cleared.";
  } catch (err) {
    saveNote.className = "save-note err";
    saveNote.textContent = `Could not save the key (${err.message}).`;
  } finally {
    btn.disabled = false;
  }
});

/* -------------------------------------------------------------- mic test */
let micTest = null;

async function refreshDevices() {
  const inputs = await listInputs();
  const current = micSelect.value || micDeviceId;
  micSelect.innerHTML = '<option value="">System default</option>';
  for (const d of inputs) {
    const opt = document.createElement("option");
    opt.value = d.deviceId;
    // Labels stay blank until mic permission has been granted at least once.
    opt.textContent = d.label || `Input ${micSelect.length}`;
    micSelect.appendChild(opt);
  }
  micSelect.value = current || "";
}

micSelect.addEventListener("change", () => {
  micDeviceId = micSelect.value;
  localStorage.setItem(LS_MIC, micDeviceId);
  if (micTest) { stopMicTest(); startMicTest(); }
});

$("meterMark").style.left = `${SPEECH_THRESHOLD * 100}%`;

async function startMicTest() {
  try {
    micTest = await openMic({
      deviceId: micDeviceId,
      onLevel: (level) => {
        meterFill.style.width = `${Math.min(100, level * 100)}%`;
        meterNote.textContent =
          level > SPEECH_THRESHOLD ? "Hearing you clearly." : "Testing — say something.";
      },
    });
    $("testMic").textContent = "Stop test";
    meterNote.textContent = "Testing — say something.";
    refreshDevices(); // labels populate once permission is granted
  } catch {
    meterNote.textContent = "Could not open that microphone. Check macOS mic permission.";
  }
}

function stopMicTest() {
  if (!micTest) return;
  micTest.stop();
  micTest = null;
  meterFill.style.width = "0%";
  meterNote.textContent = "Not testing.";
  $("testMic").textContent = "Test microphone";
}

$("testMic").addEventListener("click", () => (micTest ? stopMicTest() : startMicTest()));

/* ----------------------------------------------------------------- turn */
function decodeHeader(res, name) {
  const raw = res.headers.get(name);
  if (!raw) return "";
  try { return decodeURIComponent(raw); } catch { return raw; }
}

function stopPlayback() {
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  stopPlaybackTap?.();
  stopPlaybackTap = null;
}

/** Send one utterance and play the reply. Resolves true to continue the loop. */
async function sendTurn(wavBlob, signal) {
  setState("thinking");
  showThinking();

  let res;
  try {
    res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "audio/wav" },
      body: wavBlob,
      signal,
    });
  } catch (err) {
    clearThinking(); clearLive();
    if (err.name === "AbortError") return false;
    addNote("Couldn't reach the local backend. Is it still running?", true);
    return false;
  }

  if (!res.ok) {
    clearThinking(); clearLive();
    let detail = `The backend returned ${res.status}.`;
    try {
      const body = await res.json();
      if (body.transcript) addTurn("You", body.transcript, "you");
      if (body.detail) detail = body.detail;
      if (body.error === "no_api_key") setKeyState(false);
    } catch {}
    addNote(detail, true);
    return false;
  }

  const blob = await res.blob();
  const transcript = decodeHeader(res, "X-OVA-Transcript");
  const reply = decodeHeader(res, "X-OVA-Reply");
  clearThinking();
  // The committed transcript supersedes whatever the partials were showing.
  clearLive();

  if (!blob.size && !transcript) {
    addNote("Didn't catch that — nothing was transcribed.");
    return true;
  }
  if (transcript) addTurn("You", transcript, "you");
  if (reply) addTurn("Assistant", reply, "assistant");
  if (!blob.size) return true;

  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentAudio = audio;
  stopPlaybackTap = analysePlayback(audio, (lvl) => orb?.setAmp(lvl));

  setState("speaking");
  await new Promise((resolve) => {
    const done = () => {
      URL.revokeObjectURL(url);
      stopPlaybackTap?.();
      stopPlaybackTap = null;
      if (currentAudio === audio) currentAudio = null;
      orb?.setAmp(0);
      resolve();
    };
    audio.onended = done;
    audio.onerror = () => { addNote("The reply audio could not be played.", true); done(); };
    signal?.addEventListener("abort", () => { audio.pause(); done(); }, { once: true });
    audio.play().catch(() => { addNote("Playback was blocked.", true); done(); });
  });

  return !signal?.aborted;
}

/** One listen → send → speak cycle. */
async function runTurn(signal) {
  setState("listening");
  orb?.setAmp(0);
  let wav;
  try {
    wav = await recordUtterance({
      deviceId: micDeviceId,
      signal,
      startThreshold: SPEECH_THRESHOLD,
      onLevel: (lvl) => orb?.setAmp(lvl),
      onProgress: (blob) => sendPartial(blob, signal),
    });
  } catch {
    clearLive();
    addNote("Microphone permission was denied. Allow access in System Settings and try again.", true);
    return false;
  }
  orb?.setAmp(0);
  if (signal.aborted) { clearLive(); return false; }
  if (!wav) {
    clearLive();
    addNote("Didn't hear anything.");
    return false;
  }
  return await sendTurn(wav, signal);
}

async function conversation() {
  if (conversing) return;
  conversing = true;
  turnAbort = new AbortController();
  const { signal } = turnAbort;
  setState("listening");
  try {
    // Keeps cycling on its own — one press starts a whole conversation.
    while (!signal.aborted) {
      const ok = await runTurn(signal);
      if (!ok || signal.aborted) break;
      // Let the speaker tail decay before reopening the mic.
      await new Promise((r) => setTimeout(r, 450));
    }
  } finally {
    conversing = false;
    orb?.setAmp(0);
    clearLive();
    if (!signal.aborted) setState("idle");
  }
}

function stopConversation() {
  turnAbort?.abort();
  turnAbort = null;
  stopPlayback();
  conversing = false;
  clearThinking();
  clearLive();
  orb?.setAmp(0);
  setState("idle");
}

/* ---------------------------------------------------------------- input */
function toggle() {
  if (state === "loading") return;
  audioContext(); // must be resumed from a user gesture
  if (conversing) stopConversation();
  else conversation();
}

talkBtn.addEventListener("click", toggle);
orbWrap.addEventListener("click", toggle);
orbWrap.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.code === "Space") { e.preventDefault(); toggle(); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeSheet(); return; }
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if (e.code === "Space" && !typing && !sheet.classList.contains("open")) {
    e.preventDefault();
    toggle();
  }
});
navigator.mediaDevices?.addEventListener?.("devicechange", refreshDevices);

/* ----------------------------------------------------------------- boot */
(async function boot() {
  setState("loading");
  for (let attempt = 0; ; attempt++) {
    if (await loadSettings()) break;
    await new Promise((r) => setTimeout(r, 1500));
  }
  refreshDevices();
  setState("idle");
  if (!hasApiKey) addNote("Add your Ollama Cloud API key in settings to get replies.");
})();
