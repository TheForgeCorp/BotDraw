/* BotDraw emulator canvas player with layer / pen filters */
class EmulatorPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
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
  }

  load(plan) {
    this.plan = plan;
    this.index = 0;
    this.ink = [];
    this.playing = false;
    this.hiddenPassIds.clear();
    this.hiddenPenIds.clear();
    this.soloPassId = null;
    this.drawFrame();
    this._stats("Loaded");
  }

  setSpeed(v) { this.speed = Number(v) || 1; }
  setGhost(v) { this.showGhost = !!v; this.drawFrame(); }

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

  drawFrame() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#f7f1e8";
    ctx.fillRect(0, 0, w, h);
    if (!this.plan) return;
    const sx = w / this.plan.width_mm;
    const sy = h / this.plan.height_mm;

    const current = this.plan.segments[Math.min(this.index, this.plan.segments.length - 1)];
    const theta = current && current.base_theta_rad ? current.base_theta_rad : 0;
    ctx.save();
    if (theta) {
      ctx.translate(w / 2, h / 2);
      ctx.rotate(theta);
      ctx.translate(-w / 2, -h / 2);
      ctx.strokeStyle = "rgba(47,111,106,0.25)";
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, Math.min(w, h) * 0.42, 0, Math.PI * 2);
      ctx.stroke();
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

    if (this.plan.stats) {
      const s = this.plan.stats;
      const visibleInk = this.ink.filter((seg) => this._visible(seg)).length;
      this._stats(
        `ink segs ${visibleInk}/${this.ink.length} · paths ${s.stroke_count} · pens ${s.pen_ids.length} · ETA ${s.estimated_time_s.toFixed(1)}s`
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
