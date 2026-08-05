/* BotDraw emulator — aspect-true, layered, time-based canvas player.
 *
 * Design notes:
 * - All plan geometry is in mm. A single uniform scale (px/mm) is computed to
 *   fit the paper into the canvas, so the paper aspect ratio is always exact.
 * - Ink is accumulated incrementally into one offscreen canvas per pass, so a
 *   frame costs O(new segments), not O(all segments). Layers are composited
 *   with `multiply` so overlapping pens mix like real ink on paper.
 * - Playback is clocked in plan-seconds with within-segment interpolation, so
 *   the pen head moves continuously and the timeline is scrubbable.
 */
class EmulatorPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.plan = null;

    // Playback state
    this.playing = false;
    this.speed = 16;
    this.time = 0; // plan seconds
    this.duration = 0;
    this.applied = 0; // segments fully drawn into layers
    this.starts = []; // cumulative start time per segment
    this.raf = null;
    this.lastTs = 0;

    // Visibility filters
    this.hiddenPassIds = new Set();
    this.hiddenPenIds = new Set();
    this.soloPassId = null;
    this.showGhost = true;

    // View transform (fit + user zoom/pan, in device px)
    this.dpr = window.devicePixelRatio || 1;
    this.fitScale = 1; // px per mm at zoom 1
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;

    // Offscreen ink layers, keyed by pass id, plus a ghost (pen-up) layer
    this.layers = new Map(); // passId -> {canvas, ctx, penId}
    this.layerScale = 1; // px per mm in layer space
    this.ghost = null;
    this.paperTexture = null;

    // Joined pen-down chain buffer (for round joins across short mark edges)
    this._strokeChain = null;

    // Loupe (magnifier) — default off
    this.loupeOn = false;
    this.loupeFactor = 4;
    this.loupeRadiusCss = 72;
    this._pointerCss = null;

    // Callbacks
    this.onStats = null;
    this.onTime = null; // (time, duration, playing)
    this.onPlayState = null; // (playing)
    this.onLoupeChange = null; // (loupeOn)

    this._penInfo = new Map();
    this._theme = this._readTheme();
    this._bindView();
    this._observeResize();
    this._observeTheme();
    this._layout();
    this.drawFrame();
  }

  /* ---------------- public API ---------------- */

  load(plan) {
    this.plan = plan;
    this.playing = false;
    this.time = 0;
    this.applied = 0;
    this.hiddenPassIds.clear();
    this.hiddenPenIds.clear();
    this.soloPassId = null;
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;

    this._penInfo = new Map();
    for (const p of plan.palette_snapshot || plan.palette || []) {
      this._penInfo.set(p.id, p);
    }
    // Cumulative timeline
    this.starts = new Array(plan.segments.length);
    let t = 0;
    for (let i = 0; i < plan.segments.length; i++) {
      this.starts[i] = t;
      t += Math.max(plan.segments[i].duration_s || 0, 0);
    }
    this.duration = t;

    this._layout();
    this._rebuildLayers();
    this.drawFrame();
    this._emitTime();
    this._stats("Loaded");
  }

  play() {
    if (!this.plan || this.playing) return;
    if (this.time >= this.duration) this.setTime(0);
    this.playing = true;
    this.lastTs = performance.now();
    if (this.onPlayState) this.onPlayState(true);
    const loop = (ts) => {
      if (!this.playing) return;
      const dt = (ts - this.lastTs) / 1000;
      this.lastTs = ts;
      this._advance(this.time + dt * this.speed);
      if (this.time >= this.duration) {
        this.playing = false;
        if (this.onPlayState) this.onPlayState(false);
        this._stats("Complete");
        this._emitTime();
        return;
      }
      this._emitTime();
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  pause() {
    this.playing = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    if (this.onPlayState) this.onPlayState(false);
    this._emitTime();
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  skipEnd() {
    if (!this.plan) return;
    this.pause();
    this.setTime(this.duration);
    this._stats("Skipped to end");
  }

  setSpeed(v) {
    this.speed = Math.max(0.1, Number(v) || 1);
  }

  setGhost(v) {
    this.showGhost = !!v;
    this.drawFrame();
  }

  setLoupe(on) {
    this.loupeOn = !!on;
    if (this.onLoupeChange) this.onLoupeChange(this.loupeOn);
    this.drawFrame();
  }

  toggleLoupe() {
    this.setLoupe(!this.loupeOn);
  }

  /** Client (viewport) coords → paper mm. */
  clientToMm(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = (clientX - rect.left) * this.dpr;
    const my = (clientY - rect.top) * this.dpr;
    const o = this._origin();
    const s = this._scale() || 1;
    return { x_mm: (mx - o.x) / s, y_mm: (my - o.y) / s };
  }

  /** Paper mm → client (viewport) coords. */
  mmToClient(xMm, yMm) {
    const rect = this.canvas.getBoundingClientRect();
    const o = this._origin();
    const s = this._scale() || 1;
    return {
      x: rect.left + (o.x + xMm * s) / this.dpr,
      y: rect.top + (o.y + yMm * s) / this.dpr,
    };
  }

  setPassVisible(passId, visible) {
    if (visible) this.hiddenPassIds.delete(passId);
    else this.hiddenPassIds.add(passId);
    this.drawFrame();
  }

  setPenVisible(penId, visible) {
    if (visible) this.hiddenPenIds.delete(penId);
    else this.hiddenPenIds.add(penId);
    this.drawFrame();
  }

  soloPass(passId) {
    this.soloPassId = this.soloPassId === passId ? null : passId;
    this.drawFrame();
  }

  /** Seek to plan time in seconds (scrubbing). */
  setTime(t) {
    if (!this.plan) return;
    t = Math.min(Math.max(t, 0), this.duration);
    if (t >= this.time) {
      this._advance(t);
    } else {
      // Backward seek: replay layers from scratch up to t
      this.time = t;
      this.applied = 0;
      this._clearLayers();
      this._advance(t, true);
    }
    this._emitTime();
  }

  seekFraction(f) {
    this.setTime(this.duration * Math.min(Math.max(f, 0), 1));
  }

  nudge(seconds) {
    this.setTime(this.time + seconds);
  }

  fitView() {
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.drawFrame();
  }

  /* ---------------- layout & view ---------------- */

  _observeResize() {
    const ro = new ResizeObserver(() => {
      this._layout();
      this._rebuildLayers();
      this.drawFrame();
    });
    ro.observe(this.canvas.parentElement || this.canvas);
  }

  _observeTheme() {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      this._theme = this._readTheme();
      this.paperTexture = null;
      this.drawFrame();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  }

  _readTheme() {
    const cs = getComputedStyle(document.documentElement);
    const v = (name, fallback) => (cs.getPropertyValue(name) || "").trim() || fallback;
    return {
      paper: v("--emu-paper", "#ffffff"),
      paperShadow: v("--emu-paper-shadow", "rgba(15, 18, 25, 0.22)"),
      margin: v("--emu-margin", "rgba(60, 90, 200, 0.10)"),
      ghost: v("--emu-ghost", "rgba(90, 100, 120, 0.35)"),
      empty: v("--emu-empty", "rgba(120, 125, 135, 0.4)"),
      turntable: v("--emu-turntable", "rgba(120, 130, 150, 0.35)"),
    };
  }

  _layout() {
    const host = this.canvas.parentElement || this.canvas;
    const rect = host.getBoundingClientRect();
    const w = Math.max(64, rect.width);
    const h = Math.max(64, rect.height);
    this.dpr = window.devicePixelRatio || 1;
    const bw = Math.round(w * this.dpr);
    const bh = Math.round(h * this.dpr);
    if (this.canvas.width !== bw || this.canvas.height !== bh) {
      this.canvas.width = bw;
      this.canvas.height = bh;
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
    }
    const pw = this.plan ? this.plan.width_mm : 210;
    const ph = this.plan ? this.plan.height_mm : 297;
    const pad = 28 * this.dpr;
    this.fitScale = Math.min((bw - pad * 2) / pw, (bh - pad * 2) / ph);
  }

  /** Current scale in device px per mm. */
  _scale() {
    return this.fitScale * this.zoom;
  }

  /** Top-left of the paper in device px. */
  _origin() {
    const s = this._scale();
    const pw = this.plan ? this.plan.width_mm : 210;
    const ph = this.plan ? this.plan.height_mm : 297;
    return {
      x: (this.canvas.width - pw * s) / 2 + this.panX * this.dpr,
      y: (this.canvas.height - ph * s) / 2 + this.panY * this.dpr,
    };
  }

  _bindView() {
    const el = this.canvas;
    el.addEventListener(
      "wheel",
      (e) => {
        if (!this.plan) return;
        e.preventDefault();
        const rect = el.getBoundingClientRect();
        const mx = (e.clientX - rect.left) * this.dpr;
        const my = (e.clientY - rect.top) * this.dpr;
        const prev = this.zoom;
        const next = Math.min(12, Math.max(0.4, prev * Math.exp(-e.deltaY * 0.0015)));
        if (next === prev) return;
        // Keep the point under the cursor stationary
        const o = this._origin();
        const k = next / prev;
        this.zoom = next;
        this.panX += ((mx - o.x) * (1 - k)) / this.dpr;
        this.panY += ((my - o.y) * (1 - k)) / this.dpr;
        this.drawFrame();
      },
      { passive: false }
    );
    let drag = null;
    const trackPointer = (e) => {
      const rect = el.getBoundingClientRect();
      this._pointerCss = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      if (this.loupeOn && !drag) this.drawFrame();
    };
    el.addEventListener("pointerdown", (e) => {
      if (!this.plan) return;
      if (this._textDragHit && this._textDragHit(e)) return; // app handles text drag
      trackPointer(e);
      drag = { x: e.clientX, y: e.clientY, panX: this.panX, panY: this.panY };
      el.setPointerCapture(e.pointerId);
      el.style.cursor = "grabbing";
    });
    el.addEventListener("pointermove", (e) => {
      trackPointer(e);
      if (!drag) return;
      this.panX = drag.panX + (e.clientX - drag.x);
      this.panY = drag.panY + (e.clientY - drag.y);
      this.drawFrame();
    });
    const endDrag = (e) => {
      if (drag && el.hasPointerCapture && el.hasPointerCapture(e.pointerId)) {
        el.releasePointerCapture(e.pointerId);
      }
      drag = null;
      el.style.cursor = "";
    };
    el.addEventListener("pointerup", endDrag);
    el.addEventListener("pointercancel", endDrag);
    el.addEventListener("pointerleave", () => {
      this._pointerCss = null;
      if (this.loupeOn) this.drawFrame();
    });
    window.addEventListener("keydown", (e) => {
      if (e.key === "l" || e.key === "L") {
        const tag = (e.target && e.target.tagName) || "";
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable) return;
        e.preventDefault();
        this.toggleLoupe();
      }
    });
  }

  /* ---------------- ink layers ---------------- */

  _rebuildLayers() {
    this.layers = new Map();
    this.ghost = null;
    this._strokeChain = null;
    if (!this.plan) return;
    const pw = this.plan.width_mm;
    const ph = this.plan.height_mm;
    // Fixed layer resolution: crisp at fit, still good when zoomed in.
    const target = this.fitScale * 1.6;
    this.layerScale = Math.min(target, 4096 / Math.max(pw, ph));
    const mk = () => {
      const c = document.createElement("canvas");
      c.width = Math.max(2, Math.round(pw * this.layerScale));
      c.height = Math.max(2, Math.round(ph * this.layerScale));
      const cx = c.getContext("2d");
      cx.lineCap = "round";
      cx.lineJoin = "round";
      return { canvas: c, ctx: cx, penId: null };
    };
    this.ghost = mk();
    // Replay applied segments into fresh layers
    const upto = this.applied;
    this.applied = 0;
    this._applyRange(0, upto);
  }

  _clearLayers() {
    this._flushStrokeChain();
    for (const layer of this.layers.values()) {
      layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height);
    }
    if (this.ghost) {
      this.ghost.ctx.clearRect(0, 0, this.ghost.canvas.width, this.ghost.canvas.height);
    }
    this._strokeChain = null;
  }

  _layerFor(seg) {
    const key = seg.pass_id || "default";
    let layer = this.layers.get(key);
    if (!layer) {
      const c = document.createElement("canvas");
      c.width = this.ghost.canvas.width;
      c.height = this.ghost.canvas.height;
      const cx = c.getContext("2d");
      cx.lineCap = "round";
      cx.lineJoin = "round";
      layer = { canvas: c, ctx: cx, penId: seg.pen_id || null };
      this.layers.set(key, layer);
    }
    return layer;
  }

  /** Advance the clock to t, drawing crossed segments into layers. */
  _advance(t, forceDraw = false) {
    if (!this.plan) return;
    t = Math.min(Math.max(t, 0), this.duration);
    const segs = this.plan.segments;
    while (this.applied < segs.length) {
      const seg = segs[this.applied];
      const end = this.starts[this.applied] + Math.max(seg.duration_s || 0, 0);
      if (end > t) break;
      this._applySegment(seg);
      this.applied += 1;
    }
    // Keep open chain if the next (partial) segment continues it; else flush
    const next = this.applied < segs.length ? segs[this.applied] : null;
    const chain = this._strokeChain;
    const continues =
      next &&
      chain &&
      next.kind === "pen_down" &&
      next.pen_id === chain.pen_id &&
      (next.pass_id || "default") === chain.pass_id &&
      this._near(chain.x, chain.y, next.x0, next.y0);
    if (!continues) this._flushStrokeChain();
    this.time = t;
    this.drawFrame();
    if (forceDraw) this.drawFrame();
  }

  _applyRange(from, to) {
    const segs = this.plan.segments;
    for (let i = from; i < to && i < segs.length; i++) {
      this._applySegment(segs[i]);
    }
    this._flushStrokeChain();
    this.applied = Math.min(to, segs.length);
  }

  _applySegment(seg) {
    const s = this.layerScale;
    if (seg.kind === "pen_down") {
      this._enqueuePenDown(seg);
    } else {
      this._flushStrokeChain();
      if (seg.kind === "pen_up") {
        const ctx = this.ghost.ctx;
        ctx.strokeStyle = this._theme.ghost;
        ctx.lineWidth = Math.max(0.75, 0.18 * s);
        ctx.setLineDash([2.2 * s * 0.5, 2.2 * s * 0.5]);
        ctx.beginPath();
        ctx.moveTo(seg.x0 * s, seg.y0 * s);
        ctx.lineTo(seg.x1 * s, seg.y1 * s);
        ctx.stroke();
        ctx.setLineDash([]);
      } else if (seg.kind === "pen_change") {
        this._stats(`Pen change → ${seg.pen_id || "?"}`);
      }
    }
  }

  _near(ax, ay, bx, by, tol = 1e-4) {
    return Math.abs(ax - bx) <= tol && Math.abs(ay - by) <= tol;
  }

  _enqueuePenDown(seg) {
    const chain = this._strokeChain;
    const samePen =
      chain &&
      chain.pen_id === seg.pen_id &&
      chain.pass_id === (seg.pass_id || "default") &&
      this._near(chain.x, chain.y, seg.x0, seg.y0);
    if (!samePen) {
      this._flushStrokeChain();
      this._strokeChain = {
        pen_id: seg.pen_id,
        pass_id: seg.pass_id || "default",
        color_hex: seg.color_hex,
        width_mm: seg.width_mm,
        opacity: seg.opacity,
        points: [
          [seg.x0, seg.y0],
          [seg.x1, seg.y1],
        ],
        x: seg.x1,
        y: seg.y1,
      };
      return;
    }
    chain.points.push([seg.x1, seg.y1]);
    chain.x = seg.x1;
    chain.y = seg.y1;
  }

  _flushStrokeChain() {
    const chain = this._strokeChain;
    this._strokeChain = null;
    if (!chain || chain.points.length < 2) return;
    const layer = this._layerFor({ pass_id: chain.pass_id, pen_id: chain.pen_id });
    this._strokePolyline(layer.ctx, chain, this.layerScale, 1);
  }

  /** Stroke a polyline chain with nib-aware rendering and round joins. */
  _strokePolyline(ctx, chain, s, frac) {
    const pen = this._penInfo.get(chain.pen_id) || {};
    const nib = pen.nib_type || "fineliner";
    const width = (chain.width_mm || pen.width_mm || 0.4) * s;
    const opacity = chain.opacity ?? pen.opacity ?? 1;
    const pts = chain.points;
    if (pts.length < 2) return;

    // Optional frac only affects the final segment (live partial)
    let drawPts = pts;
    if (frac < 1 && pts.length >= 2) {
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      drawPts = pts.slice(0, -1).concat([[a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac]]);
    }

    const stroke = (w, alpha, cap) => {
      ctx.strokeStyle = this._rgba(chain.color_hex || pen.color_hex || "#111111", alpha);
      ctx.lineWidth = Math.max(0.75, w);
      ctx.lineCap = cap;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(drawPts[0][0] * s, drawPts[0][1] * s);
      for (let i = 1; i < drawPts.length; i++) {
        ctx.lineTo(drawPts[i][0] * s, drawPts[i][1] * s);
      }
      ctx.stroke();
    };

    if (nib === "highlighter") {
      stroke(width * 1.15, Math.min(opacity, 0.5), "butt");
    } else if (nib === "brush" || nib === "marker") {
      stroke(width * 1.35, opacity * 0.35, "round");
      stroke(width * 0.85, opacity, "round");
    } else {
      stroke(width, opacity, "round");
    }
  }

  /** Stroke one pen-down segment (partial preview). */
  _strokeSegment(ctx, seg, s, frac) {
    this._strokePolyline(
      ctx,
      {
        pen_id: seg.pen_id,
        color_hex: seg.color_hex,
        width_mm: seg.width_mm,
        opacity: seg.opacity,
        points: [
          [seg.x0, seg.y0],
          [seg.x1, seg.y1],
        ],
      },
      s,
      frac
    );
  }

  /* ---------------- frame composition ---------------- */

  drawFrame() {
    const ctx = this.ctx;
    const W = this.canvas.width;
    const H = this.canvas.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!this.plan) {
      this._drawEmpty(ctx, W, H);
      return;
    }

    const s = this._scale();
    const o = this._origin();
    const pw = this.plan.width_mm;
    const ph = this.plan.height_mm;
    const cx = o.x + (pw / 2) * s;
    const cy = o.y + (ph / 2) * s;

    // Turntable rotation (mm-space, about the page center, uniform scale
    // applied afterwards — no shear)
    const current = this._currentSegment();
    const theta = current && current.base_theta_rad ? current.base_theta_rad : 0;

    ctx.save();
    if (theta) {
      // Turntable platter under the paper
      ctx.strokeStyle = this._theme.turntable;
      ctx.lineWidth = 1.25 * this.dpr;
      ctx.beginPath();
      ctx.arc(cx, cy, (Math.hypot(pw, ph) / 2) * s * 1.04, 0, Math.PI * 2);
      ctx.stroke();
      ctx.translate(cx, cy);
      ctx.rotate(theta);
      ctx.translate(-cx, -cy);
    }

    // Paper with soft shadow
    ctx.save();
    ctx.shadowColor = this._theme.paperShadow;
    ctx.shadowBlur = 18 * this.dpr;
    ctx.shadowOffsetY = 6 * this.dpr;
    ctx.fillStyle = this._theme.paper;
    ctx.fillRect(o.x, o.y, pw * s, ph * s);
    ctx.restore();

    // Subtle paper grain
    ctx.save();
    ctx.beginPath();
    ctx.rect(o.x, o.y, pw * s, ph * s);
    ctx.clip();
    ctx.fillStyle = this._texture();
    ctx.fillRect(o.x, o.y, pw * s, ph * s);
    ctx.restore();

    // 10mm margin guide
    ctx.strokeStyle = this._theme.margin;
    ctx.lineWidth = 1 * this.dpr;
    ctx.strokeRect(o.x + 10 * s, o.y + 10 * s, (pw - 20) * s, (ph - 20) * s);

    // Ghost (pen-up travel) — plain alpha compositing
    if (this.showGhost && this.ghost) {
      ctx.drawImage(this.ghost.canvas, o.x, o.y, pw * s, ph * s);
    }

    // Ink layers — multiply so overlapping pens blend like ink
    ctx.save();
    ctx.globalCompositeOperation = "multiply";
    for (const [passId, layer] of this.layers) {
      if (!this._passVisible(passId, layer.penId)) continue;
      ctx.drawImage(layer.canvas, o.x, o.y, pw * s, ph * s);
    }

    // Live partial segment on top of its layer content
    const partial = this._partialSegment();
    if (partial && partial.seg.kind === "pen_down" && this._passVisible(partial.seg.pass_id, partial.seg.pen_id)) {
      ctx.translate(o.x, o.y);
      this._strokeSegment(ctx, partial.seg, s, partial.frac);
      ctx.translate(-o.x, -o.y);
    }
    ctx.restore();

    // Pen head
    this._drawPenHead(ctx, o, s, partial);
    ctx.restore();

    if (this.loupeOn && this._pointerCss) {
      this._drawLoupe(ctx);
    }
  }

  _drawLoupe(ctx) {
    const p = this._pointerCss;
    const r = this.loupeRadiusCss * this.dpr;
    const factor = this.loupeFactor;
    const W = this.canvas.width;
    const H = this.canvas.height;
    const px = p.x * this.dpr;
    const py = p.y * this.dpr;

    // Snapshot current frame into an offscreen buffer, then magnify into the clip
    const snap = document.createElement("canvas");
    snap.width = W;
    snap.height = H;
    snap.getContext("2d").drawImage(this.canvas, 0, 0);

    ctx.save();
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = this._theme.paper;
    ctx.fillRect(px - r, py - r, r * 2, r * 2);
    ctx.drawImage(
      snap,
      px - r / factor,
      py - r / factor,
      (r * 2) / factor,
      (r * 2) / factor,
      px - r,
      py - r,
      r * 2,
      r * 2
    );
    ctx.restore();

    ctx.save();
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(17,17,17,0.55)";
    ctx.lineWidth = 2 * this.dpr;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(px - 8 * this.dpr, py);
    ctx.lineTo(px + 8 * this.dpr, py);
    ctx.moveTo(px, py - 8 * this.dpr);
    ctx.lineTo(px, py + 8 * this.dpr);
    ctx.strokeStyle = "rgba(17,17,17,0.35)";
    ctx.lineWidth = 1 * this.dpr;
    ctx.stroke();
    ctx.restore();
  }

  _drawEmpty(ctx, W, H) {
    const s = this.fitScale;
    const pw = 210;
    const ph = 297;
    const x = (W - pw * s) / 2;
    const y = (H - ph * s) / 2;
    ctx.strokeStyle = this._theme.empty;
    ctx.lineWidth = 1.25 * this.dpr;
    ctx.setLineDash([6 * this.dpr, 6 * this.dpr]);
    ctx.strokeRect(x, y, pw * s, ph * s);
    ctx.setLineDash([]);
    ctx.fillStyle = this._theme.empty;
    ctx.font = `${13 * this.dpr}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("Render a job to see the plotter emulator", W / 2, y + (ph * s) / 2);
  }

  _drawPenHead(ctx, o, s, partial) {
    if (!this.plan || !this.plan.segments.length) return;
    let seg;
    let frac = 1;
    if (partial) {
      seg = partial.seg;
      frac = partial.frac;
    } else {
      seg = this.plan.segments[Math.min(Math.max(this.applied - 1, 0), this.plan.segments.length - 1)];
    }
    if (!seg) return;
    const x = o.x + (seg.x0 + (seg.x1 - seg.x0) * frac) * s;
    const y = o.y + (seg.y0 + (seg.y1 - seg.y0) * frac) * s;
    const pen = this._penInfo.get(seg.pen_id) || {};
    const color = seg.color_hex || pen.color_hex || "#111111";
    const down = seg.kind === "pen_down";
    const r = (down ? 4.5 : 5.5) * this.dpr;
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.35)";
    ctx.shadowBlur = 4 * this.dpr;
    ctx.fillStyle = this._theme.paper;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5 * this.dpr;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();
    if (down) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, r * 0.45, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  _texture() {
    if (this.paperTexture) return this.paperTexture;
    const size = 96;
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const cx = c.getContext("2d");
    const img = cx.createImageData(size, size);
    for (let i = 0; i < img.data.length; i += 4) {
      const n = 110 + Math.random() * 60;
      img.data[i] = n;
      img.data[i + 1] = n;
      img.data[i + 2] = n;
      img.data[i + 3] = 6; // near-invisible grain
    }
    cx.putImageData(img, 0, 0);
    this.paperTexture = this.ctx.createPattern(c, "repeat");
    return this.paperTexture;
  }

  /* ---------------- helpers ---------------- */

  _currentSegment() {
    if (!this.plan || !this.plan.segments.length) return null;
    const i = Math.min(this.applied, this.plan.segments.length - 1);
    return this.plan.segments[i];
  }

  _partialSegment() {
    if (!this.plan) return null;
    if (this.applied >= this.plan.segments.length) return null;
    const seg = this.plan.segments[this.applied];
    const dur = Math.max(seg.duration_s || 0, 0);
    if (dur <= 0) return { seg, frac: 1 };
    const frac = Math.min(Math.max((this.time - this.starts[this.applied]) / dur, 0), 1);
    return { seg, frac };
  }

  _passVisible(passId, penId) {
    if (this.soloPassId && passId !== this.soloPassId) return false;
    if (passId && this.hiddenPassIds.has(passId)) return false;
    if (penId && this.hiddenPenIds.has(penId)) return false;
    return true;
  }

  _rgba(hex, opacity) {
    const h = (hex || "#111111").replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${opacity})`;
  }

  _emitTime() {
    if (this.onTime) this.onTime(this.time, this.duration, this.playing);
    if (this.plan && this.plan.stats) {
      const s = this.plan.stats;
      const loupe = this.loupeOn ? " · loupe" : "";
      this._stats(
        `${this.applied}/${this.plan.segments.length} segs · ${s.stroke_count} paths · ${s.pen_ids.length} pens · zoom ${this.zoom.toFixed(2)}×${loupe}`
      );
    }
  }

  _stats(msg) {
    if (this.onStats) this.onStats(msg);
  }
}

window.EmulatorPlayer = EmulatorPlayer;
