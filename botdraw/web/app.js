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
  player.load(lastPayload);
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
    draft: data.draft,
  };
  renderInspector();
  if (autoplay) player.play();
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

function renderGenArt() {
  const list = styles.filter((s) => ["artistic", "pattern", "technical"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "stipple";
  controls.innerHTML = `
    <h3>GenArtBot · Dev</h3>
    <p class="muted">Tune vectorization + multicolor layers, then inspect / export JSON.</p>
    <h4>Style</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    <div class="row"><button class="primary" id="go">Render &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    renderWithSettings({ appName: "genartbot", busyText: "Rendering GenArt…" });
}

function renderPortrait() {
  const list = styles.filter((s) => s.category === "portrait");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "portrait_linework";
  controls.innerHTML = `
    <h3>PortraitBot · Dev</h3>
    <p class="muted">Face/image → style engine → palette-quantized layers.</p>
    <h4>Portrait style</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    <div class="row"><button class="primary" id="go">Capture &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
  controls.querySelector("#go").onclick = () =>
    renderWithSettings({ appName: "portraitbot", busyText: "Rendering portrait…" });
}

function renderLetters() {
  controls.innerHTML = `
    <h3>LettersBot · Dev</h3>
    <p class="muted">Stroke-font layout is fast. Slowdowns are usually local AI draft or emulator playback.</p>
    ${field("Names", `<input id="names" value="Aanya & Kabir" />`)}
    <div class="grid-2">
      ${field("Language", `<select id="lang"><option value="en">en</option><option value="hi">hi</option><option value="pa">pa</option><option value="ur">ur</option></select>`)}
      ${field("Era", `<select id="era"><option>golden</option><option>70s</option><option selected>90s</option><option>2000s</option><option>contemporary</option></select>`)}
    </div>
    ${field("Mood", `<input id="mood" value="romantic" />`)}
    ${field("Facts", `<textarea id="facts">Met at a cousin's wedding.</textarea>`)}
    ${field("Guest quote", `<textarea id="quote" placeholder="Paste lyric/line"></textarea>`)}
    ${field("Or paste letter body (skips draft)", `<textarea id="body" placeholder="Leave empty to auto-draft"></textarea>`)}
    <div class="row" style="gap:1rem;flex-wrap:wrap;margin:0.5rem 0">
      <label><input id="use_llm" type="checkbox" /> Use local AI draft (slow if Ollama cold)</label>
      <label><input id="highlight" type="checkbox" checked /> Highlighter pass</label>
    </div>
    <h4>Palette</h4>
    ${field("Palette", paletteSelectHtml())}
    ${penChipsHtml(currentPalette())}
    ${field("Seed", `<input id="seed" type="number" value="${state.seed}" />`)}
    <div class="row"><button class="primary" id="go">Draft &amp; Inspect</button></div>
  `;
  applyCommonDefaults();
  controls.querySelector("#go").onclick = async () => {
    selectedPaletteId = val("palette", selectedPaletteId);
    const useLlm = !!controls.querySelector("#use_llm")?.checked;
    const bodyText = val("body").trim();
    statsEl.textContent = bodyText
      ? "Vectorizing pasted text…"
      : useLlm
        ? "Drafting with Ollama (can take a while)…"
        : "Template draft + vectorize…";
    const t0 = performance.now();
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
        body: bodyText || null,
        use_llm: useLlm,
        highlight: !!controls.querySelector("#highlight")?.checked,
        optimize: false,
        palette_id: selectedPaletteId,
        seed: num("seed", 7),
      }),
    });
    loadResult(data, { autoplay: false });
    player.skipEnd();
    const timing = data.settings?.timing_s || {};
    const src = data.draft?.source || data.settings?.draft_source || "?";
    const wall = ((performance.now() - t0) / 1000).toFixed(2);
    statsEl.textContent =
      `Ready · source=${src} · draft ${timing.draft ?? "?"}s · vector ${timing.vectorize ?? "?"}s · wall ${wall}s · Play to scrub plot`;
  };
}

function renderRdlab() {
  const list = styles.filter((s) => ["backlog", "pattern"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = "spiral";
  controls.innerHTML = `
    <h3>R&amp;D Lab · Dev</h3>
    <p class="muted">Experimental motifs + rotating-base kinematics.</p>
    <h4>Experiment</h4>
    ${styleButtons(list)}
    ${commonDevOpts()}
    ${field("Turntable RPM", `<input id="rpm" type="number" step="0.5" value="${state.rpm}" />`)}
    <div class="row"><button class="primary" id="go">Run &amp; Inspect</button></div>
  `;
  bindStyleGrid();
  applyCommonDefaults();
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
    <h3>Palette Lab</h3>
    <p class="muted">Edit established palettes and save as a new JSON preset for renders.</p>
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
  if (currentApp === "genartbot") return renderGenArt();
  if (currentApp === "portraitbot") return renderPortrait();
  if (currentApp === "lettersbot") return renderLetters();
  if (currentApp === "rdlab") return renderRdlab();
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

renderControls().catch((e) => {
  statsEl.textContent = String(e);
  console.error(e);
});
