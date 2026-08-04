const player = new EmulatorPlayer(document.getElementById("emu"));
const lettersPlayer = new EmulatorPlayer(document.getElementById("letters-emu"));
const portraitPlayer = new EmulatorPlayer(document.getElementById("portrait-emu"));
const statsEl = document.getElementById("stats");
const lettersStatsEl = document.getElementById("letters-stats");
const portraitStatsEl = document.getElementById("portrait-stats");
const controls = document.getElementById("controls");
const inspectorBody = document.getElementById("inspector-body");
const downloadSvg = document.getElementById("download-svg");
const labShell = document.getElementById("lab-shell");
const lettersShell = document.getElementById("letters-shell");
const portraitShell = document.getElementById("portrait-shell");
player.onStats = (m) => { statsEl.textContent = m; };
lettersPlayer.onStats = (m) => { if (lettersStatsEl) lettersStatsEl.textContent = m; };
portraitPlayer.onStats = (m) => { if (portraitStatsEl) portraitStatsEl.textContent = m; };
let portraitImageMode = "photo";
let portraitFile = null;
let portraitIngestId = null;
let portraitPaperId = "natural-cream";
let papers = [];
let linesCatalog = [];
let selectedLineId = "solid";
let selectedPaperId = "natural-cream";
let labIngestId = null; // shared GenArt / R&D ingest
let portraitLineType = "solid";
let portraitForceReingest = false;
let portraitAutoFrame = true;
let portraitCrop = null; // {x,y,w,h,source} normalized or null
let portraitIngestPreview = null; // last ingest API payload
let portraitShowEdges = true;
let portraitShowRegions = true;
let portraitShowCrop = true;
let portraitShowHatch = true;
let portraitHatchEnabled = true;
let portraitEnsemble = null; // null = auto (studio-hq photo on); bool overrides
let portraitScanMode = "auto"; // Inkscape Trace Bitmap–inspired filter
let portraitPathSimplify = 2; // contour_simplify / Path→Simplify strength (1=finest)
let portraitLineSource = "auto"; // auto | neural | classic
let portraitAiReview = false; // Claude vision scene + one critique loop
let portraitIngestUnderlay = "scan"; // scan | tone | photo | none
let portraitIngestTimer = null;
let portraitPenMap = null;
const PORTRAIT_LINE_TYPES = [
  "solid", "dashed", "dotted", "dash_dot", "zigzag", "triangle", "wave", "square_wave",
  "half_circle", "scallop_alt", "beads", "double", "railroad", "stitch", "hatch_tick",
  "chevron", "spring", "bounce", "wobble", "ladder",
];

let currentApp = "genartbot";
let inspTab = "layers";
let styles = [];
let palettes = [];
let selectedStyle = "stipple";
let selectedPaletteId = "default-6";
let lastJob = null;
let lastPayload = null;
let lastLayers = null;
let lastSettings = null;
let inspectorJson = null;
let letterType = "personal";
let letterLayerTab = "layer-0";
let letterFonts = [];
let letterLayersState = [];
let letterVectorizeTimer = null;
let letterLayerSpans = {};

const LETTER_TYPE_DEFAULTS = {
  professional: {
    title: "Professional",
    names: "Alex Rivera",
    body: "Dear Hiring Manager,\n\nI am writing to express my interest in the role.\n\nSincerely,",
    mood: "formal",
    facts: "Available to start in three weeks.",
  },
  marketing: {
    title: "Marketing",
    names: "BotDraw Studio",
    body: "Hello,\n\nA handwritten note stops the scroll.\nPlot your next campaign with us.\n\n— BotDraw",
    mood: "bold",
    facts: "Spring launch offer.",
  },
  envelopes: {
    title: "Envelopes",
    names: "Aanya & Kabir",
    body: "Aanya Sharma\n14 Garden Lane\nToronto ON",
    mood: "neutral",
    facts: "Return address on flap.",
  },
  personal: {
    title: "Personal",
    names: "Aanya & Kabir",
    body: "HELLO",
    mood: "romantic",
    facts: "Met at a cousin's wedding.",
  },
  invitations: {
    title: "Invitations",
    names: "Aanya & Kabir",
    body: "Together with their families\nAanya & Kabir\ninvite you to celebrate\nSaturday, the twelfth of June",
    mood: "celebratory",
    facts: "Ceremony at 4pm.",
  },
  postcards: {
    title: "Postcards",
    names: "Sam",
    body: "Wish you were here.\nThe light is perfect.\n\n— Sam",
    mood: "casual",
    facts: "Front image separate.",
  },
};

function ensureLineFields(layer) {
  if (!layer.line) {
    layer.line = { x0_mm: 20, y0_mm: 40, x1_mm: 120, y1_mm: 40, style: "solid", dash_mm: 2, gap_mm: 1.2, width_mm: null };
  }
  if (!layer.snap) {
    layer.snap = { target_layer_id: null, span_index: null, role: "underline" };
  }
  if (layer.draw_mode == null) layer.draw_mode = "text";
  if (layer.leading_variation == null) layer.leading_variation = 0.12;
  if (layer.line_angle_deg == null) layer.line_angle_deg = 0;
  if (layer.placement == null) layer.placement = "freehand";
  return layer;
}

function defaultLetterLayers(bodyText = "HELLO") {
  const pal = currentPalette();
  const ink = pal?.pens?.find((p) => p.profile?.nib_type !== "highlighter") || pal?.pens?.[0];
  return [
    ensureLineFields({
      id: "layer-0",
      name: "Ink",
      body: bodyText,
      font_name: "simplex",
      size_mm: 4.5,
      pen_id: ink?.id || "ink",
      language: "en",
      translate_from_en: false,
      offset_x_mm: 0,
      offset_y_mm: 0,
      kind: "ink",
      tracking: 0.15,
      humanize: 0.08,
      highlight_words: [],
      draw_mode: "text",
      leading_variation: 0.12,
      line_angle_deg: 0,
      placement: "freehand",
    }),
  ];
}

function textLayerOptionsHtml(selectedId) {
  const texts = letterLayersState.filter((l) => (l.draw_mode || "text") === "text");
  if (!texts.length) return `<option value="">—</option>`;
  return texts.map((l) =>
    `<option value="${l.id}" ${l.id === selectedId ? "selected" : ""}>${l.name || l.id}</option>`
  ).join("");
}

function spanOptionsHtml(targetId, selectedIdx) {
  const spans = letterLayerSpans[targetId] || [];
  if (!spans.length) return `<option value="">No spans yet — Vectorize</option>`;
  return spans.map((s, i) => {
    const label = (s.text || `span ${i}`).slice(0, 24);
    return `<option value="${i}" ${Number(selectedIdx) === i ? "selected" : ""}>${i}: ${label}</option>`;
  }).join("");
}

function applySnapToLayer(layer) {
  ensureLineFields(layer);
  if ((layer.placement || "freehand") !== "snap") return;
  const tid = layer.snap.target_layer_id;
  const sidx = layer.snap.span_index;
  const spans = letterLayerSpans[tid] || [];
  if (sidx == null || sidx === "" || !spans[sidx]) return;
  const span = spans[sidx];
  const role = layer.snap.role || "underline";
  let x0 = span.x0 != null ? span.x0 : span.x;
  let y0 = span.y0 != null ? span.y0 : (span.baseline_y ?? span.y);
  let x1 = span.x1 != null ? span.x1 : span.x + span.w;
  let y1 = span.y1 != null ? span.y1 : y0;
  if (role === "highlight") {
    const mid = span.y + span.h * 0.55;
    x0 = span.x - 0.4; x1 = span.x + span.w + 0.4; y0 = mid; y1 = mid;
  } else {
    const uy = (span.baseline_y != null ? span.baseline_y : y0) + span.h * 0.12;
    y0 = uy; y1 = uy;
  }
  layer.line.x0_mm = x0; layer.line.y0_mm = y0; layer.line.x1_mm = x1; layer.line.y1_mm = y1;
}

function syncLineHandles() {
  const layer = activeLetterLayer();
  if (!layer || !lettersPlayer) return;
  ensureLineFields(layer);
  if ((layer.draw_mode || "text") === "line") {
    lettersPlayer.setEditLine(layer.line);
    if (layer.placement === "snap" && layer.snap?.target_layer_id != null && layer.snap.span_index != null) {
      const sp = (letterLayerSpans[layer.snap.target_layer_id] || [])[layer.snap.span_index];
      lettersPlayer.setSnapGhost(sp || null);
    } else {
      lettersPlayer.setSnapGhost(null);
    }
  } else {
    lettersPlayer.setEditLine(null);
    lettersPlayer.setSnapGhost(null);
  }
}

function readMargins() {
  return {
    left: Number(document.getElementById("margin-left")?.value || 18),
    top: Number(document.getElementById("margin-top")?.value || 18),
    right: Number(document.getElementById("margin-right")?.value || 18),
    bottom: Number(document.getElementById("margin-bottom")?.value || 18),
  };
}

const state = {
  paper: "A4",
  quality: "booth-balanced",
  seed: 42,
  density: 1.0,
  pen_up_speed_mm_s: 100,
  pen_down_speed_mm_s: 25,
  rpm: 3,
};

document.getElementById("play").onclick = () => player.play();
document.getElementById("pause").onclick = () => player.pause();
document.getElementById("skip").onclick = () => player.skipEnd();
document.getElementById("speed").oninput = (e) => player.setSpeed(e.target.value);
document.getElementById("ghost").onchange = (e) => player.setGhost(e.target.checked);

document.getElementById("letters-play").onclick = () => lettersPlayer.play();
document.getElementById("letters-pause").onclick = () => lettersPlayer.pause();
document.getElementById("letters-skip").onclick = () => lettersPlayer.skipEnd();
document.getElementById("letters-speed").oninput = (e) => lettersPlayer.setSpeed(e.target.value);
document.getElementById("portrait-play").onclick = () => portraitPlayer.play();
document.getElementById("portrait-pause").onclick = () => portraitPlayer.pause();
document.getElementById("portrait-skip").onclick = () => portraitPlayer.skipEnd();
document.getElementById("portrait-speed").oninput = (e) => portraitPlayer.setSpeed(e.target.value);

function setShellForApp(app) {
  document.body.dataset.app = app;
  const letters = app === "lettersbot";
  const portrait = app === "portraitbot";
  labShell.hidden = letters || portrait;
  if (lettersShell) lettersShell.hidden = !letters;
  if (portraitShell) portraitShell.hidden = !portrait;
}

function stagePlayer() {
  if (currentApp === "lettersbot") return lettersPlayer;
  if (currentApp === "portraitbot") return portraitPlayer;
  return player;
}

document.querySelectorAll("#tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentApp = btn.dataset.app;
    setShellForApp(currentApp);
    renderControls();
  };
});

document.querySelectorAll(".insp-tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".insp-tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    inspTab = btn.dataset.insp;
    renderInspector();
  };
});

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function field(label, html) {
  return `<label>${label}</label>${html}`;
}

function val(id, fallback = "") {
  const el = controls.querySelector(`#${id}`);
  return el ? el.value : fallback;
}

function num(id, fallback = 0) {
  return Number(val(id, fallback));
}

function syncStateFromForm() {
  if (controls.querySelector("#paper")) state.paper = val("paper", state.paper);
  if (controls.querySelector("#quality")) state.quality = val("quality", state.quality);
  if (controls.querySelector("#seed")) state.seed = num("seed", state.seed);
  if (controls.querySelector("#density")) state.density = num("density", state.density);
  if (controls.querySelector("#pen_up")) state.pen_up_speed_mm_s = num("pen_up", state.pen_up_speed_mm_s);
  if (controls.querySelector("#pen_down")) state.pen_down_speed_mm_s = num("pen_down", state.pen_down_speed_mm_s);
  if (controls.querySelector("#rpm")) state.rpm = num("rpm", state.rpm);
  if (controls.querySelector("#palette")) selectedPaletteId = val("palette", selectedPaletteId);
}

function setExportEnabled(on) {
  ["export-pack", "export-settings", "export-layers", "export-motion", "export-palette", "copy-json"].forEach((id) => {
    document.getElementById(id).disabled = !on;
  });
}

function loadResult(data, opts = {}) {
  const autoplay = opts.autoplay !== false;
  lastJob = data.job;
  lastPayload = data.emulator;
  lastLayers = data.layers || data.emulator?.layers || null;
  lastSettings = data.settings || data.emulator?.settings || {
    app: data.job?.app,
    style_id: data.job?.style_id,
    palette_id: data.job?.palette_id,
    quality: data.job?.quality,
    seed: data.job?.seed,
    density: data.job?.params?.density,
  };
  const pl = stagePlayer();
  const paperHex = data.emulator?.paper_color_hex || data.layers?.meta?.paper_color_hex || lastSettings?.paper_color_hex;
  pl.load(lastPayload, {
    preserveVisibility: currentApp === "lettersbot",
    paperColor: paperHex,
  });
  if (paperHex) pl.setPaperColor(paperHex);
  if (data.emulator?.settings?.ingest_id) portraitIngestId = data.emulator.settings.ingest_id;
  if (data.job?.params?.ingest_id) portraitIngestId = data.job.params.ingest_id;
  if (lastJob?.id && downloadSvg) {
    downloadSvg.hidden = currentApp === "portraitbot" || currentApp === "lettersbot";
    downloadSvg.href = `/api/jobs/${lastJob.id}/svg`;
  }
  if (currentApp === "portraitbot") setPortraitDownloads(true, lastJob?.id);
  if (currentApp !== "portraitbot" && currentApp !== "lettersbot") setExportEnabled(true);
  inspectorJson = {
    settings: lastSettings,
    layers: lastLayers,
    stats: lastPayload?.stats,
    job: lastJob,
    draft: data.draft,
  };
  if (currentApp !== "portraitbot" && currentApp !== "lettersbot") renderInspector();
  if (autoplay && currentApp !== "portraitbot" && currentApp !== "lettersbot") pl.play();
  else pl.skipEnd();
}

function setPortraitDownloads(enabled, jobId) {
  const svgBtn = document.getElementById("portrait-dl-svg");
  const motionBtn = document.getElementById("portrait-dl-motion");
  const packBtn = document.getElementById("portrait-dl-pack");
  [svgBtn, motionBtn, packBtn].forEach((b) => { if (b) b.disabled = !enabled; });
  if (!svgBtn) return;
  svgBtn.onclick = () => {
    if (!jobId) return;
    const a = document.createElement("a");
    a.href = `/api/jobs/${jobId}/svg`;
    a.download = `botdraw-${jobId}-portrait.svg`;
    a.click();
  };
  motionBtn.onclick = async () => {
    if (!jobId) return;
    downloadJson(`botdraw-${jobId}-motion.json`, await api(`/api/jobs/${jobId}/motion`));
  };
  packBtn.onclick = async () => {
    if (!jobId) return;
    downloadJson(`botdraw-${jobId}-pack.json`, await api(`/api/jobs/${jobId}/export`));
  };
}

