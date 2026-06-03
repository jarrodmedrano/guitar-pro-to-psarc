interface Track {
  index: number;
  name: string;
  strings: number;
  notes: number;
  is_drums: boolean;
  selected: boolean;
  arrangement: string;
}

interface AudioMeta {
  title?: string;
  artist?: string;
  album?: string;
  year?: string;
}

interface UploadResponse {
  session_id: string;
  title: string;
  artist: string;
  album: string;
  tracks: Track[];
}

type WsMessage =
  | { stage: string; progress: number; done?: false; error?: undefined }
  | { done: true; progress: 100; stage: string; filename: string; download_url: string }
  | { error: string };

// ── State ────────────────────────────────────────────────────────────────────

let sessionId = "";
let audioReady = false;
let audioOffset = 0;

// ── Panel helpers ────────────────────────────────────────────────────────────

type PanelId = "panel-drop" | "panel-parsed" | "panel-progress" | "panel-result";

function showPanel(id: PanelId): void {
  (["panel-drop", "panel-parsed", "panel-progress", "panel-result"] as PanelId[]).forEach(p => {
    document.getElementById(p)!.classList.toggle("hidden", p !== id);
  });
}

function el<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

// ── Drop zone (GP file) ──────────────────────────────────────────────────────

const dropzone = el<HTMLDivElement>("dropzone");
const gpInput  = el<HTMLInputElement>("gp-input");
const dropError = el<HTMLParagraphElement>("drop-error");

dropzone.addEventListener("dragover", e => {
  e.preventDefault();
  dropzone.classList.add("border-indigo-500", "bg-zinc-800");
});
dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("border-indigo-500", "bg-zinc-800");
});
dropzone.addEventListener("drop", e => {
  e.preventDefault();
  dropzone.classList.remove("border-indigo-500", "bg-zinc-800");
  const file = e.dataTransfer?.files[0];
  if (file) handleGpFile(file);
});
dropzone.addEventListener("click", () => gpInput.click());
gpInput.addEventListener("change", () => {
  if (gpInput.files?.[0]) handleGpFile(gpInput.files[0]);
});

async function handleGpFile(file: File): Promise<void> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!["gp", "gp3", "gp4", "gp5", "gpx"].includes(ext)) {
    showError(`Unsupported file type ".${ext}"`);
    return;
  }
  dropError.classList.add("hidden");
  dropzone.classList.add("opacity-50", "pointer-events-none");

  try {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/upload", { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? res.statusText);
    }
    const data: UploadResponse = await res.json();
    populateParsedPanel(data);
    showPanel("panel-parsed");
  } catch (err) {
    showError((err as Error).message);
  } finally {
    dropzone.classList.remove("opacity-50", "pointer-events-none");
    gpInput.value = "";
  }
}

function showError(msg: string): void {
  dropError.textContent = msg;
  dropError.classList.remove("hidden");
}

// ── Parsed panel ─────────────────────────────────────────────────────────────

function populateParsedPanel(data: UploadResponse): void {
  sessionId = data.session_id;
  audioReady = false;

  el<HTMLInputElement>("meta-title").value  = data.title;
  el<HTMLInputElement>("meta-artist").value = data.artist;
  el<HTMLInputElement>("meta-album").value  = data.album;
  el<HTMLInputElement>("meta-year").value   = "";

  renderTracks(data.tracks);
  resetArtZone();
  resetAudioZone();
}

const ARRANGEMENTS = ["Lead", "Rhythm", "Bass", "Drums", "Keys", "Vocals"];

function renderTracks(tracks: Track[]): void {
  const list = el<HTMLDivElement>("track-list");
  list.innerHTML = "";

  tracks.forEach(t => {
    const row = document.createElement("div");
    row.className = "flex items-center gap-3 rounded-lg bg-zinc-800 px-3 py-2";
    row.dataset.index = String(t.index);

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = t.selected;
    checkbox.className = "h-4 w-4 rounded border-zinc-600 bg-zinc-700 text-indigo-500 focus:ring-indigo-500";

    const label = document.createElement("span");
    label.className = "flex-1 text-sm text-zinc-200 truncate";
    label.textContent = t.name;

    const badge = document.createElement("span");
    badge.className = "text-xs text-zinc-500";
    badge.textContent = t.is_drums
      ? `drums · ${t.notes}n`
      : `${t.strings}str · ${t.notes}n`;

    const select = document.createElement("select");
    select.className = "rounded bg-zinc-700 border border-zinc-600 px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500";
    ARRANGEMENTS.forEach(name => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      opt.selected = name === t.arrangement;
      select.appendChild(opt);
    });

    row.appendChild(checkbox);
    row.appendChild(label);
    row.appendChild(badge);
    if (t.is_drums) {
      const warn = document.createElement("span");
      warn.className = "text-xs text-amber-500 shrink-0";
      warn.title = "Rocksmith has no drums arrangement — including this may cause the game to default to the wrong track";
      warn.textContent = "⚠ not for RS";
      row.appendChild(warn);
    }
    row.appendChild(select);
    list.appendChild(row);
  });
}

// ── Album art drop zone ──────────────────────────────────────────────────────

