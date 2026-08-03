const player = new EmulatorPlayer(document.getElementById("emu"));
const statsEl = document.getElementById("stats");
const controls = document.getElementById("controls");
const downloadSvg = document.getElementById("download-svg");
player.onStats = (m) => { statsEl.textContent = m; };

let currentApp = "genartbot";
let styles = [];
let selectedStyle = "stipple";
let lastJobId = null;

document.getElementById("play").onclick = () => player.play();
document.getElementById("pause").onclick = () => player.pause();
document.getElementById("skip").onclick = () => player.skipEnd();
document.getElementById("speed").oninput = (e) => player.setSpeed(e.target.value);

document.querySelectorAll("#tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentApp = btn.dataset.app;
    renderControls();
  };
});

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function field(label, html) {
  return `<label>${label}</label>${html}`;
}

function loadIntoPlayer(payload, job) {
  player.load(payload);
  lastJobId = job?.id || null;
  if (lastJobId) {
    downloadSvg.hidden = false;
    downloadSvg.href = `/api/jobs/${lastJobId}/svg`;
  }
}

async function renderControls() {
  if (!styles.length) {
    styles = await api("/api/styles");
  }
  if (currentApp === "genartbot") return renderGenArt();
  if (currentApp === "portraitbot") return renderPortrait();
  if (currentApp === "lettersbot") return renderLetters();
  if (currentApp === "rdlab") return renderRdlab();
  return renderTools();
}

