const player = new EmulatorPlayer(document.getElementById("emu"));
const lettersPlayer = new EmulatorPlayer(document.getElementById("letters-emu"));
const portraitPlayer = new EmulatorPlayer(document.getElementById("portrait-emu"));
const statsEl = document.getElementById("stats");
const lettersStatsEl = statsEl;
const portraitStatsEl = statsEl;
const controls = document.getElementById("controls");
const inspectorBody = document.getElementById("inspector-body");
const downloadSvg = document.getElementById("download-svg");
const railInspector = document.getElementById("rail-inspector");
const textDragHandle = document.getElementById("text-drag-handle");
const stageSegEl = document.getElementById("stage-seg");
let portraitStageSeg = "vector";
player.onStats = (m) => { statsEl.textContent = m; };
lettersPlayer.onStats = (m) => { statsEl.textContent = m; };
portraitPlayer.onStats = (m) => { statsEl.textContent = m; };
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
let portraitAiReview = "off"; // off | live (scene) | studio (scene+critique)
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
  orientation: "portrait",
  quality: "booth-balanced",
  seed: 42,
  density: 1.0,
  pen_up_speed_mm_s: 100,
  pen_down_speed_mm_s: 25,
  rpm: 3,
  sensor_demo: "temperature",
  sensor_mode: "ribbon",
  sensor_folds: 6,
};

function stagePlayer() {
  if (currentApp === "lettersbot") return lettersPlayer;
  if (currentApp === "portraitbot") return portraitPlayer;
  return player;
}

const pageTextState = {
  lines: ["", "", ""],
  size_mm: 5,
  x_mm: 12,
  y_mm: 14,
  pen_id: "black",
  pass_id: "page-text",
  active: false,
};

function setTextStatus(msg, { error = false } = {}) {
  const el = document.getElementById("text-status");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("error", !!error && !!msg);
}

function refreshTextPenSelect() {
  const sel = document.getElementById("text-pen");
  if (!sel) return;
  const jobPalId = lastJob?.palette_id;
  const palette =
    (jobPalId && palettes.find((p) => p.id === jobPalId)) ||
    currentPalette();
  const pens = (palette?.pens || []).filter((p) => (p.profile?.nib_type || "") !== "highlighter");
  sel.innerHTML = pens
    .map((p) => `<option value="${p.id}" ${p.id === pageTextState.pen_id ? "selected" : ""}>${p.id}</option>`)
    .join("");
  if (!pens.find((p) => p.id === pageTextState.pen_id) && pens[0]) {
    pageTextState.pen_id = pens[0].id;
    sel.value = pens[0].id;
  }
}

function readPageTextForm() {
  pageTextState.lines = [
    document.getElementById("text-line1")?.value || "",
    document.getElementById("text-line2")?.value || "",
    document.getElementById("text-line3")?.value || "",
  ];
  pageTextState.size_mm = Number(document.getElementById("text-size")?.value || pageTextState.size_mm);
  pageTextState.pen_id = document.getElementById("text-pen")?.value || pageTextState.pen_id;
}

function positionTextHandle() {
  if (!textDragHandle || !pageTextState.active || !lastJob) {
    if (textDragHandle) textDragHandle.hidden = true;
    return;
  }
  const pt = player.mmToClient(pageTextState.x_mm, pageTextState.y_mm);
  const stage = document.getElementById("lab-emu-frame") || document.getElementById("stage-canvas");
  const rect = stage.getBoundingClientRect();
  textDragHandle.hidden = false;
  // Absolute inside #stage-canvas (same containing block as the canvas)
  textDragHandle.style.left = `${pt.x - rect.left}px`;
  textDragHandle.style.top = `${pt.y - rect.top}px`;
}

