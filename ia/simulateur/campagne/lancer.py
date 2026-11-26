"""
Une instance de campagne sans écran : site statique, passerelle de la chaîne IA, Chromium sans écran.

    site statique (dist/)  <-  Chromium sans écran (2028 x 1520, WebGL 2 sur le GPU NVIDIA)
                                     |  images  ->  passerelle chaine_cerema.py --campagne DOSSIER
                                     |  <- « pas » après chaque image (temps simulé)

Suit window.campagne et la passerelle, s'arrête à la fin, sur erreur ou délai dépassé, puis copie le dossier de
résultats sur le Drive (rclone). Les ports sont choisis libres : plusieurs instances peuvent partager un GPU.

    python ia/simulateur/campagne/lancer.py --graine 1000 --episodes 20 --duree 180 --tache 1

Python : celui qui a Playwright (--python-chaine donne celui de la chaîne : ultralytics, OpenCV, ONNX Runtime).
Sortie : 0 campagne finie, 1 erreur, 2 délai dépassé.
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ICI = Path(__file__).resolve().parent
SIMU = ICI.parent
DEPOT = SIMU.parents[1]
LARGEUR, HAUTEUR = 2028, 1520  # image de la caméra IMX500

# Chromium sans écran avec le GPU NVIDIA (ANGLE sur EGL) ; Vulkan retombe sur SwiftShader.
ARGS_CHROMIUM = [
    "--use-gl=angle", "--use-angle=gl-egl", "--ignore-gpu-blocklist", "--enable-gpu",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows", "--no-first-run",
]


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def journal(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def rendu_webgl(page) -> dict:
    """Carte qui fait le rendu WebGL 2 dans la page (NVIDIA attendu, pas SwiftShader)."""
    return page.evaluate("""() => {
        const gl = document.createElement('canvas').getContext('webgl2');
        if (!gl) return {webgl2: false};
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        return {webgl2: true,
                vendeur: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                rendu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)};
    }""")


def logiciel(rendu: dict) -> bool:
    r = (rendu.get("rendu") or "").lower()
    return not rendu.get("webgl2") or "swiftshader" in r or "llvmpipe" in r or "software" in r


class Passerelle:
    """chaine_cerema.py en sous-processus ; garde sa sortie dans un fichier et repère « CAMPAGNE FINIE »."""

    def __init__(self, python: str, port: int, dossier: Path | None, detecteur: str, fichier: Path):
        cmd = [python, str(SIMU / "bridge" / "chaine_cerema.py"), "--port", str(port), "--detecteur", detecteur]
        if dossier is not None:
            cmd += ["--campagne", str(dossier)]
        self.sortie = open(fichier, "w", encoding="utf-8")
        self.finie = threading.Event()
        self.prete = threading.Event()
        self.derniere = ""
        self.ips = []  # img/s annoncés par la passerelle (mode normal)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(cmd, cwd=DEPOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, env=env)
        threading.Thread(target=self._lire, daemon=True).start()

    def _lire(self):
        for ligne in self.proc.stdout:
            self.sortie.write(ligne)
            self.sortie.flush()
            ligne = ligne.strip()
            if not ligne:
                continue
            self.derniere = ligne
            if "en attente du simulateur" in ligne:
                self.prete.set()
            if ligne == "CAMPAGNE FINIE":
                self.finie.set()
            if " img/s" in ligne:
                try:
                    self.ips.append(float(ligne.split(" img/s")[0].split("·")[-1].strip()))
                except ValueError:
                    pass

    def arreter(self, delai=20):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(delai)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.sortie.close()


def copier_drive(rclone: str, dossier: Path, dest: str) -> bool:
    journal(f"copie vers {dest}")
    r = subprocess.run([rclone, "copy", str(dossier), dest, "--transfers", "4"], capture_output=True, text=True)
    if r.returncode != 0:
        journal(f"rclone a échoué ({r.returncode}) : {r.stderr.strip()[-500:]}")
    return r.returncode == 0


class Arret(Exception):
    """SIGTERM de Slurm (fin de --time, scancel) : on s'arrête proprement et on copie ce qui est fait."""


def sur_signal(num, _):
    raise Arret(f"signal {signal.Signals(num).name}")


def heure_limite(texte: str | None) -> float | None:
    """« 06:45 » -> instant (time.time) de la prochaine occurrence de cette heure."""
    if not texte:
        return None
    h, m = map(int, texte.split(":"))
    now = datetime.now()
    cible = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if cible <= now:
        cible += timedelta(days=1)
    return cible.timestamp()