function styleButtons(list, selected) {
  return `<div class="style-grid">${list.map((s) =>
    `<button type="button" data-style="${s.id}" class="${s.id === selected ? "selected" : ""}"><strong>${s.name}</strong><div class="muted">${s.id}</div></button>`
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

function commonOpts() {
  return `
    ${field("Palette", `<select id="palette"><option>default-6</option><option>blueprint-3</option><option>wedding-highlight</option></select>`)}
    ${field("Quality", `<select id="quality"><option value="booth-fast">booth-fast</option><option value="booth-balanced" selected>booth-balanced</option><option value="studio-hq">studio-hq</option></select>`)}
    ${field("Seed", `<input id="seed" type="number" value="42" />`)}
    ${field("Density", `<input id="density" type="number" step="0.1" value="1.0" />`)}
  `;
}

function renderGenArt() {
  const list = styles.filter((s) => ["artistic", "pattern", "technical"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "stipple";
  controls.innerHTML = `
    <h3>GenArtBot</h3>
    <p class="muted">Multicolor generative styles → SVG → emulator</p>
    ${styleButtons(list, selectedStyle)}
    ${commonOpts()}
    <div class="row"><button class="primary" id="go">Render &amp; Emulate</button></div>
  `;
  bindStyleGrid();
  controls.querySelector("#go").onclick = async () => {
    const body = {
      app: "genartbot",
      style_id: selectedStyle,
      palette_id: controls.querySelector("#palette").value,
      quality: controls.querySelector("#quality").value,
      seed: Number(controls.querySelector("#seed").value),
      density: Number(controls.querySelector("#density").value),
    };
    statsEl.textContent = "Rendering…";
    const data = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
}

function renderPortrait() {
  const list = styles.filter((s) => s.category === "portrait");
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = list[0]?.id || "portrait_linework";
  controls.innerHTML = `
    <h3>PortraitBot</h3>
    <p class="muted">Multi-style portrait gallery. Event default falls back to booth-fast if needed.</p>
    ${styleButtons(list, selectedStyle)}
    ${commonOpts()}
    ${field("Upload photo (optional)", `<input id="photo" type="file" accept="image/*" />`)}
    <div class="row"><button class="primary" id="go">Capture Style</button></div>
  `;
  bindStyleGrid();
  controls.querySelector("#go").onclick = async () => {
    const file = controls.querySelector("#photo").files[0];
    statsEl.textContent = "Rendering portrait…";
    let data;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("style_id", selectedStyle);
      fd.append("app_name", "portraitbot");
      fd.append("palette_id", controls.querySelector("#palette").value);
      fd.append("quality", controls.querySelector("#quality").value);
      fd.append("seed", controls.querySelector("#seed").value);
      fd.append("density", controls.querySelector("#density").value);
      data = await api("/api/render/upload", { method: "POST", body: fd });
    } else {
      data = await api("/api/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app: "portraitbot",
          style_id: selectedStyle,
          palette_id: controls.querySelector("#palette").value,
          quality: controls.querySelector("#quality").value,
          seed: Number(controls.querySelector("#seed").value),
          density: Number(controls.querySelector("#density").value),
        }),
      });
    }
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
}

function renderLetters() {
  controls.innerHTML = `
    <h3>LettersBot</h3>
    <p class="muted">Wedding love letters · EN/HI/PA/UR · guest quote · highlight passes</p>
    ${field("Names", `<input id="names" value="Aanya & Kabir" />`)}
    ${field("Language", `<select id="lang"><option value="en">English</option><option value="hi">Hindi</option><option value="pa">Punjabi</option><option value="ur">Urdu</option></select>`)}
    ${field("Era", `<select id="era"><option>golden</option><option>70s</option><option selected>90s</option><option>2000s</option><option>contemporary</option></select>`)}
    ${field("Mood", `<input id="mood" value="romantic" />`)}
    ${field("Facts", `<textarea id="facts">Met at a cousin's wedding. Share late-night chai and bad jokes.</textarea>`)}
    ${field("Guest quote (optional)", `<textarea id="quote" placeholder="Paste a favorite line here"></textarea>`)}
    <div class="row"><button class="primary" id="go">Draft &amp; Emulate</button></div>
  `;
  controls.querySelector("#go").onclick = async () => {
    statsEl.textContent = "Drafting letter…";
    const data = await api("/api/letters/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        names: controls.querySelector("#names").value,
        language: controls.querySelector("#lang").value,
        era: controls.querySelector("#era").value,
        mood: controls.querySelector("#mood").value,
        facts: controls.querySelector("#facts").value,
        guest_quote: controls.querySelector("#quote").value || null,
        highlight: true,
      }),
    });
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
}

function renderRdlab() {
  const list = styles.filter((s) => ["backlog", "pattern"].includes(s.category));
  if (!list.find((s) => s.id === selectedStyle)) selectedStyle = "spiral";
  controls.innerHTML = `
    <h3>R&amp;D Lab</h3>
    <p class="muted">Experimental patterns + rotating-base kinematics in the emulator</p>
    ${styleButtons(list, selectedStyle)}
    ${field("Turntable RPM", `<input id="rpm" type="number" step="0.5" value="3" />`)}
    ${field("Seed", `<input id="seed" type="number" value="42" />`)}
    <div class="row"><button class="primary" id="go">Run Experiment</button></div>
  `;
  bindStyleGrid();
  controls.querySelector("#go").onclick = async () => {
    statsEl.textContent = "R&D render…";
    const rpm = controls.querySelector("#rpm").value;
    const seed = controls.querySelector("#seed").value;
    const data = await api(`/api/rdlab/render?style_id=${encodeURIComponent(selectedStyle)}&rpm=${rpm}&seed=${seed}`, { method: "POST" });
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
}

function renderTools() {
  controls.innerHTML = `
    <h3>Tools</h3>
    <p class="muted">Audio demo, handwriting clone, palette calibrate, plot stub</p>
    <div class="row"><button class="primary" id="audio">Audio → Vector demo</button></div>
    <div class="row"><button id="hw">Handwriting demo (Hello)</button></div>
    ${field("Calibrate palette", `<select id="palette"><option>default-6</option><option>wedding-highlight</option></select>`)}
    ${field("Pen id", `<input id="pen" value="highlight" />`)}
    ${field("Width mm", `<input id="width" type="number" step="0.1" value="3.5" />`)}
    <div class="row"><button id="cal">Save calibration</button></div>
    ${field("Plot stub job id", `<input id="jobid" placeholder="from last render" />`)}
    <div class="row"><button id="stub">Run AxiDraw stub</button></div>
  `;
  controls.querySelector("#audio").onclick = async () => {
    const data = await api("/api/audio/demo", { method: "POST" });
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
  controls.querySelector("#hw").onclick = async () => {
    // seed a simple glyph set then render
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
    loadIntoPlayer(data.emulator, data.job);
    player.play();
  };
  controls.querySelector("#cal").onclick = async () => {
    await api("/api/palettes/calibrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        palette_id: controls.querySelector("#palette").value,
        pen_id: controls.querySelector("#pen").value,
        width_mm: Number(controls.querySelector("#width").value),
        nib_type: "highlighter",
        opacity: 0.4,
      }),
    });
    statsEl.textContent = "Palette calibrated";
  };
  controls.querySelector("#stub").onclick = async () => {
    const id = controls.querySelector("#jobid").value || lastJobId;
    if (!id) return alert("Render something first");
    const data = await api(`/api/plot/stub?job_id=${id}`, { method: "POST" });
    statsEl.textContent = `Stub ok · emu ${data.emulator_run.elapsed_s.toFixed(2)}s`;
  };
}

renderControls().catch((e) => {
  statsEl.textContent = String(e);
  console.error(e);
});
