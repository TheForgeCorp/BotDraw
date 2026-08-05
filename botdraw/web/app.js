const player = new EmulatorPlayer(document.getElementById("emu"));
const statsEl = document.getElementById("stats");
const controls = document.getElementById("controls");
const inspectorBody = document.getElementById("inspector-body");
const downloadSvg = document.getElementById("download-svg");
player.onStats = (m) => { statsEl.textContent = m; };

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

const state = {
  paper: "A4",
  orientation: "portrait",
  quality: "booth-balanced",
  seed: 42,
  density: 1.0,
  pen_up_speed_mm_s: 100,
  pen_down_speed_mm_s: 25,
  rpm: 3,
};

/* ---------------- transport ---------------- */

const playToggle = document.getElementById("play-toggle");
const iconPlay = playToggle.querySelector(".i-play");
const iconPause = playToggle.querySelector(".i-pause");
const scrub = document.getElementById("scrub");
const timeNow = document.getElementById("time-now");
const timeTotal = document.getElementById("time-total");
const ghostBtn = document.getElementById("ghost-btn");

function fmtTime(s) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function setPlayIcon(playing) {
  iconPlay.hidden = playing;
  iconPause.hidden = !playing;
  playToggle.setAttribute("aria-label", playing ? "Pause" : "Play");
}

playToggle.onclick = () => player.toggle();
document.getElementById("skip").onclick = () => player.skipEnd();
document.getElementById("fit").onclick = () => player.fitView();

player.onPlayState = setPlayIcon;
player.onTime = (t, total, playing) => {
  timeNow.textContent = fmtTime(t);
  timeTotal.textContent = fmtTime(total);
  const p = total > 0 ? (t / total) * 100 : 0;
  scrub.value = String(Math.round(p * 10));
  scrub.style.setProperty("--p", p);
  setPlayIcon(playing);
};

scrub.addEventListener("input", () => {
  player.seekFraction(Number(scrub.value) / 1000);
});

document.querySelectorAll("#speed-seg button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#speed-seg button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    player.setSpeed(btn.dataset.speed);
  };
});

