// Phase 8: hidden operator console. Joins the call's room as a listen-only,
// hidden participant (AGENTS.md section 1), plays both remote audio tracks,
// shows the same live transcript text stream the customer sees, and sends
// whisper guidance to the agent only via `publishData` with
// `destinationIdentities` so the customer's client never receives it.

const { Room, RoomEvent } = LivekitClient;

const callIdInput = document.getElementById("call-id-input");
const joinBtn = document.getElementById("join-btn");
const leaveBtn = document.getElementById("leave-btn");
const takeoverBtn = document.getElementById("takeover-btn");
const handbackBtn = document.getElementById("handback-btn");
const whisperInput = document.getElementById("whisper-input");
const whisperBtn = document.getElementById("whisper-btn");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const remoteAudioContainer = document.getElementById("remote-audio-container");
const whisperLogEl = document.getElementById("whisper-log");

const WHISPER_TOPIC = "operator_whisper";
const TAKEOVER_START_TOPIC = "operator_takeover_start";
const TAKEOVER_END_TOPIC = "operator_takeover_end";

let room = null;
let callId = null;
let agentIdentity = null;
let takenOver = false;
// True for the whole duration of takeOver(), not just until the button is
// clicked once -- trackAgentIdentity() re-enables takeoverBtn as soon as it
// spots the agent on whichever room is current, which happens mid-reconnect
// (before `takenOver` flips true), so without this a second click during
// that window fires a second, concurrent takeOver() that races the first
// one over the shared `room` variable.
let takeoverInFlight = false;
// Set right before disconnecting the listen-only room to reconnect as the
// takeover (publishing) identity, so that room's Disconnected event doesn't
// run the "call ended" reset -- see takeOver().
let switchingRoom = false;

const transcriptLines = new Map();

function setStatus(text) {
  statusEl.textContent = text;
}

function logWhisper(text, receivedAt) {
  const entry = document.createElement("div");
  entry.className = "entry";
  const time = document.createElement("time");
  time.textContent = new Date(receivedAt).toLocaleTimeString();
  entry.append(time, document.createTextNode(text));
  whisperLogEl.appendChild(entry);
  whisperLogEl.scrollTop = whisperLogEl.scrollHeight;
}

// Past whispers (this call may have had other operator tabs, or this tab may
// have refreshed) come from `GET /calls/{id}`, which Phase 9 started
// returning alongside transcript/compliance.
async function loadWhisperHistory() {
  try {
    const res = await fetch(`/calls/${callId}`);
    if (!res.ok) return;
    const body = await res.json();
    for (const w of body.whispers ?? []) {
      logWhisper(w.text, w.received_at);
    }
  } catch (err) {
    console.error("failed to load whisper history", err);
  }
}

function lineFor(segmentId, speaker) {
  let line = transcriptLines.get(segmentId);
  if (line) return line;

  const el = document.createElement("div");
  el.className = `line ${speaker} interim`;
  const label = document.createElement("span");
  label.className = "speaker";
  label.textContent = speaker === "user" ? "Customer: " : "Agent: ";
  const body = document.createElement("span");
  el.append(label, body);
  transcriptEl.appendChild(el);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;

  line = { el, body, buffer: "" };
  transcriptLines.set(segmentId, line);
  return line;
}

function attachTranscriptHandler(activeRoom) {
  activeRoom.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
    const segmentId = reader.info.attributes?.["lk.segment_id"] ?? reader.info.id;
    const speaker = participantInfo.identity === `customer-${callId}` ? "user" : "agent";
    const line = lineFor(segmentId, speaker);

    line.buffer = "";
    try {
      for await (const chunk of reader) {
        line.buffer += chunk;
        line.body.textContent = line.buffer;
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
      }
      line.el.classList.remove("interim");
    } catch (err) {
      console.error("transcription stream failed", err);
    }
  });
}

// The agent's identity is assigned by the worker (`agent-<job id>`) and not
// knowable ahead of time, so whoever joins the room that isn't the known
// customer identity is the agent -- the only other participant in a call.
function trackAgentIdentity(identity) {
  if (identity !== `customer-${callId}` && !identity.startsWith("operator-")) {
    agentIdentity = identity;
    whisperInput.disabled = false;
    whisperBtn.disabled = false;
    if (!takenOver && !takeoverInFlight) takeoverBtn.disabled = false;
  }
}

// Shared between the initial listen-only join and the takeover reconnect
// (joinCall and takeOver both need the same transcript/audio/identity wiring
// on whichever Room object is currently live).
function setupRoomHandlers(activeRoom) {
  attachTranscriptHandler(activeRoom);

  activeRoom.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind !== "audio") return;
    const el = track.attach();
    remoteAudioContainer.appendChild(el);
  });
  activeRoom.on(RoomEvent.ParticipantConnected, (p) => trackAgentIdentity(p.identity));
  activeRoom.on(RoomEvent.Disconnected, () => {
    if (switchingRoom) return;
    resetUi();
  });
}

