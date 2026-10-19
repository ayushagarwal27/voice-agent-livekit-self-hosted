// Phase 8: hidden operator console. Joins the call's room as a listen-only,
// hidden participant (AGENTS.md section 1), plays both remote audio tracks,
// shows the same live transcript text stream the customer sees, and sends
// whisper guidance to the agent only via `publishData` with
// `destinationIdentities` so the customer's client never receives it.

const { Room, RoomEvent } = LivekitClient;

const callIdInput = document.getElementById("call-id-input");
const joinBtn = document.getElementById("join-btn");
const leaveBtn = document.getElementById("leave-btn");
const whisperInput = document.getElementById("whisper-input");
const whisperBtn = document.getElementById("whisper-btn");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const remoteAudioContainer = document.getElementById("remote-audio-container");

const WHISPER_TOPIC = "operator_whisper";

let room = null;
let callId = null;
let agentIdentity = null;

const transcriptLines = new Map();

function setStatus(text) {
  statusEl.textContent = text;
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
  if (identity !== `customer-${callId}`) {
    agentIdentity = identity;
    whisperInput.disabled = false;
    whisperBtn.disabled = false;
  }
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
    attachTranscriptHandler(room);

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== "audio") return;
      const el = track.attach();
      remoteAudioContainer.appendChild(el);
    });
    room.on(RoomEvent.ParticipantConnected, (p) => trackAgentIdentity(p.identity));
    room.on(RoomEvent.Disconnected, () => resetUi());

    await room.connect(livekit_url, token);
    for (const p of room.remoteParticipants.values()) {
      trackAgentIdentity(p.identity);
    }

    setStatus(`Listening on ${roomName}.`);
    leaveBtn.disabled = false;
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

function sendWhisper() {
  const text = whisperInput.value.trim();
  if (!text || !room || !agentIdentity) return;

  const payload = new TextEncoder().encode(text);
  room.localParticipant.publishData(payload, {
    reliable: true,
    destinationIdentities: [agentIdentity],
    topic: WHISPER_TOPIC,
  });
  whisperInput.value = "";
}

function resetUi() {
  room = null;
  agentIdentity = null;
  joinBtn.disabled = false;
  leaveBtn.disabled = true;
  whisperInput.disabled = true;
  whisperBtn.disabled = true;
  remoteAudioContainer.innerHTML = "";
  setStatus("Call ended.");
}

joinBtn.addEventListener("click", joinCall);
leaveBtn.addEventListener("click", leaveCall);
whisperBtn.addEventListener("click", sendWhisper);
whisperInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendWhisper();
});