function toggleGhost() {
  const on = ghostBtn.getAttribute("aria-pressed") !== "true";
  ghostBtn.setAttribute("aria-pressed", String(on));
  ghostBtn.classList.toggle("active", on);
  player.setGhost(on);
}
ghostBtn.onclick = toggleGhost;

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
  const b = typeof btn === "string" ? controls.querySelector(btn) : btn;
  if (b) {
    b.classList.add("loading");
    b.disabled = true;
  }
  try {
    return await fn();
  } catch (e) {
    statsEl.textContent = String(e.message || e);
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

function loadResult(data) {
  if (!data) return;
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
  player.load(lastPayload);
  scrub.disabled = false;
  if (lastJob?.id) {
    downloadSvg.hidden = false;
    downloadSvg.href = `/api/jobs/${lastJob.id}/svg`;
  }
  setExportEnabled(true);
  inspectorJson = {
    settings: lastSettings,
    layers: lastLayers,
    stats: lastPayload?.stats,
    job: lastJob,
  };
  renderInspector();
  player.play();
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
    <h4>Page</h4>
    <div class="grid-2">
      ${field("Paper", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
      ${field("Orientation", segHtml("orient", [
        { value: "portrait", label: "Portrait" },
        { value: "landscape", label: "Landscape" },
      ], state.orientation))}
    </div>
    <h4>Render</h4>
    ${field("Quality", segHtml("quality-seg", [
      { value: "booth-fast", label: "Fast" },
      { value: "booth-balanced", label: "Balanced" },
      { value: "studio-hq", label: "HQ" },
    ], state.quality))}
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
    <h4>Input</h4>
    ${field("Upload image (optional)", `<input id="photo" type="file" accept="image/*" />`)}
    ${field("Import settings JSON", `<input id="import-settings" type="file" accept="application/json,.json" />`)}
  `;
}

function applyCommonDefaults() {
  const paper = controls.querySelector("#paper");
  if (paper) paper.value = state.paper;
  bindSeg("orient", (v) => { state.orientation = v; });
  bindSeg("quality-seg", (v) => { state.quality = v; });
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
    fd.append("orientation", state.orientation);
    fd.append("seed", String(state.seed));
    fd.append("density", String(state.density));
    fd.append("pen_up_speed_mm_s", String(state.pen_up_speed_mm_s));
    fd.append("pen_down_speed_mm_s", String(state.pen_down_speed_mm_s));
    if (extraFormData) Object.entries(extraFormData).forEach(([k, v]) => fd.append(k, v));
    data = await api("/api/render/upload", { method: "POST", body: fd });
  } else {
    data = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app: appName,
        style_id: selectedStyle,
        palette_id: selectedPaletteId,
        paper: state.paper,
        orientation: state.orientation,
        quality: state.quality,
        seed: state.seed,
        density: state.density,
        pen_up_speed_mm_s: state.pen_up_speed_mm_s,
        pen_down_speed_mm_s: state.pen_down_speed_mm_s,
      }),
    });
  }
  loadResult(data);
}

/* ---------------- app views ---------------- */

function renderGenArt() {
  const list = styles.filter((s) => ["artistic", "pattern", "technical"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "stipple";
  controls.innerHTML = `
    <h3>GenArtBot</h3>
    <p class="muted">Tune vectorization + multicolor layers, then inspect / export JSON.</p>
    <h4>Style</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    <div class="row"><button class="primary" id="go">Render &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", () => renderWithSettings({ appName: "genartbot", busyText: "Rendering GenArt…" }));
}

function fractalDevOpts() {
  return `
    <h4>Page</h4>
    <div class="grid-2">
      ${field("Paper", `<select id="paper"><option>A4</option><option>Letter</option><option>A3</option><option>A5</option><option>Card</option></select>`)}
      ${field("Orientation", segHtml("orient", [
        { value: "portrait", label: "Portrait" },
        { value: "landscape", label: "Landscape" },
      ], state.orientation))}
    </div>
    <h4>Render</h4>
    ${field("Quality", segHtml("quality-seg", [
      { value: "booth-fast", label: "Fast" },
      { value: "booth-balanced", label: "Balanced" },
      { value: "studio-hq", label: "HQ" },
    ], state.quality))}
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
    <h4>Input</h4>
    ${field("Import settings JSON", `<input id="import-settings" type="file" accept="application/json,.json" />`)}
  `;
}

function renderFractal() {
  const list = styles.filter((s) => s.category === "fractal");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "hilbert_curve";
  controls.innerHTML = `
    <h3>Fractal</h3>
    <p class="muted">Escape-time + single-stroke space-filling / L-system curves for plotter wall art.</p>
    <div class="fractal-ref">
      <img src="/static/previews/single_line_fractals.png" alt="Single-line fractal family" />
    </div>
    <h4>Style</h4>
    ${styleButtons(list)}
    ${fractalDevOpts()}
    <div class="row"><button class="primary" id="go">Render &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", () => renderWithSettings({ appName: "fractalbot", busyText: "Rendering fractal…" }));
}

function designLibraryParams() {
  if (selectedStyle === "phyllotaxis") {
    return {
      n_points: Number(controls.querySelector("#phy-points")?.value || 900),
      angle_deg: Number(controls.querySelector("#phy-angle")?.value || 137.5),
    };
  }
  if (selectedStyle === "modular_chords") {
    return {
      n_points: Number(controls.querySelector("#mod-n")?.value || 200),
      k: Number(controls.querySelector("#mod-k")?.value || 77),
    };
  }
  if (selectedStyle === "prime_sieve") {
    return {
      max_n: Number(controls.querySelector("#sieve-n")?.value || 212),
      grid_cols: Number(controls.querySelector("#sieve-cols")?.value || 6),
      show_arcs: !!controls.querySelector("#sieve-arcs")?.checked,
      show_sieve: !!controls.querySelector("#sieve-grid")?.checked,
    };
  }
  return {
    cols: Number(controls.querySelector("#ca-cols")?.value || 120),
    rows: Number(controls.querySelector("#ca-rows")?.value || 90),
    rule: Number(controls.querySelector("#ca-rule")?.value || 30),
  };
}

function designLibraryKnobsHtml() {
  if (selectedStyle === "phyllotaxis") {
    return `
      <h4>Sunflower</h4>
      <p class="muted">r = c√n · θ = n × golden angle — Fibonacci spiral families.</p>
      <div class="grid-2">
        ${field("Points", `<input id="phy-points" type="number" min="50" max="4000" value="900" />`)}
        ${field("Angle °", `<input id="phy-angle" type="number" min="1" max="179" step="0.1" value="137.5" />`)}
      </div>
    `;
  }
  if (selectedStyle === "modular_chords") {
    return `
      <h4>Circle steps</h4>
      <p class="muted">i → (i + k) mod N — petals from periodicity, dense ring from chord interference.</p>
      <div class="grid-2">
        ${field("N points", `<input id="mod-n" type="number" min="12" max="2000" value="200" />`)}
        ${field("Step k", `<input id="mod-k" type="number" min="1" max="1999" value="77" />`)}
      </div>
    `;
  }
  if (selectedStyle === "prime_sieve") {
    return `
      <h4>Prime sieve</h4>
      <p class="muted">Left: arc spire between primes. Right: circled primes / struck composites. Cols=6 → vertical lanes.</p>
      <div class="grid-2">
        ${field("Max n", `<input id="sieve-n" type="number" min="10" max="2000" value="212" />`)}
        ${field("Grid cols", `<input id="sieve-cols" type="number" min="2" max="20" value="6" />`)}
      </div>
      <div class="chk-row">
        <label><input id="sieve-arcs" type="checkbox" checked /> Arc spire</label>
        <label><input id="sieve-grid" type="checkbox" checked /> Sieve grid</label>
      </div>
    `;
  }
  return `
    <h4>Automaton</h4>
    <div class="grid-2">
      ${field("Cols", `<input id="ca-cols" type="number" min="16" max="400" value="120" />`)}
      ${field("Rows", `<input id="ca-rows" type="number" min="12" max="300" value="90" />`)}
    </div>
    ${field("Rule", `<input id="ca-rule" type="number" min="0" max="255" value="30" />`)}
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
  const list = styles.filter((s) => s.category === "portrait");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "portrait_linework";
  controls.innerHTML = `
    <h3>PortraitBot</h3>
    <p class="muted">Face/image → style engine → palette-quantized layers.</p>
    <h4>Portrait style</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    <div class="row"><button class="primary" id="go">Capture &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", () => renderWithSettings({ appName: "portraitbot", busyText: "Rendering portrait…" }));
}

function renderLetters() {
  controls.innerHTML = `
    <h3>LettersBot</h3>
    <p class="muted">Ink pass + highlighter overlay pass. Export settings/layers as JSON.</p>
    ${field("Names", `<input id="names" value="Aanya & Kabir" />`)}
    <div class="grid-2">
      ${field("Language", `<select id="lang"><option value="en">en</option><option value="hi">hi</option><option value="pa">pa</option><option value="ur">ur</option></select>`)}
      ${field("Era", `<select id="era"><option>golden</option><option>70s</option><option selected>90s</option><option>2000s</option><option>contemporary</option></select>`)}
    </div>
    ${field("Mood", `<input id="mood" value="romantic" />`)}
    ${field("Facts", `<textarea id="facts">Met at a cousin's wedding.</textarea>`)}
    ${field("Guest quote", `<textarea id="quote" placeholder="Paste lyric/line"></textarea>`)}
    <h4>Palette</h4>
    ${field("Palette", paletteSelectHtml())}
    ${penChipsHtml(currentPalette())}
    ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
    <div class="row"><button class="primary" id="go">Draft &amp; Inspect</button></div>
  `;
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", async () => {
      selectedPaletteId = val("palette", selectedPaletteId);
      statsEl.textContent = "Drafting letter…";
      const data = await api("/api/letters/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          names: val("names"),
          language: val("lang"),
          era: val("era"),
          mood: val("mood"),
          facts: val("facts"),
          guest_quote: val("quote") || null,
          highlight: true,
          palette_id: selectedPaletteId,
          seed: num("seed", 7),
        }),
      });
      loadResult(data);
    });
}

function renderRdlab() {
  const list = styles.filter((s) => ["backlog", "pattern"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = "spiral";
  controls.innerHTML = `
    <h3>R&amp;D Lab</h3>
    <p class="muted">Experimental motifs + rotating-base kinematics.</p>
    <h4>Experiment</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    ${field("Turntable RPM", `<input id="rpm" type="number" step="0.5" value="${state.rpm}" />`)}
    <div class="row"><button class="primary" id="go">Run &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    withBusy("#go", async () => {
      syncStateFromForm();
      const file = controls.querySelector("#photo")?.files?.[0];
      const fd = new FormData();
      fd.append("style_id", selectedStyle);
      fd.append("rpm", String(state.rpm));
      fd.append("seed", String(state.seed));
      fd.append("palette_id", selectedPaletteId);
      fd.append("quality", state.quality);
      fd.append("density", String(state.density));
      fd.append("orientation", state.orientation);
      if (file) fd.append("file", file);
      statsEl.textContent = "R&D render…";
      const data = await api("/api/rdlab/render", { method: "POST", body: fd });
      loadResult(data);
    });
}

function renderPalettes() {
  const palette = currentPalette();
  const penBlock = (pen, idx) => `
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
          ${["fineliner", "marker", "brush", "calligraphy", "highlighter"].map((n) =>
            `<option ${((pen.profile?.nib_type) || "fineliner") === n ? "selected" : ""}>${n}</option>`
          ).join("")}
        </select>`)}
      </div>
    </div>
  `;

  controls.innerHTML = `
    <h3>Palette Lab</h3>
    <p class="muted">Edit established palettes and save as a new JSON preset for renders.</p>
    ${field("Load palette", paletteSelectHtml())}
    ${penChipsHtml(palette)}
    ${field("New palette id", `<input id="new_id" value="${palette?.id || "custom"}-dev" />`)}
    ${field("Name", `<input id="new_name" value="${palette?.name || "Custom"} (edited)" />`)}
    ${field("Paper notes", `<input id="paper_notes" value="${palette?.paper_notes || ""}" />`)}
    <div class="pen-editor" id="pen-editor">${(palette?.pens || []).map(penBlock).join("")}</div>
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
    editor.insertAdjacentHTML(
      "beforeend",
      penBlock(
        {
          id: `pen${idx + 1}`,
          name: `Pen ${idx + 1}`,
          color_hex: "#336699",
          profile: { width_mm: 0.5, opacity: 1, nib_type: "fineliner" },
        },
        idx
      )
    );
  };
  controls.querySelector("#save-pal").onclick = () =>
    withBusy("#save-pal", async () => {
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
    });
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

/* ---------------- inspector ---------------- */

const EYE_SVG = `<svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true">
  <path d="M1.2 7.5S3.6 3.4 7.5 3.4s6.3 4.1 6.3 4.1-2.4 4.1-6.3 4.1S1.2 7.5 1.2 7.5z" fill="none" stroke="currentColor" stroke-width="1.3"/>
  <circle class="pupil" cx="7.5" cy="7.5" r="1.9" fill="currentColor"/>
  <path class="strike" d="M2.5 12.5l10-10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
</svg>`;

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
          <button type="button" class="vis" data-pass="${p.id}"
            aria-pressed="${player.hiddenPassIds.has(p.id) ? "false" : "true"}"
            aria-label="Toggle ${p.name}">${EYE_SVG}</button>
          <span class="swatch" style="background:${p.color_hex}; opacity:${p.opacity}"></span>
          <div>
            <div><strong>${p.name}</strong> <span class="muted">${p.kind}</span></div>
            <div class="layer-meta">${p.pen_id} · ${p.color_hex} · ${p.width_mm}mm · ${p.nib_type} · polys ${p.polyline_count} · pts ${p.point_count}</div>
          </div>
          <button type="button" class="solo-btn" data-solo="${p.id}">Solo</button>
        </div>
      `).join("")}
    `;
    inspectorBody.querySelectorAll(".vis").forEach((btn) => {
      btn.onclick = () => {
        const visible = btn.getAttribute("aria-pressed") !== "true";
        btn.setAttribute("aria-pressed", String(visible));
        player.setPassVisible(btn.dataset.pass, visible);
      };
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
  if (currentApp === "genartbot") return renderGenArt();
  if (currentApp === "fractalbot") return renderFractal();
  if (currentApp === "design") return renderDesignLibrary();
  if (currentApp === "portraitbot") return renderPortrait();
  if (currentApp === "lettersbot") return renderLetters();
  if (currentApp === "rdlab") return renderRdlab();
  if (currentApp === "palettes") return renderPalettes();
  return renderTools();
}

/* ---------------- export bar ---------------- */

const moreBtn = document.getElementById("export-more");
const exportMenu = document.getElementById("export-menu");

function closeMenu() {
  exportMenu.hidden = true;
  moreBtn.setAttribute("aria-expanded", "false");
}

moreBtn.onclick = (e) => {
  e.stopPropagation();
  const open = exportMenu.hidden;
  exportMenu.hidden = !open;
  moreBtn.setAttribute("aria-expanded", String(open));
};

document.addEventListener("click", (e) => {
  if (!exportMenu.hidden && !exportMenu.contains(e.target) && e.target !== moreBtn) closeMenu();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeMenu();
});

document.getElementById("export-pack").onclick = async () => {
  if (!lastJob?.id) return;
  const pack = await api(`/api/jobs/${lastJob.id}/export`);
  downloadJson(`botdraw-${lastJob.id}-pack.json`, pack);
};
document.getElementById("export-settings").onclick = () => {
  closeMenu();
  const settings = lastSettings || {
    app: currentApp,
    style_id: selectedStyle,
    palette_id: selectedPaletteId,
    ...state,
  };
  downloadJson(`botdraw-settings.json`, settings);
};
document.getElementById("export-layers").onclick = async () => {
  closeMenu();
  if (lastLayers) return downloadJson(`botdraw-${lastJob?.id || "layers"}.json`, lastLayers);
  if (lastJob?.id) downloadJson(`botdraw-${lastJob.id}-layers.json`, await api(`/api/jobs/${lastJob.id}/layers`));
};
document.getElementById("export-motion").onclick = async () => {
  closeMenu();
  if (!lastJob?.id) return;
  downloadJson(`botdraw-${lastJob.id}-motion.json`, await api(`/api/jobs/${lastJob.id}/motion`));
};
document.getElementById("export-palette").onclick = () => {
  closeMenu();
  const pal = currentPalette();
  if (pal) downloadJson(`${pal.id}.json`, pal);
};
document.getElementById("copy-json").onclick = async () => {
  closeMenu();
  const text = JSON.stringify(inspectorJson || lastSettings || {}, null, 2);
  await navigator.clipboard.writeText(text);
  statsEl.textContent = "Copied inspector JSON";
};

renderControls().catch((e) => {
  statsEl.textContent = String(e);
  console.error(e);
});
