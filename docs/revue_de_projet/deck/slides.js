// Revue de projet (jalon J3), refaite à partir de la version de l'équipe
// et de la réunion client du 15/10/2026. Une idée par slide.
const RED = '#CF5044', BLUE = '#1C758A', GREEN = '#699C52', GOLD = '#C78D46', GRAY = '#8a8a8a';
const DATE = '21 octobre 2026';
const AR = `<defs><marker id="ar" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#000"/></marker>
  <marker id="arR" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="${RED}"/></marker></defs>`;

// ---------- planning v2, par grandes tâches ----------
function gantt() {
  const X0 = 290, D0 = Date.UTC(2026, 8, 28), PX = 9.4; // px par jour
  const x = (j, m) => X0 + (Date.UTC(2026, m - 1, j) - D0) / 864e5 * PX;
  const rows = [
    ['L1 · Prise en main du matériel', [28, 9], [30, 10], GOLD],
    ['L1 · Intégration, propulsion', [2, 11], [22, 11], GRAY],
    ['L1 · Ajustements, tests', [23, 11], [7, 12], GRAY],
    ['L2 · Architecture et démo', [28, 9], [15, 10], GREEN],
    ['L2 · Experts, base de données', [16, 10], [22, 11], BLUE],
    ['L2 · Tests sur le Pi', [16, 11], [27, 11], GRAY],
    ['L3 · Intégration et recette', [30, 11], [18, 12], GRAY],
  ];
  const T = 70, H = 46;
  let s = `<svg width="1150" height="500" viewBox="0 0 1150 500" fill="none">${AR}`;
  // semaines
  for (let k = 0; k <= 12; k++) {
    const xx = X0 + k * 7 * PX, d = new Date(D0 + k * 7 * 864e5);
    s += `<line x1="${xx}" y1="${T - 10}" x2="${xx}" y2="${T + rows.length * H}" stroke="#e4e4e4"/>`;
    if (k % 2 === 0) s += `<text x="${xx}" y="${T - 20}" text-anchor="middle" class="d-lab s">${String(d.getUTCDate()).padStart(2, '0')}/${String(d.getUTCMonth() + 1).padStart(2, '0')}</text>`;
  }
  rows.forEach(([lab, a, b, c], i) => {
    const y = T + i * H;
    s += `<text x="0" y="${y + 29}" class="d-lab" style="font-size:19px">${lab}</text>
    <rect x="${x(...a)}" y="${y + 10}" width="${x(...b) - x(...a)}" height="26" rx="6" fill="${c}"/>`;
  });
  // retard L1
  const yL1 = T + 10;
  s += `<text x="${x(30, 10) + 10}" y="${yL1 + 19}" class="d-lab s" style="fill:${GOLD};font-size:16px">glisse : GPS bloqué</text>`;
  // aujourd'hui
  const xt = x(21, 10);
  s += `<line x1="${xt}" y1="${T - 10}" x2="${xt}" y2="${T + rows.length * H + 8}" stroke="${RED}" stroke-width="2.5"/>
  <text x="${xt}" y="${T + rows.length * H + 30}" text-anchor="middle" class="d-lab" style="fill:${RED};font-size:17px">aujourd'hui</text>`;
  // jalons
  const yj = T + rows.length * H + 66;
  [['J4', 23, 10], ['J5', 5, 11], ['J6', 20, 11], ['J7', 27, 11], ['J8', 18, 12]].forEach(([n, j, m]) => {
    const xx = x(j, m);
    s += `<rect x="${xx - 9}" y="${yj - 9}" width="18" height="18" transform="rotate(45 ${xx} ${yj})" fill="#000"/>
    <text x="${xx}" y="${yj + 34}" text-anchor="middle" class="d-lab" style="font-size:17px">${n}</text>`;
  });
  s += `<text x="0" y="${yj + 6}" class="d-lab b" style="font-size:19px">Jalons</text>`;
  // légende
  const lg = [[GREEN, 'terminé'], [BLUE, 'en cours'], [GOLD, 'en retard'], [GRAY, 'à venir']];
  lg.forEach(([c, n], i) => {
    const xx = 0 + i * 150;
    s += `<rect x="${xx}" y="${T - 52}" width="22" height="14" rx="4" fill="${c}"/><text x="${xx + 30}" y="${T - 40}" class="d-lab s" style="font-size:15px">${n}</text>`;
  });
  return s + '</svg>';
}

