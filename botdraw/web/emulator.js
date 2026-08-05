/* BotDraw emulator canvas player — HiDPI, zoom-to-cursor, pan, loupe */
class EmulatorPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    // Write-oriented playback; avoid willReadFrequently (DESIGN.md).
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
    this.paperColor = "#ffffff";
    this.loupeOn = false;
    this.loupeFactor = 4;
    this.loupeRadiusCss = 72;
    this._pointerCss = null;
    this.editLine = null;
    this.snapGhost = null;
    this.onLineEdit = null;
    this.onZoomChange = null;
    this._drag = null;
    this._panDrag = null;
    this._settleRaf = null;
    this._spaceDown = false;
    this._bound = false;
    this._dpr = 1;
    this._cssW = 0;
    this._cssH = 0;
    this.syncSize();
  }

  syncSize() {
    const c = this.canvas;
    const rect = c.getBoundingClientRect();
    const cssW = Math.max(1, Math.round(rect.width || c.clientWidth || 640));
    const cssH = Math.max(1, Math.round(rect.height || c.clientHeight || 480));
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    if (cssW === this._cssW && cssH === this._cssH && dpr === this._dpr) return;
    this._cssW = cssW;
    this._cssH = cssH;
    this._dpr = dpr;
    c.width = Math.round(cssW * dpr);
    c.height = Math.round(cssH * dpr);
    c.style.width = `${cssW}px`;
    c.style.height = `${cssH}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.drawFrame();
  }

  load(plan, opts = {}) {
    const preserve = !!opts.preserveVisibility;
    const savedHiddenPass = preserve ? new Set(this.hiddenPassIds) : null;
    const savedHiddenPen = preserve ? new Set(this.hiddenPenIds) : null;
    const savedSolo = preserve ? this.soloPassId : null;
    this.plan = plan;
    if (plan?.paper_color_hex) this.paperColor = plan.paper_color_hex;
    if (opts.paperColor) this.paperColor = opts.paperColor;
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
    this.syncSize();
    this.drawFrame();
    this._stats("Loaded");
  }

  setPaperColor(hex) {
    this.paperColor = hex || "#ffffff";
    this.drawFrame();
  }

  setSpeed(v) { this.speed = Number(v) || 1; }
  setGhost(v) { this.showGhost = !!v; this.drawFrame(); }

  setZoom(z, anchorCss = null) {
    this._cancelSettle();
    const next = Math.max(0.25, Math.min(16, Number(z) || 1));
    if (anchorCss && this._cssW) {
      // Zoom toward cursor (CSS px space)
      const { w, h } = this._paperScaleCss();
      const ax = anchorCss.x;
      const ay = anchorCss.y;
      const worldX = (ax - (w / 2 + this.panX)) / this.zoom + w / 2;
      const worldY = (ay - (h / 2 + this.panY)) / this.zoom + h / 2;
      this.zoom = next;
      this.panX = ax - w / 2 - (worldX - w / 2) * this.zoom;
      this.panY = ay - h / 2 - (worldY - h / 2) * this.zoom;
    } else {
      this.zoom = next;
    }
    const hard = this._clampPan(this.panX, this.panY);
    this.panX = hard.x;
    this.panY = hard.y;
    this.drawFrame();
    if (this.onZoomChange) this.onZoomChange(this.zoom);
  }

  zoomBy(factor, anchorCss = null) {
    this.setZoom(this.zoom * factor, anchorCss);
  }

  fitZoom() {
    this._cancelSettle();
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.drawFrame();
    if (this.onZoomChange) this.onZoomChange(this.zoom);
  }

  _panLimits() {
    const { w, h } = this._paperScaleCss();
    const maxX = Math.max(24, (w * Math.max(0, this.zoom - 1)) / 2 + 24);
    const maxY = Math.max(24, (h * Math.max(0, this.zoom - 1)) / 2 + 24);
    return { maxX, maxY };
  }

  _clampPan(x, y, { rubber = false } = {}) {
    const { maxX, maxY } = this._panLimits();
    const axis = (v, max) => {
      if (!rubber) return Math.max(-max, Math.min(max, v));
      if (v > max) return max + (v - max) * 0.35;
      if (v < -max) return -max + (v + max) * 0.35;
      return v;
    };
    return { x: axis(x, maxX), y: axis(y, maxY) };
  }

  _cancelSettle() {
    if (this._settleRaf) {
      cancelAnimationFrame(this._settleRaf);
      this._settleRaf = null;
    }
  }

  _settlePan(vx = 0, vy = 0) {
    this._cancelSettle();
    const reduce = typeof window !== "undefined"
      && window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      const hard = this._clampPan(this.panX, this.panY);
      this.panX = hard.x;
      this.panY = hard.y;
      this.drawFrame();
      return;
    }
    let velX = vx;
    let velY = vy;
    const step = () => {
      const hard = this._clampPan(this.panX, this.panY);
      const ax = (hard.x - this.panX) * 0.22;
      const ay = (hard.y - this.panY) * 0.22;
      velX = velX * 0.88 + ax;
      velY = velY * 0.88 + ay;
      this.panX += velX;
      this.panY += velY;
      const settled =
        Math.abs(this.panX - hard.x) < 0.45
        && Math.abs(this.panY - hard.y) < 0.45
        && Math.hypot(velX, velY) < 0.35;
      if (settled) {
        this.panX = hard.x;
        this.panY = hard.y;
        this._settleRaf = null;
        this.drawFrame();
        return;
      }
      this.drawFrame();
      this._settleRaf = requestAnimationFrame(step);
    };
    this._settleRaf = requestAnimationFrame(step);
  }

  setLoupe(on) {
    this.loupeOn = !!on;
    this.drawFrame();
  }

  toggleLoupe() {
    this.setLoupe(!this.loupeOn);
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
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const anchor = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      this.zoomBy(factor, anchor);
    }, { passive: false });
    window.addEventListener("keydown", (e) => {
      if (e.code === "Space") this._spaceDown = true;
      if (e.key === "l" || e.key === "L") this.toggleLoupe();
    });
    window.addEventListener("keyup", (e) => {
      if (e.code === "Space") this._spaceDown = false;
    });
    window.addEventListener("resize", () => this.syncSize());
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

  /** CSS-pixel paper scale (after ctx DPR transform). */
  _paperScaleCss() {
    if (!this.plan) return { sx: 1, sy: 1, w: this._cssW || 1, h: this._cssH || 1 };
    const w = this._cssW || this.canvas.clientWidth || 1;
    const h = this._cssH || this.canvas.clientHeight || 1;
    return { sx: w / this.plan.width_mm, sy: h / this.plan.height_mm, w, h };
  }

  _applyViewTransform(ctx) {
    const { w, h } = this._paperScaleCss();
    ctx.translate(w / 2 + this.panX, h / 2 + this.panY);
    ctx.scale(this.zoom, this.zoom);
    ctx.translate(-w / 2, -h / 2);
  }

  _cssFromClient(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top };
  }

  canvasToMm(clientX, clientY) {
    const { x: cssX, y: cssY } = this._cssFromClient(clientX, clientY);
    const { sx, sy, w, h } = this._paperScaleCss();
    let x = (cssX - (w / 2 + this.panX)) / this.zoom + w / 2;
    let y = (cssY - (h / 2 + this.panY)) / this.zoom + h / 2;
    return { x_mm: x / sx, y_mm: y / sy };
  }

  _handleScreen(x_mm, y_mm) {
    const { sx, sy, w, h } = this._paperScaleCss();
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
    const { x, y } = this._cssFromClient(clientX, clientY);
    const r = 10;
    if (Math.hypot(x - a.x, y - a.y) <= r) return "a";
    if (Math.hypot(x - b.x, y - b.y) <= r) return "b";
    return null;
  }

  _onPointerDown(e) {
    this._pointerCss = this._cssFromClient(e.clientX, e.clientY);
    const hit = this._hitHandle(e.clientX, e.clientY);
    if (hit && this.editLine) {
      this._drag = { end: hit };
      this.canvas.setPointerCapture?.(e.pointerId);
      e.preventDefault();
      return;
    }
    if (this._spaceDown || e.button === 1 || e.buttons === 4) {
      this._cancelSettle();
      this._panDrag = {
        x: e.clientX,
        y: e.clientY,
        panX: this.panX,
        panY: this.panY,
        lastX: e.clientX,
        lastY: e.clientY,
        lastT: performance.now(),
        vx: 0,
        vy: 0,
      };
      this.canvas.setPointerCapture?.(e.pointerId);
      e.preventDefault();
    }
  }

  _onPointerMove(e) {
    this._pointerCss = this._cssFromClient(e.clientX, e.clientY);
    if (this.loupeOn) this.drawFrame();
    if (this._panDrag) {
      const now = performance.now();
      const dt = Math.max(8, now - this._panDrag.lastT);
      const idx = e.clientX - this._panDrag.lastX;
      const idy = e.clientY - this._panDrag.lastY;
      this._panDrag.vx = (idx / dt) * 16;
      this._panDrag.vy = (idy / dt) * 16;
      this._panDrag.lastX = e.clientX;
      this._panDrag.lastY = e.clientY;
      this._panDrag.lastT = now;
      const rawX = this._panDrag.panX + (e.clientX - this._panDrag.x);
      const rawY = this._panDrag.panY + (e.clientY - this._panDrag.y);
      const c = this._clampPan(rawX, rawY, { rubber: true });
      this.panX = c.x;
      this.panY = c.y;
      this.drawFrame();
      return;
    }
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
    if (this._panDrag) {
      const vx = this._panDrag.vx;
      const vy = this._panDrag.vy;
      this._panDrag = null;
      this._settlePan(vx, vy);
      return;
    }
    if (!this._drag) return;
    this._drag = null;
    if (this.onLineEdit && this.editLine) this.onLineEdit({ ...this.editLine }, { live: false });
  }

  _drawInk(ctx, sx, sy) {
    for (const seg of this.ink) {
      if (!this._visible(seg)) continue;
      ctx.beginPath();
      ctx.strokeStyle = this._color(seg.color_hex || "#111", seg.opacity ?? 1);
      ctx.lineWidth = Math.max(0.5, (seg.width_mm || 0.4) * sx);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.moveTo(seg.x0 * sx, seg.y0 * sy);
      ctx.lineTo(seg.x1 * sx, seg.y1 * sy);
      ctx.stroke();
    }
  }

  drawFrame() {
    this.syncSize();
    const ctx = this.ctx;
    const { w, h, sx, sy } = this._paperScaleCss();
    ctx.save();
    ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = this.paperColor || "#ffffff";
    ctx.fillRect(0, 0, w, h);
    if (!this.plan) {
      ctx.restore();
      return;
    }

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

    this._drawInk(ctx, sx, sy);

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

    if (this.loupeOn && this._pointerCss) {
      this._drawLoupe(ctx, sx, sy);
    }

    if (this.plan.stats) {
      const s = this.plan.stats;
      const visibleInk = this.ink.filter((seg) => this._visible(seg)).length;
      const mm = this._pointerCss
        ? this.canvasToMm(
            this.canvas.getBoundingClientRect().left + this._pointerCss.x,
            this.canvas.getBoundingClientRect().top + this._pointerCss.y
          )
        : null;
      const mmLabel = mm ? ` · ${mm.x_mm.toFixed(1)},${mm.y_mm.toFixed(1)}mm` : "";
      this._stats(
        `ink ${visibleInk}/${this.ink.length} · paths ${s.stroke_count} · pens ${s.pen_ids.length} · ETA ${s.estimated_time_s.toFixed(1)}s · zoom ${this.zoom.toFixed(2)}×${this.loupeOn ? " · loupe" : ""}${mmLabel}`
      );
    }
    ctx.restore();
  }

  _drawLoupe(ctx, sx, sy) {
    const p = this._pointerCss;
    const r = this.loupeRadiusCss;
    const factor = this.loupeFactor;
    ctx.save();
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.clip();
    // Fill paper in loupe
    ctx.fillStyle = this.paperColor || "#ffffff";
    ctx.fillRect(p.x - r, p.y - r, r * 2, r * 2);
    ctx.save();
    // Map: zoom extra around pointer in CSS space
    const { w, h } = this._paperScaleCss();
    ctx.translate(p.x, p.y);
    ctx.scale(factor, factor);
    ctx.translate(-p.x, -p.y);
    ctx.translate(w / 2 + this.panX, h / 2 + this.panY);
    ctx.scale(this.zoom, this.zoom);
    ctx.translate(-w / 2, -h / 2);
    this._drawInk(ctx, sx, sy);
    ctx.restore();
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(17,17,17,0.55)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(p.x - 8, p.y);
    ctx.lineTo(p.x + 8, p.y);
    ctx.moveTo(p.x, p.y - 8);
    ctx.lineTo(p.x, p.y + 8);
    ctx.strokeStyle = "rgba(17,17,17,0.35)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
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