async function applyPageText({ clear = false } = {}) {
  if (!lastJob?.id) {
    setTextStatus("Render a job before adding text", { error: true });
    return;
  }
  readPageTextForm();
  if (!clear && !pageTextState.lines.some((l) => l.trim())) {
    setTextStatus("Enter at least one text line", { error: true });
    return;
  }
  setTextStatus(clear ? "Clearing page text…" : "Adding page text…");
  const data = await api(`/api/jobs/${lastJob.id}/overlay-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lines: pageTextState.lines,
      x_mm: pageTextState.x_mm,
      y_mm: pageTextState.y_mm,
      size_mm: pageTextState.size_mm,
      pen_id: pageTextState.pen_id,
      replace_pass_id: pageTextState.pass_id,
      clear,
    }),
  });
  const hasPass = !!(data.layers?.passes || []).some((p) => p.id === pageTextState.pass_id);
  if (!clear && data.page_text && !hasPass) {
    setTextStatus("No strokes generated — try different text or pen", { error: true });
    return;
  }
  loadResult(data);
  pageTextState.active = !clear && hasPass;
  if (data.page_text) {
    pageTextState.x_mm = data.page_text.x_mm;
    pageTextState.y_mm = data.page_text.y_mm;
  }
  positionTextHandle();
  if (!clear && hasPass) {
    player.skipEnd();
    setTextStatus("Page text added — drag the handle to move");
  } else if (clear) {
    setTextStatus("Page text cleared");
  }
}

function bindPageTextPanel() {
  refreshTextPenSelect();
  const addBtn = document.getElementById("text-add");
  const clearBtn = document.getElementById("text-clear");
  if (addBtn) addBtn.onclick = () => withBusy(addBtn, () => applyPageText());
  if (clearBtn) clearBtn.onclick = () => withBusy(clearBtn, () => applyPageText({ clear: true }));

  if (textDragHandle && !textDragHandle._bound) {
    textDragHandle._bound = true;
    let drag = null;
    textDragHandle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      drag = { x0: e.clientX, y0: e.clientY, mmX: pageTextState.x_mm, mmY: pageTextState.y_mm };
      textDragHandle.setPointerCapture(e.pointerId);
    });
    textDragHandle.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const a = player.clientToMm(drag.x0, drag.y0);
      const b = player.clientToMm(e.clientX, e.clientY);
      pageTextState.x_mm = drag.mmX + (b.x_mm - a.x_mm);
      pageTextState.y_mm = drag.mmY + (b.y_mm - a.y_mm);
      positionTextHandle();
    });
    textDragHandle.addEventListener("pointerup", async (e) => {
      if (!drag) return;
      drag = null;
      try {
        textDragHandle.releasePointerCapture(e.pointerId);
      } catch (_) {}
      try {
        await applyPageText();
      } catch (err) {
        setTextStatus(String(err.message || err), { error: true });
        console.error(err);
      }
    });
  }
  player._textDragHit = (e) => {
    if (!pageTextState.active || textDragHandle?.hidden) return false;
    const r = textDragHandle.getBoundingClientRect();
    return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
  };
}

document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  if (e.code === "Space") {
    e.preventDefault();
    player.toggle();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    player.nudge(Math.max(2, player.duration * 0.02));
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    player.nudge(-Math.max(2, player.duration * 0.02));
  } else if (e.key === "g" || e.key === "G") {
    toggleGhost();
  }
});

/* ---------------- app tabs / inspector tabs ---------------- */

document.querySelectorAll("#tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentApp = btn.dataset.app;
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

/* ---------------- helpers ---------------- */

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

async function withBusy(btn, fn) {
  const b =
    typeof btn === "string"
      ? controls.querySelector(btn) || document.querySelector(btn)
      : btn;
  if (b) {
    b.classList.add("loading");
    b.disabled = true;
  }
  try {
    return await fn();
  } catch (e) {
    const msg = String(e.message || e);
    statsEl.textContent = msg;
    setTextStatus(msg, { error: true });
    console.error(e);
  } finally {
    if (b) {
      b.classList.remove("loading");
      b.disabled = false;
    }
  }
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

function segHtml(id, options, selected) {
  return `<div class="seg-control mini wide" id="${id}" role="group">${options
    .map(
      (o) =>
        `<button type="button" data-value="${o.value}" class="${o.value === selected ? "active" : ""}">${o.label}</button>`
    )
    .join("")}</div>`;
}

function bindSeg(id, onChange) {
  const el = controls.querySelector(`#${id}`);
  if (!el) return;
  el.querySelectorAll("button").forEach((b) => {
    b.onclick = () => {
      el.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      if (onChange) onChange(b.dataset.value);
    };
  });
}

function segVal(id, fallback) {
  const el = controls.querySelector(`#${id} button.active`);
  return el ? el.dataset.value : fallback;
}

function syncStateFromForm() {
  if (controls.querySelector("#paper")) state.paper = val("paper", state.paper);
  if (controls.querySelector("#orient")) state.orientation = segVal("orient", state.orientation);
  if (controls.querySelector("#quality-seg")) state.quality = segVal("quality-seg", state.quality);
  if (controls.querySelector("#seed")) state.seed = num("seed", state.seed);
  if (controls.querySelector("#density")) state.density = num("density", state.density);
  if (controls.querySelector("#pen_up")) state.pen_up_speed_mm_s = num("pen_up", state.pen_up_speed_mm_s);
  if (controls.querySelector("#pen_down")) state.pen_down_speed_mm_s = num("pen_down", state.pen_down_speed_mm_s);
  if (controls.querySelector("#rpm")) state.rpm = num("rpm", state.rpm);
  if (controls.querySelector("#palette")) selectedPaletteId = val("palette", selectedPaletteId);
}

function setExportEnabled(on) {
  ["export-pack", "export-more"].forEach((id) => {
    document.getElementById(id).disabled = !on;
  });
}


function syncZoomLabel(z) {
  const zl = document.getElementById("zoom-label");
  if (zl) zl.textContent = `${Number(z || 1).toFixed(2)}×`;
  const loupe = document.getElementById("loupe");
  if (loupe) loupe.classList.toggle("active", !!stagePlayer().loupeOn);
}

function setPortraitStageSeg(seg) {
  const prev = portraitStageSeg;
  portraitStageSeg = seg || "vector";
  if (stageSegEl) {
    stageSegEl.querySelectorAll("button").forEach((b) => {
      b.classList.toggle("active", b.dataset.seg === portraitStageSeg);
    });
  }
  document.querySelectorAll("#portrait-sheet [data-seg-view]").forEach((el) => {
    el.hidden = el.dataset.segView !== portraitStageSeg;
  });
  const toggles = document.getElementById("ingest-toggles");
  if (toggles) toggles.hidden = portraitStageSeg !== "ingest";
  if (prev !== portraitStageSeg) {
    animateSheetSwap(document.getElementById("portrait-sheet"));
  }
  if (portraitStageSeg === "vector") {
    setDeskState({
      empty: !lastPayload,
      loading: false,
      hint: "Drop a photo, then Ingest",
    });
  } else if (portraitStageSeg === "source") {
    setDeskState({
      empty: !portraitFile && !portraitIngestPreview,
      loading: false,
      hint: "Drop a photo or choose a file",
    });
  } else {
    setDeskState({
      empty: !portraitIngestPreview,
      loading: false,
      hint: "Ingest to preview linework",
    });
  }
  requestAnimationFrame(() => {
    portraitPlayer.syncSize();
    portraitPlayer.fitZoom();
  });
}

function setShellForApp(app) {
  const prevApp = document.body.dataset.app;
  document.body.dataset.app = app;
  const letters = app === "lettersbot";
  const portrait = app === "portraitbot";
  const lab = !letters && !portrait;

  const controlsEl = document.getElementById("controls");
  const lettersRail = document.getElementById("letters-rail");
  const portraitContent = document.getElementById("portrait-content");
  if (controlsEl) controlsEl.hidden = !lab;
  if (lettersRail) lettersRail.hidden = !letters;
  if (portraitContent) portraitContent.hidden = !portrait;
  if (railInspector) railInspector.hidden = !lab;

  const labSheet = document.getElementById("lab-sheet");
  const lettersSheet = document.getElementById("letters-sheet");
  const portraitSheet = document.getElementById("portrait-sheet");
  if (labSheet) labSheet.hidden = !lab;
  if (lettersSheet) lettersSheet.hidden = !letters;
  if (portraitSheet) portraitSheet.hidden = !portrait;
  if (stageSegEl) stageSegEl.hidden = !portrait;

  const exportPack = document.getElementById("export-pack");
  const letterSvg = document.getElementById("letters-dl-svg");
  const portraitSvg = document.getElementById("portrait-dl-svg");
  // Show app-appropriate export actions inside the shared menu
  ["export-pack", "export-settings", "export-layers", "export-motion", "export-palette", "copy-json", "download-svg"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !lab;
  });
  ["letters-dl-svg", "letters-dl-motion", "letters-dl-pack"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !letters;
  });
  ["portrait-dl-svg", "portrait-dl-motion", "portrait-dl-pack"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !portrait;
  });
  void exportPack;
  void letterSvg;
  void portraitSvg;

  if (portrait) {
    setPortraitStageSeg(portraitStageSeg);
  } else {
    setDeskState({
      empty: !lastPayload,
      loading: false,
      hint: letters ? "Compose layers, then Vectorize" : "Drop a photo or Vectorize",
    });
  }
  if (prevApp && prevApp !== app) {
    const sheet = lab ? labSheet : letters ? lettersSheet : portraitSheet;
    animateSheetSwap(sheet);
  }
  requestAnimationFrame(() => {
    const pl = stagePlayer();
    pl.syncSize();
    syncZoomLabel(pl.zoom);
  });
}

document.getElementById("play").onclick = () => stagePlayer().play();
document.getElementById("pause").onclick = () => stagePlayer().pause();
document.getElementById("skip").onclick = () => stagePlayer().skipEnd();
document.getElementById("speed").oninput = (e) => stagePlayer().setSpeed(e.target.value);
document.getElementById("ghost").onchange = (e) => stagePlayer().setGhost(e.target.checked);

