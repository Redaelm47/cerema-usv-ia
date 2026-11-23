// Assemble index.html à partir du template 3b1b-light-deck (repo claude-presentation-skills).
// Usage: node build.js <chemin vers .claude/skills>
const fs = require('fs'), path = require('path');
const SK = process.argv[2];
const tpl = fs.readFileSync(path.join(SK, '3b1b-light-deck/reference/deck-template.html'), 'utf8');

// ---- polices CMU Serif embarquées (équivalent mkfonts.js) ----
const mfDir = path.join(SK, '3b1b-light-deck/fonts');
let fonts = '';
for (const f of JSON.parse(fs.readFileSync(path.join(mfDir, 'fonts.manifest.json'), 'utf8'))) {
  const b = fs.readFileSync(path.join(mfDir, f.file)).toString('base64');
  fonts += `@font-face{font-family:'${f.family}';font-style:${f.style || 'normal'};font-weight:${f.weight};font-display:swap;src:url(data:font/ttf;base64,${b}) format('truetype');}\n`;
}

// ---- squelette du template : tête (CSS, defs) + pied (nav, script) ----
let head = tpl.slice(0, tpl.indexOf('<div id="stage">') + '<div id="stage">'.length);
let tail = tpl.slice(tpl.indexOf('<div id="progress">'));

const RED = '#CF5044', BLUE = '#1C758A', GOLD = '#C78D46';
const EXTRA = `
/* ---- ajouts Projet 20 : listes courtes, cartes, couverture ---- */
.pts{list-style:none; text-align:left; display:flex; flex-direction:column; gap:26px; font-size:28px; line-height:1.25; max-width:1000px;}
.pts li{position:relative; padding-left:40px;}
.pts li::before{content:''; position:absolute; left:4px; top:11px; width:13px; height:13px; border-radius:50%; border:3px solid ${BLUE}; background:#fff;}
.pts li.hot::before{background:${RED}; border-color:${RED};}
.pts b{font-weight:700;}
.pts.num{counter-reset:n;}
.pts.num li{counter-increment:n; padding-left:52px;}
.pts.num li::before{content:counter(n); border:none; background:none; width:auto; height:auto; top:0; left:0; color:${BLUE}; font-weight:700; font-size:28px;}
.pts.lab li{padding-left:50px;}
.pts.lab li::before{content:attr(data-n); border:none; background:none; width:auto; height:auto; top:0; left:0; color:${BLUE}; font-weight:700;}
.pts.lab li.hot::before{background:none; color:${RED};}
.ph{color:${GOLD};}
.big{font-size:35px; line-height:1.42; max-width:1000px;}
.big b{font-weight:700;}
.chips{display:flex; gap:26px; justify-content:center; margin-top:44px;}
.chip{border:2px solid #000; border-radius:999px; padding:9px 26px; font-size:22px;}
.cards{display:flex; gap:30px; width:100%; max-width:1130px; align-items:stretch;}
.card{flex:1; border:2px solid #000; border-radius:14px; padding:24px 24px 26px; text-align:left;}
.card.c1{border-color:${BLUE}; background:rgba(28,117,138,.10);}
.card.c3{border-color:${RED}; background:rgba(207,80,68,.08);}
.card .n{font-size:15px; letter-spacing:.2em; text-transform:uppercase; color:#777;}
.card h3{font-size:25px; font-weight:700; margin:6px 0 4px; line-height:1.15;}
.card .tool{font-size:19px; font-style:italic; color:#555; margin-bottom:16px;}
.card ul{list-style:none; display:flex; flex-direction:column; gap:10px; font-size:20px; line-height:1.25;}
.card li{padding-left:20px; position:relative;}
.card li::before{content:''; position:absolute; left:0; top:9px; width:7px; height:7px; border-radius:50%; background:#000;}
.card .role{margin-top:auto; padding-top:14px; font-size:17.5px; white-space:nowrap; font-weight:700; color:${BLUE};}
.card .role .rl{display:block; margin-top:14px; padding-top:12px; border-top:1px solid #ccc; font-size:13px; font-weight:400; letter-spacing:.2em; text-transform:uppercase; color:#777;}
.grid{display:grid; grid-template-columns:repeat(3,1fr); gap:24px; width:100%; max-width:1130px;}
.cell{border:2px solid #000; border-radius:14px; padding:22px 22px; text-align:left; min-height:150px;}
.cell h3{font-size:23px; font-weight:700; line-height:1.18;}
.cell p{font-size:19px; color:#555; font-style:italic; margin-top:9px; line-height:1.28;}
.qs{display:grid; grid-template-columns:1fr 1fr; grid-auto-flow:column; grid-template-rows:repeat(4,auto); gap:22px 60px; text-align:left; font-size:23px; line-height:1.25; width:100%; max-width:1120px;}
.qs div{display:flex; gap:16px;}
.qs div i{font-style:normal; font-weight:700; color:${BLUE}; min-width:24px;}
.cov{flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:40px 64px;}
.cov h1{font-size:62px; font-weight:400; line-height:1.12;}
.cov .meta{display:grid; grid-template-columns:auto auto; gap:8px 22px; margin-top:26px; font-size:21px; text-align:left;}
.cov .meta > span:nth-child(odd){color:#777; text-align:right;}
.corner{position:absolute; font-size:14px; letter-spacing:.18em; text-transform:uppercase; color:#999;}
.two{display:flex; gap:60px; align-items:center; width:100%; max-width:1150px;} .two .pts{flex:1;}
.d-opt{fill:rgba(199,141,70,.13); stroke:${GOLD}; stroke-width:2; stroke-dasharray:6 5;}
.d-lab{font-size:17.5px;} .d-lab.s{font-size:15px;}
.d-red{fill:rgba(207,80,68,.08); stroke:${RED}; stroke-width:2;}
`;