async function joinCall() {
  callId = Number(callIdInput.value);
  if (!callId) {
    setStatus("Enter a call ID first.");
    return;
  }

  joinBtn.disabled = true;
  setStatus("Joining...");

  try {
    const res = await fetch(`/calls/${callId}/operator-token`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `could not get operator token (${res.status})`);
    }
    const { room: roomName, token, livekit_url } = await res.json();

    room = new Room();
    setupRoomHandlers(room);

    await room.connect(livekit_url, token);
    for (const p of room.remoteParticipants.values()) {
      trackAgentIdentity(p.identity);
    }

    setStatus(`Listening on ${roomName}.`);
    leaveBtn.disabled = false;
    await loadWhisperHistory();
  } catch (err) {
    setStatus(`Error: ${err.message}`);
    joinBtn.disabled = false;
  }
}

async function leaveCall() {
  if (room) {
    await room.disconnect();
  }
}

// "Take over": reconnect as a new, visible (non-hidden) identity that can
// publish a mic track -- LiveKit grants are fixed per token, so upgrading
// from listen-only to publishing means a fresh connection, not a toggle on
// the existing one. Tell the agent only after the mic track is actually
// publishing, so it doesn't attach its takeover STT to a track that isn't
// there yet.
async function takeOver() {
  if (!room || !callId || !agentIdentity || takeoverInFlight || takenOver) return;

  takeoverInFlight = true;
  takeoverBtn.disabled = true;
  setStatus("Taking over...");

  try {
    const res = await fetch(`/calls/${callId}/takeover-token`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `could not get takeover token (${res.status})`);
    }
    const { token, livekit_url } = await res.json();

    switchingRoom = true;
    const oldRoom = room;
    await oldRoom.disconnect();
    switchingRoom = false;

    const newRoom = new Room();
    setupRoomHandlers(newRoom);
    await newRoom.connect(livekit_url, token);
    for (const p of newRoom.remoteParticipants.values()) {
      trackAgentIdentity(p.identity);
    }
    await newRoom.localParticipant.setMicrophoneEnabled(true);
    room = newRoom;

    room.localParticipant.publishData(new TextEncoder().encode("start"), {
      reliable: true,
      destinationIdentities: [agentIdentity],
      topic: TAKEOVER_START_TOPIC,
    });

    takenOver = true;
    takeoverBtn.classList.add("active");
    handbackBtn.disabled = false;
    setStatus("You're live -- the customer hears you. Agent is silent.");
  } catch (err) {
    setStatus(`Error taking over: ${err.message}`);
    takeoverBtn.disabled = false;
  } finally {
    takeoverInFlight = false;
  }
}

// "Hand back": stop publishing the mic and tell the agent to resume. The
// operator identity stays connected and visible for the rest of the call
// (see README known limitations) -- reverting to hidden would need yet
// another reconnect, which isn't worth it for how this is used.
async function handBack() {
  if (!room || !agentIdentity) return;

  handbackBtn.disabled = true;
  try {
    await room.localParticipant.setMicrophoneEnabled(false);
    room.localParticipant.publishData(new TextEncoder().encode("end"), {
      reliable: true,
      destinationIdentities: [agentIdentity],
      topic: TAKEOVER_END_TOPIC,
    });
    takenOver = false;
    takeoverBtn.classList.remove("active");
    takeoverBtn.disabled = false;
    setStatus("Handed back. Agent has resumed.");
  } catch (err) {
    setStatus(`Error handing back: ${err.message}`);
    handbackBtn.disabled = false;
  }
}

function sendWhisper() {
  const text = whisperInput.value.trim();
  if (!text || !room || !agentIdentity) return;

  const payload = new TextEncoder().encode(text);
  room.localParticipant.publishData(payload, {
    reliable: true,
    destinationIdentities: [agentIdentity],
    topic: WHISPER_TOPIC,
  });
  logWhisper(text, Date.now());
  whisperInput.value = "";
}

function resetUi() {
  room = null;
  agentIdentity = null;
  takenOver = false;
  takeoverInFlight = false;
  joinBtn.disabled = false;
  leaveBtn.disabled = true;
  takeoverBtn.disabled = true;
  takeoverBtn.classList.remove("active");
  handbackBtn.disabled = true;
  whisperInput.disabled = true;
  whisperBtn.disabled = true;
  remoteAudioContainer.innerHTML = "";
  whisperLogEl.innerHTML = "";
  setStatus("Call ended.");
}

joinBtn.addEventListener("click", joinCall);
leaveBtn.addEventListener("click", leaveCall);
takeoverBtn.addEventListener("click", takeOver);
handbackBtn.addEventListener("click", handBack);
whisperBtn.addEventListener("click", sendWhisper);
whisperInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendWhisper();
});