function drawPortraitSourcePreview(file, crop) {
  const canvas = document.getElementById("portrait-src");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
  ctx.fillStyle = "#f4f4f5";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const drawCrop = (ox, oy, dw, dh) => {
    const c = crop || portraitCrop || portraitIngestPreview?.crop;
    if (!portraitShowCrop || !c || c.w == null) return;
    ctx.save();
    ctx.strokeStyle = "rgba(234, 88, 12, 0.95)";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(ox + c.x * dw, oy + c.y * dh, c.w * dw, c.h * dh);
    ctx.fillStyle = "rgba(234, 88, 12, 0.08)";
    ctx.fillRect(ox + c.x * dw, oy + c.y * dh, c.w * dw, c.h * dh);
    ctx.restore();
  };

  if (!file) {
    ctx.fillStyle = "#a3a3a3";
    ctx.font = "12px sans-serif";
    ctx.fillText("Synthetic / upload a photo", 16, 28);
    // Still show crop relative to full canvas if present
    drawCrop(0, 0, canvas.width, canvas.height);
    return;
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const ox = (canvas.width - w) / 2;
    const oy = (canvas.height - h) / 2;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, ox, oy, w, h);
    drawCrop(ox, oy, w, h);
    URL.revokeObjectURL(url);
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    ctx.fillStyle = "#92400e";
    ctx.font = "12px sans-serif";
    ctx.fillText("Could not preview image", 16, 28);
  };
  img.src = url;
}

function clearPortraitIngestCanvas(msg) {
  const canvas = document.getElementById("portrait-ingest");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: false, alpha: true });
  ctx.fillStyle = "#f7f1e8";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (msg) {
    ctx.fillStyle = "#737373";
    ctx.font = "12px sans-serif";
    ctx.fillText(msg, 16, 28);
  }
}

function drawPortraitIngestPreview(preview) {
  const canvas = document.getElementById("portrait-ingest");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: false, alpha: true });
  const paperHex = papers.find((p) => p.id === portraitPaperId)?.color_hex || "#f7f1e8";
  ctx.fillStyle = paperHex;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (!preview) {
    ctx.fillStyle = "#737373";
    ctx.font = "12px sans-serif";
    ctx.fillText("Run Ingest to see raw vectorization", 16, 28);
    return;
  }

  const [pw, ph] = preview.page_mm || [210, 297];
  const sx = canvas.width / pw;
  const sy = canvas.height / ph;
  const s = Math.min(sx, sy);
  const ox = (canvas.width - pw * s) / 2;
  const oy = (canvas.height - ph * s) / 2;

  // Underlay: scan intermediate, tone-code heatmap, or photo
  let underlayB64 = null;
  let underlayAlpha = 0.22;
  if (portraitIngestUnderlay === "tone" && preview.tone_heatmap_png_b64) {
    underlayB64 = preview.tone_heatmap_png_b64;
    underlayAlpha = 0.55;
  } else if (portraitIngestUnderlay === "photo" && preview.preview_png_b64) {
    underlayB64 = preview.preview_png_b64;
    underlayAlpha = 0.28;
  } else if (portraitIngestUnderlay === "scan") {
    underlayB64 = preview.intermediate_png_b64 || preview.preview_png_b64;
    underlayAlpha = preview.intermediate_png_b64 ? 0.38 : 0.22;
  } else if (portraitIngestUnderlay === "none") {
    underlayB64 = null;
  } else {
    underlayB64 = preview.intermediate_png_b64 || preview.tone_heatmap_png_b64 || preview.preview_png_b64;
    underlayAlpha = preview.tone_heatmap_png_b64 && !preview.intermediate_png_b64 ? 0.5 : 0.32;
  }
  if (underlayB64) {
    const img = new Image();
    img.onload = () => {
      ctx.globalAlpha = underlayAlpha;
      ctx.drawImage(img, ox, oy, pw * s, ph * s);
      ctx.globalAlpha = 1;
      _strokeIngestGeometry(ctx, preview, ox, oy, s);
    };
    img.src = `data:image/png;base64,${underlayB64}`;
  } else {
    _strokeIngestGeometry(ctx, preview, ox, oy, s);
  }

  const dl = document.getElementById("portrait-dl-ingest-svg");
  if (dl && preview.ingest_id) {
    dl.hidden = false;
    dl.href = `/api/portrait/ingest/${preview.ingest_id}/svg`;
    dl.download = `botdraw-ingest-${preview.ingest_id}.svg`;
  }
}

function _strokeIngestGeometry(ctx, preview, ox, oy, s) {
  const map = (pt) => [ox + pt[0] * s, oy + pt[1] * s];

  if (portraitShowHatch && preview.hatch_polylines_mm?.length) {
    ctx.strokeStyle = "rgba(194, 65, 12, 0.7)";
    ctx.lineWidth = 0.85;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const pts of preview.hatch_polylines_mm) {
      if (!pts || pts.length < 2) continue;
      ctx.beginPath();
      const p0 = map(pts[0]);
      ctx.moveTo(p0[0], p0[1]);
      for (let i = 1; i < pts.length; i++) {
        const p = map(pts[i]);
        ctx.lineTo(p[0], p[1]);
      }
      ctx.stroke();
    }
  }

  if (portraitShowRegions && preview.regions?.length) {
    ctx.strokeStyle = "rgba(162, 28, 175, 0.85)";
    ctx.lineWidth = 1.25;
    for (const r of preview.regions) {
      const pts = r.points_mm || [];
      if (pts.length < 2) continue;
      ctx.beginPath();
      const p0 = map(pts[0]);
      ctx.moveTo(p0[0], p0[1]);
      for (let i = 1; i < pts.length; i++) {
        const p = map(pts[i]);
        ctx.lineTo(p[0], p[1]);
      }
      ctx.closePath();
      ctx.stroke();
    }
  }

  if (portraitShowEdges && preview.edge_polylines_mm?.length) {
    ctx.strokeStyle = "rgba(14, 116, 144, 0.95)";
    ctx.lineWidth = 1.1;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const pts of preview.edge_polylines_mm) {
      if (!pts || pts.length < 2) continue;
      ctx.beginPath();
      const p0 = map(pts[0]);
      ctx.moveTo(p0[0], p0[1]);
      for (let i = 1; i < pts.length; i++) {
        const p = map(pts[i]);
        ctx.lineTo(p[0], p[1]);
      }
      ctx.stroke();
    }
  }

  // Legend
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.font = "11px sans-serif";
  const legendY = (ctx.canvas?.height || 640) - 12;
  ctx.fillText(
    `edges ${preview.edge_count ?? 0} · hatch ${preview.hatch_count ?? 0} · regions ${preview.region_count ?? 0}`,
    10,
    legendY
  );
}

/** Copy File bytes so DOM rebuilds cannot invalidate the handle. */
async function snapshotPortraitFile(file) {
  if (!file) return null;
  const buf = await file.arrayBuffer();
  return new File([buf], file.name || "portrait.png", {
    type: file.type || "image/png",
    lastModified: file.lastModified || Date.now(),
  });
}

/** Downscale for upload: max side ≤ 1280 to avoid proxy timeouts / huge multipart. */
async function downscalePortraitForUpload(file, maxSide = 1280) {
  if (!file) return null;
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("Could not decode image for upload"));
      i.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
    const w = Math.max(1, Math.round(img.width * scale));
    const h = Math.max(1, Math.round(img.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    // Readback-friendly: we call toBlob after draw (DESIGN.md analysis canvas).
    const ctx = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
    ctx.drawImage(img, 0, 0, w, h);
    const preferJpeg = !/^image\/png$/i.test(file.type || "");
    const blob = await new Promise((resolve) => {
      canvas.toBlob(
        (b) => resolve(b),
        preferJpeg ? "image/jpeg" : "image/png",
        preferJpeg ? 0.88 : undefined
      );
    });
    if (!blob) return file;
    const base = (file.name || "portrait").replace(/\.[^.]+$/, "");
    const name = preferJpeg ? `${base}.jpg` : `${base}.png`;
    return new File([blob], name, { type: blob.type, lastModified: Date.now() });
  } finally {
    URL.revokeObjectURL(url);
  }
}

function portraitNetworkErrorMessage(err) {
  const msg = String(err?.message || err || "");
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(msg)) {
    return "Network error — is botdraw serve reachable? Try a smaller image or booth-fast.";
  }
  return msg || "Vectorize failed";
}

function portraitContentRoot() {
  return document.getElementById("portrait-content");
}

function ensurePortraitStyleSelected(list) {
  const ids = list.map((s) => s.id);
  if (!ids.includes(selectedStyle)) {
    selectedStyle = ids[0] || "portrait_linework";
  }
  return selectedStyle;
}

function paperSelectHtml(selectedId) {
  const opts = (papers.length ? papers : [{ id: "natural-cream", name: "Natural Cream", color_hex: "#f7f1e8" }])
    .map((p) => `<option value="${p.id}" ${p.id === selectedId ? "selected" : ""}>${p.name}</option>`)
    .join("");
  return `<select id="paper-color">${opts}</select>`;
}

function lineSelectHtml(selectedId) {
  const opts = (linesCatalog.length ? linesCatalog : [{ id: "solid", name: "Solid" }])
    .map((l) => `<option value="${l.id}" ${l.id === selectedId ? "selected" : ""}>${l.name || l.id}</option>`)
    .join("");
  return `<select id="line-lib">${opts}</select>`;
}

function applyLineStockToPortraitForm(root, stock) {
  if (!root || !stock) return;
  const set = (id, v, labelId) => {
    const el = root.querySelector(`#${id}`);
    if (!el || v == null) return;
    el.value = v;
    const lab = labelId ? root.querySelector(`#${labelId}`) : null;
    if (lab) lab.textContent = Number(v).toFixed(1);
  };
  if (stock.line_type) {
    portraitLineType = stock.line_type;
    const lt = root.querySelector("#line-type");
    if (lt) lt.value = stock.line_type;
  }
  set("line-spacing", stock.line_spacing_mm, "line-spacing-val");
  set("pattern-period", stock.pattern_period_mm, "pattern-period-val");
  set("pattern-amp", stock.pattern_amplitude_mm, "pattern-amp-val");
  set("dash-mm", stock.dash_mm, "dash-mm-val");
  set("gap-mm", stock.gap_mm, "gap-mm-val");
  const amp = root.querySelector("#ornament-amp");
  const dash = root.querySelector("#ornament-dash");
  if (amp) amp.style.display = portraitOrnamentNeedsAmp(portraitLineType) ? "" : "none";
  if (dash) dash.style.display = portraitOrnamentNeedsDash(portraitLineType) ? "" : "none";
}

function ensureLabEmuInCompare() {
  const compare = document.getElementById("lab-compare");
  const pane = document.querySelector(".lab-vector-pane");
  const emu = document.getElementById("emu");
  if (!compare || !pane || !emu) return;
  compare.hidden = false;
  const stage = emu.closest(".stage");
  if (stage) stage.classList.add("compare-on");
  if (emu.parentElement !== pane) pane.appendChild(emu);
}

function drawLabSource(file) {
  const canvas = document.getElementById("lab-src");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
  ctx.fillStyle = "#f4f4f5";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!file) {
    ctx.fillStyle = "#a3a3a3";
    ctx.font = "12px sans-serif";
    ctx.fillText("Upload a photo", 16, 28);
    return;
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const ox = (canvas.width - w) / 2;
    const oy = (canvas.height - h) / 2;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, ox, oy, w, h);
    URL.revokeObjectURL(url);
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    ctx.fillStyle = "#92400e";
    ctx.font = "12px sans-serif";
    ctx.fillText("Could not preview image", 16, 28);
  };
  img.src = url;
}

function drawLabIngestPng(preview) {
  const canvas = document.getElementById("lab-ingest");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: false, alpha: true });
  ctx.fillStyle = "#f7f1e8";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!preview?.preview_png_b64) {
    ctx.fillStyle = "#737373";
    ctx.font = "12px sans-serif";
    ctx.fillText(preview ? "No preview PNG" : "Run Ingest", 16, 28);
    return;
  }
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const ox = (canvas.width - w) / 2;
    const oy = (canvas.height - h) / 2;
    ctx.drawImage(img, ox, oy, w, h);
  };
  img.src = `data:image/png;base64,${preview.preview_png_b64}`;
}

async function runLabIngest() {
  syncStateFromForm();
  const file = controls.querySelector("#photo")?.files?.[0];
  if (!file) {
    statsEl.textContent = "Choose a photo to ingest";
    return null;
  }
  statsEl.textContent = "Ingesting…";
  const fd = new FormData();
  fd.append("quality", state.quality);
  fd.append("paper", state.paper);
  fd.append("image_mode", "photo");
  fd.append("auto_frame", "true");
  fd.append("include_preview_png", "true");
  fd.append("file", file, file.name || "photo.jpg");
  const data = await api("/api/portrait/ingest/upload", { method: "POST", body: fd });
  labIngestId = data.ingest_id || null;
  ensureLabEmuInCompare();
  drawLabSource(file);
  drawLabIngestPng(data);
  statsEl.textContent =
    `Ingest ready · edges ${data.edge_count ?? "?"} · hatch ${data.hatch_count ?? 0}` +
    ` · id ${labIngestId || "?"}`;
  return data;
}

function portraitOrnamentNeedsDash(lt) {
  return ["dashed", "dotted", "dash_dot", "stitch"].includes(lt);
}

function portraitOrnamentNeedsAmp(lt) {
  return !["solid", "dashed", "dotted", "dash_dot"].includes(lt);
}

