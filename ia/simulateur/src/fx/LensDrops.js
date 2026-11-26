// Gouttes d'eau sur le hublot de la caméra : projetées quand une vague touche
// l'avant du drone (ou par vent fort), elles glissent et s'évaporent. Une vague
// qui recouvre le dôme laisse un film d'eau qui brouille l'image un instant.
// Utile pour tester la robustesse de la détection (cf. tests « gouttes » du projet).

const MAX = 32;

export class LensDrops {
  constructor() {
    this.drops = [];
    this.wash = 0;
    this.cooldown = 0;
  }

  spawn(x, y, r) {
    if (this.drops.length >= MAX) this.drops.shift();
    this.drops.push({ x, y, r, life: 3 + Math.random() * 9, age: 0, vy: 0, a: 0.75 + Math.random() * 0.25 });
  }

  update(dt, splash, wind, enabled, rain = 0) {
    if (!enabled) { this.drops.length = 0; this.wash = 0; return; }
    this.cooldown -= dt;
    // a wave over the dome: burst of drops + water film
    if (splash > 0.85 && this.cooldown <= 0) {
      this.wash = 1;
      this.cooldown = 0.8;
      const n = 6 + Math.floor(Math.random() * 10);
      for (let i = 0; i < n; i++) this.spawn(Math.random(), Math.random() * 0.75, 0.01 + Math.random() ** 2 * 0.05);
    } else if (Math.random() < (splash * 10 + Math.max(0, wind - 10) * 0.08) * dt) {
      this.spawn(Math.random(), 0.05 + Math.random() * 0.6, 0.006 + Math.random() ** 3 * 0.035);
    }
    // raindrops landing on the dome
    let n = rain * rain * 3 * dt; // the many small beads are drawn by the lens shader; these are the big ones
    while (n > 0) {
      if (Math.random() < n) this.spawn(Math.random(), Math.random(), 0.012 + Math.random() ** 2 * 0.03);
      n -= 1;
    }
    this.wash = Math.max(0, this.wash - dt * 1.4);
    for (const d of this.drops) {
      d.age += dt;
      // bigger drops slide down the dome, then everything evaporates
      if (d.r > 0.022) d.vy = Math.min(d.vy + dt * 0.05, d.r * 3);
      d.y -= d.vy * dt;
      d.x += Math.sin(d.age * 3 + d.y * 40) * d.vy * dt * 0.2;
      if (d.age > d.life * 0.6) d.r *= Math.exp(-dt * 0.6);
    }
    this.drops = this.drops.filter((d) => d.age < d.life && d.y > -0.1 && d.r > 0.003);
  }

  fill(uniformArray, aspect) {
    const n = Math.min(this.drops.length, MAX);
    for (let i = 0; i < n; i++) {
      const d = this.drops[i];
      const fade = Math.min(1, (d.life - d.age) / 1.5) * d.a;
      uniformArray[i].set(d.x, d.y, d.r, fade);
    }
    return n;
  }
}