// ---------- câblage du bateau autour du Pixhawk ----------
function cablage() {
  const bx = (x, y, w, h, t, a, c = '#000', fill = '#fff') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${fill}" stroke="${c}" stroke-width="2.5"/>
    <text x="${x + w / 2}" y="${y + (a ? h / 2 - 4 : h / 2 + 7)}" text-anchor="middle" class="d-lab" style="font-size:21px;font-weight:700">${t}</text>
    ${a ? `<text x="${x + w / 2}" y="${y + h / 2 + 20}" text-anchor="middle" class="d-lab s" style="font-size:16px">${a}</text>` : ''}`;
  let s = `<svg width="1100" height="400" viewBox="0 0 1100 400" fill="none">${AR}`;
  // Pixhawk au centre
  s += bx(420, 150, 260, 96, 'Pixhawk 6C Mini', 'ArduPilot Rover', BLUE, 'rgba(28,117,138,.10)');
  s += bx(20, 30, 270, 84, 'GPS NEO-M8P', 'Drotek · capte bien le signal');
  s += bx(20, 280, 270, 84, 'Station sol (PC)', 'QGroundControl');
  s += bx(810, 10, 270, 84, 'Batterie 4S', '14,8 V');
  s += bx(810, 156, 270, 84, 'Power module', 'répartit l\'alimentation');
  s += bx(810, 302, 270, 84, 'ESC + moteurs', 'pilotage par gouverne');
  // liens
  s += `<path d="M290 72 L350 72 L350 180 L414 180" stroke="${RED}" stroke-width="3" stroke-dasharray="8 6" marker-end="url(#arR)"/>
  <text x="340" y="150" text-anchor="end" class="d-lab" style="fill:${RED};font-size:18px;font-weight:700">bloqué ici</text>
  <path d="M290 322 L350 322 L350 216 L414 216" stroke="#000" stroke-width="2"  marker-end="url(#ar)"/>
  <text x="340" y="262" text-anchor="end" class="d-lab s" style="font-size:15px">USB, puis radio</text>
  <path d="M945 94 L945 150" stroke="#000" stroke-width="2" marker-end="url(#ar)"/>
  <path d="M810 198 L686 198" stroke="#000" stroke-width="2" marker-end="url(#ar)"/>
  <text x="748" y="188" text-anchor="middle" class="d-lab" style="font-size:17px;font-weight:700">5 V</text>
  <path d="M945 240 L945 296" stroke="#000" stroke-width="2" marker-end="url(#ar)"/>
  <text x="957" y="274" class="d-lab" style="font-size:17px;font-weight:700">14,8 V</text>
  <path d="M550 246 L550 344 L804 344" stroke="#000" stroke-width="2" marker-end="url(#ar)"/>
  <text x="680" y="334" text-anchor="middle" class="d-lab s" style="font-size:15px">commande</text>`;
  return s + '</svg>';
}

// ---------- chaîne vision ----------
function chaine() {
  const W = 160, G = 30, y = 60, H = 92;
  const box = [
    ['Caméra', 'repère les', GREEN, 'navires'],
    ['Suivi', 'un numéro', BLUE, 'par navire'],
    ['Décideur', 'choisit quoi', GREEN, 'faire'],
    ['Experts', 'type,', BLUE, 'immatriculation'],
    ['Alerte', 'message court', GREEN, 'sans image'],
    ['Station sol', 'écran de', GREEN, "l'opérateur"],
  ];
  let s = `<svg width="1110" height="300" viewBox="0 0 1110 300" fill="none">${AR}`;
  box.forEach(([t, a, c, b], i) => {
    const x = i * (W + G);
    s += `<rect x="${x + 1}" y="${y}" width="${W - 2}" height="${H}" rx="12" fill="#fff" stroke="${c}" stroke-width="3"/>
    <text x="${x + W / 2}" y="${y + 34}" text-anchor="middle" class="d-lab" style="font-size:22px;font-weight:700">${t}</text>
    <text x="${x + W / 2}" y="${y + 60}" text-anchor="middle" class="d-lab s" style="font-size:16px;fill:#555">${a}</text>
    <text x="${x + W / 2}" y="${y + 79}" text-anchor="middle" class="d-lab s" style="font-size:16px;fill:#555">${b}</text>`;
    if (i < box.length - 1) s += `<line x1="${x + W + 2}" y1="${y + H / 2}" x2="${x + W + G - 4}" y2="${y + H / 2}" stroke="#000" stroke-width="2" marker-end="url(#ar)"/>`;
  });
  const xd = 2 * (W + G) + W / 2, xe = 3 * (W + G) + W / 2;
  s += `<path d="M${xe} ${y} C ${xe} ${y - 45}, ${xd} ${y - 45}, ${xd} ${y + 2}" stroke="#555" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#ar)"/>
  <text x="${(xd + xe) / 2}" y="${y - 38}" text-anchor="middle" class="d-lab s">tant qu'il manque une info</text>`;
  const br = (x1, x2, lab) => `<path d="M${x1} 178 L${x1} 190 L${x2} 190 L${x2} 178" stroke="#999" stroke-width="1.5"/>
    <text x="${(x1 + x2) / 2}" y="214" text-anchor="middle" class="d-lab s" style="fill:#777">${lab}</text>`;
  s += br(4, 5 * (W + G) - G - 4, 'sur le drone (Raspberry Pi 4 + caméra IA IMX500)') + br(5 * (W + G) + 4, 6 * (W + G) - G - 4, 'au sol (PC)');
  [[GREEN, 'fonctionne'], [BLUE, 'en cours']].forEach(([c, n], i) => {
    const x = 410 + i * 170;
    s += `<rect x="${x}" y="252" width="26" height="18" rx="5" fill="#fff" stroke="${c}" stroke-width="3"/><text x="${x + 36}" y="267" class="d-lab s" style="font-size:17px">${n}</text>`;
  });
  return s + '</svg>';
}