function renderPortrait() {
  setShellForApp("portraitbot");
  const list = styles.filter((s) => s.category === "portrait");
  ensurePortraitStyleSelected(list);
  if (!selectedPaletteId) selectedPaletteId = "default-6";
  const root = portraitContentRoot();
  if (!root) return;
  const modes = [
    ["photo", "Photo", "Many tones"],
    ["sketch", "Sketch", "Grayscale"],
    ["lineart", "Line art", "Edges"],
    ["drawing", "Drawing", "Black / white"],
  ];
  const ltOpts = PORTRAIT_LINE_TYPES.map(
    (t) => `<option value="${t}" ${t === portraitLineType ? "selected" : ""}>${t.replace(/_/g, " ")}</option>`
  ).join("");
  const needsDash = portraitOrnamentNeedsDash(portraitLineType);
  const needsAmp = portraitOrnamentNeedsAmp(portraitLineType);
  const penList = (currentPalette()?.pens || [])
    .map(
      (pen) =>
        `<div class="pen-chip" title="${pen.profile?.nib_type || ""}">
          <span class="swatch" style="background:${pen.color_hex}"></span>
          ${pen.name} · ${pen.profile?.width_mm ?? "?"}mm · ${pen.profile?.nib_type || ""}
        </div>`
    )
    .join("");
  root.innerHTML = `
    <h3>Portrait</h3>
    <p class="muted">Step 1: Ingest (linedraw vectors). Step 2: Vectorize — styles use those edges/hatch. Prefer line type <code>solid</code>.</p>
    <h4>Image</h4>
    <div class="portrait-drop ${portraitFile ? "has-file" : ""}" id="portrait-drop">
      ${portraitFile ? portraitFile.name : "Drop a photo or choose a file"}
      <div style="margin-top:0.45rem"><input id="portrait-photo" type="file" accept="image/*" /></div>
    </div>
    <div class="row" style="margin-top:0.35rem">
      <label><input type="checkbox" id="auto-frame" ${portraitAutoFrame ? "checked" : ""}/> Auto frame subject</label>
      <label><input type="checkbox" id="hatch-shading" ${portraitHatchEnabled ? "checked" : ""}/> Hatch shading</label>
      <label title="5 tone variants + consensus pass (studio-hq photo; booth stays single-pass)"><input type="checkbox" id="ensemble-5plus1" ${
        portraitEnsemble === true || (portraitEnsemble == null && state.quality === "studio-hq" && portraitImageMode === "photo") ? "checked" : ""
      }/> Ensemble (5+1)</label>
      <button type="button" id="reset-frame">Reset frame</button>
    </div>
    <p class="muted" style="margin-top:0.25rem">Ingest: teal contours · orange hatch · magenta regions. Quality preset drives detail. Ensemble auto-on for studio-hq photo.</p>
    <h4>Image type</h4>
    <div class="image-mode-grid" id="image-mode-grid">
      ${modes.map(([id, title, sub]) =>
        `<button type="button" data-mode="${id}" class="${portraitImageMode === id ? "active" : ""}">
          <strong>${title}</strong><span>${sub}</span>
        </button>`
      ).join("")}
    </div>
    <h4>Scan filter <span class="muted">(Inkscape-style intermediate)</span></h4>
    <div class="grid-2">
      ${field(
        "Mode",
        `<select id="scan-mode">
          <option value="auto">Auto (Hybrid C)</option>
          <option value="brightness">Brightness</option>
          <option value="edges">Edges</option>
          <option value="centerline">Centerline</option>
          <option value="color_bands">Color bands</option>
        </select>`
      )}
      ${field(
        "Path simplify",
        `<input id="path-simplify" type="range" min="1" max="3" step="1" value="${portraitPathSimplify}" /><span id="path-simplify-val">${portraitPathSimplify}</span>`
      )}
    </div>
    <div class="grid-2">
      ${field(
        "Line source",
        `<select id="line-source" title="Neural = artist-line model + person matte (needs downloaded weights)">
          <option value="auto"${portraitLineSource === "auto" ? " selected" : ""}>Auto (neural if available)</option>
          <option value="neural"${portraitLineSource === "neural" ? " selected" : ""}>Neural</option>
          <option value="classic"${portraitLineSource === "classic" ? " selected" : ""}>Classic</option>
        </select>`
      )}
      ${field(
        "AI review",
        `<label style="display:flex;align-items:center;gap:0.4rem;margin:0">
          <input type="checkbox" id="ai-review" ${portraitAiReview ? "checked" : ""} title="Claude vision: scene knobs before ingest + one post-render critique (needs ANTHROPIC_API_KEY)" />
          <span class="muted">Studio (Claude)</span>
        </label>`
      )}
    </div>
    <p class="muted" style="margin-top:0.2rem">Lighter intermediates first — Brightness / Edges / Centerline map to linedraw knobs (no Potrace).</p>
    <h4>Portrait style</h4>
    ${styleButtons(list)}
    <h4>Paper</h4>
    <div class="grid-2">
      ${field("Size", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
      ${field("Color (Paper Library)", paperSelectHtml(portraitPaperId))}
    </div>
    <h4>Render settings</h4>
    <div class="grid-2">
      ${field("Quality", `<select id="quality"><option value="booth-fast">booth-fast</option><option value="booth-balanced">booth-balanced</option><option value="studio-hq">studio-hq</option></select>`)}
      ${field("Density", `<input id="density" type="number" step="0.1" value="${state.density}" />`)}
    </div>
    <div class="grid-2">
      ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
      ${field("Line type", `<select id="line-type">${ltOpts}</select>`)}
    </div>
    ${field("Line library", lineSelectHtml(selectedLineId))}
    <h4>Stroke ornament</h4>
    ${field("Line spacing mm", `<input id="line-spacing" type="range" min="0.4" max="4" step="0.1" value="1.2" /><span id="line-spacing-val">1.2</span>`)}
    <div id="ornament-amp" style="${needsAmp ? "" : "display:none"}">
      ${field("Period mm", `<input id="pattern-period" type="range" min="0.4" max="8" step="0.1" value="2" /><span id="pattern-period-val">2.0</span>`)}
      ${field("Amplitude mm", `<input id="pattern-amp" type="range" min="0" max="4" step="0.1" value="0.8" /><span id="pattern-amp-val">0.8</span>`)}
    </div>
    <div id="ornament-dash" style="${needsDash ? "" : "display:none"}">
      ${field("Dash mm", `<input id="dash-mm" type="range" min="0.2" max="8" step="0.1" value="2" /><span id="dash-mm-val">2.0</span>`)}
      ${field("Gap mm", `<input id="gap-mm" type="range" min="0.1" max="6" step="0.1" value="1.2" /><span id="gap-mm-val">1.2</span>`)}
    </div>
    <h4>Palette / pens</h4>
    ${field("Palette", paletteSelectHtml())}
    <div class="pen-chips">${penList}</div>
    <div class="row" style="margin-top:0.55rem; gap:0.35rem; flex-wrap:wrap">
      <button class="primary" id="portrait-ingest-btn">Ingest</button>
      <button type="button" id="portrait-go">Vectorize</button>
      <button type="button" id="portrait-apply" ${portraitIngestId ? "" : "disabled"}>Apply (restyle)</button>
      <button type="button" id="portrait-reingest">Re-ingest</button>
      <button type="button" id="reset-pen-map">Reset pen map</button>
    </div>
  `;

  const bindRange = (id, labelId) => {
    const el = root.querySelector(`#${id}`);
    const lab = root.querySelector(`#${labelId}`);
    if (!el || !lab) return;
    const sync = () => { lab.textContent = Number(el.value).toFixed(1); };
    el.oninput = sync;
    sync();
  };
  bindRange("line-spacing", "line-spacing-val");
  bindRange("pattern-period", "pattern-period-val");
  bindRange("pattern-amp", "pattern-amp-val");
  bindRange("dash-mm", "dash-mm-val");
  bindRange("gap-mm", "gap-mm-val");

  root.querySelectorAll("[data-style]").forEach((btn) => {
    btn.onclick = () => {
      selectedStyle = btn.dataset.style;
      renderPortrait();
    };
  });
  root.querySelector("#paper").value = state.paper;
  root.querySelector("#quality").value = state.quality;
  const scanEl = root.querySelector("#scan-mode");
  if (scanEl) {
    scanEl.value = portraitScanMode;
    scanEl.onchange = () => {
      portraitScanMode = scanEl.value;
      portraitForceReingest = true;
      const hint = document.getElementById("scan-mode-hint");
      if (hint) hint.textContent = `Scan filter: ${portraitScanMode} — re-ingest to refresh intermediate`;
    };
  }
  const simpEl = root.querySelector("#path-simplify");
  const simpVal = root.querySelector("#path-simplify-val");
  if (simpEl) {
    const syncSimp = () => {
      portraitPathSimplify = Number(simpEl.value) || 2;
      if (simpVal) simpVal.textContent = String(portraitPathSimplify);
    };
    simpEl.oninput = syncSimp;
    simpEl.onchange = () => {
      syncSimp();
      portraitForceReingest = true;
    };
    syncSimp();
  }
  root.querySelector("#palette").value = selectedPaletteId;
  root.querySelector("#palette").onchange = () => {
    selectedPaletteId = root.querySelector("#palette").value;
    renderPortrait();
  };
  root.querySelector("#paper-color").onchange = () => {
    portraitPaperId = root.querySelector("#paper-color").value;
    const stock = papers.find((p) => p.id === portraitPaperId);
    if (stock) portraitPlayer.setPaperColor(stock.color_hex);
  };
  root.querySelector("#line-type").onchange = () => {
    portraitLineType = root.querySelector("#line-type").value;
    renderPortrait();
  };
  const lineLib = root.querySelector("#line-lib");
  if (lineLib) {
    lineLib.onchange = () => {
      selectedLineId = lineLib.value;
      const stock = linesCatalog.find((l) => l.id === selectedLineId);
      if (stock) applyLineStockToPortraitForm(root, stock);
    };
  }
  root.querySelector("#auto-frame").onchange = (e) => {
    portraitAutoFrame = !!e.target.checked;
  };
  const hatchCb = root.querySelector("#hatch-shading");
  if (hatchCb) {
    hatchCb.onchange = () => {
      portraitHatchEnabled = !!hatchCb.checked;
      if (portraitIngestTimer) clearTimeout(portraitIngestTimer);
      portraitIngestTimer = setTimeout(() => {
        runPortraitIngest({ forceReingest: true }).catch((err) => {
          if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(err);
          console.error(err);
        });
      }, 300);
    };
  }
  const ensCb = root.querySelector("#ensemble-5plus1");
  if (ensCb) {
    ensCb.onchange = () => {
      portraitEnsemble = !!ensCb.checked;
      portraitForceReingest = true;
      if (portraitIngestTimer) clearTimeout(portraitIngestTimer);
      portraitIngestTimer = setTimeout(() => {
        runPortraitIngest({ forceReingest: true }).catch((err) => {
          if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(err);
          console.error(err);
        });
      }, 300);
    };
  }
  const qualityEl = root.querySelector("#quality");
  if (qualityEl) {
    qualityEl.onchange = () => {
      state.quality = qualityEl.value;
      // Refresh ensemble checkbox default when quality changes and user hasn't forced
      if (portraitEnsemble == null && ensCb) {
        ensCb.checked = state.quality === "studio-hq" && portraitImageMode === "photo";
      }
    };
  }
  root.querySelector("#reset-frame").onclick = () => {
    portraitCrop = null;
    portraitAutoFrame = true;
    portraitForceReingest = true;
    if (portraitStatsEl) portraitStatsEl.textContent = "Frame reset — next Vectorize will re-ingest";
  };
  root.querySelector("#reset-pen-map").onclick = () => {
    portraitPenMap = null;
    if (portraitStatsEl) portraitStatsEl.textContent = "Pen map cleared (auto on next render)";
  };
  root.querySelectorAll("#image-mode-grid button").forEach((btn) => {
    btn.onclick = () => {
      portraitImageMode = btn.dataset.mode;
      portraitForceReingest = true;
      renderPortrait();
    };
  });
  const fileInput = root.querySelector("#portrait-photo");
  fileInput.onchange = async () => {
    const raw = fileInput.files?.[0] || null;
    try {
      portraitFile = raw ? await snapshotPortraitFile(raw) : null;
      portraitIngestId = null;
      portraitForceReingest = true;
      portraitCrop = null;
    } catch (e) {
      portraitFile = null;
      if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(e);
      console.error(e);
      return;
    }
    drawPortraitSourcePreview(portraitFile);
    const drop = root.querySelector("#portrait-drop");
    if (drop) {
      drop.classList.toggle("has-file", !!portraitFile);
      drop.childNodes[0].textContent = portraitFile ? portraitFile.name : "Drop a photo or choose a file";
    }
  };
  drawPortraitSourcePreview(portraitFile);
  drawPortraitIngestPreview(portraitIngestPreview);
  setPortraitDownloads(!!lastJob?.id && lastJob?.app === "portraitbot", lastJob?.id);

  const te = document.getElementById("toggle-edges");
  const th = document.getElementById("toggle-hatch");
  const tr = document.getElementById("toggle-regions");
  const tc = document.getElementById("toggle-crop");
  const tu = document.getElementById("ingest-underlay");
  if (te) {
    te.checked = portraitShowEdges;
    te.onchange = () => {
      portraitShowEdges = te.checked;
      drawPortraitIngestPreview(portraitIngestPreview);
    };
  }
  if (th) {
    th.checked = portraitShowHatch;
    th.onchange = () => {
      portraitShowHatch = th.checked;
      drawPortraitIngestPreview(portraitIngestPreview);
    };
  }
  if (tr) {
    tr.checked = portraitShowRegions;
    tr.onchange = () => {
      portraitShowRegions = tr.checked;
      drawPortraitIngestPreview(portraitIngestPreview);
    };
  }
  if (tc) {
    tc.checked = portraitShowCrop;
    tc.onchange = () => {
      portraitShowCrop = tc.checked;
      drawPortraitSourcePreview(portraitFile);
    };
  }
  if (tu) {
    tu.value = portraitIngestUnderlay;
    tu.onchange = () => {
      portraitIngestUnderlay = tu.value || "scan";
      drawPortraitIngestPreview(portraitIngestPreview);
      const hint = document.getElementById("scan-mode-hint");
      if (hint && portraitIngestPreview) {
        if (portraitIngestUnderlay === "tone") {
          hint.textContent = portraitIngestPreview.tone_heatmap_png_b64
            ? "Tone grid heatmap (codes 1–4 shade, 5 edge-only)"
            : "Tone grid not available — re-ingest";
        } else if (portraitIngestUnderlay === "scan") {
          hint.textContent = portraitIngestPreview.intermediate_png_b64
            ? `Intermediate: ${portraitIngestPreview.scan_mode || "auto"} (shown under vectors)`
            : "Scan intermediate unavailable";
        }
      }
    };
  }

  const run = (opts) =>
    renderPortraitJob(opts).catch((e) => {
      if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(e);
      console.error(e);
    });
  root.querySelector("#portrait-ingest-btn").onclick = () =>
    runPortraitIngest({ forceReingest: true }).catch((e) => {
      if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(e);
      console.error(e);
    });
  root.querySelector("#portrait-go").onclick = () => run({ reuse: !!portraitIngestId });
  root.querySelector("#portrait-apply").onclick = () => run({ reuse: true });
  root.querySelector("#portrait-reingest").onclick = () =>
    runPortraitIngest({ forceReingest: true }).then(() => run({ forceReingest: false, reuse: true })).catch((e) => {
      if (portraitStatsEl) portraitStatsEl.textContent = portraitNetworkErrorMessage(e);
      console.error(e);
    });
}

