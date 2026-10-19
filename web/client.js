// Phase 5: browser client. Loads agents, places a call, and renders a live
// labelled transcript from LiveKit's built-in `lk.transcription` text stream
// (AGENTS.md section 1) rather than reconstructing it from audio ourselves.

const { Room, RoomEvent } = LivekitClient;

const agentSelect = document.getElementById("agent-select");
const callBtn = document.getElementById("call-btn");
const hangupBtn = document.getElementById("hangup-btn");
const muteBtn = document.getElementById("mute-btn");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const remoteAudioContainer = document.getElementById("remote-audio-container");

let room = null;
let muted = false;

// Keyed by the sender's text-stream segment id, since a segment's text can
// arrive as one growing stream (agent) or as several full-text snapshots
// (user STT) - either way the latest chunk buffer is the right thing to show.
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
  label.textContent = speaker === "user" ? "You: " : "Agent: ";
  const body = document.createElement("span");
  el.append(label, body);
  transcriptEl.appendChild(el);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;

  line = { el, body, buffer: "" };
  transcriptLines.set(segmentId, line);
  return line;
}

async function loadAgents() {
  const res = await fetch("/agents");
  const agentList = await res.json();
  agentSelect.innerHTML = "";
  for (const agent of agentList) {
    const opt = document.createElement("option");
    opt.value = agent.id;
    opt.textContent = agent.name;
    agentSelect.appendChild(opt);
  }
}

function attachTranscriptHandler(activeRoom) {
  activeRoom.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
    const segmentId = reader.info.attributes?.["lk.segment_id"] ?? reader.info.id;
    const speaker = participantInfo.identity === activeRoom.localParticipant.identity ? "user" : "agent";
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

async function startCall() {
  callBtn.disabled = true;
  setStatus("Starting call...");

  try {
    const res = await fetch("/calls", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent_id: Number(agentSelect.value) }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `call creation failed (${res.status})`);
    }
    const { room: roomName, token, livekit_url } = await res.json();

    room = new Room();
    attachTranscriptHandler(room);

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== "audio") return;
      const el = track.attach();
      remoteAudioContainer.appendChild(el);
    });
    room.on(RoomEvent.Disconnected, () => resetUi());

    await room.connect(livekit_url, token);
    await room.localParticipant.setMicrophoneEnabled(true);

    setStatus(`Connected to ${roomName}.`);
    hangupBtn.disabled = false;
    muteBtn.disabled = false;
  } catch (err) {
    setStatus(`Error: ${err.message}`);
    callBtn.disabled = false;
  }
}

async function hangUp() {
  if (room) {
    await room.disconnect();
  }
}

async function toggleMute() {
  if (!room) return;
  muted = !muted;
  await room.localParticipant.setMicrophoneEnabled(!muted);
  muteBtn.textContent = muted ? "Unmute" : "Mute";
}

function resetUi() {
  room = null;
  muted = false;
  callBtn.disabled = false;
  hangupBtn.disabled = true;
  muteBtn.disabled = true;
  muteBtn.textContent = "Mute";
  remoteAudioContainer.innerHTML = "";
  setStatus("Call ended.");
}

callBtn.addEventListener("click", startCall);
hangupBtn.addEventListener("click", hangUp);
muteBtn.addEventListener("click", toggleMute);

loadAgents().catch((err) => setStatus(`Failed to load agents: ${err.message}`));