const chiffre = (n, t, c = BLUE) => `<div class="cell" style="min-height:0;padding:28px"><h3 style="font-size:38px;color:${c}">${n}</h3><p style="font-style:normal;color:#333;font-size:23px">${t}</p></div>`;
const cell = (t, p, cls = '', big = false) => `<div class="cell ${cls}" style="min-height:0"><h3${big ? ' style="font-size:27px"' : ''}>${t}</h3><p${big ? ' style="font-size:22px"' : ''}>${p}</p></div>`;
const img = f => 'data:image/jpeg;base64,' + require('fs').readFileSync(require('path').join(__dirname, 'assets', f)).toString('base64');
const dot = c => `<span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${c};margin-right:10px;vertical-align:1px"></span>`;

module.exports = [
  // 1 · couverture
  { raw: (uline) => `
  <div class="corner" style="left:34px;top:26px">Projet 20 · Cerema × IMT Atlantique</div>
  <div class="corner" style="right:34px;top:26px">${DATE} · jalon J3</div>
  <div class="cov">
    <div class="kick" style="margin-bottom:18px">Revue de projet</div>
    <h1>Drone de surface<br>et détection de navires par IA</h1>
    ${uline('Drone de surface et détection')}
    <div class="meta">
      <span>Client</span><span>Antoine Douchin, Cerema (DTecREM)</span>
      <span>Tuteur</span><span>Matthieu Arzel, IMT Atlantique</span>
      <span>Équipe</span><span>Guillaume Leroy · Reda El Mekkaoui · Adam-Sabri Hlaoua</span>
      <span></span><span>Ewen Gourmelen · Rana Brini · Selma Ben-Abdelkader</span>
    </div>
  </div>` },

  // 2 · en bref
  { kick: '1 · En bref', title: 'Où en est-on à mi-parcours',
    fig: `<div class="cards" style="max-width:1100px">
      <div class="card c1"><div class="n">Lot L2 · vision</div><h3 style="font-size:30px;margin:10px 0 14px">Ça marche</h3>
        <ul style="font-size:22px;gap:14px"><li>Chaîne complète sur le Raspberry Pi</li><li>Montrée au Cerema le 15/10</li></ul></div>
      <div class="card c3"><div class="n">Lot L1 · bateau</div><h3 style="font-size:30px;margin:10px 0 14px">Ça bloque</h3>
        <ul style="font-size:22px;gap:14px"><li>Le GPS ne parle pas au Pixhawk</li><li>La propulsion attend ce point</li></ul></div>
      <div class="card"><div class="n">Prochain jalon</div><h3 style="font-size:30px;margin:10px 0 14px">J4 · 23/10</h3>
        <ul style="font-size:22px;gap:14px"><li>Cahiers des charges validés</li><li>Schéma de câblage validé</li></ul></div>
    </div>`,
    note: `Objectif : un drone de surface qui patrouille seul, repère les navires, les identifie et alerte l'opérateur.` },

  // 3 · planning
  { kick: '2 · Planning', title: 'Le planning',
    fig: `<img src="data:image/png;base64,${require('fs').readFileSync(require('path').join(__dirname, 'assets', 'gantt-synthese.png')).toString('base64')}" style="height:535px">`,
    note: `Planning du document de synthèse. Retard sur L1 : le GPS bloque l'intégration et la propulsion.` },

  // 4 · WBS
  { kick: '3 · Organisation', title: 'Quatre lots, un responsable chacun',
    fig: `<div class="grid" style="grid-template-columns:repeat(4,1fr);max-width:1180px">
      ${cell('L0 · Gestion', 'Reda · synthèse ✓, revue, plan d\'actions, suivi hebdo', '', true)}
      ${cell('L1 · Bateau', 'Ewen, avec Rana et Selma · matériel, câblage, propulsion, essais', '', true)}
      ${cell('L2 · Vision', 'Reda, avec Guillaume et Adam-Sabri · caméra, experts, station sol', '', true)}
      ${cell('L3 · Intégration', 'Guillaume · vision sur le bateau, démonstration finale', '', true)}
    </div>`,
    note: `Deux équipes de trois qui avancent en parallèle, et se rejoignent en L3 (fin novembre).` },

  // 5 · bateau : où ça bloque
  { kick: '4 · Lot L1 · bateau', title: 'Tout passe par le Pixhawk',
    fig: cablage(),
    note: `Le GPS capte bien (LED fixe), mais le Pixhawk ne le voit pas, branché sur le port GPS 2.` },

  // 6 · bateau : plan
  { kick: '4 · Lot L1 · bateau', title: 'Le plan pour débloquer',
    fig: `<ul class="pts lab" style="font-size:22px;gap:13px;max-width:1120px">
      <li data-n="1a"><b>Documentation</b> : chercher plus de documentation sur le Drotek NEO-M8P pour connaître précisément ses broches</li>
      <li data-n="1b"><b>Protocoles</b> : vérifier que ces broches sont compatibles avec le Pixhawk</li>
      <li data-n="2"><b>Port GPS 1</b> : l'utiliser au lieu du GPS 2, sans rien brancher sur les broches 6 à 9 (a priori, le GPS 2 seul devrait aussi marcher)</li>
      <li data-n="3"><b>u-center (u-blox)</b> : l'installer, réinitialiser le NEO-M8P et vérifier le baudrate</li>
      <li data-n="4"><b>QGroundControl</b> : comprendre en détail ses fonctions pour régler les bons paramètres</li>
      <li data-n="5"><b>Soudure</b> : souder les connexions sur le module</li>
      <li data-n="6" class="hot"><b>Sinon</b> : passer à un GPS u-blox F9P</li>
    </ul>`,
    note: `Conseil du Cerema : <b>le matériel d'abord, le logiciel ensuite</b>. Batterie 4S vérifiée au multimètre avant chaque branchement.` },

  // 7 · vision : chaîne
  { kick: '5 · Lot L2 · vision', title: 'La chaîne, de la caméra à la station sol',
    fig: chaine(),
    note: `La caméra regarde en continu. Les experts, plus lourds, ne tournent que quand le décideur les appelle.` },

  // 8 · simulation : avant / après
  { kick: '5 · Lot L2 · vision', title: 'La simulation montrée au client le 15/10',
    fig: `<div style="display:flex;gap:28px;align-items:flex-start">
      <figure style="margin:0;text-align:center"><img src="${img('simulation-debut.jpg')}" style="width:500px;border-radius:10px;border:2px solid #000">
        <figcaption class="note" style="margin-top:8px">Début : deux navires au loin</figcaption></figure>
      <figure style="margin:0;text-align:center"><img src="${img('simulation-alerte.jpg')}" style="width:500px;border-radius:10px;border:2px solid ${GREEN}">
        <figcaption class="note" style="margin-top:8px">21 s : type « pêche », immatriculation « GV 642410 », alerte envoyée</figcaption></figure>
    </div>`,
    note: `Simulation d'une mer agitée, analysée en entier par le Raspberry Pi. La station sol reçoit l'alerte en direct.` },

  // 8b · ce qu'on a mesuré
  { kick: '5 · Lot L2 · vision', title: 'Ce que la simulation a montré',
    fig: `<div class="grid" style="grid-template-columns:repeat(2,1fr);max-width:1000px">
      ${chiffre('2 navires, 2 alertes', 'le navire proche est identifié en 20 s', GREEN)}
      ${chiffre('1,2 s · 1,7 s', 'sur le Pi : expert type · lecture de l\'immatriculation', GREEN)}
      ${chiffre('Navire lointain', 'bien détecté, mais immatriculation illisible', RED)}
      ${chiffre('Vraie caméra', 'image floue de près : essai devant un écran pas encore concluant', RED)}
    </div>` },

  // 9 · retours du Cerema
  { kick: '6 · Retours du Cerema', title: 'Ce que le client nous a demandé',
    fig: `<div class="grid" style="grid-template-columns:repeat(2,1fr);max-width:1000px">
      ${cell('Base de données navires', 'L\'essentiel : une fiche par navire, une image, des champs qu\'on peut ajouter', 'c3')}
      ${cell('Ajouter des experts facilement', 'Pouvoir en brancher un nouveau plus tard sans tout refaire, par exemple reconnaître un navire déjà vu')}
      ${cell('Interface : ça suffit', 'Le tableau de bord actuel suffit, on le garde tel quel pour les tests')}
      ${cell('Pi : SSD et ventilateur', 'La carte SD s\'use vite, le Pi monte à 52 °C')}
    </div>`,
    note: `Paramètres (seuil, cadence) à garder réglables. Le vrai défi : détecter par mauvais temps, caméra salie.` },

  // 10 · risques
  { kick: '7 · Risques', title: 'Les risques principaux',
    fig: `<div class="tbl"><table class="cmp" style="font-size:25px">
      <tr><th>Risque</th><th>Criticité</th><th>Parade</th></tr>
      <tr><td>Immatriculation illisible à distance</td><td style="color:${RED};font-weight:700">9</td><td>Lecture seulement si l'image est nette</td></tr>
      <tr><td>GPS incompatible avec le Pixhawk <i style="color:${RED}">nouveau</i></td><td style="color:${RED};font-weight:700">6</td><td>Brochage, sinon GPS F9P</td></tr>
      <tr><td>Chauffe du Pi, carte SD usée <i style="color:${RED}">nouveau</i></td><td style="color:${RED};font-weight:700">6</td><td>Boîtier ventilé, SSD</td></tr>
      <tr><td>Pas d'images réelles d'immatriculation</td><td style="color:${RED};font-weight:700">6</td><td>Demande au Cerema, simulation</td></tr>
      <tr><td>Perte radio ou GPS en mer</td><td style="color:${RED};font-weight:700">6</td><td>Essais à quai, retour auto ArduPilot</td></tr>
    </table></div>`,
    note: `Criticité = probabilité × gravité, de 1 à 9. Tous les risques sont suivis chaque semaine dans le tableau de suivi.` },

  // 11 · relation client
  { kick: '8 · Relation client', title: 'Ce qu\'on attend du Cerema',
    fig: `<ul class="pts" style="font-size:27px">
      <li>${'<b>Validation du schéma de câblage</b> : prévue le 23/10'}</li>
      <li class="hot"><b>Images de navires avec immatriculation</b> : demandées</li>
      <li><b>Boîtier ventilé et SSD</b> pour le Pi : proposés par le client</li>
    </ul>`,
    note: `Réunion client toutes les deux semaines. Si on est bloqués : un mail, et une visio de 30 min.` },

  // 12 · rétrospective
  { kick: '9 · Rétrospective', title: 'Ce qu\'on garde, ce qu\'on change',
    fig: `<div class="cards">
      <div class="card c1"><h3>Ce qui marche</h3><ul style="margin-top:14px;font-size:21px">
        <li>Deux équipes en parallèle</li><li>Formats JSON fixés : chacun teste seul</li><li>Démo au client dès le 15/10</li></ul></div>
      <div class="card c3"><h3>Ce qui coince</h3><ul style="margin-top:14px;font-size:21px">
        <li>Câblage par essais, sans schéma</li><li>Matériel encore mal compris</li><li>Comptes rendus pas centralisés</li></ul></div>
      <div class="card"><h3>Ce qu'on décide</h3><ul style="margin-top:14px;font-size:21px">
        <li>Schéma annoté avant de brancher</li><li>Compte rendu sous 48 h</li><li>Bloqués 2 jours : on appelle</li></ul></div>
    </div>` },

  // 13 · qui fait quoi
  { kick: '10 · Qui fait quoi', title: 'Les prochaines actions',
    fig: `<div class="tbl"><table class="cmp" style="font-size:24px">
      <tr><th>Qui</th><th>Prochaine action</th><th>Pour le</th></tr>
      <tr><td>Reda, Adam-Sabri</td><td>Base de données navires, expert lecture d'immatriculation</td><td>30/10</td></tr>
      <tr><td>Guillaume</td><td>Mise au point de la caméra, essai réel, chauffe du Pi</td><td>23/10</td></tr>
      <tr><td>Ewen, Rana</td><td>Brochage GPS ↔ Pixhawk, GPS reconnu</td><td>23/10</td></tr>
      <tr><td>Selma</td><td>Cahiers des charges précis (J4)</td><td>23/10</td></tr>
    </table></div>` },

  // 14 · jalons et questions
  { kick: '11 · Suite', title: 'Les prochains jalons',
    fig: `<div class="grid" style="grid-template-columns:repeat(5,1fr);max-width:1180px;gap:18px">
        ${cell('J4 · 23/10', 'Cahiers des charges validés')}
        ${cell('J5 · 05/11', 'Plan d\'actions')}
        ${cell('J6 · 20/11', 'Bateau qui suit un cap')}
        ${cell('J7 · 27/11', 'Vision testée par mauvais temps')}
        ${cell('J8 · 18/12', 'Recette : scénario complet')}
      </div>` },
];