async function runPortraitIngest(opts = {}) {
  const root = portraitContentRoot();
  state.paper = root.querySelector("#paper")?.value || state.paper;
  state.quality = root.querySelector("#quality")?.value || state.quality;
  portraitPaperId = root.querySelector("#paper-color")?.value || portraitPaperId;
  portraitAutoFrame = !!root.querySelector("#auto-frame")?.checked;
  if (root.querySelector("#hatch-shading")) portraitHatchEnabled = !!root.querySelector("#hatch-shading").checked;
  if (portraitStatsEl) portraitStatsEl.textContent = "Ingesting (no style)…";
  const t0 = performance.now();
  let data;
  const cropJson = portraitCrop ? JSON.stringify(portraitCrop) : null;
  // hatch_size 0 = off; omit otherwise so quality defaults apply
  const knobs = portraitHatchEnabled ? {} : { hatch_size: 0 };
  if (portraitEnsemble === true) knobs.ensemble = true;
  if (portraitEnsemble === false) knobs.ensemble = false;
  knobs.scan_mode = root.querySelector("#scan-mode")?.value || portraitScanMode;
  knobs.contour_simplify = Number(root.querySelector("#path-simplify")?.value || portraitPathSimplify);
  knobs.line_source = root.querySelector("#line-source")?.value || portraitLineSource;
  const aiEl = root.querySelector("#ai-review");
  if (aiEl) portraitAiReview = !!aiEl.checked;
  knobs.ai_review = portraitAiReview;
  portraitScanMode = knobs.scan_mode;
  portraitPathSimplify = knobs.contour_simplify;
  portraitLineSource = knobs.line_source;
  if (portraitFile) {
    const uploadFile = await downscalePortraitForUpload(portraitFile, 1280);
    const fd = new FormData();
    fd.append("image_mode", portraitImageMode);
    fd.append("quality", state.quality);
    fd.append("paper", state.paper);
    fd.append("auto_frame", portraitAutoFrame ? "true" : "false");
    if (opts.forceReingest || portraitForceReingest) fd.append("force_reingest", "true");
    if (cropJson) fd.append("crop", cropJson);
    fd.append("include_preview_png", "true");
    if (!portraitHatchEnabled) fd.append("hatch_size", "0");
    if (portraitEnsemble === true) fd.append("ensemble", "true");
    if (portraitEnsemble === false) fd.append("ensemble", "false");
    fd.append("scan_mode", knobs.scan_mode);
    fd.append("contour_simplify", String(knobs.contour_simplify));
    fd.append("line_source", knobs.line_source);
    if (knobs.ai_review) fd.append("ai_review", "true");
    fd.append("file", uploadFile, uploadFile.name || "portrait.jpg");
    data = await api("/api/portrait/ingest/upload", { method: "POST", body: fd });
  } else {
    data = await api("/api/portrait/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_mode: portraitImageMode,
        quality: state.quality,
        paper: state.paper,
        auto_frame: portraitAutoFrame,
        force_reingest: !!(opts.forceReingest || portraitForceReingest),
        crop: portraitCrop || undefined,
        include_preview_png: true,
        ...knobs,
      }),
    });
  }
  portraitForceReingest = false;
  portraitIngestPreview = data;
  portraitIngestId = data.ingest_id || null;
  if (data.crop) portraitCrop = data.crop;
  drawPortraitSourcePreview(portraitFile, data.crop);
  drawPortraitIngestPreview(data);
  const wall = ((performance.now() - t0) / 1000).toFixed(2);
  const timing = data.timing_s || {};
  const meta = data.meta || {};
  if (portraitStatsEl) {
    portraitStatsEl.textContent =
      `Ingest ready · edges ${data.edge_count} · hatch ${data.hatch_count ?? 0} · regions ${data.region_count} · wall ${wall}s` +
      (timing.total != null ? ` · trace ${timing.total}s` : "") +
      (data.cache_hit ? " · cache" : "") +
      (portraitHatchEnabled ? "" : " · hatch off") +
      (meta.ensemble?.enabled ? " · ensemble 5+1" : "") +
      (meta.line_source ? ` · ${meta.line_source}` : "") +
      (data.ai_scene || meta.ai_scene ? " · ai-scene" : "") +
      (data.scan_mode || meta.scan_mode ? ` · scan ${data.scan_mode || meta.scan_mode}` : "") +
      ` · id ${portraitIngestId || "?"}`;
  }
  const hint = document.getElementById("scan-mode-hint");
  if (hint) {
    const toneN = meta.tone_grid?.code_hist
      ? Object.entries(meta.tone_grid.code_hist)
          .filter(([c, n]) => Number(c) >= 1 && Number(n) > 0)
          .map(([c, n]) => `${c}:${n}`)
          .join(" ")
      : "";
    if (portraitIngestUnderlay === "tone" && data.tone_heatmap_png_b64) {
      hint.textContent = `Tone grid${toneN ? ` · ${toneN}` : ""}`;
    } else {
      hint.textContent = data.intermediate_png_b64
        ? `Intermediate: ${data.scan_mode || meta.scan_mode || "auto"} (shown under vectors)`
          + (toneN ? ` · tone ${toneN}` : "")
        : (toneN ? `Tone codes ${toneN}` : "");
    }
  }
  const applyBtn = root.querySelector("#portrait-apply");
  if (applyBtn) applyBtn.disabled = !portraitIngestId;
  return data;
}

function collectPortraitExtra(root, { reuse = false, forceReingest = false } = {}) {
  portraitPaperId = root.querySelector("#paper-color")?.value || portraitPaperId;
  portraitLineType = root.querySelector("#line-type")?.value || portraitLineType;
  if (root.querySelector("#hatch-shading")) portraitHatchEnabled = !!root.querySelector("#hatch-shading").checked;
  const ensEl = root.querySelector("#ensemble-5plus1");
  if (ensEl) portraitEnsemble = !!ensEl.checked;
  const extra = {
    image_mode: portraitImageMode,
    paper_id: portraitPaperId,
    line_type: portraitLineType,
    line_spacing_mm: Number(root.querySelector("#line-spacing")?.value || 1.2),
    pattern_period_mm: Number(root.querySelector("#pattern-period")?.value || 2),
    pattern_amplitude_mm: Number(root.querySelector("#pattern-amp")?.value || 0.8),
    dash_mm: Number(root.querySelector("#dash-mm")?.value || 2),
    gap_mm: Number(root.querySelector("#gap-mm")?.value || 1.2),
    ornament_target: "all",
    auto_frame: portraitAutoFrame,
  };
  if (!portraitHatchEnabled) extra.hatch_size = 0;
  if (portraitEnsemble === true) extra.ensemble = true;
  if (portraitEnsemble === false) extra.ensemble = false;
  const scanSel = root.querySelector("#scan-mode");
  if (scanSel) portraitScanMode = scanSel.value;
  const simpSel = root.querySelector("#path-simplify");
  if (simpSel) portraitPathSimplify = Number(simpSel.value) || 2;
  extra.scan_mode = portraitScanMode;
  extra.contour_simplify = portraitPathSimplify;
  const lineSrcSel = root.querySelector("#line-source");
  if (lineSrcSel) portraitLineSource = lineSrcSel.value;
  extra.line_source = portraitLineSource || "auto";
  const aiEl = root.querySelector("#ai-review");
  if (aiEl) portraitAiReview = !!aiEl.checked;
  if (portraitAiReview) extra.ai_review = true;
  if (portraitCrop) extra.crop = portraitCrop;
  if (portraitPenMap) extra.pen_map = portraitPenMap;
  if (reuse && portraitIngestId && !forceReingest && !portraitForceReingest) {
    extra.reuse_ingest = true;
    extra.ingest_id = portraitIngestId;
  }
  if (forceReingest || portraitForceReingest) {
    extra.force_reingest = true;
  }
  return extra;
}

async function renderPortraitJob(opts = {}) {
  const root = portraitContentRoot();
  const list = styles.filter((s) => s.category === "portrait");
  ensurePortraitStyleSelected(list);
  state.paper = root.querySelector("#paper")?.value || state.paper;
  state.quality = root.querySelector("#quality")?.value || state.quality;
  state.seed = Number(root.querySelector("#seed")?.value || state.seed);
  state.density = Number(root.querySelector("#density")?.value || state.density);
  selectedPaletteId = root.querySelector("#palette")?.value || selectedPaletteId;
  const extra = collectPortraitExtra(root, opts);
  if (portraitStatsEl) {
    portraitStatsEl.textContent = extra.reuse_ingest ? "Restyling (cached ingest)…" : "Vectorizing portrait…";
  }
  const t0 = performance.now();
  let data;
  try {
    if (portraitFile) {
      if (portraitStatsEl && !extra.reuse_ingest) portraitStatsEl.textContent = "Preparing image…";
      const uploadFile = await downscalePortraitForUpload(portraitFile, 1280);
      if (portraitStatsEl) {
        portraitStatsEl.textContent = extra.reuse_ingest ? "Restyling…" : "Ingest + vectorize…";
      }
      const fd = new FormData();
      fd.append("style_id", selectedStyle);
      fd.append("app_name", "portraitbot");
      fd.append("palette_id", selectedPaletteId);
      fd.append("quality", state.quality);
      fd.append("paper", state.paper);
      fd.append("seed", String(state.seed));
      fd.append("density", String(state.density));
      fd.append("pen_up_speed_mm_s", String(state.pen_up_speed_mm_s));
      fd.append("pen_down_speed_mm_s", String(state.pen_down_speed_mm_s));
      fd.append("params_extra", JSON.stringify(extra));
      fd.append("image_mode", portraitImageMode);
      fd.append("paper_id", portraitPaperId);
      if (extra.reuse_ingest) fd.append("reuse_ingest", "true");
      if (extra.ingest_id) fd.append("ingest_id", extra.ingest_id);
      if (extra.force_reingest) fd.append("force_reingest", "true");
      if (extra.crop) fd.append("crop", JSON.stringify(extra.crop));
      fd.append("file", uploadFile, uploadFile.name || "portrait.jpg");
      data = await api("/api/render/upload", { method: "POST", body: fd });
    } else {
      data = await api("/api/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app: "portraitbot",
          style_id: selectedStyle,
          palette_id: selectedPaletteId,
          paper: state.paper,
          quality: state.quality,
          seed: state.seed,
          density: state.density,
          pen_up_speed_mm_s: state.pen_up_speed_mm_s,
          pen_down_speed_mm_s: state.pen_down_speed_mm_s,
          paper_id: portraitPaperId,
          reuse_ingest: !!extra.reuse_ingest,
          ingest_id: extra.ingest_id,
          force_reingest: !!extra.force_reingest,
          crop: extra.crop,
          params_extra: extra,
        }),
      });
    }
  } catch (e) {
    throw new Error(portraitNetworkErrorMessage(e));
  }
  portraitForceReingest = false;
  const ingestId =
    data.emulator?.settings?.ingest_id ||
    data.layers?.meta?.ingest_id ||
    data.job?.params?.ingest_id;
  if (ingestId) portraitIngestId = ingestId;
  currentApp = "portraitbot";
  loadResult(data, { autoplay: false });
  // Refresh ingest pane from cache so Source|Ingest|Vector stay aligned
  if (portraitIngestId && (!portraitIngestPreview || portraitIngestPreview.ingest_id !== portraitIngestId)) {
    try {
      const prev = await api(`/api/portrait/ingest/${portraitIngestId}`);
      portraitIngestPreview = prev;
      if (prev.crop) portraitCrop = prev.crop;
      drawPortraitSourcePreview(portraitFile, prev.crop);
      drawPortraitIngestPreview(prev);
    } catch (_) {
      /* preview optional after vectorize */
    }
  }
  const wall = ((performance.now() - t0) / 1000).toFixed(2);
  const budget = data.layers?.budget || data.emulator?.budget;
  const cacheHit = data.emulator?.settings?.ingest_cache_hit;
  if (portraitStatsEl) {
    const budgetLabel = budget?.label || `passes ${data.layers?.pass_count ?? "?"}`;
    const warn = budget?.over_budget ? " · over budget" : "";
    portraitStatsEl.textContent =
      `Ready · ${selectedStyle} · ${portraitImageMode} · wall ${wall}s · ${budgetLabel}${warn}` +
      (cacheHit ? " · cache hit" : " · ingest");
    if (budget?.over_budget) portraitStatsEl.style.color = "#b45309";
    else portraitStatsEl.style.color = "";
  }
}

function currentPalette() {
  return palettes.find((p) => p.id === selectedPaletteId) || palettes[0];
}

function paletteSelectHtml() {
  return `<select id="palette">${palettes.map((p) =>
    `<option value="${p.id}" ${p.id === selectedPaletteId ? "selected" : ""}>${p.id} — ${p.name}</option>`
  ).join("")}</select>`;
}

function penChipsHtml(palette) {
  if (!palette) return "";
  return `<div class="pen-chips">${palette.pens.map((pen) =>
    `<span class="pen-chip" title="${pen.profile?.nib_type || ""} ${pen.profile?.width_mm || ""}mm">
      <span class="swatch" style="background:${pen.color_hex}"></span>
      ${pen.id}
    </span>`
  ).join("")}</div>`;
}

function commonDevOpts() {
  return `
    <h4>Render settings</h4>
    <div class="grid-2">
      ${field("Paper", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
      ${field("Quality", `<select id="quality"><option value="booth-fast">booth-fast</option><option value="booth-balanced">booth-balanced</option><option value="studio-hq">studio-hq</option></select>`)}
    </div>
    <div class="grid-2">
      ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
      ${field("Density", `<input id="density" type="number" step="0.1" value="${state.density}" />`)}
    </div>
    <div class="grid-2">
      ${field("Pen-up mm/s", `<input id="pen_up" type="number" value="${state.pen_up_speed_mm_s}" />`)}
      ${field("Pen-down mm/s", `<input id="pen_down" type="number" value="${state.pen_down_speed_mm_s}" />`)}
    </div>
    <h4>Palette</h4>
    ${field("Established palette", paletteSelectHtml())}
    ${penChipsHtml(currentPalette())}
    ${field("Upload image (optional)", `<input id="photo" type="file" accept="image/*" />`)}
    ${field("Import settings JSON", `<input id="import-settings" type="file" accept="application/json,.json" />`)}
  `;
}

function applyCommonDefaults() {
  const paper = controls.querySelector("#paper");
  const quality = controls.querySelector("#quality");
  if (paper) paper.value = state.paper;
  if (quality) quality.value = state.quality;
  const palette = controls.querySelector("#palette");
  if (palette) {
    palette.onchange = () => {
      selectedPaletteId = palette.value;
      renderControls();
    };
  }
  const importer = controls.querySelector("#import-settings");
  if (importer) {
    importer.onchange = async () => {
      const file = importer.files[0];
      if (!file) return;
      const text = await file.text();
      const obj = JSON.parse(text);
      Object.assign(state, {
        paper: obj.paper || state.paper,
        quality: obj.quality || state.quality,
        seed: obj.seed ?? state.seed,
        density: obj.density ?? state.density,
        pen_up_speed_mm_s: obj.pen_up_speed_mm_s ?? state.pen_up_speed_mm_s,
        pen_down_speed_mm_s: obj.pen_down_speed_mm_s ?? state.pen_down_speed_mm_s,
        rpm: obj.rpm ?? state.rpm,
      });
      if (obj.palette_id) selectedPaletteId = obj.palette_id;
      if (obj.style_id) selectedStyle = obj.style_id;
      renderControls();
      statsEl.textContent = "Imported settings JSON";
    };
  }
}