document.getElementById("zoom-in").onclick = () => stagePlayer().zoomBy(1.15);
document.getElementById("zoom-out").onclick = () => stagePlayer().zoomBy(1 / 1.15);
document.getElementById("zoom-fit").onclick = () => stagePlayer().fitZoom();
document.getElementById("loupe").onclick = () => {
  const pl = stagePlayer();
  pl.toggleLoupe();
  document.getElementById("loupe").classList.toggle("active", pl.loupeOn);
};

if (stageSegEl) {
  stageSegEl.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => setPortraitStageSeg(btn.dataset.seg);
  });
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

document.querySelectorAll(".insp-tabs button, #insp-tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".insp-tabs button, #insp-tabs button").forEach((b) => b.classList.remove("active"));
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
  if (controls.querySelector("#orientation")) state.orientation = val("orientation", state.orientation);
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
  if (currentApp === "portraitbot") {
    setPortraitDownloads(true, lastJob?.id);
    setPortraitStageSeg("vector");
  }
  if (currentApp !== "portraitbot" && currentApp !== "lettersbot") setExportEnabled(true);
  setDeskState({ loading: false, empty: false });
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
  // Apple shell: keep a single paper hero; Source/Ingest draw to offstage canvases.
  const labSheet = document.getElementById("lab-sheet");
  if (labSheet) labSheet.hidden = false;
  requestAnimationFrame(() => player.syncSize());
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
  setDeskState({ loading: true, empty: false, hint: "Ingesting…" });
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
  setDeskState({ loading: false, empty: false });
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

const LINE_TYPE_DEFAULTS = {
  linetype: "solid",
  line_density: 1.0,
  line_pattern_width_mm: 2.0,
};

const designKnobState = {
  phyllotaxis: { n_points: 220, angle_deg: 137.5, mark: "square", mark_size_mm: 2.5 },
  modular_chords: { n_points: 200, k: 77, ...LINE_TYPE_DEFAULTS },
  prime_sieve: {
    max_n: 212,
    grid_cols: 6,
    show_arcs: true,
    show_sieve: true,
    mark_size_mm: 2.5,
    ...LINE_TYPE_DEFAULTS,
  },
  rule30: { cols: 120, rows: 90, rule: 30, ...LINE_TYPE_DEFAULTS },
};

function readLineTypeKnobs(prefix, fallback) {
  return {
    linetype: controls.querySelector(`#${prefix}-linetype`)?.value || fallback.linetype || "solid",
    line_density: Number(
      controls.querySelector(`#${prefix}-line-density`)?.value ?? fallback.line_density ?? 1.0
    ),
    line_pattern_width_mm: Number(
      controls.querySelector(`#${prefix}-line-width`)?.value ?? fallback.line_pattern_width_mm ?? 2.0
    ),
  };
}

function lineKnobsHtml(prefix, state) {
  const types = ["solid", "dashed", "dotted", "dash_dot", "double"];
  const opts = types
    .map((t) => `<option value="${t}" ${t === state.linetype ? "selected" : ""}>${t}</option>`)
    .join("");
  return `
    <h4>Line style</h4>
    <p class="muted">Plotter-safe linetypes — density tightens repeats; width is dash/dot length or double separation (mm).</p>
    ${field("Linetype", `<select id="${prefix}-linetype">${opts}</select>`)}
    <div class="grid-2">
      ${field("Pattern density", `<input id="${prefix}-line-density" type="number" min="0.4" max="2.5" step="0.1" value="${state.line_density}" />`)}
      ${field("Pattern width mm", `<input id="${prefix}-line-width" type="number" min="0.5" max="8" step="0.1" value="${state.line_pattern_width_mm}" />`)}
    </div>
  `;
}

function syncDesignKnobState() {
  if (selectedStyle === "phyllotaxis") {
    designKnobState.phyllotaxis = {
      n_points: Number(controls.querySelector("#phy-points")?.value ?? designKnobState.phyllotaxis.n_points),
      angle_deg: Number(controls.querySelector("#phy-angle")?.value ?? designKnobState.phyllotaxis.angle_deg),
      mark: controls.querySelector("#phy-mark")?.value || designKnobState.phyllotaxis.mark,
      mark_size_mm: Number(controls.querySelector("#phy-mark-size")?.value ?? designKnobState.phyllotaxis.mark_size_mm),
    };
    return;
  }
  if (selectedStyle === "modular_chords") {
    designKnobState.modular_chords = {
      n_points: Number(controls.querySelector("#mod-n")?.value ?? designKnobState.modular_chords.n_points),
      k: Number(controls.querySelector("#mod-k")?.value ?? designKnobState.modular_chords.k),
      ...readLineTypeKnobs("mod", designKnobState.modular_chords),
    };
    return;
  }
  if (selectedStyle === "prime_sieve") {
    designKnobState.prime_sieve = {
      max_n: Number(controls.querySelector("#sieve-n")?.value ?? designKnobState.prime_sieve.max_n),
      grid_cols: Number(controls.querySelector("#sieve-cols")?.value ?? designKnobState.prime_sieve.grid_cols),
      show_arcs: !!controls.querySelector("#sieve-arcs")?.checked,
      show_sieve: !!controls.querySelector("#sieve-grid")?.checked,
      mark_size_mm: Number(
        controls.querySelector("#sieve-mark-size")?.value ?? designKnobState.prime_sieve.mark_size_mm
      ),
      ...readLineTypeKnobs("sieve", designKnobState.prime_sieve),
    };
    return;
  }
  designKnobState.rule30 = {
    cols: Number(controls.querySelector("#ca-cols")?.value ?? designKnobState.rule30.cols),
    rows: Number(controls.querySelector("#ca-rows")?.value ?? designKnobState.rule30.rows),
    rule: Number(controls.querySelector("#ca-rule")?.value ?? designKnobState.rule30.rule),
    ...readLineTypeKnobs("ca", designKnobState.rule30),
  };
}

function designLibraryParams() {
  syncDesignKnobState();
  if (selectedStyle === "phyllotaxis") return { ...designKnobState.phyllotaxis };
  if (selectedStyle === "modular_chords") return { ...designKnobState.modular_chords };
  if (selectedStyle === "prime_sieve") return { ...designKnobState.prime_sieve };
  return { ...designKnobState.rule30 };
}

function designLibraryKnobsHtml() {
  if (selectedStyle === "phyllotaxis") {
    const k = designKnobState.phyllotaxis;
    const marks = ["circle", "square", "diamond", "triangle", "star", "cross"];
    const markOpts = marks
      .map((m) => `<option value="${m}" ${m === k.mark ? "selected" : ""}>${m}</option>`)
      .join("");
    return `
      <h4>Sunflower</h4>
      <p class="muted">r = c√n · θ = n × angle — Mark size is outer mm (square side / circle diameter). Raise Points only for denser packing.</p>
      <div class="grid-2">
        ${field("Points", `<input id="phy-points" type="number" min="50" max="4000" value="${k.n_points}" />`)}
        ${field("Angle °", `<input id="phy-angle" type="number" min="1" max="179" step="0.1" value="${k.angle_deg}" />`)}
      </div>
      <div class="grid-2">
        ${field("Mark", `<select id="phy-mark">${markOpts}</select>`)}
        ${field("Mark size mm", `<input id="phy-mark-size" type="number" min="1" max="8" step="0.1" value="${k.mark_size_mm}" />`)}
      </div>
    `;
  }
  if (selectedStyle === "modular_chords") {
    const k = designKnobState.modular_chords;
    return `
      <h4>Circle steps</h4>
      <p class="muted">i → (i + k) mod N — petals from periodicity, dense ring from chord interference. N is authoritative.</p>
      <div class="grid-2">
        ${field("N points", `<input id="mod-n" type="number" min="12" max="2000" value="${k.n_points}" />`)}
        ${field("Step k", `<input id="mod-k" type="number" min="1" max="1999" value="${k.k}" />`)}
      </div>
      ${lineKnobsHtml("mod", k)}
    `;
  }
  if (selectedStyle === "prime_sieve") {
    const k = designKnobState.prime_sieve;
    return `
      <h4>Prime sieve</h4>
      <p class="muted">Left: arc spire between primes. Right: circled primes / struck composites. Cols=6 → vertical lanes.</p>
      <div class="grid-2">
        ${field("Max n", `<input id="sieve-n" type="number" min="10" max="2000" value="${k.max_n}" />`)}
        ${field("Grid cols", `<input id="sieve-cols" type="number" min="2" max="20" value="${k.grid_cols}" />`)}
      </div>
      <div class="grid-2">
        ${field("Mark size mm", `<input id="sieve-mark-size" type="number" min="1" max="8" step="0.1" value="${k.mark_size_mm}" />`)}
      </div>
      <div class="chk-row">
        <label><input id="sieve-arcs" type="checkbox" ${k.show_arcs ? "checked" : ""} /> Arc spire</label>
        <label><input id="sieve-grid" type="checkbox" ${k.show_sieve ? "checked" : ""} /> Sieve grid</label>
      </div>
      ${lineKnobsHtml("sieve", k)}
    `;
  }
  const k = designKnobState.rule30;
  return `
    <h4>Automaton</h4>
    <p class="muted">Cols/rows are authoritative cell counts — live cells become horizontal strokes.</p>
    <div class="grid-2">
      ${field("Cols", `<input id="ca-cols" type="number" min="16" max="400" value="${k.cols}" />`)}
      ${field("Rows", `<input id="ca-rows" type="number" min="12" max="300" value="${k.rows}" />`)}
    </div>
    ${field("Rule", `<input id="ca-rule" type="number" min="0" max="255" value="${k.rule}" />`)}
    ${lineKnobsHtml("ca", k)}
  `;
}

function renderDesignLibrary() {
  const list = styles.filter((s) => s.category === "design");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "rule30";
  controls.innerHTML = `
    <h3>Design Library</h3>
    <p class="muted">Math-derived and structured motifs for the plotter — pick a design, then vectorize.</p>
    <h4>Math Derived</h4>
    <p class="muted">Cellular automata, primes, phyllotaxis, modular chords, and related constructions.</p>
    ${styleButtons(list)}
    ${designLibraryKnobsHtml()}
    ${fractalDevOpts()}
    <div class="row"><button class="primary" id="go">Vectorize</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", () =>
      renderWithSettings({
        appName: "design",
        busyText: "Vectorizing design…",
        paramsExtra: designLibraryParams(),
      })
    );
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
  setDeskState({
    empty: !lastPayload || currentApp !== "portraitbot",
    loading: false,
    hint: "Drop a photo, then Ingest",
  });
  root.innerHTML = `
    <h3>Portrait</h3>
    <p class="muted">Upload → Ingest → Vectorize. Stage switches Source · Ingest · Vector.</p>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Image</div>
        <div class="portrait-drop ${portraitFile ? "has-file" : ""}" id="portrait-drop">
          ${portraitFile ? portraitFile.name : "Drop a photo or choose a file"}
          <div style="margin-top:0.45rem"><input id="portrait-photo" type="file" accept="image/*" /></div>
        </div>
        <div class="row" style="margin-top:0.35rem">
          <label><input type="checkbox" id="auto-frame" ${portraitAutoFrame ? "checked" : ""}/> Auto frame</label>
          <label><input type="checkbox" id="hatch-shading" ${portraitHatchEnabled ? "checked" : ""}/> Hatch</label>
          <button type="button" class="btn btn-ghost" id="reset-frame">Reset frame</button>
        </div>
      </div>
      <div class="group-block">
        <div class="group-title">Image type</div>
        <div class="seg mode-seg" id="image-mode-grid">
          ${modes.map(([id, title, sub]) =>
            `<button type="button" data-mode="${id}" class="${portraitImageMode === id ? "active" : ""}">
              <strong>${title}</strong><span>${sub}</span>
            </button>`
          ).join("")}
        </div>
      </div>
      <div class="group-block">
        <div class="group-title">Style</div>
        ${styleButtons(list)}
      </div>
      <div class="group-block">
        <div class="group-title">Paper &amp; render</div>
        <div class="grid-2">
          ${field("Size", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
          ${field("Color", paperSelectHtml(portraitPaperId))}
        </div>
        <div class="grid-2">
          ${field("Quality", `<select id="quality"><option value="booth-fast">booth-fast</option><option value="booth-balanced">booth-balanced</option><option value="studio-hq">studio-hq</option></select>`)}
          ${field("Density", `<input id="density" type="number" step="0.1" value="${state.density}" />`)}
        </div>
        <div class="grid-2">
          ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
          ${field("Line type", `<select id="line-type">${ltOpts}</select>`)}
        </div>
        ${field("Palette", paletteSelectHtml())}
        <div class="pen-chips">${penList}</div>
      </div>
    </div>
    <div class="row" style="margin-top:0.35rem; gap:0.35rem; flex-wrap:wrap">
      <button type="button" class="btn" id="portrait-ingest-btn">Ingest</button>
      <button type="button" class="btn btn-primary primary" id="portrait-go">Vectorize</button>
      <button type="button" class="btn" id="portrait-apply" ${portraitIngestId ? "" : "disabled"}>Apply</button>
    </div>
    <details class="advanced">
      <summary>Advanced</summary>
      <div class="group">
        <div class="group-block">
          <div class="group-title">Scan &amp; AI</div>
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
              `<select id="line-source">
                <option value="auto"${portraitLineSource === "auto" ? " selected" : ""}>Auto</option>
                <option value="neural"${portraitLineSource === "neural" ? " selected" : ""}>Neural</option>
                <option value="classic"${portraitLineSource === "classic" ? " selected" : ""}>Classic</option>
              </select>`
            )}
            ${field(
              "AI review",
              `<select id="ai-review">
                <option value="off"${portraitAiReview === "off" ? " selected" : ""}>Off</option>
                <option value="live"${portraitAiReview === "live" ? " selected" : ""}>Live</option>
                <option value="studio"${portraitAiReview === "studio" ? " selected" : ""}>Studio</option>
              </select>`
            )}
          </div>
          <p class="muted" id="ai-review-hint">Live = scene only; Studio may re-ingest once.</p>
          <label title="5+1 ensemble"><input type="checkbox" id="ensemble-5plus1" ${
            portraitEnsemble === true || (portraitEnsemble == null && state.quality === "studio-hq" && portraitImageMode === "photo") ? "checked" : ""
          }/> Ensemble (5+1)</label>
        </div>
        <div class="group-block">
          <div class="group-title">Ornament</div>
          ${field("Line library", lineSelectHtml(selectedLineId))}
          ${field("Line spacing mm", `<input id="line-spacing" type="range" min="0.4" max="4" step="0.1" value="1.2" /><span id="line-spacing-val">1.2</span>`)}
          <div id="ornament-amp" style="${needsAmp ? "" : "display:none"}">
            ${field("Period mm", `<input id="pattern-period" type="range" min="0.4" max="8" step="0.1" value="2" /><span id="pattern-period-val">2.0</span>`)}
            ${field("Amplitude mm", `<input id="pattern-amp" type="range" min="0" max="4" step="0.1" value="0.8" /><span id="pattern-amp-val">0.8</span>`)}
          </div>
          <div id="ornament-dash" style="${needsDash ? "" : "display:none"}">
            ${field("Dash mm", `<input id="dash-mm" type="range" min="0.2" max="8" step="0.1" value="2" /><span id="dash-mm-val">2.0</span>`)}
            ${field("Gap mm", `<input id="gap-mm" type="range" min="0.1" max="6" step="0.1" value="1.2" /><span id="gap-mm-val">1.2</span>`)}
          </div>
          <div class="row">
            <button type="button" class="btn" id="portrait-reingest">Re-ingest</button>
            <button type="button" class="btn" id="reset-pen-map">Reset pen map</button>
          </div>
        </div>
      </div>
    </details>
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
  const aiReviewEl = root.querySelector("#ai-review");
  const aiHintEl = root.querySelector("#ai-review-hint");
  const syncAiReviewHint = () => {
    if (!aiHintEl || !aiReviewEl) return;
    const m = aiReviewEl.value || "off";
    if (m === "live") {
      aiHintEl.textContent = "Live: scene knobs only (no critique / no AI re-ingest).";
    } else if (m === "studio") {
      aiHintEl.textContent = "Studio: scene + one critique; keep_more_edges may re-ingest once.";
    } else {
      aiHintEl.textContent = "AI review off. Live = crop/suppress/tone only; Studio may re-ingest once for fidelity.";
    }
  };
  if (aiReviewEl) {
    aiReviewEl.onchange = () => {
      portraitAiReview = aiReviewEl.value || "off";
      syncAiReviewHint();
    };
    syncAiReviewHint();
  }
  if (qualityEl) {
    qualityEl.onchange = () => {
      state.quality = qualityEl.value;
      // Refresh ensemble checkbox default when quality changes and user hasn't forced
      if (portraitEnsemble == null && ensCb) {
        ensCb.checked = state.quality === "studio-hq" && portraitImageMode === "photo";
      }
      // Suggest mode when turning quality to studio-hq / booth while AI is on
      if (aiReviewEl && portraitAiReview !== "off") {
        if (state.quality === "studio-hq" && portraitAiReview === "live") {
          aiReviewEl.value = "studio";
          portraitAiReview = "studio";
        } else if (state.quality !== "studio-hq" && portraitAiReview === "studio") {
          aiReviewEl.value = "live";
          portraitAiReview = "live";
        }
        syncAiReviewHint();
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
      setDeskState({ loading: false, empty: !portraitIngestPreview, hint: "Drop a photo, then Ingest" });
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
  setDeskState({ loading: true, empty: false, hint: "Ingesting…" });
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
  if (aiEl) portraitAiReview = aiEl.value || "off";
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
    if (knobs.ai_review && knobs.ai_review !== "off") fd.append("ai_review", knobs.ai_review);
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
  setDeskState({ loading: false, empty: false });
  setPortraitStageSeg("ingest");
  const wall = ((performance.now() - t0) / 1000).toFixed(2);
  const timing = data.timing_s || {};
  const meta = data.meta || {};
  const aiChip = portraitAiReviewStatusChip(data, meta);
  if (portraitStatsEl) {
    portraitStatsEl.textContent =
      `Ingest ready · edges ${data.edge_count} · hatch ${data.hatch_count ?? 0} · regions ${data.region_count} · wall ${wall}s` +
      (timing.total != null ? ` · trace ${timing.total}s` : "") +
      (data.cache_hit ? " · cache" : "") +
      (portraitHatchEnabled ? "" : " · hatch off") +
      (meta.ensemble?.enabled ? " · ensemble 5+1" : "") +
      (meta.line_source ? ` · ${meta.line_source}` : "") +
      aiChip +
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
  if (aiEl) portraitAiReview = aiEl.value || "off";
  if (portraitAiReview && portraitAiReview !== "off") extra.ai_review = portraitAiReview;
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
  setDeskState({ loading: true, empty: false, hint: "Vectorizing…" });
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
    setDeskState({ loading: false, empty: !lastPayload, hint: "Drop a photo, then Ingest" });
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
  setDeskState({ loading: false, empty: false });
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
  const layerMeta = data.layers?.meta || data.emulator?.layers?.meta || {};
  const settings = data.emulator?.settings || {};
  const aiChip = portraitAiReviewStatusChip(
    {
      ai_review: layerMeta.ai_review || settings.params_extra?.ai_review || settings.ai_review,
      ai_review_status: layerMeta.ai_review_status || settings.params_extra?.ai_review_status,
      ai_scene: settings.ai_scene,
      ai_critique: settings.ai_critique || settings.params_extra?.ai_critique,
    },
    layerMeta
  );
  if (portraitStatsEl) {
    const budgetLabel = budget?.label || `passes ${data.layers?.pass_count ?? "?"}`;
    const warn = budget?.over_budget ? " · over budget" : "";
    portraitStatsEl.textContent =
      `Ready · ${selectedStyle} · ${portraitImageMode} · wall ${wall}s · ${budgetLabel}${warn}` +
      (cacheHit ? " · cache hit" : " · ingest") +
      aiChip;
    if (budget?.over_budget) portraitStatsEl.style.color = "#b45309";
    else portraitStatsEl.style.color = "";
  }
}

function portraitAiReviewStatusChip(data, meta) {
  const mode = data?.ai_review || meta?.ai_review;
  if (!mode || mode === "off" || mode === false) return "";
  const status = data?.ai_review_status || meta?.ai_review_status || "";
  const sceneSum = (data?.ai_scene || meta?.ai_scene || {}).summary;
  const critSum = (data?.ai_critique || meta?.ai_critique || {}).summary
    || meta?.ai_critique_summary
    || data?.ai_critique_summary;
  let chip = ` · ai:${mode}`;
  if (status) chip += `/${status}`;
  if (critSum) chip += ` · “${String(critSum).slice(0, 48)}”`;
  else if (sceneSum) chip += ` · “${String(sceneSum).slice(0, 48)}”`;
  return chip;
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
    <div class="group">
      <div class="group-block">
        <div class="group-title">Render</div>
        <div class="grid-2">
          ${field("Paper", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
          ${field("Orientation", `<select id="orientation"><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select>`)}
        </div>
        <div class="grid-2">
          ${field("Quality", `<select id="quality"><option value="booth-fast">booth-fast</option><option value="booth-balanced">booth-balanced</option><option value="studio-hq">studio-hq</option></select>`)}
          ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
        </div>
        <div class="grid-2">
          ${field("Density", `<input id="density" type="number" step="0.1" value="${state.density}" />`)}
          <span></span>
        </div>
      </div>
      <div class="group-block">
        <div class="group-title">Palette</div>
        ${field("Established palette", paletteSelectHtml())}
        ${penChipsHtml(currentPalette())}
      </div>
      <div class="group-block">
        <div class="group-title">Source</div>
        ${field("Upload image (optional)", `<input id="photo" type="file" accept="image/*" />`)}
        ${field("Import settings JSON", `<input id="import-settings" type="file" accept="application/json,.json" />`)}
      </div>
    </div>
    <details class="advanced">
      <summary>Advanced speeds</summary>
      <div class="group">
        <div class="group-block">
          <div class="grid-2">
            ${field("Pen-up mm/s", `<input id="pen_up" type="number" value="${state.pen_up_speed_mm_s}" />`)}
            ${field("Pen-down mm/s", `<input id="pen_down" type="number" value="${state.pen_down_speed_mm_s}" />`)}
          </div>
        </div>
      </div>
    </details>
  `;
}

function setDeskState({ empty, loading, hint } = {}) {
  const desk = document.getElementById("paper-desk");
  const cue = document.getElementById("sheet-empty");
  if (!desk) return;
  if (empty != null) desk.classList.toggle("is-empty", !!empty);
  if (loading != null) desk.classList.toggle("is-loading", !!loading);
  if (cue && hint != null) cue.textContent = hint;
}

function animateSheetSwap(el) {
  if (!el) return;
  el.classList.add("is-entering");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => el.classList.remove("is-entering"));
  });
}

function applyCommonDefaults() {
  const paper = controls.querySelector("#paper");
  const quality = controls.querySelector("#quality");
  const orientation = controls.querySelector("#orientation");
  if (paper) paper.value = state.paper;
  if (quality) quality.value = state.quality;
  if (orientation) orientation.value = state.orientation || "portrait";
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
        orientation: obj.orientation || state.orientation,
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
    `<button type="button" data-style="${s.id}" class="${s.id === selectedStyle ? "selected" : ""}" title="${s.id}">
      <strong>${s.name}</strong>
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
    fd.append("orientation", state.orientation || "portrait");
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
      orientation: state.orientation || "portrait",
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
  setDeskState({
    empty: !lastPayload || currentApp !== "genartbot",
    loading: false,
    hint: "Drop a photo or Vectorize",
  });
  controls.innerHTML = `
    <h3>GenArt</h3>
    <p class="muted">Pick a style, ingest a photo if you want, then vectorize.</p>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Style</div>
        ${styleButtons(list)}
      </div>
    </div>
    <div class="row actions">
      <button type="button" class="btn" id="genart-ingest">Ingest</button>
      <button type="button" class="btn btn-primary primary" id="go">Vectorize</button>
    </div>
    ${commonDevOpts()}
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
  controls.querySelector("#genart-ingest").onclick = () => {
    setDeskState({ loading: true, empty: false, hint: "Ingesting…" });
    runLabIngest().catch((e) => {
      setDeskState({ loading: false, empty: true });
      statsEl.textContent = String(e.message || e);
      console.error(e);
    });
  };
  controls.querySelector("#go").onclick = () => {
    setDeskState({ loading: true, empty: false, hint: "Vectorizing…" });
    renderWithSettings({ appName: "genartbot", busyText: "Vectorizing GenArt…" })
      .then(() => setDeskState({ loading: false, empty: false }))
      .catch((e) => {
        setDeskState({ loading: false, empty: !lastPayload });
        statsEl.textContent = String(e.message || e);
        console.error(e);
      });
  };
}

function renderFractal() {
  const list = styles.filter((s) => s.category === "fractal");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "hilbert_curve";
  setDeskState({
    empty: !lastPayload || currentApp !== "fractalbot",
    loading: false,
    hint: "Pick a fractal, then Vectorize",
  });
  controls.innerHTML = `
    <h3>Fractal</h3>
    <p class="muted">Escape-time + single-stroke space-filling / L-system curves for plotter wall art.</p>
    <div class="fractal-ref">
      <img src="/static/previews/single_line_fractals.png" alt="Single-line fractal family" />
    </div>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Style</div>
        ${styleButtons(list)}
      </div>
    </div>
    <div class="row actions">
      <button type="button" class="btn btn-primary primary" id="go">Vectorize</button>
    </div>
    ${commonDevOpts()}
  `;
  bindStyleGrid();
  applyCommonDefaults();
  // Fractals don't use photo ingest — hide source block if present
  const photo = controls.querySelector("#photo");
  if (photo) {
    const srcBlock = photo.closest(".group-block");
    if (srcBlock) srcBlock.hidden = true;
  }
  controls.querySelector("#go").onclick = () => {
    setDeskState({ loading: true, empty: false, hint: "Vectorizing…" });
    renderWithSettings({ appName: "fractalbot", busyText: "Vectorizing fractal…" })
      .then(() => setDeskState({ loading: false, empty: false }))
      .catch((e) => {
        setDeskState({ loading: false, empty: !lastPayload });
        statsEl.textContent = String(e.message || e);
        console.error(e);
      });
  };
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
    <details class="advanced">
      <summary>Advanced · AI draft</summary>
      <div class="group">
        <div class="group-block">
          <div class="group-title">Draft meta</div>
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
        </div>
      </div>
    </details>
  `;
}

function letterEditorShellHtml() {
  const def = LETTER_TYPE_DEFAULTS[letterType] || LETTER_TYPE_DEFAULTS.personal;
  return `
    <h3>${def.title}</h3>
    <p class="muted">Edit layers → Vectorize. Paper preview fills the desk.</p>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Layers</div>
        <div class="layers-head">
          <p class="muted" style="margin:0">Font or line · pen · snap</p>
          <div class="layer-actions">
            <button type="button" id="letter-layer-add" title="Add text layer (Shift: line)">+</button>
            <button type="button" id="letter-layer-remove" title="Remove layer">−</button>
          </div>
        </div>
        <div class="layer-tabs" id="letter-layer-tabs"></div>
        <div class="layer-specs" id="letter-layer-specs"></div>
      </div>
      <div class="group-block">
        <div class="group-title">Palette</div>
        ${field("Palette", paletteSelectHtml())}
      </div>
    </div>
    <div class="row actions">
      <button type="button" class="btn btn-primary primary" id="go">Vectorize</button>
    </div>
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
    setDeskState({ loading: true, empty: false, hint: "Vectorizing…" });
    lettersStatsEl.textContent = hasBody
      ? "Vectorizing…"
      : useLlm
        ? "Drafting with Ollama…"
        : "Template draft + vectorize…";
  }
  const t0 = performance.now();
  let data;
  try {
    data = await api("/api/letters/draft", {
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
  } catch (e) {
    if (!quiet) setDeskState({ loading: false, empty: !lastPayload, hint: "Compose layers, then Vectorize" });
    throw e;
  }
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
  syncZoomLabel(lettersPlayer.zoom);
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
  setDeskState({ loading: false, empty: false });
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
  lettersPlayer.onZoomChange = (z) => syncZoomLabel(z);
  syncZoomLabel(lettersPlayer.zoom);
  root.querySelector("#palette").value = selectedPaletteId;
  root.querySelector("#palette").onchange = () => {
    selectedPaletteId = root.querySelector("#palette").value;
    renderLetterLayerEditor();
    scheduleLetterVectorize();
  };
  root.querySelector("#go").onclick = () => vectorizeLetter().catch((e) => {
    setDeskState({ loading: false, empty: !lastPayload, hint: "Compose layers, then Vectorize" });
    lettersStatsEl.textContent = String(e);
    console.error(e);
  });
  renderLetterLayerEditor();
  setLettersDownloads(!!lastJob?.id, lastJob?.id);
  setDeskState({
    empty: !lastPayload,
    loading: false,
    hint: "Compose layers, then Vectorize",
  });
  scheduleLetterVectorize();
}

function renderRdlab() {
  const list = styles.filter((s) => ["backlog", "pattern"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = "spiral";
  const sensorMode = state.sensor_mode || "ribbon";
  const sensorDemo = state.sensor_demo || "temperature";
  const sensorFolds = state.sensor_folds ?? 6;
  setDeskState({
    empty: !lastPayload || currentApp !== "rdlab",
    loading: false,
    hint: "Pick an experiment, then Vectorize",
  });
  controls.innerHTML = `
    <h3>R&amp;D Lab · Dev</h3>
    <p class="muted">Experimental motifs, sensor → art, rotating-base kinematics.</p>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Experiment</div>
        ${styleButtons(list)}
      </div>
    </div>
    <div class="group">
      <div class="group-block">
        <div class="group-title">Sensor → Art</div>
        <p class="muted">Map real-world series, GPS paths, or G-force logs into symmetrical / asymmetrical / pattern drawings. CSV or JSON.</p>
        ${field("Demo", `<select id="sensor_demo">
          <option value="temperature"${sensorDemo === "temperature" ? " selected" : ""}>Daily mean temperature</option>
          <option value="gps_walk"${sensorDemo === "gps_walk" ? " selected" : ""}>GPS walk path</option>
          <option value="gforce"${sensorDemo === "gforce" ? " selected" : ""}>G-force log</option>
        </select>`)}
        ${field("Mode", `<select id="sensor_mode">
          <option value="ribbon"${sensorMode === "ribbon" ? " selected" : ""}>Ribbon (asymmetric)</option>
          <option value="mirror"${sensorMode === "mirror" ? " selected" : ""}>Mirror (bilateral)</option>
          <option value="radial"${sensorMode === "radial" ? " selected" : ""}>Radial</option>
          <option value="spiral"${sensorMode === "spiral" ? " selected" : ""}>Spiral (pattern)</option>
          <option value="path"${sensorMode === "path" ? " selected" : ""}>Path (GPS / XY)</option>
          <option value="mandala"${sensorMode === "mandala" ? " selected" : ""}>Mandala (n-fold)</option>
        </select>`)}
        ${field("Mandala folds", `<input id="sensor_folds" type="number" min="3" max="16" value="${sensorFolds}" />`)}
        ${field("Upload CSV / JSON", `<input id="sensor_file" type="file" accept=".csv,.json,text/csv,application/json" />`)}
        <div class="row actions">
          <button type="button" class="btn" id="sensor-demo">Draw demo</button>
          <button type="button" class="btn btn-primary" id="sensor-upload">Draw upload</button>
        </div>
      </div>
    </div>
    ${commonDevOpts()}
    <div class="group">
      <div class="group-block">
        <div class="group-title">Kinematics</div>
        ${field("Turntable RPM", `<input id="rpm" type="number" step="0.5" value="${state.rpm}" />`)}
      </div>
    </div>
    <div class="row actions">
      <button type="button" class="btn" id="rd-ingest">Ingest</button>
      <button type="button" class="btn btn-primary primary" id="go">Run &amp; Inspect</button>
    </div>
  `;
  bindStyleGrid();
  applyCommonDefaults();

  const syncSensorState = () => {
    state.sensor_demo = controls.querySelector("#sensor_demo")?.value || "temperature";
    state.sensor_mode = controls.querySelector("#sensor_mode")?.value || "ribbon";
    const foldsRaw = Number(controls.querySelector("#sensor_folds")?.value);
    state.sensor_folds = Number.isFinite(foldsRaw) ? foldsRaw : 6;
  };

  const sensorFormData = () => {
    syncStateFromForm();
    syncSensorState();
    const fd = new FormData();
    fd.append("mode", state.sensor_mode);
    fd.append("seed", String(state.seed));
    fd.append("palette_id", selectedPaletteId);
    fd.append("quality", state.quality);
    fd.append("density", String(state.density));
    fd.append("paper", state.paper);
    fd.append("orientation", state.orientation || "portrait");
    fd.append("folds", String(state.sensor_folds));
    return fd;
  };

  controls.querySelector("#sensor-demo").onclick = async () => {
    const fd = sensorFormData();
    fd.append("demo_id", state.sensor_demo);
    statsEl.textContent = "Sensor demo…";
    setDeskState({ loading: true, empty: false, hint: "Mapping sensor data…" });
    try {
      const data = await api("/api/rdlab/sensor/demo", { method: "POST", body: fd });
      loadResult(data);
      const meta = data.layers?.meta || {};
      statsEl.textContent = `${meta.label || "Sensor"} · ${meta.mode} · ${meta.n || "?"} pts · ${meta.strokes || "?"} strokes`;
    } catch (e) {
      setDeskState({ loading: false });
      statsEl.textContent = String(e.message || e);
      console.error(e);
    }
  };

  controls.querySelector("#sensor-upload").onclick = async () => {
    const file = controls.querySelector("#sensor_file")?.files?.[0];
    if (!file) {
      statsEl.textContent = "Choose a CSV or JSON sensor file first";
      return;
    }
    const fd = sensorFormData();
    fd.append("file", file);
    statsEl.textContent = "Sensor upload…";
    setDeskState({ loading: true, empty: false, hint: "Mapping sensor data…" });
    try {
      const data = await api("/api/rdlab/sensor/upload", { method: "POST", body: fd });
      loadResult(data);
      const meta = data.layers?.meta || {};
      statsEl.textContent = `${meta.label || file.name} · ${meta.mode} · ${meta.n || "?"} pts · ${meta.strokes || "?"} strokes`;
    } catch (e) {
      setDeskState({ loading: false });
      statsEl.textContent = String(e.message || e);
      console.error(e);
    }
  };

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

let lastD3LabResult = null;

function renderTools() {
  const families = (window.BotDrawD3Lab && BotDrawD3Lab.FAMILIES) || [];
  const familyOpts = families
    .map((f) => `<option value="${f.id}">${f.name}</option>`)
    .join("");
  controls.innerHTML = `
    <h3>Tools</h3>
    <p class="muted">Audio / handwriting / D3 Pattern Lab / plot stub / job reload.</p>

    <h4>D3 Pattern Lab</h4>
    <p class="muted">Live D3 preview → polylines → emulator. Full GenArt catalog also lists Python pattern engines.</p>
    ${field("Family", `<select id="d3-family">${familyOpts}</select>`)}
    ${field("Seed", `<input id="d3-seed" type="number" value="${state.seed}" />`)}
    ${field("Density", `<input id="d3-density" type="number" step="0.1" min="0.3" max="2.5" value="${state.density}" />`)}
    ${field("Paper", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
    ${field("Orientation", `<select id="orientation"><option value="portrait">portrait</option><option value="landscape">landscape</option></select>`)}
    ${field("Palette", paletteSelectHtml())}
    <div class="d3-lab-preview" id="d3-preview-wrap">
      <svg id="d3-preview" xmlns="http://www.w3.org/2000/svg" aria-label="D3 pattern preview"></svg>
    </div>
    <div class="row">
      <button id="d3-preview-btn">Preview</button>
      <button class="primary" id="d3-send">Send to emulator</button>
    </div>

    <h4>Audio / handwriting</h4>
    ${field("Upload WAV", `<input id="wav" type="file" accept="audio/wav,audio/*" />`)}
    <div class="row"><button class="primary" id="audio">Audio → Vector</button></div>
    <div class="row"><button id="hw">Handwriting HELLO</button></div>
    ${field("Load job id", `<input id="jobid" placeholder="${lastJob?.id || ""}" />`)}
    <div class="row"><button id="load-job">Load job into lab</button></div>
    <div class="row"><button id="stub">AxiDraw stub on last/job</button></div>
  `;
  const paper = controls.querySelector("#paper");
  if (paper) paper.value = state.paper;
  const orientation = controls.querySelector("#orientation");
  if (orientation) orientation.value = state.orientation;

  function syncToolsState() {
    if (controls.querySelector("#paper")) state.paper = val("paper", state.paper);
    if (controls.querySelector("#orientation")) state.orientation = val("orientation", state.orientation);
    if (controls.querySelector("#palette")) selectedPaletteId = val("palette", selectedPaletteId);
  }

  function runD3Preview() {
    if (!window.BotDrawD3Lab || !window.d3) {
      statsEl.textContent = "D3 Pattern Lab failed to load";
      return null;
    }
    syncToolsState();
    const seed = Number(val("d3-seed", state.seed));
    const density = Number(val("d3-density", state.density));
    const family = val("d3-family", "voronoi");
    const palette = currentPalette();
    try {
      lastD3LabResult = BotDrawD3Lab.generate({
        family,
        seed,
        density,
        paper: state.paper,
        orientation: state.orientation,
        palette,
      });
      BotDrawD3Lab.renderPreview(controls.querySelector("#d3-preview"), lastD3LabResult, palette);
      const n = lastD3LabResult.passes.reduce((a, p) => a + p.polylines.length, 0);
      statsEl.textContent = `D3 ${family} · ${n} strokes · seed ${seed}`;
      return lastD3LabResult;
    } catch (err) {
      statsEl.textContent = `D3 preview error: ${err.message || err}`;
      return null;
    }
  }

  controls.querySelector("#d3-preview-btn").onclick = () => runD3Preview();
  ["d3-family", "d3-seed", "d3-density", "paper", "orientation", "palette"].forEach((id) => {
    const el = controls.querySelector(`#${id}`);
    if (el) el.addEventListener("change", () => runD3Preview());
  });
  runD3Preview();

  controls.querySelector("#d3-send").onclick = () =>
    withBusy("#d3-send", async () => {
      const result = lastD3LabResult || runD3Preview();
      if (!result) return;
      syncToolsState();
      statsEl.textContent = "Sending D3 lab → pipeline…";
      const data = await api("/api/render/polylines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app: "tools",
          style_id: "d3_lab",
          palette_id: selectedPaletteId,
          paper: state.paper,
          orientation: state.orientation,
          quality: state.quality,
          seed: Number(val("d3-seed", state.seed)),
          density: Number(val("d3-density", state.density)),
          params_extra: { family: result.family },
          passes: result.passes,
        }),
      });
      loadResult(data);
    });

  controls.querySelector("#audio").onclick = () =>
    withBusy("#audio", async () => {
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
    });
  controls.querySelector("#hw").onclick = () =>
    withBusy("#hw", async () => {
      await api("/api/handwriting/samples", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "demo",
          glyphs: {
            H: [[[0, 0], [0, 10]], [[0, 5], [6, 5]], [[6, 0], [6, 10]]],
            E: [[[0, 0], [0, 10], [6, 10]], [[0, 5], [5, 5]], [[0, 0], [6, 0]]],
            L: [[[0, 0], [0, 10], [6, 10]]],
            O: [[[1, 0], [5, 0], [7, 2], [7, 8], [5, 10], [1, 10], [-1, 8], [-1, 2], [1, 0]]],
          },
        }),
      });
      const data = await api("/api/handwriting/render?user_id=demo&text=HELLO", { method: "POST" });
      loadResult(data);
    });
  controls.querySelector("#load-job").onclick = () =>
    withBusy("#load-job", async () => {
      const id = val("jobid") || lastJob?.id;
      if (!id) {
        statsEl.textContent = "No job id";
        return;
      }
      const data = await api(`/api/jobs/${id}`);
      loadResult(data);
    });
  controls.querySelector("#stub").onclick = () =>
    withBusy("#stub", async () => {
      const id = val("jobid") || lastJob?.id;
      if (!id) {
        statsEl.textContent = "Render or load a job first";
        return;
      }
      const data = await api(`/api/plot/stub?job_id=${id}`, { method: "POST" });
      statsEl.textContent = `Stub ok · emu ${data.emulator_run.elapsed_s.toFixed(2)}s`;
    });
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
  if (currentApp === "fractalbot") return renderFractal();
  if (currentApp === "design") return renderDesignLibrary();
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

function wireSharedPlayers() {
  [player, lettersPlayer, portraitPlayer].forEach((emu) => {
    emu.onZoomChange = (z) => {
      if (emu === stagePlayer()) syncZoomLabel(z);
    };
    emu.enableInteraction();
    emu.syncSize();
  });
}

wireSharedPlayers();
setShellForApp(currentApp);

renderControls().catch((e) => {
  statsEl.textContent = String(e);
  console.error(e);
});
