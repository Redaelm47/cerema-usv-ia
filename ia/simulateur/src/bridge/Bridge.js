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
    this._attente = null;   // mode campagne : réponse « pas » attendue pour l'image envoyée
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
    ws.onclose = () => {
      this.ws = null; this.status = this.enabled ? 'connecting' : 'off';
      if (this._attente) { this._attente(false); this._attente = null; }
      this._retry();
    };
    ws.onerror = () => {};
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return;
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === 'pas') { if (this._attente) { this._attente(true); this._attente = null; } return; }
      if (this.onCommand) this.onCommand(msg);
    };
    this.ws = ws;
  }

  _retry() {
    if (!this.enabled) return;
    clearTimeout(this._t);
    this._t = setTimeout(() => this.connect(), 2500);
  }

  /** Mode campagne : attend que la passerelle soit connectée. */
  async attendreConnexion(delaiMs = 60000) {
    const fin = performance.now() + delaiMs;
    while (this.status !== 'connected') {
      if (performance.now() > fin) return false;
      await new Promise((r) => setTimeout(r, 200));
    }
    return true;
  }

  /** Mode campagne : message texte vers la passerelle (début et fin d'épisode, fin de campagne). */
  envoyerTexte(objet) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(objet));
  }

  /**
   * Mode campagne : envoie l'image qui vient d'être dessinée, puis attend la réponse « pas » de la passerelle
   * (rendue après le traitement de l'image par la chaîne). À appeler juste après le dessin, comme maybeSend.
   */
  envoyerEtAttendre(canvas, meta, delaiMs = 30000) {
    return new Promise((resolve) => {
      if (!this.ws || this.ws.readyState !== 1) { resolve(false); return; }
      const minuterie = setTimeout(() => { if (this._attente) { this._attente = null; resolve(false); } }, delaiMs);
      this._attente = (ok) => { clearTimeout(minuterie); resolve(ok); };
      canvas.toBlob(async (blob) => {
        if (!blob || !this.ws || this.ws.readyState !== 1) { if (this._attente) { this._attente(false); this._attente = null; } return; }
        const jpeg = new Uint8Array(await blob.arrayBuffer());
        const json = new TextEncoder().encode(JSON.stringify(meta));
        const buf = new Uint8Array(4 + json.length + jpeg.length);
        new DataView(buf.buffer).setUint32(0, json.length, true);
        buf.set(json, 4);
        buf.set(jpeg, 4 + json.length);
        this.ws.send(buf);
        this.sent++;
      }, 'image/jpeg', this.quality);
    });
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