function styleButtons(list) {
  return `<div class="style-grid">${list.map((s) =>
    `<button type="button" data-style="${s.id}" class="${s.id === selectedStyle ? "selected" : ""}">
      <strong>${s.name}</strong><div class="muted">${s.id}</div>
    </button>`
  ).join("")}</div>`;
}

function bindStyleGrid() {
  controls.querySelectorAll("[data-style]").forEach((btn) => {
    btn.onclick = () => {
      selectedStyle = btn.dataset.style;
      renderControls();
    };
  });
}

async function renderWithSettings({ appName, busyText = "Rendering…", extraFormData }) {
  syncStateFromForm();
  const file = controls.querySelector("#photo")?.files?.[0];
  statsEl.textContent = busyText;
  let data;
  if (file) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("style_id", selectedStyle);
    fd.append("app_name", appName);
    fd.append("palette_id", selectedPaletteId);
    fd.append("quality", state.quality);
    fd.append("paper", state.paper);
    fd.append("seed", String(state.seed));
    fd.append("density", String(state.density));
    fd.append("pen_up_speed_mm_s", String(state.pen_up_speed_mm_s));
    fd.append("pen_down_speed_mm_s", String(state.pen_down_speed_mm_s));
    if (labIngestId) {
      fd.append("ingest_id", labIngestId);
      fd.append("reuse_ingest", "true");
    }
    if (extraFormData) Object.entries(extraFormData).forEach(([k, v]) => fd.append(k, v));
    data = await api("/api/render/upload", { method: "POST", body: fd });
  } else {
    const body = {
      app: appName,
      style_id: selectedStyle,
      palette_id: selectedPaletteId,
      paper: state.paper,
      quality: state.quality,
      seed: state.seed,
      density: state.density,
      pen_up_speed_mm_s: state.pen_up_speed_mm_s,
      pen_down_speed_mm_s: state.pen_down_speed_mm_s,
    };
    if (labIngestId) {
      body.ingest_id = labIngestId;
      body.reuse_ingest = true;
    }
    data = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  if (data.emulator?.settings?.ingest_id) labIngestId = data.emulator.settings.ingest_id;
  loadResult(data);
}

function renderGenArt() {
  const list = styles.filter((s) =>
    ["artistic", "pattern", "technical", "portrait"].includes(s.category)
  );
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "stipple";
  controls.innerHTML = `
    <h3>GenArtBot · Dev</h3>
    <p class="muted">Tune vectorization + multicolor layers. Optional photo ingest (linedraw) before Vectorize.</p>
    <h4>Style</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    <div class="row">
      <button type="button" id="genart-ingest">Ingest</button>
      <button class="primary" id="go">Vectorize</button>
    </div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  const photo = controls.querySelector("#photo");
  if (photo) {
    photo.onchange = () => {
      labIngestId = null;
      const f = photo.files?.[0] || null;
      if (f) drawLabSource(f);
    };
  }
  controls.querySelector("#genart-ingest").onclick = () =>
    runLabIngest().catch((e) => {
      statsEl.textContent = String(e.message || e);
      console.error(e);
    });
  controls.querySelector("#go").onclick = () =>
    renderWithSettings({ appName: "genartbot", busyText: "Vectorizing GenArt…" }).catch((e) => {
      statsEl.textContent = String(e.message || e);
      console.error(e);
    });
}

function letterContentRoot() {
  return document.getElementById("letter-content");
}

function lval(id, fallback = "") {
  const el = letterContentRoot()?.querySelector(`#${id}`);
  return el ? el.value : fallback;
}

function lnum(id, fallback = 0) {
  return Number(lval(id, fallback));
}

function activeLetterLayer() {
  return letterLayersState.find((l) => l.id === letterLayerTab) || letterLayersState[0];
}

function setLettersDownloads(enabled, jobId) {
  const svgBtn = document.getElementById("letters-dl-svg");
  const motionBtn = document.getElementById("letters-dl-motion");
  const packBtn = document.getElementById("letters-dl-pack");
  [svgBtn, motionBtn, packBtn].forEach((b) => { if (b) b.disabled = !enabled; });
  if (!svgBtn) return;
  svgBtn.onclick = () => {
    if (!jobId) return;
    const a = document.createElement("a");
    a.href = `/api/jobs/${jobId}/svg`;
    a.download = `botdraw-${jobId}-letter.svg`;
    a.click();
  };
  motionBtn.onclick = async () => {
    if (!jobId) return;
    downloadJson(`botdraw-${jobId}-motion.json`, await api(`/api/jobs/${jobId}/motion`));
  };
  packBtn.onclick = async () => {
    if (!jobId) return;
    downloadJson(`botdraw-${jobId}-pack.json`, await api(`/api/jobs/${jobId}/export`));
  };
}

const LETTER_PAPER_MM = {
  A5: [148, 210], A4: [210, 297], Letter: [216, 279], A3: [297, 420], Card: [105, 148],
};

function updatePaperFrame() {
  const paper = document.getElementById("letters-paper")?.value || "A5";
  const orientation = document.getElementById("letters-orientation")?.value || "portrait";
  const m = readMargins();
  const frame = document.getElementById("paper-frame");
  if (!frame) return;
  frame.dataset.orientation = orientation;
  frame.dataset.paper = paper;
  let [pw, ph] = LETTER_PAPER_MM[paper] || LETTER_PAPER_MM.A5;
  if (orientation === "landscape") [pw, ph] = [ph, pw];
  const canvas = document.getElementById("letters-emu");
  if (canvas) {
    const maxW = 740;
    const scale = maxW / pw;
    const tw = Math.round(pw * scale);
    const th = Math.round(ph * scale);
    if (canvas.width !== tw || canvas.height !== th) {
      canvas.width = tw;
      canvas.height = th;
      if (lastPayload) {
        lettersPlayer.load(lastPayload, { preserveVisibility: true });
        lettersPlayer.skipEnd();
        syncLineHandles();
      } else {
        lettersPlayer.drawFrame();
      }
    }
  }
  const limit = document.getElementById("print-limit");
  if (!limit) return;
  const scaleCss = 0.55;
  limit.style.top = `${12 + m.top * scaleCss}px`;
  limit.style.right = `${12 + m.right * scaleCss}px`;
  limit.style.bottom = `${12 + m.bottom * scaleCss}px`;
  limit.style.left = `${12 + m.left * scaleCss}px`;
}

function scheduleLetterVectorize() {
  clearTimeout(letterVectorizeTimer);
  letterVectorizeTimer = setTimeout(() => {
    vectorizeLetter({ quiet: true }).catch((e) => {
      lettersStatsEl.textContent = String(e);
      console.error(e);
    });
  }, 320);
}

function penOptionsHtml(selectedId) {
  const pal = currentPalette();
  if (!pal?.pens?.length) return `<option value="ink">ink</option>`;
  return pal.pens.map((p) => {
    const board = p.board_id || `BD-${(p.id || "").toUpperCase()}`;
    const sel = p.id === selectedId ? "selected" : "";
    return `<option value="${p.id}" ${sel}>${board} · ${p.name}</option>`;
  }).join("");
}

function fontOptionsHtml(selectedId) {
  const list = letterFonts.length
    ? letterFonts
    : [{ id: "simplex", label: "Hershey Sans (stroke)" }];
  return list.map((f) =>
    `<option value="${f.id}" ${f.id === selectedId ? "selected" : ""}>${f.label || f.id}</option>`
  ).join("");
}

function penCardHtml(penId) {
  const pen = currentPalette()?.pens?.find((p) => p.id === penId);
  if (!pen) return `<p class="muted">Select a pen.</p>`;
  const board = pen.board_id || `BD-${pen.id.toUpperCase()}`;
  return `
    <div class="pen-card">
      <span class="swatch" style="background:${pen.color_hex}"></span>
      <div>
        <div><strong>${pen.name}</strong> <span class="meta">${board}</span></div>
        <div class="meta">${pen.profile?.nib_type || "?"} · ${pen.profile?.width_mm ?? "?"}mm · opacity ${pen.profile?.opacity ?? 1}</div>
        <div class="meta">id ${pen.id} · sample board mapping pending</div>
      </div>
    </div>`;
}

function syncActiveLayerFromForm() {
  const layer = activeLetterLayer();
  if (!layer) return;
  ensureLineFields(layer);
  const specs = document.getElementById("letter-layer-specs");
  if (!specs) return;
  const g = (id) => specs.querySelector(`#${id}`);
  if (g("layer-name")) layer.name = g("layer-name").value;
  if (g("layer-draw-mode")) layer.draw_mode = g("layer-draw-mode").value;
  if (g("layer-pen")) layer.pen_id = g("layer-pen").value;
  if (g("layer-kind")) layer.kind = g("layer-kind").value;
  if ((layer.draw_mode || "text") === "line") {
    if (g("layer-placement")) layer.placement = g("layer-placement").value;
    if (g("layer-snap-target")) layer.snap.target_layer_id = g("layer-snap-target").value || null;
    if (g("layer-snap-span")) {
      const v = g("layer-snap-span").value;
      layer.snap.span_index = v === "" ? null : Number(v);
    }
    if (g("layer-snap-role")) layer.snap.role = g("layer-snap-role").value;
    if (g("line-x0")) layer.line.x0_mm = Number(g("line-x0").value || 0);
    if (g("line-y0")) layer.line.y0_mm = Number(g("line-y0").value || 0);
    if (g("line-x1")) layer.line.x1_mm = Number(g("line-x1").value || 0);
    if (g("line-y1")) layer.line.y1_mm = Number(g("line-y1").value || 0);
    if (g("line-style")) layer.line.style = g("line-style").value;
    if (g("line-dash")) layer.line.dash_mm = Number(g("line-dash").value || 2);
    if (g("line-gap")) layer.line.gap_mm = Number(g("line-gap").value || 1.2);
    if (g("line-width") && g("line-width").value !== "") layer.line.width_mm = Number(g("line-width").value);
    if (layer.placement === "snap") applySnapToLayer(layer);
  } else {
    if (g("layer-body")) layer.body = g("layer-body").value;
    if (g("layer-font")) layer.font_name = g("layer-font").value;
    if (g("layer-size")) layer.size_mm = Number(g("layer-size").value || 4.5);
    if (g("layer-lang")) layer.language = g("layer-lang").value;
    if (g("layer-translate")) layer.translate_from_en = !!g("layer-translate").checked;
    if (g("layer-ox")) layer.offset_x_mm = Number(g("layer-ox").value || 0);
    if (g("layer-oy")) layer.offset_y_mm = Number(g("layer-oy").value || 0);
    if (g("layer-tracking")) layer.tracking = Number(g("layer-tracking").value || 0.15);
    if (g("layer-humanize")) layer.humanize = Number(g("layer-humanize").value || 0.08);
    if (g("layer-leading-var")) layer.leading_variation = Number(g("layer-leading-var").value || 0);
    if (g("layer-angle")) {
      let a = Number(g("layer-angle").value || 0);
      a = Math.round(a / 0.05) * 0.05;
      layer.line_angle_deg = Math.max(-0.5, Math.min(0.5, a));
    }
  }
}

function layerEditorFieldsHtml(layer) {
  ensureLineFields(layer);
  const mode = layer.draw_mode || "text";
  const showTranslate = (layer.language || "en") !== "en";
  const modeToggle = `
    <div class="mode-toggle" id="draw-mode-toggle">
      <button type="button" data-mode="text" class="${mode === "text" ? "active" : ""}">Font</button>
      <button type="button" data-mode="line" class="${mode === "line" ? "active" : ""}">Line</button>
    </div>
    <input type="hidden" id="layer-draw-mode" value="${mode}" />`;
  const shared = `
      ${field("Layer name", `<input id="layer-name" value="${layer.name || ""}" />`)}
      ${modeToggle}
      ${field("Pen / marker", `<select id="layer-pen">${penOptionsHtml(layer.pen_id)}</select>`)}
      <div id="pen-card">${penCardHtml(layer.pen_id)}</div>
      ${field("Kind", `<select id="layer-kind">
          <option value="ink" ${layer.kind === "ink" ? "selected" : ""}>ink</option>
          <option value="highlight" ${layer.kind === "highlight" ? "selected" : ""}>highlight</option>
          <option value="accent" ${layer.kind === "accent" ? "selected" : ""}>accent</option>
          <option value="underline" ${layer.kind === "underline" ? "selected" : ""}>underline</option>
        </select>`)}`;
  if (mode === "line") {
    const dashed = (layer.line.style || "solid") === "dashed";
    return `
    <div class="spec-block layer-editor">
      ${shared}
      ${field("Placement", `<select id="layer-placement">
        <option value="freehand" ${layer.placement === "freehand" ? "selected" : ""}>Freehand</option>
        <option value="snap" ${layer.placement === "snap" ? "selected" : ""}>Snap to text</option>
      </select>`)}
      <div id="snap-fields" style="${layer.placement === "snap" ? "" : "display:none"}">
        ${field("Snap target layer", `<select id="layer-snap-target">${textLayerOptionsHtml(layer.snap.target_layer_id)}</select>`)}
        ${field("Snap span", `<select id="layer-snap-span">${spanOptionsHtml(layer.snap.target_layer_id, layer.snap.span_index)}</select>`)}
        ${field("Snap role", `<select id="layer-snap-role">
          <option value="underline" ${layer.snap.role === "underline" ? "selected" : ""}>underline</option>
          <option value="highlight" ${layer.snap.role === "highlight" ? "selected" : ""}>highlight</option>
        </select>`)}
      </div>
      <div class="grid-2">
        ${field("X0 mm", `<input id="line-x0" type="number" step="0.1" value="${layer.line.x0_mm}" />`)}
        ${field("Y0 mm", `<input id="line-y0" type="number" step="0.1" value="${layer.line.y0_mm}" />`)}
      </div>
      <div class="grid-2">
        ${field("X1 mm", `<input id="line-x1" type="number" step="0.1" value="${layer.line.x1_mm}" />`)}
        ${field("Y1 mm", `<input id="line-y1" type="number" step="0.1" value="${layer.line.y1_mm}" />`)}
      </div>
      <p class="muted">Drag endpoint handles on the emulator, or edit numbers.</p>
      ${field("Line style", `<select id="line-style">
        <option value="solid" ${!dashed ? "selected" : ""}>Continuous</option>
        <option value="dashed" ${dashed ? "selected" : ""}>Dashed</option>
      </select>`)}
      <div class="grid-2" id="dash-fields" style="${dashed ? "" : "display:none"}">
        ${field("Dash mm", `<input id="line-dash" type="number" step="0.1" min="0.2" value="${layer.line.dash_mm}" />`)}
        ${field("Gap mm", `<input id="line-gap" type="number" step="0.1" min="0.1" value="${layer.line.gap_mm}" />`)}
      </div>
      ${field("Width mm (optional)", `<input id="line-width" type="number" step="0.1" min="0" value="${layer.line.width_mm ?? ""}" placeholder="pen default" />`)}
      <div class="row" style="margin-top:0.55rem">
        <button type="button" id="letter-solo">Solo</button>
        <button type="button" id="letter-hide">Hide</button>
      </div>
    </div>`;
  }
  return `
    <div class="spec-block layer-editor">
      ${shared}
      ${field("Body", `<textarea id="layer-body" rows="5">${layer.body || ""}</textarea>`)}
      <div class="grid-2">
        ${field("Font", `<select id="layer-font">${fontOptionsHtml(layer.font_name)}</select>`)}
        ${field("Size mm", `<input id="layer-size" type="number" step="0.1" min="1" value="${layer.size_mm}" />`)}
      </div>
      <div class="grid-2">
        ${field("Language", `<select id="layer-lang">
          <option value="en" ${layer.language === "en" ? "selected" : ""}>en</option>
          <option value="hi" ${layer.language === "hi" ? "selected" : ""}>hi</option>
          <option value="pa" ${layer.language === "pa" ? "selected" : ""}>pa</option>
          <option value="ur" ${layer.language === "ur" ? "selected" : ""}>ur</option>
        </select>`)}
        ${field("Line angle °", `<input id="layer-angle" type="number" step="0.05" min="-0.5" max="0.5" value="${layer.line_angle_deg}" />`)}
      </div>
      <div class="chk-row" id="translate-row" style="${showTranslate ? "" : "display:none"}">
        <label><input id="layer-translate" type="checkbox" ${layer.translate_from_en ? "checked" : ""} /> Translate from English (AI)</label>
      </div>
      <p class="muted translate-note" id="translate-note" style="${showTranslate && layer.translate_from_en ? "" : "display:none"}">
        AI translation not processed yet — English source kept.
      </p>
      <div class="grid-2">
        ${field("Offset X mm", `<input id="layer-ox" type="number" step="0.5" value="${layer.offset_x_mm}" />`)}
        ${field("Offset Y mm", `<input id="layer-oy" type="number" step="0.5" value="${layer.offset_y_mm}" />`)}
      </div>
      <div class="grid-2">
        ${field("Tracking", `<input id="layer-tracking" type="number" step="0.05" value="${layer.tracking}" />`)}
        ${field("Humanize", `<input id="layer-humanize" type="number" step="0.01" min="0" max="1" value="${layer.humanize}" />`)}
      </div>
      ${field("Leading variation", `<input id="layer-leading-var" type="number" step="0.01" min="0" max="1" value="${layer.leading_variation}" />`)}
      <div class="row" style="margin-top:0.55rem">
        <button type="button" id="letter-solo">Solo</button>
        <button type="button" id="letter-hide">Hide</button>
      </div>
    </div>`;
}