const artDropzone = el<HTMLDivElement>("art-dropzone");
const artInput    = el<HTMLInputElement>("art-input");
const artPreview  = el<HTMLImageElement>("art-preview");
const artIcon     = el<HTMLElement>("art-icon");
const artLabel    = el<HTMLParagraphElement>("art-label");

function showArtPreview(objectUrl: string): void {
  artPreview.src = objectUrl;
  artPreview.style.display = "block";
  artIcon.style.display = "none";
}

function hideArtPreview(): void {
  if (artPreview.src.startsWith("blob:")) URL.revokeObjectURL(artPreview.src);
  artPreview.removeAttribute("src");
  artPreview.style.display = "none";
  artIcon.style.display = "";
}

function resetArtZone(): void {
  hideArtPreview();
  artLabel.textContent = "Drop an image or click to browse";
  artDropzone.classList.remove("border-emerald-500");
  artDropzone.classList.add("border-zinc-700", "border-dashed");
}

artDropzone.addEventListener("dragover", e => {
  e.preventDefault();
  artDropzone.classList.add("border-indigo-500");
});
artDropzone.addEventListener("dragleave", () => {
  artDropzone.classList.remove("border-indigo-500");
});
artDropzone.addEventListener("drop", e => {
  e.preventDefault();
  artDropzone.classList.remove("border-indigo-500");
  const file = e.dataTransfer?.files[0];
  if (file) handleArtFile(file);
});
artDropzone.addEventListener("click", () => artInput.click());
artInput.addEventListener("change", () => {
  if (artInput.files?.[0]) handleArtFile(artInput.files[0]);
});

async function handleArtFile(file: File): Promise<void> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!["jpg", "jpeg", "png", "webp", "dds"].includes(ext)) {
    artLabel.textContent = `Unsupported type ".${ext}"`;
    return;
  }

  // Show the dropped image instantly — browsers can't render .dds so skip it
  if (ext !== "dds") {
    showArtPreview(URL.createObjectURL(file));
  }

  artLabel.textContent = `Uploading ${file.name}…`;

  try {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file);
    const res = await fetch("/upload-art", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);

    artDropzone.classList.remove("border-zinc-700", "border-dashed");
    artDropzone.classList.add("border-emerald-500", "border-solid");
    artLabel.textContent = file.name;
  } catch (err) {
    artLabel.textContent = `Upload failed: ${(err as Error).message}`;
    hideArtPreview();
  } finally {
    artInput.value = "";
  }
}

// ── Audio drop zone ──────────────────────────────────────────────────────────

const audioDropzone = el<HTMLDivElement>("audio-dropzone");
const audioInput    = el<HTMLInputElement>("audio-input");
const audioLabel    = el<HTMLDivElement>("audio-label");

function resetAudioZone(): void {
  audioReady = false;
  audioLabel.innerHTML = `Drop an audio file (mp3/ogg/wav) or click to browse
    <span class="block text-xs text-zinc-500 mt-0.5">Optional — MIDI audio used if omitted</span>`;
  audioDropzone.classList.remove("border-emerald-500");
  audioDropzone.classList.add("border-zinc-700");
  audioOffset = 0;
  el<HTMLInputElement>("audio-offset").value = "0";
  el("audio-sync").classList.add("hidden");
  el("sync-status").classList.add("hidden");
  el("sync-status").textContent = "";
}

audioDropzone.addEventListener("dragover", e => {
  e.preventDefault();
  audioDropzone.classList.add("border-indigo-500");
});
audioDropzone.addEventListener("dragleave", () => {
  audioDropzone.classList.remove("border-indigo-500");
});
audioDropzone.addEventListener("drop", e => {
  e.preventDefault();
  audioDropzone.classList.remove("border-indigo-500");
  const file = e.dataTransfer?.files[0];
  if (file) handleAudioFile(file);
});
audioDropzone.addEventListener("click", () => audioInput.click());
audioInput.addEventListener("change", () => {
  if (audioInput.files?.[0]) handleAudioFile(audioInput.files[0]);
});

async function handleAudioFile(file: File): Promise<void> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!["mp3", "ogg", "wav", "flac"].includes(ext)) {
    audioLabel.innerHTML = `<span class="text-red-400">Unsupported audio type ".${ext}"</span>`;
    return;
  }

  audioLabel.innerHTML = `<span class="text-zinc-400">Uploading ${file.name}…</span>`;

  try {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file);
    const res = await fetch("/upload-audio", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);

    const { meta }: { meta: AudioMeta } = await res.json();

    audioReady = true;
    audioDropzone.classList.remove("border-zinc-700");
    audioDropzone.classList.add("border-emerald-500");
    audioLabel.innerHTML = `<span class="text-emerald-400">✓ ${file.name}</span>`;

    applyAudioMeta(meta);
    el("audio-sync").classList.remove("hidden");
  } catch (err) {
    audioLabel.innerHTML = `<span class="text-red-400">Upload failed: ${(err as Error).message}</span>`;
  } finally {
    audioInput.value = "";
  }
}

