/**
 * D3 Pattern Lab — browser preview generators for BotDraw Tools.
 * Uses vendored d3 (non-DOM geometry) and emits paper-mm polylines.
 */
(function (global) {
  const PAPER_MM = {
    A4: [210, 297],
    Letter: [215.9, 279.4],
    A3: [297, 420],
    A5: [148, 210],
    Card: [127, 178],
  };

  const FAMILIES = [
    { id: "voronoi", name: "Voronoi" },
    { id: "delaunay", name: "Delaunay" },
    { id: "hexbin", name: "Hexbin" },
    { id: "contour", name: "Contour" },
    { id: "force_pack", name: "Force pack" },
    { id: "radial_burst", name: "Radial burst" },
    { id: "chord_arcs", name: "Chord arcs" },
    { id: "stream_ribbons", name: "Stream ribbons" },
    { id: "symbol_stamp", name: "Symbol stamp" },
  ];

  function paperDims(paper, orientation) {
    const base = PAPER_MM[paper] || PAPER_MM.A4;
    let w = base[0];
    let h = base[1];
    if (orientation === "landscape") {
      return [h, w];
    }
    return [w, h];
  }

  function marginBox(pw, ph, margin) {
    margin = margin == null ? 10 : margin;
    return { x0: margin, y0: margin, x1: pw - margin, y1: ph - margin, w: pw - 2 * margin, h: ph - 2 * margin };
  }

  function inkPens(palette) {
    const pens = (palette && palette.pens) || [];
    const ink = pens.filter((p) => (p.profile && p.profile.nib_type) !== "highlighter");
    return ink.length ? ink : pens;
  }

  function mulberry32(a) {
    return function () {
      let t = (a += 0x6d2b79f5);
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function randomSites(box, n, rand) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      pts.push([box.x0 + rand() * box.w, box.y0 + rand() * box.h]);
    }
    return pts;
  }

  function bucketPasses(pens, strokes) {
    const buckets = {};
    pens.forEach((p) => {
      buckets[p.id] = [];
    });
    strokes.forEach((s, i) => {
      const pen = pens[i % pens.length];
      buckets[pen.id].push(s);
    });
    return pens
      .map((p) => ({
        pen_id: p.id,
        name: p.name || p.id,
        polylines: buckets[p.id],
      }))
      .filter((p) => p.polylines.length);
  }

  function genVoronoi(d3, box, pens, density, rand) {
    const n = Math.max(20, Math.floor(80 * density));
    const sites = randomSites(box, n, rand);
    const delaunay = d3.Delaunay.from(sites);
    const voronoi = delaunay.voronoi([box.x0, box.y0, box.x1, box.y1]);
    const strokes = [];
    for (let i = 0; i < sites.length; i++) {
      const poly = voronoi.cellPolygon(i);
      if (poly && poly.length >= 3) strokes.push(poly);
    }
    return bucketPasses(pens, strokes);
  }

  function genDelaunay(d3, box, pens, density, rand) {
    const n = Math.max(24, Math.floor(100 * density));
    const sites = randomSites(box, n, rand);
    const delaunay = d3.Delaunay.from(sites);
    const strokes = [];
    const { points, halfedges, triangles } = delaunay;
    for (let e = 0; e < halfedges.length; e++) {
      if (e > halfedges[e]) continue;
      const p = triangles[e];
      const q = triangles[e % 3 === 2 ? e - 2 : e + 1];
      strokes.push([
        [points[p * 2], points[p * 2 + 1]],
        [points[q * 2], points[q * 2 + 1]],
      ]);
    }
    return bucketPasses(pens, strokes);
  }

  function genHexbin(d3, box, pens, density) {
    const r = Math.max(3, 9 / density);
    const strokes = [];
    let row = 0;
    const dx = 1.5 * r;
    const dy = Math.sqrt(3) * r;
    for (let y = box.y0 + r; y < box.y1 - r; y += dy, row++) {
      const xOff = row % 2 ? 0.75 * r : 0;
      for (let x = box.x0 + r + xOff; x < box.x1 - r; x += dx) {
        const pts = [];
        for (let k = 0; k <= 6; k++) {
          const a = (Math.PI / 3) * k - Math.PI / 6;
          pts.push([x + r * 0.95 * Math.cos(a), y + r * 0.95 * Math.sin(a)]);
        }
        strokes.push(pts);
      }
    }
    return bucketPasses(pens, strokes);
  }

  function genContour(d3, box, pens, density, rand) {
    const cols = Math.max(24, Math.floor(40 * density));
    const rows = Math.max(24, Math.floor(40 * density * (box.h / box.w)));
    const cx = [box.x0 + box.w * (0.3 + 0.1 * rand()), box.y0 + box.h * (0.4 + 0.2 * rand())];
    const cy = [box.x0 + box.w * (0.6 + 0.1 * rand()), box.y0 + box.h * (0.4 + 0.2 * rand())];
    const values = new Array(cols * rows);
    const k = 0.25 * density;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const x = (i / (cols - 1)) * box.w;
        const y = (j / (rows - 1)) * box.h;
        const d1 = Math.hypot(x - (cx[0] - box.x0), y - (cx[1] - box.y0));
        const d2 = Math.hypot(x - (cy[0] - box.x0), y - (cy[1] - box.y0));
        values[j * cols + i] = Math.sin(k * d1) + Math.sin(k * d2);
      }
    }
    const thresholds = d3.range(-1.5, 1.6, 0.4);
    const contours = d3.contours().size([cols, rows]).thresholds(thresholds)(values);
    const sx = box.w / (cols - 1);
    const sy = box.h / (rows - 1);
    const strokes = [];
    contours.forEach((c) => {
      c.coordinates.forEach((poly) => {
        poly.forEach((ring) => {
          const pts = ring.map(([u, v]) => [box.x0 + u * sx, box.y0 + v * sy]);
          if (pts.length >= 2) strokes.push(pts);
        });
      });
    });
    return bucketPasses(pens, strokes);
  }

  function genForcePack(d3, box, pens, density, rand, seed) {
    const n = Math.max(16, Math.floor(40 * density));
    const nodes = [];
    for (let i = 0; i < n; i++) {
      nodes.push({
        x: box.x0 + rand() * box.w,
        y: box.y0 + rand() * box.h,
        r: 1.5 + rand() * (6 / density),
      });
    }
    const sim = d3
      .forceSimulation(nodes)
      .force("x", d3.forceX((box.x0 + box.x1) / 2).strength(0.02))
      .force("y", d3.forceY((box.y0 + box.y1) / 2).strength(0.02))
      .force(
        "collide",
        d3.forceCollide().radius((d) => d.r + 0.3)
      )
      .stop();
    for (let i = 0; i < 120; i++) sim.tick();
    const strokes = nodes.map((d) => {
      const pts = [];
      for (let k = 0; k <= 24; k++) {
        const a = (Math.PI * 2 * k) / 24;
        pts.push([d.x + d.r * Math.cos(a), d.y + d.r * Math.sin(a)]);
      }
      return pts;
    });
    return bucketPasses(pens, strokes);
  }

  function genRadialBurst(box, pens, density) {
    const cx = (box.x0 + box.x1) / 2;
    const cy = (box.y0 + box.y1) / 2;
    const rMax = Math.min(box.w, box.h) / 2 * 0.95;
    const rings = Math.max(6, Math.floor(16 * density));
    const rays = Math.max(12, Math.floor(32 * density));
    const strokes = [];
    for (let i = 0; i < rings; i++) {
      const r = (rMax * (i + 1)) / rings;
      const pts = [];
      for (let k = 0; k <= 64; k++) {
        const a = (Math.PI * 2 * k) / 64;
        pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
      }
      strokes.push(pts);
    }
    for (let j = 0; j < rays; j++) {
      const a = (Math.PI * 2 * j) / rays;
      strokes.push([
        [cx + 2 * Math.cos(a), cy + 2 * Math.sin(a)],
        [cx + rMax * Math.cos(a), cy + rMax * Math.sin(a)],
      ]);
    }
    return bucketPasses(pens, strokes);
  }

  function genChordArcs(box, pens, density, rand) {
    const cx = (box.x0 + box.x1) / 2;
    const cy = (box.y0 + box.y1) / 2;
    const r = Math.min(box.w, box.h) / 2 * 0.9;
    const n = Math.max(8, Math.floor(14 * density));
    const nodes = [];
    for (let i = 0; i < n; i++) {
      const a = (Math.PI * 2 * i) / n;
      nodes.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    }
    const ring = [];
    for (let k = 0; k <= 72; k++) {
      const a = (Math.PI * 2 * k) / 72;
      ring.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    }
    const strokes = [ring];
    const nChords = Math.floor(n * 1.5 * density);
    for (let k = 0; k < nChords; k++) {
      const i = Math.floor(rand() * n);
      let j = Math.floor(rand() * n);
      if (i === j) continue;
      const a = nodes[i];
      const b = nodes[j];
      const mx = (a[0] + b[0]) / 2;
      const my = (a[1] + b[1]) / 2;
      const mid = [mx + (cx - mx) * 0.35, my + (cy - my) * 0.35];
      const pts = [];
      for (let t = 0; t <= 1.001; t += 1 / 20) {
        const u = 1 - t;
        pts.push([
          u * u * a[0] + 2 * u * t * mid[0] + t * t * b[0],
          u * u * a[1] + 2 * u * t * mid[1] + t * t * b[1],
        ]);
      }
      strokes.push(pts);
    }
    return bucketPasses(pens, strokes);
  }

  function genStreamRibbons(box, pens, density, rand) {
    const nX = Math.max(20, Math.floor(36 * density));
    const nLayers = Math.max(3, Math.min(pens.length * 2, Math.floor(5 * density)));
    const xs = [];
    for (let i = 0; i < nX; i++) xs.push(box.x0 + (box.w * i) / (nX - 1));
    const layers = [];
    for (let li = 0; li < nLayers; li++) {
      let v = 0;
      const arr = [];
      let min = Infinity;
      let max = -Infinity;
      for (let i = 0; i < nX; i++) {
        v += (rand() - 0.5) * 2;
        arr.push(v);
        if (v < min) min = v;
        if (v > max) max = v;
      }
      const span = max - min || 1;
      layers.push(arr.map((x) => ((x - min) / span) * box.h * 0.08 + 2));
    }
    let stack = new Array(nX).fill(0);
    let maxStack = 0;
    layers.forEach((thick) => {
      for (let i = 0; i < nX; i++) {
        stack[i] += thick[i];
        if (stack[i] > maxStack) maxStack = stack[i];
      }
    });
    const yStart = box.y0 + (box.h - maxStack) / 2;
    stack = new Array(nX).fill(0);
    const strokes = [];
    layers.forEach((thick) => {
      const mid = [];
      const top = [];
      for (let i = 0; i < nX; i++) {
        const t = yStart + stack[i] + thick[i];
        const b = yStart + stack[i];
        mid.push([xs[i], (t + b) / 2]);
        top.push([xs[i], t]);
        stack[i] += thick[i];
      }
      strokes.push(mid, top);
    });
    return bucketPasses(pens, strokes);
  }

  function genSymbolStamp(d3, box, pens, density, rand) {
    const spacing = Math.max(6, 14 / density);
    const strokes = [];
    const symbols = [
      d3.symbolCircle,
      d3.symbolCross,
      d3.symbolDiamond,
      d3.symbolSquare,
      d3.symbolTriangle,
      d3.symbolStar,
    ];
    let row = 0;
    for (let y = box.y0 + spacing; y < box.y1 - spacing; y += spacing, row++) {
      for (let x = box.x0 + spacing; x < box.x1 - spacing; x += spacing) {
        if (rand() < 0.15) continue;
        const sym = d3.symbol().type(symbols[(row + Math.floor(x)) % symbols.length]).size(spacing * spacing * 0.35);
        const path = sym();
        // Parse simple SVG path M/L/Z into polyline via CanvasPath — use d3 path sampling via temporary path
        const pts = pathToPoints(path, x, y);
        if (pts.length >= 2) strokes.push(pts);
      }
    }
    return bucketPasses(pens, strokes);
  }

  function pathToPoints(d, ox, oy) {
    // Minimal SVG path tokenizer for M/L/Z absolute/relative from d3.symbol
    const pts = [];
    const re = /([MLCZ])\s*([^MLCZ]*)/gi;
    let m;
    let x = 0;
    let y = 0;
    let startX = 0;
    let startY = 0;
    while ((m = re.exec(d))) {
      const cmd = m[1];
      const nums = (m[2].match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi) || []).map(Number);
      if (cmd === "M" || cmd === "m") {
        if (cmd === "M") {
          x = nums[0];
          y = nums[1];
        } else {
          x += nums[0];
          y += nums[1];
        }
        startX = x;
        startY = y;
        pts.push([ox + x, oy + y]);
        for (let i = 2; i + 1 < nums.length; i += 2) {
          if (cmd === "M") {
            x = nums[i];
            y = nums[i + 1];
          } else {
            x += nums[i];
            y += nums[i + 1];
          }
          pts.push([ox + x, oy + y]);
        }
      } else if (cmd === "L" || cmd === "l") {
        for (let i = 0; i + 1 < nums.length; i += 2) {
          if (cmd === "L") {
            x = nums[i];
            y = nums[i + 1];
          } else {
            x += nums[i];
            y += nums[i + 1];
          }
          pts.push([ox + x, oy + y]);
        }
      } else if (cmd === "Z" || cmd === "z") {
        pts.push([ox + startX, oy + startY]);
        x = startX;
        y = startY;
      }
    }
    return pts;
  }

  function generate(opts) {
    const d3 = global.d3;
    if (!d3) throw new Error("d3 not loaded");
    const family = opts.family || "voronoi";
    const seed = opts.seed == null ? 42 : opts.seed | 0;
    const density = opts.density == null ? 1 : Number(opts.density);
    const [pw, ph] = paperDims(opts.paper || "A4", opts.orientation || "portrait");
    const box = marginBox(pw, ph, 10);
    const pens = inkPens(opts.palette);
    if (!pens.length) throw new Error("No pens in palette");
    const rand = mulberry32(seed);
    let passes;
    switch (family) {
      case "delaunay":
        passes = genDelaunay(d3, box, pens, density, rand);
        break;
      case "hexbin":
        passes = genHexbin(d3, box, pens, density);
        break;
      case "contour":
        passes = genContour(d3, box, pens, density, rand);
        break;
      case "force_pack":
        passes = genForcePack(d3, box, pens, density, rand, seed);
        break;
      case "radial_burst":
        passes = genRadialBurst(box, pens, density);
        break;
      case "chord_arcs":
        passes = genChordArcs(box, pens, density, rand);
        break;
      case "stream_ribbons":
        passes = genStreamRibbons(box, pens, density, rand);
        break;
      case "symbol_stamp":
        passes = genSymbolStamp(d3, box, pens, density, rand);
        break;
      case "voronoi":
      default:
        passes = genVoronoi(d3, box, pens, density, rand);
        break;
    }
    return { width_mm: pw, height_mm: ph, passes, family, seed, density };
  }

  function renderPreview(svgEl, result, palette) {
    const pens = inkPens(palette);
    const colorBy = {};
    pens.forEach((p) => {
      colorBy[p.id] = p.color_hex || "#222";
    });
    const d3 = global.d3;
    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${result.width_mm} ${result.height_mm}`);
    svg.attr("preserveAspectRatio", "xMidYMid meet");
    const g = svg.append("g").attr("fill", "none").attr("stroke-linecap", "round").attr("stroke-linejoin", "round");
    result.passes.forEach((pass) => {
      const stroke = colorBy[pass.pen_id] || "#333";
      const layer = g.append("g").attr("stroke", stroke).attr("stroke-width", 0.35);
      pass.polylines.forEach((pts) => {
        if (!pts || pts.length < 2) return;
        layer.append("path").attr("d", d3.line()(pts));
      });
    });
  }

  global.BotDrawD3Lab = {
    FAMILIES,
    paperDims,
    generate,
    renderPreview,
  };
})(typeof window !== "undefined" ? window : globalThis);