head = head
  .replace('/*FONTS*/', fonts)
  .replace(/<title>.*?<\/title>/, '<title>Revue de projet · Projet 20</title>')
  .replace('/* ---- nav ---- */', EXTRA + '\n/* ---- nav ---- */')
  // règle du thème clair : l'emphase est le stylo rouge red_e, jamais le jaune
  .replace(/rgba\(232,193,28,\.1[56]\)/g, 'rgba(207,80,68,.08)')
  .replace(/#E8C11C/g, RED);
tail = tail.replace(/#E8C11C/g, RED);

const slides = require('./slides.js');
const N = slides.length;
const pad = n => String(n).padStart(2, '0');
const uline = t => {
  const w = Math.round(34 + t.replace(/&amp;/g, '&').length * 19);
  return `<svg class="uline" width="${w}" height="14" viewBox="0 0 ${w} 14"><path d="M4 8 C ${Math.round(w * .28)} 3, ${Math.round(w * .7)} 12, ${w - 4} 6" stroke="${RED}" stroke-width="3.5" fill="none" stroke-linecap="round"/></svg>`;
};

const body = slides.map((s, k) => {
  const act = k === 0 ? ' active' : '';
  if (s.raw) return `<section class="slide${act}">${s.raw(uline)}<div class="pageno">${pad(k + 1)} / ${pad(N)}</div></section>`;
  return `<section class="slide${act}">
  <div class="scn">
    <div class="kick">${s.kick}</div>
    <h2>${s.title}</h2>
    ${uline(s.ulen ? 'x'.repeat(s.ulen) : s.title)}
    ${s.fig ? `<div class="fig">${s.fig}</div>` : ''}
    ${s.note ? `<p class="note">${s.note}</p>` : ''}
  </div>
  <div class="pageno">${pad(k + 1)} / ${pad(N)}</div>
</section>`;
}).join('\n\n');

const html = head + '\n\n' + body + '\n\n</div>\n\n' + tail;
if (/\{\{/.test(html)) throw new Error('placeholder {{ restant');
if (/—|–/.test(html.replace(/base64,[^)]+\)/g, ''))) throw new Error('tiret long détecté');
fs.writeFileSync(path.join(__dirname, 'index.html'), html);
console.log('index.html :', N, 'slides,', (html.length / 1024).toFixed(0), 'Ko');