def main():
    ap = argparse.ArgumentParser(description="Une instance de campagne du simulateur, sans écran")
    ap.add_argument("--graine", type=int, default=1000, help="graine du premier épisode")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--duree", type=float, default=180, help="secondes simulées par épisode")
    ap.add_argument("--img-s", type=float, default=5, help="images par seconde simulée envoyées à la chaîne")
    ap.add_argument("--detecteur", default="best4_2")
    ap.add_argument("--tache", default="0", help="nom de la tâche dans le dossier du Drive (tache_<k>)")
    ap.add_argument("--campagne-nom", default=None, help="AAAA-MM-JJ_HHMM commun aux tâches (défaut : maintenant)")
    ap.add_argument("--travail", type=Path, default=None, help="dossier local des résultats (défaut : $TMPDIR)")
    ap.add_argument("--dist", type=Path, default=SIMU / "dist", help="site statique construit (npm run build)")
    ap.add_argument("--python-chaine", default=os.environ.get("PYTHON_CHAINE", sys.executable))
    ap.add_argument("--rclone", default=os.environ.get("RCLONE", "rclone"))
    ap.add_argument("--drive", default="gdrive:Minos/cerema-usv-ia/campagnes", help="« non » : pas de copie")
    ap.add_argument("--delai", type=float, default=None,
                    help="délai maximal en secondes (défaut : 10 s réelles par seconde simulée + 10 min)")
    ap.add_argument("--arret-a", default=None, metavar="HH:MM",
                    help="heure d'arrêt propre (les épisodes finis sont gardés et copiés)")
    ap.add_argument("--copie-min", type=float, default=10,
                    help="copie partielle sur le Drive toutes les N minutes (0 : seulement à la fin)")
    ap.add_argument("--sans-progres", type=float, default=600, help="arrêt si rien n'avance pendant ce temps (s)")
    ap.add_argument("--accepter-logiciel", action="store_true", help="continuer même si WebGL est SwiftShader")
    ap.add_argument("--mode-normal", type=float, default=None, metavar="SECONDES",
                    help="essai : simulateur actuel en temps réel (demo-tuteur, passerelle sans --campagne) "
                         "pendant SECONDES, pour mesurer les images par seconde")
    args = ap.parse_args()

    if not (args.dist / "index.html").exists():
        sys.exit(f"{args.dist}/index.html absent : lancer « npm ci && npm run build » dans {SIMU}")
    nom = args.campagne_nom or datetime.now().strftime("%Y-%m-%d_%H%M")
    base = args.travail or Path(os.environ.get("TMPDIR", "/tmp")) / f"campagne_{os.getpid()}"
    dossier = base / f"tache_{args.tache}"
    dossier.mkdir(parents=True, exist_ok=True)
    p_web, p_ws = port_libre(), port_libre()
    normal = args.mode_normal is not None
    delai = args.mode_normal + 120 if normal else (args.delai or args.episodes * args.duree * 10 + 600)
    if normal:
        url = (f"http://127.0.0.1:{p_web}/?scenario=demo-tuteur&bridge=1&ws=ws://127.0.0.1:{p_ws}&ui=0&dpr=1")
    else:
        url = (f"http://127.0.0.1:{p_web}/?campagne=1&graine={args.graine}&episodes={args.episodes}"
               f"&duree={args.duree:g}&img_s={args.img_s:g}&ws=ws://127.0.0.1:{p_ws}&ui=0&dpr=1")
    commit = subprocess.run(["git", "-C", str(DEPOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    infos = {"nom": nom, "tache": args.tache, "graine": args.graine, "episodes": args.episodes,
             "duree_s": args.duree, "img_s": args.img_s, "detecteur": args.detecteur, "url": url,
             "commit": commit, "noeud": socket.gethostname(), "job": os.environ.get("SLURM_JOB_ID"),
             "debut": datetime.now().isoformat(timespec="seconds"), "mode_normal_s": args.mode_normal}
    journal(f"tâche {args.tache} : {url}")

    limite = heure_limite(args.arret_a)
    signal.signal(signal.SIGTERM, sur_signal)
    web = subprocess.Popen([sys.executable, "-m", "http.server", str(p_web), "--bind", "127.0.0.1",
                            "--directory", str(args.dist)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    passerelle = Passerelle(args.python_chaine, p_ws, None if normal else dossier, args.detecteur,
                            dossier / "passerelle.log")
    console = open(dossier / "navigateur.log", "w", encoding="utf-8")
    code, raison, etat = 1, "", {}
    t0 = time.monotonic()
    try:
        if not passerelle.prete.wait(300):
            raise RuntimeError(f"passerelle pas prête en 5 min : {passerelle.derniere}")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            nav = pw.chromium.launch(headless=True, args=ARGS_CHROMIUM)
            page = nav.new_page(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=1)
            page.on("console", lambda m: console.write(f"{m.type}: {m.text}\n"))
            page.on("pageerror", lambda e: console.write(f"pageerror: {e}\n"))
            page.goto(f"http://127.0.0.1:{p_web}/", wait_until="domcontentloaded")
            infos["webgl"] = rendu_webgl(page)
            journal(f"WebGL : {infos['webgl']}")
            if logiciel(infos["webgl"]) and not args.accepter_logiciel:
                raise RuntimeError("rendu WebGL logiciel (SwiftShader) : pas de GPU dans le navigateur")
            page.goto(url, wait_until="domcontentloaded")
            avance, t_avance = None, time.monotonic()
            t_copie = time.monotonic()
            while True:
                time.sleep(5)
                ecoule = time.monotonic() - t0
                if limite and time.time() >= limite:
                    code, raison = 2, f"heure d'arrêt {args.arret_a} atteinte"
                    break
                if (args.drive != "non" and args.copie_min > 0 and not normal
                        and time.monotonic() - t_copie > args.copie_min * 60):
                    t_copie = time.monotonic()  # point de sauvegarde : episodes.jsonl et journaux déjà écrits
                    threading.Thread(target=copier_drive, daemon=True,
                                     args=(args.rclone, dossier, f"{args.drive}/{nom}/tache_{args.tache}")).start()
                if passerelle.finie.is_set():
                    code, raison = 0, "campagne finie"
                    break
                if passerelle.proc.poll() is not None:
                    raison = f"passerelle arrêtée (code {passerelle.proc.returncode}) : {passerelle.derniere}"
                    break
                if normal:
                    if ecoule >= args.mode_normal:
                        code, raison = 0, "essai fini"
                        break
                    continue
                etat = page.evaluate("() => window.campagne || null") or {}
                if etat.get("etat") == "erreur":
                    raison = f"erreur dans la page : {etat.get('message')}"
                    break
                cle = (etat.get("episode"), etat.get("images"))
                if cle != avance:
                    avance, t_avance = cle, time.monotonic()
                    if int(ecoule) % 60 < 5:
                        journal(f"épisode {etat.get('episode')}/{etat.get('episodes')}, {etat.get('images')} images, "
                                f"{etat.get('t_simule_s', 0):.0f} s simulées")
                elif time.monotonic() - t_avance > args.sans_progres:
                    raison = f"plus rien n'avance depuis {args.sans_progres:.0f} s : {etat}"
                    break
                if ecoule > delai:
                    code, raison = 2, f"délai dépassé ({delai:.0f} s)"
                    break
            try:
                page.screenshot(path=str(dossier / "derniere_image.jpg"), type="jpeg", quality=80)
            except Exception:
                pass
            nav.close()
    except Arret as e:
        code, raison = 2, raison or f"arrêt demandé ({e})"
    except Exception as e:
        raison = raison or f"{type(e).__name__} : {e}"
    finally:
        passerelle.arreter()
        web.terminate()
        console.close()

    duree = time.monotonic() - t0
    infos.update({"fin": datetime.now().isoformat(timespec="seconds"), "duree_reelle_s": round(duree, 1),
                  "code": code, "raison": raison, "etat_page": etat})
    if normal and passerelle.ips:
        infos["img_s_passerelle"] = passerelle.ips
        infos["img_s_moyen"] = round(sum(passerelle.ips[1:] or passerelle.ips) / len(passerelle.ips[1:] or passerelle.ips), 2)
    (dossier / "lancement.json").write_text(json.dumps(infos, ensure_ascii=False, indent=1))
    journal(f"fin : {raison} ({duree / 60:.1f} min)")
    if normal and passerelle.ips:
        journal(f"images par seconde à la passerelle : {infos['img_s_moyen']} (relevés {passerelle.ips})")

    if args.drive != "non":
        if copier_drive(args.rclone, dossier, f"{args.drive}/{nom}/tache_{args.tache}"):
            shutil.rmtree(dossier, ignore_errors=True)  # /Brain est presque plein : rien ne reste sur place
            try:
                base.rmdir()
            except OSError:
                pass
        else:
            journal(f"résultats gardés dans {dossier}")
    sys.exit(code)


if __name__ == "__main__":
    main()