function renderLetterLayerEditor() {
  if (!letterLayersState.length) {
    letterLayersState = defaultLetterLayers(LETTER_TYPE_DEFAULTS[letterType]?.body || "HELLO");
  }
  letterLayersState.forEach(ensureLineFields);
  if (!letterLayersState.find((l) => l.id === letterLayerTab)) {
    letterLayerTab = letterLayersState[0].id;
  }
  const tabs = document.getElementById("letter-layer-tabs");
  const specs = document.getElementById("letter-layer-specs");
  if (!tabs || !specs) return;
  const layer = activeLetterLayer();
  tabs.innerHTML = letterLayersState.map((l) =>
    `<button type="button" data-layer="${l.id}" class="${l.id === letterLayerTab ? "active" : ""}">${l.name || l.id}</button>`
  ).join("");
  specs.innerHTML = layerEditorFieldsHtml(layer);

  tabs.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      syncActiveLayerFromForm();
      letterLayerTab = btn.dataset.layer;
      renderLetterLayerEditor();
      syncLineHandles();
    };
  });

  specs.querySelectorAll("#draw-mode-toggle button").forEach((btn) => {
    btn.onclick = () => {
      syncActiveLayerFromForm();
      layer.draw_mode = btn.dataset.mode;
      if (layer.draw_mode === "line") {
        layer.kind = layer.kind === "ink" ? "underline" : layer.kind;
        layer.placement = "snap";
        const t = letterLayersState.find((l) => l.id !== layer.id && (l.draw_mode || "text") === "text")
          || letterLayersState.find((l) => (l.draw_mode || "text") === "text");
        layer.snap.target_layer_id = t?.id || null;
        if (layer.snap.span_index == null) layer.snap.span_index = 0;
        applySnapToLayer(layer);
      }
      renderLetterLayerEditor();
      scheduleLetterVectorize();
    };
  });

  const onEdit = () => {
    const prevMode = layer.draw_mode;
    const prevPlacement = layer.placement;
    syncActiveLayerFromForm();
    const mode = specs.querySelector("#layer-draw-mode")?.value || layer.draw_mode;
    const place = specs.querySelector("#layer-placement")?.value;
    const style = specs.querySelector("#line-style")?.value;
    const snapBox = specs.querySelector("#snap-fields");
    const dashBox = specs.querySelector("#dash-fields");
    if (snapBox && place) snapBox.style.display = place === "snap" ? "" : "none";
    if (dashBox && style) dashBox.style.display = style === "dashed" ? "" : "none";
    const lang = specs.querySelector("#layer-lang")?.value || "en";
    const tr = specs.querySelector("#translate-row");
    const note = specs.querySelector("#translate-note");
    const trCb = specs.querySelector("#layer-translate");
    if (tr) tr.style.display = lang === "en" ? "none" : "";
    if (note) note.style.display = lang !== "en" && trCb?.checked ? "" : "none";
    const penSel = specs.querySelector("#layer-pen");
    if (penSel) {
      const card = specs.querySelector("#pen-card");
      if (card) card.innerHTML = penCardHtml(penSel.value);
    }
    // Refresh span options when target changes
    const targetSel = specs.querySelector("#layer-snap-target");
    const spanSel = specs.querySelector("#layer-snap-span");
    if (targetSel && spanSel && targetSel.value !== (layer.snap.target_layer_id || "")) {
      // already synced
    }
    if (targetSel && spanSel) {
      const html = spanOptionsHtml(targetSel.value, layer.snap.span_index);
      if (spanSel.innerHTML !== html) {
        const cur = spanSel.value;
        spanSel.innerHTML = html;
        if ([...spanSel.options].some((o) => o.value === cur)) spanSel.value = cur;
      }
    }
    if (layer.placement === "snap") {
      applySnapToLayer(layer);
      if (specs.querySelector("#line-x0")) {
        specs.querySelector("#line-x0").value = layer.line.x0_mm.toFixed(2);
        specs.querySelector("#line-y0").value = layer.line.y0_mm.toFixed(2);
        specs.querySelector("#line-x1").value = layer.line.x1_mm.toFixed(2);
        specs.querySelector("#line-y1").value = layer.line.y1_mm.toFixed(2);
      }
    }
    syncLineHandles();
    scheduleLetterVectorize();
  };
  specs.querySelectorAll("input, select, textarea").forEach((el) => {
    el.addEventListener("input", onEdit);
    el.addEventListener("change", onEdit);
  });
  specs.querySelector("#letter-solo")?.addEventListener("click", () => {
    lettersPlayer.soloPass(layer.id);
  });
  specs.querySelector("#letter-hide")?.addEventListener("click", () => {
    const hidden = lettersPlayer.hiddenPassIds.has(layer.id);
    lettersPlayer.setPassVisible(layer.id, hidden);
  });
  syncLineHandles();
}

function draftMetaHtml() {
  if (!selectedPaletteId || selectedPaletteId === "default-6") {
    selectedPaletteId = "wedding-highlight";
  }
  const def = LETTER_TYPE_DEFAULTS[letterType] || LETTER_TYPE_DEFAULTS.personal;
  return `
    <h4>Draft meta</h4>
    <p class="muted">Used for AI draft only. Letter text lives on layers above.</p>
    ${field("Names", `<input id="names" value="${def.names}" />`)}
    <div class="grid-2">
      ${field("Mood", `<input id="mood" value="${def.mood}" />`)}
      ${field("Seed", `<input id="seed" type="number" value="7" />`)}
    </div>
    ${field("Era", `<select id="era"><option>golden</option><option>70s</option><option selected>90s</option><option>2000s</option><option>contemporary</option></select>`)}
    ${field("Facts", `<textarea id="facts" style="min-height:56px">${def.facts}</textarea>`)}
    ${field("Guest quote", `<textarea id="quote" style="min-height:48px" placeholder="Optional line"></textarea>`)}
    <div class="chk-row">
      <label><input id="use_llm" type="checkbox" /> Local AI draft</label>
    </div>
    <h4>Palette</h4>
    ${field("Palette", paletteSelectHtml())}
    <div class="row"><button class="primary" id="go">Vectorize</button></div>
  `;
}

function letterEditorShellHtml() {
  const def = LETTER_TYPE_DEFAULTS[letterType] || LETTER_TYPE_DEFAULTS.personal;
  return `
    <h3>${def.title}</h3>
    <p class="muted">Layers drive text passes · paper preview on the right.</p>
    <div class="layers-head">
      <div>
        <h4>Layers</h4>
        <p class="muted">Font or line · pen · snap</p>
      </div>
      <div class="layer-actions">
        <button type="button" id="letter-layer-add" title="Add text layer (Shift: line)">+</button>
        <button type="button" id="letter-layer-remove" title="Remove layer">−</button>
      </div>
    </div>
    <div class="layer-tabs" id="letter-layer-tabs"></div>
    <div class="layer-specs" id="letter-layer-specs"></div>
    ${draftMetaHtml()}
  `;
}

function bindLetterTypeRail() {
  document.querySelectorAll("#letter-types button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.type === letterType);
    btn.onclick = () => {
      syncActiveLayerFromForm();
      letterType = btn.dataset.type;
      const def = LETTER_TYPE_DEFAULTS[letterType];
      letterLayersState = defaultLetterLayers(def?.body || "HELLO");
      letterLayerTab = letterLayersState[0].id;
      renderLetters();
    };
  });
}

function bindLayerChrome() {
  const addBtn = document.getElementById("letter-layer-add");
  const removeBtn = document.getElementById("letter-layer-remove");
  if (!addBtn || !removeBtn) return;
  addBtn.onclick = (ev) => {
    syncActiveLayerFromForm();
    const pal = currentPalette();
    const pens = pal?.pens || [];
    const nextPen = pens[letterLayersState.length % Math.max(1, pens.length)] || pens[0];
    const id = `layer-${Date.now().toString(36)}`;
    const addLine = !!ev.shiftKey || nextPen?.profile?.nib_type === "highlighter";
    const textTarget = letterLayersState.find((l) => (l.draw_mode || "text") === "text");
    if (addLine) {
      const layer = ensureLineFields({
        id,
        name: nextPen?.profile?.nib_type === "highlighter" ? "Highlight" : `Line ${letterLayersState.length}`,
        body: "",
        font_name: "simplex",
        size_mm: 4.5,
        pen_id: nextPen?.id || "ink",
        language: "en",
        translate_from_en: false,
        offset_x_mm: 0,
        offset_y_mm: 0,
        kind: nextPen?.profile?.nib_type === "highlighter" ? "highlight" : "underline",
        tracking: 0.15,
        humanize: 0.08,
        highlight_words: [],
        draw_mode: "line",
        leading_variation: 0.12,
        line_angle_deg: 0,
        placement: textTarget ? "snap" : "freehand",
        snap: {
          target_layer_id: textTarget?.id || null,
          span_index: 0,
          role: nextPen?.profile?.nib_type === "highlighter" ? "highlight" : "underline",
        },
        line: {
          x0_mm: 20, y0_mm: 40, x1_mm: 120, y1_mm: 40,
          style: "solid", dash_mm: 2, gap_mm: 1.2, width_mm: null,
        },
      });
      applySnapToLayer(layer);
      letterLayersState.push(layer);
    } else {
      letterLayersState.push(ensureLineFields({
        id,
        name: `Ink ${letterLayersState.length + 1}`,
        body: letterLayersState[0]?.body || "HELLO",
        font_name: "simplex",
        size_mm: 4.5,
        pen_id: nextPen?.id || "ink",
        language: "en",
        translate_from_en: false,
        offset_x_mm: 0,
        offset_y_mm: 0,
        kind: "ink",
        tracking: 0.15,
        humanize: 0.08,
        highlight_words: [],
        draw_mode: "text",
        leading_variation: 0.12,
        line_angle_deg: 0,
        placement: "freehand",
      }));
    }
    letterLayerTab = id;
    renderLetterLayerEditor();
    scheduleLetterVectorize();
  };
  removeBtn.onclick = () => {
    if (letterLayersState.length <= 1) return;
    syncActiveLayerFromForm();
    letterLayersState = letterLayersState.filter((l) => l.id !== letterLayerTab);
    letterLayerTab = letterLayersState[0].id;
    renderLetterLayerEditor();
    scheduleLetterVectorize();
  };
}