function applyAudioMeta(meta: AudioMeta): void {
  const fields: Array<[keyof AudioMeta, string]> = [
    ["title",  "meta-title"],
    ["artist", "meta-artist"],
    ["album",  "meta-album"],
    ["year",   "meta-year"],
  ];
  let filled = 0;
  fields.forEach(([key, id]) => {
    const input = el<HTMLInputElement>(id);
    if (!input.value.trim() && meta[key]) {
      input.value = meta[key]!;
      input.classList.add("ring-1", "ring-indigo-400");
      setTimeout(() => input.classList.remove("ring-1", "ring-indigo-400"), 2000);
      filled++;
    }
  });
  if (filled > 0) {
    audioLabel.innerHTML = `<span class="text-emerald-400">✓ ${audioLabel.textContent?.replace("✓ ", "") ?? ""}</span>
      <span class="block text-xs text-indigo-400 mt-0.5">Filled ${filled} field${filled > 1 ? "s" : ""} from audio tags</span>`;
  }
}

// ── Audio sync ───────────────────────────────────────────────────────────────

el<HTMLInputElement>("audio-offset").addEventListener("input", e => {
  audioOffset = parseFloat((e.target as HTMLInputElement).value) || 0;
});

el("auto-detect-btn").addEventListener("click", async () => {
  const btn = el<HTMLButtonElement>("auto-detect-btn");
  const status = el("sync-status");
  btn.disabled = true;
  btn.textContent = "Detecting…";
  status.className = "text-xs text-zinc-400";
  status.textContent = "Analysing audio…";
  status.classList.remove("hidden");

  try {
    const form = new FormData();
    form.append("session_id", sessionId);
    const res = await fetch("/detect-offset", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
    const { offset }: { offset: number } = await res.json();
    audioOffset = offset;
    el<HTMLInputElement>("audio-offset").value = String(offset);
    status.className = "text-xs text-emerald-400";
    status.textContent = `Detected ${offset.toFixed(3)} s — adjust by ear if needed`;
  } catch (err) {
    status.className = "text-xs text-red-400";
    status.textContent = `Detection failed: ${(err as Error).message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Auto Detect";
  }
});

// ── Back / again buttons ─────────────────────────────────────────────────────

el("back-btn").addEventListener("click", () => showPanel("panel-drop"));
el("edit-btn").addEventListener("click", () => showPanel("panel-parsed"));
el("again-btn").addEventListener("click", () => showPanel("panel-drop"));

// ── Build ────────────────────────────────────────────────────────────────────

el("build-btn").addEventListener("click", startBuild);

function getSelectedTracks(): { indices: number[]; arrangements: string[] } {
  const rows = el<HTMLDivElement>("track-list").querySelectorAll<HTMLDivElement>("[data-index]");
  const indices: number[] = [];
  const arrangements: string[] = [];
  rows.forEach(row => {
    const cb = row.querySelector<HTMLInputElement>("input[type=checkbox]")!;
    if (cb.checked) {
      indices.push(Number(row.dataset.index));
      arrangements.push(row.querySelector<HTMLSelectElement>("select")!.value);
    }
  });
  return { indices, arrangements };
}

function startBuild(): void {
  const { indices, arrangements } = getSelectedTracks();
  if (indices.length === 0) {
    alert("Select at least one track.");
    return;
  }

  const title   = el<HTMLInputElement>("meta-title").value.trim();
  const artist  = el<HTMLInputElement>("meta-artist").value.trim();
  const album   = el<HTMLInputElement>("meta-album").value.trim();
  const year    = el<HTMLInputElement>("meta-year").value.trim();

  showPanel("panel-progress");
  setProgress(0, "Starting…");

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const params  = new URLSearchParams({
    session_id: sessionId,
    title, artist, album, year,
    tracks: indices.join(","),
    arrangements: arrangements.join(","),
    audio_offset: String(audioOffset),
  });
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/build?${params}`);

  ws.addEventListener("message", e => {
    const msg: WsMessage = JSON.parse(e.data);
    if ("error" in msg && msg.error) {
      showResult({ error: msg.error });
    } else if ("done" in msg && msg.done) {
      showResult({ filename: msg.filename, downloadUrl: msg.download_url });
    } else if ("stage" in msg) {
      setProgress(msg.progress, msg.stage);
    }
  });

  ws.addEventListener("close", () => {
    // If we're still on the progress panel after close, something went wrong
    if (!el("panel-result").classList.contains("hidden") === false) {
      showResult({ error: "Connection closed unexpectedly." });
    }
  });
}

function setProgress(pct: number, stage: string): void {
  el("progress-bar").style.width = `${Math.min(100, pct)}%`;
  el("progress-stage").textContent = stage;
}

function showResult(data: { filename: string; downloadUrl: string } | { error: string }): void {
  showPanel("panel-result");

  if ("error" in data) {
    el("result-error").classList.remove("hidden");
    el("result-success").classList.add("hidden");
    el("error-message").textContent = data.error;
  } else {
    el("result-success").classList.remove("hidden");
    el("result-error").classList.add("hidden");
    el("result-filename").textContent = data.filename;
    const link = el<HTMLAnchorElement>("download-link");
    link.href = data.downloadUrl;
    link.download = data.filename;
  }
}
