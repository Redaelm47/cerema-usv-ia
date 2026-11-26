// WebSocket bridge to an external perception / decision pipeline (Python, ROS...).
// Each frame message is binary: [uint32 LE json length][json utf-8][jpeg bytes].
// Commands come back as JSON text messages (see README.md, "Brancher votre pipeline").

export class Bridge {
  constructor(url = 'ws://127.0.0.1:8765') {
    this.url = url;
    this.ws = null;
    this.status = 'off'; // off | connecting | connected
    this.enabled = false;
    this.fps = 10;
    this.quality = 0.85;
    this._last = 0;
    this._busy = false;
    this.onCommand = null;
    this.sent = 0;
  }

  enable(on) {
    const changed = on !== this.enabled;
    this.enabled = on;
    if (changed && this.onStatus) this.onStatus(on);
    if (on) this.connect();
    else if (this.ws) { this.ws.close(); this.ws = null; this.status = 'off'; }
  }

  connect() {
    if (!this.enabled || this.ws) return;
    this.status = 'connecting';
    let ws;
    try { ws = new WebSocket(this.url); } catch { this._retry(); return; }
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => { this.status = 'connected'; };
    ws.onclose = () => { this.ws = null; this.status = this.enabled ? 'connecting' : 'off'; this._retry(); };
    ws.onerror = () => {};
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return;
      try { const msg = JSON.parse(e.data); if (this.onCommand) this.onCommand(msg); } catch { /* ignore */ }
    };
    this.ws = ws;
  }

  _retry() {
    if (!this.enabled) return;
    clearTimeout(this._t);
    this._t = setTimeout(() => this.connect(), 2500);
  }

  /** call right after the frame has been drawn to the canvas */
  maybeSend(canvas, now, metaFn) {
    if (this.status !== 'connected' || this._busy) return;
    if (now - this._last < 1000 / this.fps) return;
    this._last = now;
    this._busy = true;
    const meta = metaFn();
    canvas.toBlob(async (blob) => {
      try {
        if (!blob || !this.ws || this.ws.readyState !== 1) return;
        const jpeg = new Uint8Array(await blob.arrayBuffer());
        const json = new TextEncoder().encode(JSON.stringify(meta));
        const buf = new Uint8Array(4 + json.length + jpeg.length);
        new DataView(buf.buffer).setUint32(0, json.length, true);
        buf.set(json, 4);
        buf.set(jpeg, 4 + json.length);
        this.ws.send(buf);
        this.sent++;
      } finally { this._busy = false; }
    }, 'image/jpeg', this.quality);
  }
}