async function vectorizeLetter(opts = {}) {
  const quiet = !!opts.quiet;
  syncActiveLayerFromForm();
  const root = letterContentRoot();
  selectedPaletteId = lval("palette", selectedPaletteId);
  const useLlm = !!root?.querySelector("#use_llm")?.checked;
  const hasBody = letterLayersState.some((l) => (l.body || "").trim());
  if (!quiet) {
    lettersStatsEl.textContent = hasBody
      ? "Vectorizing…"
      : useLlm
        ? "Drafting with Ollama…"
        : "Template draft + vectorize…";
  }
  const t0 = performance.now();
  const data = await api("/api/letters/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      letter_type: letterType,
      names: lval("names"),
      language: letterLayersState[0]?.language || "en",
      era: lval("era"),
      mood: lval("mood"),
      facts: lval("facts"),
      guest_quote: lval("quote") || null,
      body: letterLayersState[0]?.body || null,
      use_llm: useLlm,
      highlight: false,
      optimize: false,
      palette_id: selectedPaletteId,
      seed: lnum("seed", 7),
      paper: document.getElementById("letters-paper").value,
      orientation: document.getElementById("letters-orientation").value,
      margins: readMargins(),
      font_name: letterLayersState[0]?.font_name || "simplex",
      layers: letterLayersState,
    }),
  });
  lastJob = data.job;
  lastPayload = data.emulator;
  lastLayers = data.layers || data.emulator?.layers || null;
  lastSettings = data.settings;
  letterLayerSpans = data.settings?.layer_spans || {};
  for (const meta of (data.settings?.letter_layers || [])) {
    if (meta.draw_mode !== "line" || !meta.line) continue;
    const L = letterLayersState.find((x) => x.id === meta.id);
    if (!L) continue;
    ensureLineFields(L);
    Object.assign(L.line, meta.line);
  }
  lettersPlayer.load(lastPayload, { preserveVisibility: true });
  lettersPlayer.skipEnd();
  // Refresh snap span options in-place (avoid full re-render / focus loss).
  const specs = document.getElementById("letter-layer-specs");
  const targetSel = specs?.querySelector("#layer-snap-target");
  const spanSel = specs?.querySelector("#layer-snap-span");
  if (targetSel && spanSel) {
    const cur = spanSel.value;
    spanSel.innerHTML = spanOptionsHtml(targetSel.value, cur === "" ? null : Number(cur));
    if ([...spanSel.options].some((o) => o.value === cur)) spanSel.value = cur;
  }
  const layer = activeLetterLayer();
  if (layer && (layer.draw_mode || "text") === "line" && layer.placement === "snap") {
    applySnapToLayer(layer);
    if (specs?.querySelector("#line-x0")) {
      specs.querySelector("#line-x0").value = Number(layer.line.x0_mm).toFixed(2);
      specs.querySelector("#line-y0").value = Number(layer.line.y0_mm).toFixed(2);
      specs.querySelector("#line-x1").value = Number(layer.line.x1_mm).toFixed(2);
      specs.querySelector("#line-y1").value = Number(layer.line.y1_mm).toFixed(2);
    }
  }
  syncLineHandles();
  const zl = document.getElementById("letters-zoom-label");
  if (zl) zl.textContent = `${lettersPlayer.zoom.toFixed(2)}×`;
  setLettersDownloads(true, lastJob?.id);
  const timing = data.settings?.timing_s || {};
  const src = data.draft?.source || "?";
  const wall = ((performance.now() - t0) / 1000).toFixed(2);
  const missing = (data.settings?.missing_scripts || []).join(",") || "none";
  const tr = data.settings?.translate_pending
    ? " · AI translation pending"
    : "";
  lettersStatsEl.textContent =
    `Ready · ${src} · draft ${timing.draft ?? "?"}s · vector ${timing.vectorize ?? "?"}s · wall ${wall}s · missing ${missing}${tr}`;
  return data;
}

async function renderLetters() {
  setShellForApp("lettersbot");
  if (!selectedPaletteId || selectedPaletteId === "default-6") selectedPaletteId = "wedding-highlight";
  if (!letterFonts.length) {
    try {
      const data = await api("/api/letters/fonts");
      letterFonts = data.fonts || [];
    } catch (_) {
      letterFonts = [{ id: "simplex", label: "Hershey Sans (stroke)" }];
    }
  }
  if (!letterLayersState.length) {
    letterLayersState = defaultLetterLayers(LETTER_TYPE_DEFAULTS[letterType]?.body || "HELLO");
    letterLayerTab = letterLayersState[0].id;
  }
  bindLetterTypeRail();
  updatePaperFrame();
  ["letters-paper", "letters-orientation"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => { updatePaperFrame(); scheduleLetterVectorize(); };
  });
  ["margin-left", "margin-top", "margin-right", "margin-bottom"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.oninput = () => { updatePaperFrame(); scheduleLetterVectorize(); };
    }
  });

  const root = letterContentRoot();
  root.innerHTML = letterEditorShellHtml();
  bindLayerChrome();
  lettersPlayer.enableInteraction();
  lettersPlayer.onLineEdit = (line, opts) => {
    const layer = activeLetterLayer();
    if (!layer || (layer.draw_mode || "text") !== "line") return;
    ensureLineFields(layer);
    layer.placement = "freehand";
    Object.assign(layer.line, line);
    const specs = document.getElementById("letter-layer-specs");
    if (specs?.querySelector("#line-x0")) {
      specs.querySelector("#line-x0").value = Number(line.x0_mm).toFixed(2);
      specs.querySelector("#line-y0").value = Number(line.y0_mm).toFixed(2);
      specs.querySelector("#line-x1").value = Number(line.x1_mm).toFixed(2);
      specs.querySelector("#line-y1").value = Number(line.y1_mm).toFixed(2);
      const place = specs.querySelector("#layer-placement");
      if (place) place.value = "freehand";
    }
    if (!opts?.live) scheduleLetterVectorize();
    else {
      clearTimeout(letterVectorizeTimer);
      letterVectorizeTimer = setTimeout(() => scheduleLetterVectorize(), 180);
    }
  };
  const setZoomUi = () => {
    const zl = document.getElementById("letters-zoom-label");
    if (zl) zl.textContent = `${lettersPlayer.zoom.toFixed(2)}×`;
  };
  lettersPlayer.onZoomChange = () => setZoomUi();
  const zin = document.getElementById("letters-zoom-in");
  const zout = document.getElementById("letters-zoom-out");
  const zfit = document.getElementById("letters-zoom-fit");
  if (zin) zin.onclick = () => { lettersPlayer.zoomBy(1.15); };
  if (zout) zout.onclick = () => { lettersPlayer.zoomBy(1 / 1.15); };
  if (zfit) zfit.onclick = () => { lettersPlayer.fitZoom(); };
  setZoomUi();
  root.querySelector("#palette").value = selectedPaletteId;
  root.querySelector("#palette").onchange = () => {
    selectedPaletteId = root.querySelector("#palette").value;
    renderLetterLayerEditor();
    scheduleLetterVectorize();
  };
  root.querySelector("#go").onclick = () => vectorizeLetter().catch((e) => {
    lettersStatsEl.textContent = String(e);
    console.error(e);
  });
  renderLetterLayerEditor();
  setLettersDownloads(!!lastJob?.id, lastJob?.id);
  scheduleLetterVectorize();
}

function renderRdlab() {
  const list = styles.filter((s) => ["backlog", "pattern"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = "spiral";
  controls.innerHTML = `
    <h3>R&amp;D Lab · Dev</h3>
    <p class="muted">Experimental motifs + rotating-base kinematics. Optional photo ingest.</p>
    <h4>Experiment</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    ${field("Turntable RPM", `<input id="rpm" type="number" step="0.5" value="${state.rpm}" />`)}
    <div class="row">
      <button type="button" id="rd-ingest">Ingest</button>
      <button class="primary" id="go">Run &amp; Inspect</button>
    </div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#rd-ingest").onclick = () =>
    runLabIngest().catch((e) => {
      statsEl.textContent = String(e.message || e);
      console.error(e);
    });
  controls.querySelector("#go").onclick = async () => {
    syncStateFromForm();
    const file = controls.querySelector("#photo")?.files?.[0];
    const fd = new FormData();
    fd.append("style_id", selectedStyle);
    fd.append("rpm", String(state.rpm));
    fd.append("seed", String(state.seed));
    fd.append("palette_id", selectedPaletteId);
    fd.append("quality", state.quality);
    fd.append("density", String(state.density));
    if (file) fd.append("file", file);
    if (labIngestId) {
      fd.append("ingest_id", labIngestId);
      fd.append("reuse_ingest", "true");
    }
    statsEl.textContent = "R&D render…";
    const data = await api("/api/rdlab/render", { method: "POST", body: fd });
    loadResult(data);
  };
}

function renderPalettes() {
  const palette = currentPalette();
  const pensHtml = (palette?.pens || []).map((pen, idx) => `
    <div class="pen-block" data-idx="${idx}">
      <div class="grid-2">
        ${field("id", `<input data-k="id" value="${pen.id}" />`)}
        ${field("name", `<input data-k="name" value="${pen.name}" />`)}
      </div>
      <div class="grid-2">
        ${field("color", `<input data-k="color_hex" type="color" value="${pen.color_hex}" />`)}
        ${field("width mm", `<input data-k="width_mm" type="number" step="0.1" value="${pen.profile?.width_mm ?? 0.5}" />`)}
      </div>
      <div class="grid-2">
        ${field("opacity", `<input data-k="opacity" type="number" step="0.05" min="0" max="1" value="${pen.profile?.opacity ?? 1}" />`)}
        ${field("nib", `<select data-k="nib_type">
          ${["fineliner","marker","brush","calligraphy","highlighter"].map((n) =>
            `<option ${((pen.profile?.nib_type) || "fineliner") === n ? "selected" : ""}>${n}</option>`
          ).join("")}
        </select>`)}
      </div>
    </div>
  `).join("");

  controls.innerHTML = `
    <h3>Pen Library</h3>
    <p class="muted">Customize pens and save palette sets for all bots.</p>
    ${field("Load palette", paletteSelectHtml())}
    ${penChipsHtml(palette)}
    ${field("New palette id", `<input id="new_id" value="${palette?.id || "custom"}-dev" />`)}
    ${field("Name", `<input id="new_name" value="${palette?.name || "Custom"} (edited)" />`)}
    ${field("Paper notes", `<input id="paper_notes" value="${palette?.paper_notes || ""}" />`)}
    <div class="pen-editor" id="pen-editor">${pensHtml}</div>
    <div class="row">
      <button class="primary" id="save-pal">Save palette JSON</button>
      <button id="export-pal-local">Download current JSON</button>
      <button id="add-pen">Add pen</button>
    </div>
  `;
  controls.querySelector("#palette").onchange = () => {
    selectedPaletteId = val("palette");
    renderControls();
  };
  controls.querySelector("#export-pal-local").onclick = () => {
    downloadJson(`${selectedPaletteId}.json`, currentPalette());
  };
  controls.querySelector("#add-pen").onclick = () => {
    const editor = controls.querySelector("#pen-editor");
    const idx = editor.querySelectorAll(".pen-block").length;
    editor.insertAdjacentHTML("beforeend", `
      <div class="pen-block" data-idx="${idx}">
        <div class="grid-2">
          ${field("id", `<input data-k="id" value="pen${idx + 1}" />`)}
          ${field("name", `<input data-k="name" value="Pen ${idx + 1}" />`)}
        </div>
        <div class="grid-2">
          ${field("color", `<input data-k="color_hex" type="color" value="#336699" />`)}
          ${field("width mm", `<input data-k="width_mm" type="number" step="0.1" value="0.5" />`)}
        </div>
        <div class="grid-2">
          ${field("opacity", `<input data-k="opacity" type="number" step="0.05" min="0" max="1" value="1" />`)}
          ${field("nib", `<select data-k="nib_type"><option>fineliner</option><option>marker</option><option>brush</option><option>calligraphy</option><option>highlighter</option></select>`)}
        </div>
      </div>`);
  };
  controls.querySelector("#save-pal").onclick = async () => {
    const pens = [...controls.querySelectorAll(".pen-block")].map((block) => {
      const get = (k) => block.querySelector(`[data-k="${k}"]`).value;
      return {
        id: get("id"),
        name: get("name"),
        color_hex: get("color_hex"),
        profile: {
          width_mm: Number(get("width_mm")),
          opacity: Number(get("opacity")),
          nib_type: get("nib_type"),
        },
      };
    });
    const body = {
      id: val("new_id"),
      name: val("new_name"),
      paper_notes: val("paper_notes"),
      pens,
    };
    const saved = await api("/api/palettes/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    palettes = await api("/api/palettes");
    selectedPaletteId = saved.id;
    downloadJson(`${saved.id}.json`, saved);
    statsEl.textContent = `Saved palette ${saved.id}`;
    renderControls();
  };
}

function fillPaperForm(stock) {
  if (!stock) return;
  const set = (id, v) => {
    const el = controls.querySelector(`#${id}`);
    if (el && v != null) el.value = v;
  };
  set("paper_id", stock.id);
  set("paper_name", stock.name);
  set("paper_color", stock.color_hex || "#f7f1e8");
  set("paper_finish", stock.finish || "matte");
  set("paper_size_hint", stock.size_hint || "A4");
  set("paper_notes", stock.notes || "");
  const swatch = controls.querySelector("#paper-swatch");
  if (swatch) swatch.style.background = stock.color_hex || "#f7f1e8";
}

function renderPaperLibrary() {
  if (!selectedPaperId && papers[0]) selectedPaperId = papers[0].id;
  const stock = papers.find((p) => p.id === selectedPaperId) || papers[0] || {
    id: "custom-paper",
    name: "Custom Paper",
    color_hex: "#f7f1e8",
    finish: "matte",
    size_hint: "A4",
    notes: "",
  };
  const chips = papers
    .map(
      (p) =>
        `<button type="button" data-paper="${p.id}" class="${p.id === (stock.id || selectedPaperId) ? "active" : ""}">${p.name}</button>`
    )
    .join("");
  controls.innerHTML = `
    <h3>Paper Library</h3>
    <p class="muted">Paper stocks with color + finish for Portrait and the emulator.</p>
    <div class="library-list" id="paper-list">${chips || '<span class="muted">No papers loaded</span>'}</div>
    <div class="paper-swatch" id="paper-swatch" style="background:${stock.color_hex || "#f7f1e8"}"></div>
    <div class="grid-2">
      ${field("id", `<input id="paper_id" value="${stock.id || ""}" />`)}
      ${field("name", `<input id="paper_name" value="${stock.name || ""}" />`)}
    </div>
    <div class="grid-2">
      ${field("color", `<input id="paper_color" type="color" value="${stock.color_hex || "#f7f1e8"}" />`)}
      ${field("finish", `<select id="paper_finish">
        ${["matte", "smooth", "toothy"].map((f) =>
          `<option value="${f}" ${(stock.finish || "matte") === f ? "selected" : ""}>${f}</option>`
        ).join("")}
      </select>`)}
    </div>
    <div class="grid-2">
      ${field("size hint", `<input id="paper_size_hint" value="${stock.size_hint || "A4"}" />`)}
      ${field("notes", `<input id="paper_notes" value="${stock.notes || ""}" />`)}
    </div>
    <div class="row">
      <button class="primary" id="save-paper">Save paper</button>
      <button id="delete-paper">Delete</button>
    </div>
  `;
  controls.querySelectorAll("[data-paper]").forEach((btn) => {
    btn.onclick = () => {
      selectedPaperId = btn.dataset.paper;
      fillPaperForm(papers.find((p) => p.id === selectedPaperId));
      controls.querySelectorAll("[data-paper]").forEach((b) =>
        b.classList.toggle("active", b.dataset.paper === selectedPaperId)
      );
    };
  });
  const colorEl = controls.querySelector("#paper_color");
  if (colorEl) {
    colorEl.oninput = () => {
      const swatch = controls.querySelector("#paper-swatch");
      if (swatch) swatch.style.background = colorEl.value;
    };
  }
  controls.querySelector("#save-paper").onclick = async () => {
    const body = {
      id: val("paper_id"),
      name: val("paper_name"),
      color_hex: val("paper_color", "#f7f1e8"),
      finish: val("paper_finish", "matte"),
      size_hint: val("paper_size_hint", "A4"),
      notes: val("paper_notes", ""),
    };
    try {
      const saved = await api("/api/papers/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      papers = await api("/api/papers");
      selectedPaperId = saved.id;
      statsEl.textContent = `Saved paper ${saved.id}`;
      await renderControls();
    } catch (e) {
      statsEl.textContent = String(e.message || e);
      console.error(e);
    }
  };
  controls.querySelector("#delete-paper").onclick = async () => {
    const id = val("paper_id");
    if (!id) return;
    try {
      await api(`/api/papers/${encodeURIComponent(id)}`, { method: "DELETE" });
      papers = await api("/api/papers");
      selectedPaperId = papers[0]?.id || "natural-cream";
      statsEl.textContent = `Deleted paper ${id}`;
      await renderControls();
    } catch (e) {
      const msg = String(e.message || e);
      statsEl.textContent = /403|preset|Cannot delete/i.test(msg)
        ? `Cannot delete preset paper: ${id}`
        : msg;
      console.error(e);
    }
  };
}

function refreshLinePreview(lineId) {
  const img = controls.querySelector("#line-preview");
  if (!img || !lineId) return;
  img.src = `/api/lines/${encodeURIComponent(lineId)}/preview.svg?t=${Date.now()}`;
}

function fillLineForm(stock) {
  if (!stock) return;
  const set = (id, v) => {
    const el = controls.querySelector(`#${id}`);
    if (el && v != null) el.value = v;
  };
  set("line_id", stock.id);
  set("line_name", stock.name);
  set("line_type", stock.line_type || "solid");
  set("line_spacing_mm", stock.line_spacing_mm ?? 1.2);
  set("pattern_period_mm", stock.pattern_period_mm ?? 2.0);
  set("pattern_amplitude_mm", stock.pattern_amplitude_mm ?? 0.8);
  set("dash_mm", stock.dash_mm ?? 2.0);
  set("gap_mm", stock.gap_mm ?? 1.2);
  set("ornament_target", stock.ornament_target || "all");
  set("line_notes", stock.notes || "");
  refreshLinePreview(stock.id);
}

