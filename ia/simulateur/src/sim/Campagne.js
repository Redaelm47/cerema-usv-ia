// Mode campagne : des centaines d'épisodes tirés au hasard, en temps simulé, pour mesurer la chaîne IA.
//
//   ?campagne=1&graine=1000&episodes=20&duree=180&img_s=5&ws=ws://127.0.0.1:8765&ui=0&dpr=1
//
// Pour chaque épisode (graine G + k) : météo, heure, houle, pluie, buée, 0 à 3 navires et position du drone sur une
// route de patrouille sont tirés au hasard, de façon reproductible. Puis le simulateur avance à pas fixe : physique
// par pas de 1/30 s, une image toutes les 1/img_s s envoyée à la chaîne, et il attend sa réponse avant de continuer.
// Le temps simulé ne dépend donc pas de la machine : une machine rapide finit plus tôt, avec le même résultat.
// L'état est lisible dans window.campagne (lanceur sans écran, ia/simulateur/campagne/).

const DEG = Math.PI / 180;

/** Générateur pseudo-aléatoire reproductible (mulberry32). */
export function mulberry32(graine) {
  let a = graine >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const choisir = (rnd, poids) => {
  const total = poids.reduce((s, [, p]) => s + p, 0);
  let r = rnd() * total;
  for (const [v, p] of poids) { r -= p; if (r <= 0) return v; }
  return poids[poids.length - 1][0];
};
const entre = (rnd, a, b) => a + (b - a) * rnd();

// Préréglages météo du simulateur, avec leur fréquence dans les campagnes (pas de nuit pour l'instant).
const METEOS = [['Clair', 3], ['Nuageux', 3], ['Couvert', 2], ['Brume', 2], ['Coup de vent', 1], ['Couchant', 1], ['Pluie', 2], ['Grain', 1]];
// Nombre de navires : un épisode sur cinq sans navire, pour compter les hallucinations sur la mer vide.
const NOMBRE_NAVIRES = [[0, 2], [1, 4], [2, 2.5], [3, 1.5]];
// Types de navires : surtout des chalutiers, les seuls qui portent une immatriculation à lire.
const TYPES = [['trawler', 5], ['sailboat', 2], ['motorboat', 2], ['tug', 1], ['ferry', 1], ['container', 1]];
const VITESSE_KN = { trawler: [0.5, 4], sailboat: [2, 6], motorboat: [4, 12], tug: [3, 9], ferry: [8, 14], container: [6, 12] };
const TIRANT_M = { trawler: 3, sailboat: 2, motorboat: 1.5, tug: 4, ferry: 4, container: 8 };

// Routes de patrouille en boucle, vérifiées sur le relief : plus de 8 m d'eau, à plus de 200 m de la côte.
export const ZONES = [
  { nom: 'Le Dellec', route: [[48.34878, -4.56607], [48.34608, -4.57754], [48.34293, -4.58698], [48.33942, -4.59642], [48.33996, -4.58698], [48.34320, -4.57349]] },
  { nom: 'Sainte-Anne', route: [[48.35134, -4.53486], [48.35225, -4.53966], [48.3504, -4.54726], [48.34765, -4.55007], [48.34674, -4.54527], [48.34859, -4.53766]] },
  { nom: 'Rade centre', route: [[48.33331, -4.46692], [48.3372, -4.47299], [48.3372, -4.48513], [48.33331, -4.4912], [48.32941, -4.48513], [48.32941, -4.47299]] },
  { nom: 'Entrée du Goulet', route: [[48.33224, -4.61293], [48.33406, -4.61855], [48.33243, -4.62768], [48.32898, -4.63118], [48.32716, -4.62556], [48.32879, -4.61644]] },
  { nom: 'Goulet sud', route: [[48.33995, -4.57045], [48.34019, -4.57658], [48.33715, -4.58636], [48.33387, -4.59002], [48.33362, -4.58389], [48.33666, -4.57411]] },
];

/** Tire un scénario au hasard (format de public/scenarios/*.json, navires en x/z du monde). */
export function genererScenario(graine, app) {
  const rnd = mulberry32(graine);
  const meteo = choisir(rnd, METEOS);
  const p = app.weatherPresets[meteo];
  const zone = ZONES[Math.floor(rnd() * ZONES.length)];
  // départ du drone : un point au hasard sur un tronçon de la route, cap vers le point suivant
  const route = zone.route.map(([lat, lon]) => app.fromLatLon(lat, lon));
  const i = Math.floor(rnd() * route.length);
  const a = route[i], b = route[(i + 1) % route.length], t = rnd();
  const x0 = a.x + (b.x - a.x) * t, z0 = a.z + (b.z - a.z) * t;
  const cap = Math.atan2(b.x - a.x, -(b.z - a.z));
  const debut = app.toLatLon(x0, z0);
  const sc = {
    graine, zone: zone.nom, weather: meteo,
    hour: meteo === 'Couchant' ? entre(rnd, 19.5, 21) : entre(rnd, 8, 18.5),
    month: 3 + Math.floor(rnd() * 8),
    wind: Math.max(1, p.wind * entre(rnd, 0.7, 1.3)),
    windDir: Math.floor(rnd() * 360),
    swell: Math.max(0.1, p.swell * entre(rnd, 0.7, 1.3)),
    auto_traffic: false,
    drone: { lat: debut.lat, lon: debut.lon, heading_deg: cap / DEG, patrol_kn: 3, route: zone.route, loop: true },
    ships: [],
  };
  const n = choisir(rnd, NOMBRE_NAVIRES);
  for (let k = 0; k < n; k++) {
    const kind = choisir(rnd, TYPES);
    // distance de 120 m à 1,5 km (plus souvent proche), et le plus souvent devant le drone
    const d = Math.exp(entre(rnd, Math.log(120), Math.log(1500)));
    const relevement = rnd() < 0.8 ? cap + entre(rnd, -50, 50) * DEG : rnd() * 2 * Math.PI;
    const q = app.map?.nearestWater(x0 + Math.sin(relevement) * d, z0 - Math.cos(relevement) * d, TIRANT_M[kind] ?? 2, 400);
    if (!q) continue;
    const [v0, v1] = VITESSE_KN[kind];
    sc.ships.push({ kind, x: q.x, z: q.z, heading_deg: rnd() * 360, speed_kn: entre(rnd, v0, v1), distance_m: Math.round(Math.hypot(q.x - x0, q.z - z0)) });
  }
  return sc;
}

export class Campagne {
  constructor(app, params) {
    this.app = app;
    this.graine = +(params.get('graine') ?? 1);
    this.episodes = +(params.get('episodes') ?? 10);
    this.duree = +(params.get('duree') ?? 180);
    this.imgS = +(params.get('img_s') ?? 5);
    this.pas = 1 / 30;
    this.etat = window.campagne = {
      etat: 'attente', episode: 0, episodes: this.episodes, images: 0, t_simule_s: 0, sans_reponse: 0, message: '',
    };
  }

  async lancer() {
    const { app, etat } = this;
    const pont = app.bridge;
    try {
      if (!(await pont.attendreConnexion(120000))) throw new Error('passerelle injoignable');
      etat.etat = 'en_cours';
      const dtImage = 1 / this.imgS;
      const n = Math.max(1, Math.round(dtImage / this.pas));
      for (let k = 0; k < this.episodes; k++) {
        const graine = this.graine + k;
        etat.episode = k;
        // tout l'aléatoire de l'épisode (plaques, modèles 3D, sillages) part de la même graine : épisode reproductible
        Math.random = mulberry32(graine * 7919 + 17);
        for (const v of app.traffic.vessels.slice()) app.traffic.remove(v);
        const sc = genererScenario(graine, app);
        app.appliquerScenario(sc);
        app.simSeconds = 0;
        pont.envoyerTexte({ type: 'episode_debut', numero: k, graine, scenario: sc });
        // une seconde pour poser la mer et faire flotter les coques avant la première image
        for (let i = 0; i < 30; i++) { app.avancerMer(this.pas); app.simuler(this.pas); }
        app.simSeconds = 0;
        for (let t = 0; t < this.duree - 1e-6; t += dtImage) {
          app.avancerMer(dtImage);
          for (let i = 0; i < n; i++) app.simuler(dtImage / n);
          app.dessiner(dtImage);
          const ok = await pont.envoyerEtAttendre(app.canvas, app.frameMeta());
          if (!ok) {
            etat.sans_reponse++;
            if (pont.status !== 'connected' && !(await pont.attendreConnexion(60000))) throw new Error('passerelle perdue');
          }
          etat.images++;
          etat.t_simule_s += dtImage;
        }
        pont.envoyerTexte({ type: 'episode_fin', numero: k });
      }
      pont.envoyerTexte({ type: 'campagne_fin' });
      etat.etat = 'finie';
    } catch (e) {
      etat.etat = 'erreur';
      etat.message = String(e?.message || e);
      console.error('campagne :', e);
    }
  }
}
