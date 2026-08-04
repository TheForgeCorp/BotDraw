/* BotDraw emulator canvas player with layer / pen filters, zoom, line handles */
class EmulatorPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    // Write-oriented playback; avoid willReadFrequently (readback/CPU path).
    // https://html.spec.whatwg.org/multipage/canvas.html#concept-canvas-will-read-frequently
    this.ctx = canvas.getContext("2d", { willReadFrequently: false, alpha: true });
    this.plan = null;
    this.index = 0;
    this.playing = false;
    this.speed = 16;
    this.ink = [];
    this.raf = null;
    this.acc = 0;
    this.lastTs = 0;
    this.onStats = null;
    this.hiddenPassIds = new Set();
    this.hiddenPenIds = new Set();
    this.showGhost = true;
    this.soloPassId = null;
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.editLine = null; // { x0_mm, y0_mm, x1_mm, y1_mm }
    this.snapGhost = null; // { x, y, w, h }
    this.onLineEdit = null; // (line) => void while dragging / after
    this._drag = null; // { end: 'a'|'b' }
    this._bound = false;
  }

  load(plan, opts = {}) {
    const preserve = !!opts.preserveVisibility;
    const savedHiddenPass = preserve ? new Set(this.hiddenPassIds) : null;
    const savedHiddenPen = preserve ? new Set(this.hiddenPenIds) : null;
    const savedSolo = preserve ? this.soloPassId : null;
    this.plan = plan;
    this.index = 0;
    this.ink = [];
    this.playing = false;
    if (!preserve) {
      this.hiddenPassIds.clear();
      this.hiddenPenIds.clear();
      this.soloPassId = null;
    } else {
      this.hiddenPassIds = savedHiddenPass;
      this.hiddenPenIds = savedHiddenPen;
      this.soloPassId = savedSolo;
    }
    this.drawFrame();
    this._stats("Loaded");
  }

  setSpeed(v) { this.speed = Number(v) || 1; }
  setGhost(v) { this.showGhost = !!v; this.drawFrame(); }

  setZoom(z) {
    this.zoom = Math.max(0.5, Math.min(3, Number(z) || 1));
    this.drawFrame();
    if (this.onZoomChange) this.onZoomChange(this.zoom);
  }

  zoomBy(factor) {
    this.setZoom(this.zoom * factor);
  }

  fitZoom() {
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.drawFrame();
  }

  setEditLine(line) {
    this.editLine = line ? { ...line } : null;
    this.drawFrame();
  }

  setSnapGhost(span) {
    this.snapGhost = span ? { ...span } : null;
    this.drawFrame();
  }

  enableInteraction() {
    if (this._bound) return;
    this._bound = true;
    const c = this.canvas;
    c.style.touchAction = "none";
    c.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    c.addEventListener("pointermove", (e) => this._onPointerMove(e));
    c.addEventListener("pointerup", (e) => this._onPointerUp(e));
    c.addEventListener("pointerleave", (e) => this._onPointerUp(e));
    c.addEventListener("wheel", (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      this.zoomBy(e.deltaY < 0 ? 1.08 : 1 / 1.08);
    }, { passive: false });
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

  play() {
    if (!this.plan) return;
    this.playing = true;
    this.lastTs = performance.now();
    const loop = (ts) => {
      if (!this.playing) return;
      const dt = (ts - this.lastTs) / 1000;
      this.lastTs = ts;
      this.acc += dt * this.speed;
      while (this.plan && this.index < this.plan.segments.length) {
        const seg = this.plan.segments[this.index];
        const need = Math.max(seg.duration_s || 0.0001, 0.0001);
        if (this.acc < need) break;
        this.acc -= need;
        this._apply(seg);
        this.index += 1;
      }
      this.drawFrame();
      if (this.index >= this.plan.segments.length) {
        this.playing = false;
        this._stats("Complete");
        return;
      }
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  pause() { this.playing = false; }

  skipEnd() {
    if (!this.plan) return;
    while (this.index < this.plan.segments.length) {
      this._apply(this.plan.segments[this.index]);
      this.index += 1;
    }
    this.playing = false;
    this.drawFrame();
    this._stats("Skipped to end");
  }

  _visible(seg) {
    if (this.soloPassId && seg.pass_id !== this.soloPassId) return false;
    if (seg.pass_id && this.hiddenPassIds.has(seg.pass_id)) return false;
    if (seg.pen_id && this.hiddenPenIds.has(seg.pen_id)) return false;
    return true;
  }

  _apply(seg) {
    if (seg.kind === "pen_down") this.ink.push(seg);
    if (seg.kind === "pen_change") this._stats(`Pen change → ${seg.pen_id || "?"}`);
  }

  _paperScale() {
    if (!this.plan) return { sx: 1, sy: 1, w: this.canvas.width, h: this.canvas.height };
    const w = this.canvas.width;
    const h = this.canvas.height;
    return { sx: w / this.plan.width_mm, sy: h / this.plan.height_mm, w, h };
  }

  /** Apply zoom/pan about paper center. */
  _applyViewTransform(ctx) {
    const { w, h } = this._paperScale();
    ctx.translate(w / 2 + this.panX, h / 2 + this.panY);
    ctx.scale(this.zoom, this.zoom);
    ctx.translate(-w / 2, -h / 2);
  }

  canvasToMm(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const cssX = clientX - rect.left;
    const cssY = clientY - rect.top;
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    let x = cssX * scaleX;
    let y = cssY * scaleY;
    const { sx, sy, w, h } = this._paperScale();
    // Inverse of view transform
    x = (x - (w / 2 + this.panX)) / this.zoom + w / 2;
    y = (y - (h / 2 + this.panY)) / this.zoom + h / 2;
    return { x_mm: x / sx, y_mm: y / sy };
  }

  _handleScreen(x_mm, y_mm) {
    const { sx, sy, w, h } = this._paperScale();
    let x = x_mm * sx;
    let y = y_mm * sy;
    x = (x - w / 2) * this.zoom + w / 2 + this.panX;
    y = (y - h / 2) * this.zoom + h / 2 + this.panY;
    return { x, y };
  }

  _hitHandle(clientX, clientY) {
    if (!this.editLine) return null;
    const a = this._handleScreen(this.editLine.x0_mm, this.editLine.y0_mm);
    const b = this._handleScreen(this.editLine.x1_mm, this.editLine.y1_mm);
    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    const x = (clientX - rect.left) * scaleX;
    const y = (clientY - rect.top) * scaleY;
    const r = 10;
    if (Math.hypot(x - a.x, y - a.y) <= r) return "a";
    if (Math.hypot(x - b.x, y - b.y) <= r) return "b";
    return null;
  }

  _onPointerDown(e) {
    const hit = this._hitHandle(e.clientX, e.clientY);
    if (!hit || !this.editLine) return;
    this._drag = { end: hit };
    this.canvas.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }

  _onPointerMove(e) {
    if (!this._drag || !this.editLine) return;
    const mm = this.canvasToMm(e.clientX, e.clientY);
    if (this._drag.end === "a") {
      this.editLine.x0_mm = mm.x_mm;
      this.editLine.y0_mm = mm.y_mm;
    } else {
      this.editLine.x1_mm = mm.x_mm;
      this.editLine.y1_mm = mm.y_mm;
    }
    this.drawFrame();
    if (this.onLineEdit) this.onLineEdit({ ...this.editLine }, { live: true });
  }

  _onPointerUp(e) {
    if (!this._drag) return;
    this._drag = null;
    if (this.onLineEdit && this.editLine) this.onLineEdit({ ...this.editLine }, { live: false });
  }

  drawFrame() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#f7f1e8";
    ctx.fillRect(0, 0, w, h);
    if (!this.plan) return;
    const { sx, sy } = this._paperScale();

    const current = this.plan.segments[Math.min(this.index, this.plan.segments.length - 1)];
    const theta = current && current.base_theta_rad ? current.base_theta_rad : 0;
    ctx.save();
    this._applyViewTransform(ctx);
    if (theta) {
      ctx.translate(w / 2, h / 2);
      ctx.rotate(theta);
      ctx.translate(-w / 2, -h / 2);
      ctx.strokeStyle = "rgba(47,111,106,0.25)";
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, Math.min(w, h) * 0.42, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (this.snapGhost) {
      const g = this.snapGhost;
      ctx.fillStyle = "rgba(59, 130, 246, 0.12)";
      ctx.strokeStyle = "rgba(59, 130, 246, 0.45)";
      ctx.lineWidth = 1;
      ctx.fillRect(g.x * sx, g.y * sy, g.w * sx, g.h * sy);
      ctx.strokeRect(g.x * sx, g.y * sy, g.w * sx, g.h * sy);
    }

    for (const seg of this.ink) {
      if (!this._visible(seg)) continue;
      ctx.beginPath();
      ctx.strokeStyle = this._color(seg.color_hex || "#111", seg.opacity ?? 1);
      ctx.lineWidth = Math.max(1, (seg.width_mm || 0.4) * sx);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.moveTo(seg.x0 * sx, seg.y0 * sy);
      ctx.lineTo(seg.x1 * sx, seg.y1 * sy);
      ctx.stroke();
    }

    if (current) {
      ctx.fillStyle = "#9b3b2e";
      ctx.beginPath();
      ctx.arc(current.x1 * sx, current.y1 * sy, 4, 0, Math.PI * 2);
      ctx.fill();
      if (this.showGhost && current.kind === "pen_up") {
        ctx.strokeStyle = "rgba(0,0,0,0.2)";
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(current.x0 * sx, current.y0 * sy);
        ctx.lineTo(current.x1 * sx, current.y1 * sy);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    ctx.restore();

    // Handles in screen space (after view restore) so size stays constant
    if (this.editLine) {
      const a = this._handleScreen(this.editLine.x0_mm, this.editLine.y0_mm);
      const b = this._handleScreen(this.editLine.x1_mm, this.editLine.y1_mm);
      ctx.save();
      ctx.strokeStyle = "rgba(17,17,17,0.55)";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.setLineDash([]);
      for (const p of [a, b]) {
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "#111";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.rect(p.x - 5, p.y - 5, 10, 10);
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }

    if (this.plan.stats) {
      const s = this.plan.stats;
      const visibleInk = this.ink.filter((seg) => this._visible(seg)).length;
      this._stats(
        `ink segs ${visibleInk}/${this.ink.length} · paths ${s.stroke_count} · pens ${s.pen_ids.length} · ETA ${s.estimated_time_s.toFixed(1)}s · zoom ${this.zoom.toFixed(2)}×`
      );
    }
  }

  _color(hex, opacity) {
    const h = (hex || "#111111").replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${opacity})`;
  }

  _stats(msg) {
    if (this.onStats) this.onStats(msg);
  }
}

window.EmulatorPlayer = EmulatorPlayer;