function renderLineLibrary() {
  if (!selectedLineId && linesCatalog[0]) selectedLineId = linesCatalog[0].id;
  const stock = linesCatalog.find((l) => l.id === selectedLineId) || linesCatalog[0] || {
    id: "custom-line",
    name: "Custom Line",
    line_type: "solid",
    line_spacing_mm: 1.2,
    pattern_period_mm: 2.0,
    pattern_amplitude_mm: 0.8,
    dash_mm: 2.0,
    gap_mm: 1.2,
    ornament_target: "all",
    notes: "",
  };
  const chips = linesCatalog
    .map(
      (l) =>
        `<button type="button" data-line="${l.id}" class="${l.id === stock.id ? "active" : ""}">${l.name || l.id}</button>`
    )
    .join("");
  const ltOpts = PORTRAIT_LINE_TYPES.map(
    (t) => `<option value="${t}" ${(stock.line_type || "solid") === t ? "selected" : ""}>${t.replace(/_/g, " ")}</option>`
  ).join("");
  controls.innerHTML = `
    <h3>Line Library</h3>
    <p class="muted">Stroke ornament presets shared by Portrait and other bots.</p>
    <div class="library-list" id="line-list">${chips || '<span class="muted">No lines loaded</span>'}</div>
    <div class="line-preview-frame">
      <img id="line-preview" alt="Line preview" src="/api/lines/${encodeURIComponent(stock.id)}/preview.svg" />
    </div>
    <div class="grid-2">
      ${field("id", `<input id="line_id" value="${stock.id || ""}" />`)}
      ${field("name", `<input id="line_name" value="${stock.name || ""}" />`)}
    </div>
    <div class="grid-2">
      ${field("line type", `<select id="line_type">${ltOpts}</select>`)}
      ${field("ornament target", `<select id="ornament_target">
        ${["all", "edges", "fills"].map((t) =>
          `<option value="${t}" ${(stock.ornament_target || "all") === t ? "selected" : ""}>${t}</option>`
        ).join("")}
      </select>`)}
    </div>
    <div class="grid-2">
      ${field("spacing mm", `<input id="line_spacing_mm" type="number" step="0.1" value="${stock.line_spacing_mm ?? 1.2}" />`)}
      ${field("period mm", `<input id="pattern_period_mm" type="number" step="0.1" value="${stock.pattern_period_mm ?? 2}" />`)}
    </div>
    <div class="grid-2">
      ${field("amplitude mm", `<input id="pattern_amplitude_mm" type="number" step="0.1" value="${stock.pattern_amplitude_mm ?? 0.8}" />`)}
      ${field("dash mm", `<input id="dash_mm" type="number" step="0.1" value="${stock.dash_mm ?? 2}" />`)}
    </div>
    <div class="grid-2">
      ${field("gap mm", `<input id="gap_mm" type="number" step="0.1" value="${stock.gap_mm ?? 1.2}" />`)}
      ${field("notes", `<input id="line_notes" value="${stock.notes || ""}" />`)}
    </div>
    <div class="row">
      <button class="primary" id="save-line">Save line</button>
      <button id="delete-line">Delete</button>
    </div>
  `;
  controls.querySelectorAll("[data-line]").forEach((btn) => {
    btn.onclick = () => {
      selectedLineId = btn.dataset.line;
      fillLineForm(linesCatalog.find((l) => l.id === selectedLineId));
      controls.querySelectorAll("[data-line]").forEach((b) =>
        b.classList.toggle("active", b.dataset.line === selectedLineId)
      );
    };
  });
  controls.querySelector("#save-line").onclick = async () => {
    const body = {
      id: val("line_id"),
      name: val("line_name"),
      line_type: val("line_type", "solid"),
      line_spacing_mm: num("line_spacing_mm", 1.2),
      pattern_period_mm: num("pattern_period_mm", 2),
      pattern_amplitude_mm: num("pattern_amplitude_mm", 0.8),
      dash_mm: num("dash_mm", 2),
      gap_mm: num("gap_mm", 1.2),
      ornament_target: val("ornament_target", "all"),
      notes: val("line_notes", ""),
    };
    try {
      const saved = await api("/api/lines/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      linesCatalog = await api("/api/lines");
      selectedLineId = saved.id;
      statsEl.textContent = `Saved line ${saved.id}`;
      await renderControls();
      refreshLinePreview(saved.id);
    } catch (e) {
      statsEl.textContent = String(e.message || e);
      console.error(e);
    }
  };
  controls.querySelector("#delete-line").onclick = async () => {
    const id = val("line_id");
    if (!id) return;
    try {
      await api(`/api/lines/${encodeURIComponent(id)}`, { method: "DELETE" });
      linesCatalog = await api("/api/lines");
      selectedLineId = linesCatalog[0]?.id || "solid";
      statsEl.textContent = `Deleted line ${id}`;
      await renderControls();
    } catch (e) {
      const msg = String(e.message || e);
      statsEl.textContent = /403|preset|Cannot delete/i.test(msg)
        ? `Cannot delete preset line: ${id}`
        : msg;
      console.error(e);
    }
  };
}

function renderTools() {
  controls.innerHTML = `
    <h3>Tools</h3>
    <p class="muted">Audio / handwriting / plot stub / job reload.</p>
    ${field("Upload WAV", `<input id="wav" type="file" accept="audio/wav,audio/*" />`)}
    <div class="row"><button class="primary" id="audio">Audio → Vector</button></div>
    <div class="row"><button id="hw">Handwriting HELLO</button></div>
    ${field("Load job id", `<input id="jobid" placeholder="${lastJob?.id || ""}" />`)}
    <div class="row"><button id="load-job">Load job into lab</button></div>
    <div class="row"><button id="stub">AxiDraw stub on last/job</button></div>
  `;
  controls.querySelector("#audio").onclick = async () => {
    const file = controls.querySelector("#wav").files[0];
    statsEl.textContent = "Audio render…";
    let data;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      data = await api("/api/audio/upload", { method: "POST", body: fd });
    } else {
      data = await api("/api/audio/demo", { method: "POST" });
    }
    loadResult(data);
  };
  controls.querySelector("#hw").onclick = async () => {
    await api("/api/handwriting/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: "demo",
        glyphs: {
          H: [[[0,0],[0,10]],[[0,5],[6,5]],[[6,0],[6,10]]],
          E: [[[0,0],[0,10],[6,10]],[[0,5],[5,5]],[[0,0],[6,0]]],
          L: [[[0,0],[0,10],[6,10]]],
          O: [[[1,0],[5,0],[7,2],[7,8],[5,10],[1,10],[-1,8],[-1,2],[1,0]]],
        },
      }),
    });
    const data = await api("/api/handwriting/render?user_id=demo&text=HELLO", { method: "POST" });
    loadResult(data);
  };
  controls.querySelector("#load-job").onclick = async () => {
    const id = val("jobid") || lastJob?.id;
    if (!id) return alert("No job id");
    const data = await api(`/api/jobs/${id}`);
    loadResult(data);
  };
  controls.querySelector("#stub").onclick = async () => {
    const id = val("jobid") || lastJob?.id;
    if (!id) return alert("Render or load a job first");
    const data = await api(`/api/plot/stub?job_id=${id}`, { method: "POST" });
    statsEl.textContent = `Stub ok · emu ${data.emulator_run.elapsed_s.toFixed(2)}s`;
  };
}

function renderInspector() {
  if (inspTab === "layers") {
    if (!lastLayers?.passes?.length) {
      inspectorBody.innerHTML = `<p class="muted">No layers yet. Render a job to see vectorization / color passes.</p>`;
      return;
    }
    inspectorBody.innerHTML = `
      <p class="muted">${lastLayers.pass_count} passes · ${lastLayers.width_mm}×${lastLayers.height_mm} mm
      ${lastLayers.meta?.style ? `· style ${lastLayers.meta.style}` : ""}</p>
      ${lastLayers.passes.map((p) => `
        <div class="layer-row ${player.soloPassId === p.id ? "solo" : ""}" data-pass="${p.id}">
          <input type="checkbox" class="vis" data-pass="${p.id}" checked />
          <span class="swatch" style="background:${p.color_hex}; opacity:${p.opacity}"></span>
          <div>
            <div><strong>${p.name}</strong> <span class="muted">${p.kind}</span></div>
            <div class="layer-meta">${p.pen_id} · ${p.color_hex} · ${p.width_mm}mm · ${p.nib_type}<br/>
            polys ${p.polyline_count} · pts ${p.point_count}</div>
          </div>
          <button type="button" data-solo="${p.id}">Solo</button>
        </div>
      `).join("")}
      <p class="muted" style="margin-top:0.8rem">Toggle visibility to isolate colorization / layering behavior in the emulator.</p>
    `;
    inspectorBody.querySelectorAll(".vis").forEach((cb) => {
      cb.onchange = () => player.setPassVisible(cb.dataset.pass, cb.checked);
    });
    inspectorBody.querySelectorAll("[data-solo]").forEach((btn) => {
      btn.onclick = () => {
        player.soloPass(btn.dataset.solo);
        renderInspector();
      };
    });
    inspectorJson = lastLayers;
    return;
  }
  if (inspTab === "job") {
    inspectorJson = lastJob;
    inspectorBody.innerHTML = `<textarea class="json-view" readonly>${JSON.stringify(lastJob || { hint: "No job" }, null, 2)}</textarea>`;
    return;
  }
  // json tab
  inspectorJson = {
    settings: lastSettings,
    layers: lastLayers,
    stats: lastPayload?.stats,
    palette: lastPayload?.palette,
  };
  inspectorBody.innerHTML = `<textarea class="json-view" readonly>${JSON.stringify(inspectorJson || { hint: "No data" }, null, 2)}</textarea>`;
}

async function renderControls() {
  if (!styles.length) styles = await api("/api/styles");
  if (!palettes.length) palettes = await api("/api/palettes");
  if (!papers.length) {
    try { papers = await api("/api/papers"); } catch (_) { papers = []; }
  }
  if (!linesCatalog.length) {
    try { linesCatalog = await api("/api/lines"); } catch (_) { linesCatalog = []; }
  }
  if (currentApp === "genartbot") return renderGenArt();
  if (currentApp === "portraitbot") return renderPortrait();
  if (currentApp === "lettersbot") return renderLetters();
  if (currentApp === "rdlab") return renderRdlab();
  if (currentApp === "papers") return renderPaperLibrary();
  if (currentApp === "lines") return renderLineLibrary();
  if (currentApp === "palettes") return renderPalettes();
  return renderTools();
}

document.getElementById("export-pack").onclick = async () => {
  if (!lastJob?.id) return;
  const pack = await api(`/api/jobs/${lastJob.id}/export`);
  downloadJson(`botdraw-${lastJob.id}-pack.json`, pack);
};
document.getElementById("export-settings").onclick = () => {
  const settings = lastSettings || {
    app: currentApp,
    style_id: selectedStyle,
    palette_id: selectedPaletteId,
    ...state,
  };
  downloadJson(`botdraw-settings.json`, settings);
};
document.getElementById("export-layers").onclick = async () => {
  if (lastLayers) return downloadJson(`botdraw-${lastJob?.id || "layers"}.json`, lastLayers);
  if (lastJob?.id) downloadJson(`botdraw-${lastJob.id}-layers.json`, await api(`/api/jobs/${lastJob.id}/layers`));
};
document.getElementById("export-motion").onclick = async () => {
  if (!lastJob?.id) return;
  downloadJson(`botdraw-${lastJob.id}-motion.json`, await api(`/api/jobs/${lastJob.id}/motion`));
};
document.getElementById("export-palette").onclick = () => {
  const pal = currentPalette();
  if (pal) downloadJson(`${pal.id}.json`, pal);
};
document.getElementById("copy-json").onclick = async () => {
  const text = JSON.stringify(inspectorJson || lastSettings || {}, null, 2);
  await navigator.clipboard.writeText(text);
  statsEl.textContent = "Copied inspector JSON";
};

function wireZoomToolbar(prefix, emu) {
  const zin = document.getElementById(`${prefix}-zoom-in`);
  const zout = document.getElementById(`${prefix}-zoom-out`);
  const zfit = document.getElementById(`${prefix}-zoom-fit`);
  const loupe = document.getElementById(`${prefix}-loupe`);
  const zl = document.getElementById(`${prefix}-zoom-label`);
  emu.onZoomChange = (z) => { if (zl) zl.textContent = `${z.toFixed(2)}×`; };
  if (zin) zin.onclick = () => emu.zoomBy(1.15);
  if (zout) zout.onclick = () => emu.zoomBy(1 / 1.15);
  if (zfit) zfit.onclick = () => emu.fitZoom();
  if (loupe) loupe.onclick = () => {
    emu.toggleLoupe();
    loupe.classList.toggle("active", emu.loupeOn);
  };
  emu.enableInteraction();
  emu.syncSize();
}

wireZoomToolbar("letters", lettersPlayer);
wireZoomToolbar("portrait", portraitPlayer);
player.enableInteraction();
player.syncSize();

renderControls().catch((e) => {
  statsEl.textContent = String(e);
  console.error(e);
});
