"""Environnement marin pour la vidéo de test de vision embarquée (Blender 5.x).

Mer animée (modificateur Ocean : houle + clapot), ciel (HDRI Poly Haven si le
fichier est présent, sinon ciel procédural), brume d'horizon, côte lointaine,
caméra de petit drone de surface qui bouge avec la mer, flottaison des navires,
sillage, réglages de rendu.

Conventions : mètres, Z vers le haut, surface moyenne de la mer à z = 0.
Rose des vents : +Y = nord (cap 0°), +X = est (cap 90°). La caméra est près de
l'origine et regarde vers +Y. Les navires ont l'étrave vers +X.

Utilisation type (depuis un autre script) :

    import mer
    mer.vider_scene()
    mer.creer_mer(etat=3)
    mer.creer_ciel(heure=17.0, couverture=0.4)
    mer.creer_camera(etat=3)          # après creer_mer : elle suit la vraie surface
    route = bpy.data.objects.new("Route", None)   # parent : position et cap animés
    navire = creer_bateau(...); navire.parent = route
    mer.faire_flotter(navire, longueur=14.0, etat=3)
    mer.creer_sillage(navire, longueur=14.0, largeur=4.0, vitesse_noeuds=8.0)
    mer.regler_rendu(qualite="finale")
"""

import json
import math
import os
import random
import warnings

import bpy
import numpy as np

NOM_MER = "Mer"
NOM_MATERIAU_EAU = "Eau"
NOM_DRONE = "Drone"
NOM_CAMERA = "Camera"
NOM_BRUME = "Brume"
NOM_COTE = "Cote"
NOM_MONDE = "Ciel"
PREMIERE_IMAGE = 1

# Dossier des ressources téléchargées (non versionné) : .../cerema-usv-ia/data/blender/ressources
DOSSIER_RESSOURCES = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "blender", "ressources"))

# Ciels HDRI (Poly Haven, CC0), choisis selon la couverture nuageuse.
# (couverture maximale, fichier, intensité du fond)
CIELS_HDRI = [
    (0.45, "kloofendal_38d_partly_cloudy_puresky_4k.hdr", 1.0),   # éclaircies, nuages, soleil à 38°
    (0.75, "kloofendal_28d_misty_puresky_4k.hdr", 1.0),           # voilé, soleil diffus à 28°
    (1.01, "overcast_soil_puresky_4k.hdr", 1.0),                  # couvert gris
]

# Échelle de Douglas : hauteur significative totale, part de houle, longueur d'onde de houle,
# vaguelettes courtes (elles donnent la cambrure que le spectre du clapot n'a pas), et seuil
# d'écume : les crêtes plus hautes que seuil × Hs moutonnent (2 = jamais).
_ETATS = {
    2: dict(hs=0.35, hs_houle=0.18, lambda_houle=38.0, hs_rides=0.10, lambda_rides=2.0, ecume=2.00),
    3: dict(hs=0.90, hs_houle=0.45, lambda_houle=55.0, hs_rides=0.22, lambda_rides=2.8, ecume=0.50),
    4: dict(hs=1.80, hs_houle=0.95, lambda_houle=75.0, hs_rides=0.34, lambda_rides=4.5, ecume=0.36),
}
G = 9.81


# --------------------------------------------------------------------------- utilitaires

def _etat_mer(etat):
    """Paramètres physiques interpolés pour un état de mer (2 à 4, décimales admises)."""
    e = min(4.0, max(2.0, float(etat)))
    bas = int(math.floor(e))
    haut = min(4, bas + 1)
    t = e - bas
    p = {c: _ETATS[bas][c] * (1 - t) + _ETATS[haut][c] * t for c in _ETATS[bas]}
    p["hs_clapot"] = math.sqrt(max(p["hs"] ** 2 - p["hs_houle"] ** 2, 0.01))
    # Mer du vent jeune, donc plus courte et plus cambrée que la mer pleinement développée
    # de Pierson-Moskowitz (Hs = 0,21 U²/g) : vent du spectre réduit d'un tiers (clapot côtier).
    p["vent"] = 0.68 * math.sqrt(p["hs_clapot"] * G / 0.21)
    p["lambda_clapot"] = 8.2 * p["vent"] ** 2 / G
    p["periode_clapot"] = math.sqrt(2 * math.pi * p["lambda_clapot"] / G)
    p["periode_houle"] = math.sqrt(2 * math.pi * p["lambda_houle"] / G)
    return p


def _scene():
    return bpy.context.scene


def _lier(objet):
    _scene().collection.objects.link(objet)
    return objet


def _arbre(bloc):
    """Arbre de nœuds vidé d'un matériau ou d'un monde."""
    if bloc.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bloc.use_nodes = True
    bloc.node_tree.nodes.clear()
    return bloc.node_tree


def _courbes(bloc):
    """Toutes les courbes d'animation d'un bloc (actions à couches de Blender 4.4+/5)."""
    ad = getattr(bloc, "animation_data", None)
    if not ad or not ad.action:
        return []
    action = ad.action
    resultat = []
    if hasattr(action, "layers"):
        for couche in action.layers:
            for bande in couche.strips:
                for sac in getattr(bande, "channelbags", []):
                    resultat.extend(sac.fcurves)
    elif hasattr(action, "fcurves"):
        resultat.extend(action.fcurves)
    return resultat


def _poser_courbe(bloc, chemin, valeurs, indice=-1, proprietaire=None, image_debut=PREMIERE_IMAGE,
                  extrapolation="CONSTANT"):
    """Écrit une clé par image sur `chemin` (interpolation linéaire), sans toucher aux autres canaux.

    `proprietaire` : structure sur laquelle appeler keyframe_insert (modificateur, prise de nœud…),
    `bloc` restant le bloc de données qui porte l'animation.
    """
    cible = proprietaire if proprietaire is not None else bloc
    chemin_local = chemin if proprietaire is None else chemin.rsplit(".", 1)[-1]
    if indice >= 0:
        cible.keyframe_insert(chemin_local, index=indice, frame=image_debut)
    else:
        cible.keyframe_insert(chemin_local, frame=image_debut)
    courbe = None
    for c in _courbes(bloc):
        if c.data_path == chemin and (indice < 0 or c.array_index == indice):
            courbe = c
    if courbe is None:
        raise RuntimeError(f"courbe introuvable : {chemin}")
    n = len(valeurs)
    courbe.keyframe_points.clear()
    courbe.keyframe_points.add(n)
    co = np.empty(2 * n, dtype=np.float32)
    co[0::2] = np.arange(image_debut, image_debut + n)
    co[1::2] = valeurs
    courbe.keyframe_points.foreach_set("co", co)
    for point in courbe.keyframe_points:
        point.interpolation = "LINEAR"
    courbe.extrapolation = extrapolation
    courbe.update()
    return courbe


def _deux_cles(bloc, chemin, v0, v1, n_images, proprietaire, indice=-1):
    """Deux clés (début, fin), linéaire, extrapolée : temps de l'océan, dérive des bruits."""
    courbe = _poser_courbe(bloc, chemin, [v0, v1], indice=indice, proprietaire=proprietaire,
                           extrapolation="LINEAR")
    courbe.keyframe_points[1].co = (PREMIERE_IMAGE + n_images - 1, v1)
    courbe.keyframe_points[1].interpolation = "LINEAR"
    courbe.update()
    return courbe


def _positions_evaluees(objet):
    """Sommets de l'objet après modificateurs, tableau (n, 3)."""
    graphe = bpy.context.evaluated_depsgraph_get()
    graphe.update()
    maillage = objet.evaluated_get(graphe).data
    co = np.empty(len(maillage.vertices) * 3, dtype=np.float32)
    maillage.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _grille(nom, cote, n, centree=False):
    """Petit maillage carré régulier (sommets et faces), pour étalonner ou sonder l'océan."""
    xs = np.linspace(0.0, cote, n, endpoint=False) - (cote / 2 if centree else 0.0)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    co = np.stack([X.ravel(), Y.ravel(), np.zeros(n * n)], axis=1)
    idx = np.arange(n * n).reshape(n, n)
    faces = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1, 4)
    maillage = bpy.data.meshes.new(nom)
    maillage.from_pydata(co.tolist(), [], faces.tolist())
    return _lier(bpy.data.objects.new(nom, maillage))


def _supprimer(objet):
    donnees = objet.data
    bpy.data.objects.remove(objet, do_unlink=True)
    if donnees is not None and donnees.users == 0:
        bpy.data.meshes.remove(donnees)


def _cap_vers_xy(cap_deg):
    """Vecteur horizontal unitaire pointant vers le cap donné (0° = +Y, 90° = +X)."""
    a = math.radians(cap_deg)
    return math.sin(a), math.cos(a)


def vider_scene():
    """Supprime tous les objets et les données orphelines de la scène courante."""
    for objet in list(bpy.data.objects):
        bpy.data.objects.remove(objet, do_unlink=True)
    for famille in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights,
                    bpy.data.materials, bpy.data.worlds, bpy.data.actions, bpy.data.node_groups,
                    bpy.data.images, bpy.data.textures):
        for bloc in list(famille):
            if bloc.users == 0 or famille in (bpy.data.worlds, bpy.data.actions):
                try:
                    famille.remove(bloc)
                except (RuntimeError, ReferenceError):
                    pass
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    scene = _scene()
    scene.world = None
    scene.camera = None
    scene.frame_set(PREMIERE_IMAGE)


# --------------------------------------------------------------------------- nœuds

class _Noeuds:
    """Petit assistant de construction d'arbres de nœuds."""

    def __init__(self, arbre):
        self.arbre = arbre
        self.liens = arbre.links

    def nouveau(self, genre, nom=None, **proprietes):
        noeud = self.arbre.nodes.new(genre)
        if nom:
            noeud.name = nom
            noeud.label = nom
        for cle, valeur in proprietes.items():
            setattr(noeud, cle, valeur)
        return noeud

    def brancher(self, prise, valeur):
        """Relie une prise de sortie, ou fixe une constante, sur une prise d'entrée."""
        if isinstance(valeur, bpy.types.NodeSocket):
            self.liens.new(valeur, prise)
        else:
            prise.default_value = valeur

    def math(self, operation, a, b=None, c=None, borne=False):
        noeud = self.nouveau("ShaderNodeMath", operation=operation, use_clamp=borne)
        self.brancher(noeud.inputs[0], a)
        if b is not None:
            self.brancher(noeud.inputs[1], b)
        if c is not None:
            self.brancher(noeud.inputs[2], c)
        return noeud.outputs[0]

    def lisse(self, valeur, de_min, de_max, vers_min=0.0, vers_max=1.0, lineaire=False):
        """Transition douce (smoothstep) de `valeur` entre deux seuils."""
        noeud = self.nouveau("ShaderNodeMapRange")
        noeud.interpolation_type = "LINEAR" if lineaire else "SMOOTHSTEP"
        noeud.clamp = True
        for i, v in enumerate((valeur, de_min, de_max, vers_min, vers_max)):
            self.brancher(noeud.inputs[i], v)
        return noeud.outputs[0]

    def melange(self, facteur, a, b):
        """Mélange de deux scalaires."""
        noeud = self.nouveau("ShaderNodeMix", data_type="FLOAT")
        self.brancher(noeud.inputs[0], facteur)
        self.brancher(noeud.inputs[2], a)
        self.brancher(noeud.inputs[3], b)
        return noeud.outputs[0]

    def melange_couleur(self, facteur, a, b, mode="MIX"):
        noeud = self.nouveau("ShaderNodeMix", data_type="RGBA", blend_type=mode)
        self.brancher(noeud.inputs[0], facteur)
        self.brancher(noeud.inputs[6], a)
        self.brancher(noeud.inputs[7], b)
        return noeud.outputs[2]

    def bruit(self, vecteur, echelle, detail=2.0, rugosite=0.5, dimensions="3D", w=None):
        noeud = self.nouveau("ShaderNodeTexNoise", noise_dimensions=dimensions)
        self.brancher(noeud.inputs["Vector"], vecteur)
        noeud.inputs["Scale"].default_value = echelle
        noeud.inputs["Detail"].default_value = detail
        noeud.inputs["Roughness"].default_value = rugosite
        if w is not None and dimensions == "4D":
            self.brancher(noeud.inputs["W"], w)
        return noeud


def _couleur(r, g, b):
    return (r, g, b, 1.0)


# --------------------------------------------------------------------------- mer

def _maillage_mer(rayon, demi_angle_deg, pas_fin_deg, pas_grossier_deg=3.0,
                  r0=0.6, pas_min=0.10, croissance=0.015):
    """Disque en anneaux : fin près de la caméra et dans le secteur filmé (autour de +Y),
    de plus en plus lâche vers l'horizon. Le pas radial suit la taille d'un pixel projeté
    sur l'eau depuis une caméra au ras de l'eau."""
    rayons = [r0]
    while rayons[-1] < rayon:
        rayons.append(rayons[-1] + max(pas_min, rayons[-1] * croissance))
    rayons = np.array(rayons)
    n_fin = int(round(2 * demi_angle_deg / pas_fin_deg))
    fins = np.linspace(-demi_angle_deg, demi_angle_deg, n_fin + 1)
    n_gros = max(3, int(round((360 - 2 * demi_angle_deg) / pas_grossier_deg)))
    gros = np.linspace(demi_angle_deg, 360 - demi_angle_deg, n_gros + 1)[1:-1]
    angles = np.radians(np.concatenate([fins, gros]))      # mesurés depuis +Y, sens horaire
    na, nr = len(angles), len(rayons)

    co = np.zeros((nr * na + 1, 3), dtype=np.float32)
    co[:-1, 0] = (rayons[:, None] * np.sin(angles)[None, :]).ravel()
    co[:-1, 1] = (rayons[:, None] * np.cos(angles)[None, :]).ravel()
    centre = nr * na

    idx = np.arange(nr * na).reshape(nr, na)
    suiv = np.roll(idx, -1, axis=1)
    quads = np.stack([idx[:-1], suiv[:-1], suiv[1:], idx[1:]], axis=-1).reshape(-1, 4)
    tris = np.stack([np.full(na, centre), suiv[0], idx[0]], axis=-1)

    boucles = np.concatenate([quads.ravel(), tris.ravel()]).astype(np.int32)
    debuts = np.concatenate([np.arange(len(quads)) * 4,
                             len(quads) * 4 + np.arange(len(tris)) * 3]).astype(np.int32)
    maillage = bpy.data.meshes.new(NOM_MER)
    maillage.vertices.add(len(co))
    maillage.loops.add(len(boucles))
    maillage.polygons.add(len(debuts))
    maillage.vertices.foreach_set("co", co.ravel())
    maillage.loops.foreach_set("vertex_index", boucles)
    maillage.polygons.foreach_set("loop_start", debuts)
    maillage.update(calc_edges=True)
    maillage.validate()
    return maillage


def _angle_ocean(cap_propagation_deg):
    """Angle `wave_direction` du modificateur Ocean pour des vagues allant vers ce cap.
    Mesuré sur Blender 5.2 : avec l'angle θ les vagues vont vers (−cos θ, sin θ)."""
    dx, dy = _cap_vers_xy(cap_propagation_deg)
    return math.atan2(dy, -dx)


def _ajouter_ocean(objet, p):
    m = objet.modifiers.new(p["nom"], "OCEAN")
    m.geometry_mode = "DISPLACE"
    m.spectrum = p["spectre"]
    m.spatial_size = int(p["taille"])
    m.resolution = int(p["resolution"])
    m.viewport_resolution = int(p["resolution"])     # même champ de vagues en vue et au rendu
    m.wind_velocity = p["vent"]
    m.wave_alignment = p["alignement"]
    m.damping = p["amortissement"]
    m.wave_direction = p["angle"]
    m.wave_scale = p["echelle"]
    m.wave_scale_min = p["echelle_min"]
    m.choppiness = p["choppiness"]
    m.random_seed = int(p["graine"])
    m.depth = 200.0
    m.use_normals = False
    m.use_foam = False       # l'écume du modificateur sature en grandes taches : faite dans le matériau
    m.time = 0.0
    return m


def _etalonner(p, hs_voulue, n=192):
    """Règle `echelle` pour que le modificateur donne la hauteur significative voulue (Hs = 4 σ),
    puis réduit `choppiness` tant que la surface se replie sur elle-même (crêtes en boucle)."""
    cote = float(int(p["taille"]))
    grille = _grille("_etalon", cote, n)
    m = _ajouter_ocean(grille, dict(p, echelle=1.0, choppiness=0.0))
    variances = []
    for t in (0.0, 7.3, 15.1):
        m.time = t
        variances.append(float(_positions_evaluees(grille)[:, 2].var()))
    p["echelle"] = hs_voulue / (4.0 * math.sqrt(max(np.mean(variances), 1e-12)))
    m.wave_scale = p["echelle"]
    for _ in range(12):
        m.choppiness = p["choppiness"]
        co = _positions_evaluees(grille).reshape(n, n, 3).astype(np.float64)
        pas = cote / n
        dxx, dxy = np.diff(co[:, :-1, 0], axis=0) / pas, np.diff(co[:-1, :, 0], axis=1) / pas
        dyx, dyy = np.diff(co[:, :-1, 1], axis=0) / pas, np.diff(co[:-1, :, 1], axis=1) / pas
        jacobien = dxx * dyy - dxy * dyx
        if float((jacobien < 0.25).mean()) < 0.002:
            break
        p["choppiness"] *= 0.8
    _supprimer(grille)
    return p["echelle"]


def _parametres_oceans(etat, direction_vent_deg, graine):
    """Trois champs superposés, de périodes spatiales sans rapport simple (répétition masquée)."""
    e = _etat_mer(etat)
    cap_vent = direction_vent_deg + 180.0             # le vent vient de `direction`, les vagues y vont
    lam_h = e["lambda_houle"]
    houle = dict(nom="Houle", spectre="PHILLIPS", taille=int(max(211, 4.3 * lam_h)) | 1, resolution=12,
                 vent=math.sqrt(lam_h * G / 8.9), alignement=6.0, amortissement=0.9,
                 angle=_angle_ocean(cap_vent - 25.0), echelle=1.0, echelle_min=lam_h / 5.0,
                 choppiness=0.6, graine=graine * 2 + 11)
    lam_c = e["lambda_clapot"]
    clapot = dict(nom="Clapot", spectre="PIERSON_MOSKOWITZ",
                  taille=int(min(131, max(47, 3.2 * lam_c))) | 1, resolution=20,
                  vent=e["vent"], alignement=1.5, amortissement=0.6,
                  angle=_angle_ocean(cap_vent), echelle=1.0, echelle_min=0.02,
                  choppiness=1.1, graine=graine * 2 + 12)
    lam_r = e["lambda_rides"]
    rides = dict(nom="Vaguelettes", spectre="PIERSON_MOSKOWITZ", taille=int(6.5 * lam_r) | 1,
                 resolution=16, vent=math.sqrt(lam_r * G / 8.2), alignement=1.0, amortissement=0.4,
                 angle=_angle_ocean(cap_vent + 12.0), echelle=1.0, echelle_min=0.02,
                 choppiness=0.9, graine=graine * 2 + 13)
    _etalonner(houle, e["hs_houle"])
    _etalonner(clapot, e["hs_clapot"])
    _etalonner(rides, e["hs_rides"])
    return [houle, clapot, rides]


def _materiau_eau(hs, seuil_ecume, cap_vent_deg, duree_s, n_images):
    mat = bpy.data.materials.get(NOM_MATERIAU_EAU) or bpy.data.materials.new(NOM_MATERIAU_EAU)
    n = _Noeuds(_arbre(mat))

    coords = n.nouveau("ShaderNodeTexCoord")
    geometrie = n.nouveau("ShaderNodeNewGeometry")
    camera = n.nouveau("ShaderNodeCameraData")
    distance = camera.outputs["View Distance"]

    # --- relief fin (non maillé) : trois bruits animés, étirés en travers du vent, qui avancent
    # avec lui. Hauteurs en mètres : ils donnent les pentes courtes que le maillage ne porte pas,
    # donc le contraste de Fresnel entre faces tournées vers la caméra et faces fuyantes.
    dx, dy = _cap_vers_xy(cap_vent_deg)
    aligne = n.nouveau("ShaderNodeVectorRotate", rotation_type="Z_AXIS")
    n.brancher(aligne.inputs["Vector"], coords.outputs["Object"])
    aligne.inputs["Angle"].default_value = -math.atan2(dy, dx)        # x' = sens du vent
    repere = n.nouveau("ShaderNodeMapping", name="Derive", vector_type="POINT")
    repere.inputs["Scale"].default_value = (1.0, 0.33, 1.0)
    n.brancher(repere.inputs["Vector"], aligne.outputs["Vector"])
    _deux_cles(mat.node_tree, 'nodes["Derive"].inputs[1].default_value', 0.0, -1.1 * duree_s,
               n_images, repere.inputs["Location"], indice=0)
    proche = n.lisse(distance, 5.0, 160.0, 1.0, 0.0)
    moyen = n.lisse(distance, 30.0, 500.0, 1.0, 0.0)
    relief = None
    for nom, echelle, hauteur_m, vitesse, fondu in (("Rides1", 1.0, 0.022 + 0.028 * hs, 0.45, moyen),
                                                    ("Rides2", 3.1, 0.020, 0.9, proche),
                                                    ("Rides3", 11.0, 0.005, 1.8, proche)):
        bruit = n.bruit(repere.outputs["Vector"], echelle, detail=3.0, rugosite=0.6, dimensions="4D")
        bruit.name = nom
        _deux_cles(mat.node_tree, f'nodes["{nom}"].inputs[1].default_value', 0.0, duree_s * vitesse,
                   n_images, bruit.inputs["W"])
        terme = n.math("MULTIPLY", n.math("MULTIPLY", bruit.outputs["Fac"], hauteur_m), fondu)
        relief = terme if relief is None else n.math("ADD", relief, terme)
    bosse = n.nouveau("ShaderNodeBump", name="Rides")
    bosse.inputs["Strength"].default_value = 1.0
    bosse.inputs["Distance"].default_value = 1.0
    n.brancher(bosse.inputs["Height"], relief)

    # --- au loin, les vagues ne sont plus résolues : les facettes qu'on voit sont celles qui
    # penchent vers l'observateur (pente efficace ~10°). On incline donc la normale vers la caméra,
    # sinon la mer lointaine serait un miroir du ciel d'horizon, aussi claire que lui.
    penche = n.nouveau("ShaderNodeVectorMath", operation="SCALE")
    n.brancher(penche.inputs[0], geometrie.outputs["Incoming"])
    n.brancher(penche.inputs["Scale"], n.lisse(distance, 15.0, 350.0, 0.02, 0.17))
    somme = n.nouveau("ShaderNodeVectorMath", operation="ADD")
    n.brancher(somme.inputs[0], geometrie.outputs["Normal"])
    n.brancher(somme.inputs[1], penche.outputs[0])
    normale = n.nouveau("ShaderNodeVectorMath", operation="NORMALIZE")
    n.brancher(normale.inputs[0], somme.outputs[0])
    n.brancher(bosse.inputs["Normal"], normale.outputs[0])

    # --- rugosité : les vagues non résolues au loin deviennent de la rugosité (pas de scintillement)
    rugosite_eau = n.lisse(distance, 8.0, 700.0, 0.07, 0.40)

    # --- couleur du corps d'eau : gris-vert sombre, un peu plus clair dans les crêtes minces
    altitude = n.nouveau("ShaderNodeSeparateXYZ")
    n.brancher(altitude.inputs[0], geometrie.outputs["Position"])
    crete = n.lisse(altitude.outputs["Z"], 0.15 * hs, 0.75 * hs, 0.0, 1.0)
    corps = n.melange_couleur(crete, _couleur(0.012, 0.030, 0.032), _couleur(0.020, 0.048, 0.046))

    # --- écume : moutons sur les crêtes les plus hautes, morcelés par un bruit, plus les sillages
    grain = n.bruit(coords.outputs["Object"], 1.6, detail=5.0, rugosite=0.7)
    grain_fin = n.bruit(coords.outputs["Object"], 9.0, detail=3.0, rugosite=0.6)
    morcele = n.math("ADD", n.math("MULTIPLY", grain.outputs["Fac"], 0.7),
                     n.math("MULTIPLY", grain_fin.outputs["Fac"], 0.3))
    paquets = n.bruit(coords.outputs["Object"], 0.22, detail=2.0, rugosite=0.5)
    ecume_vagues = n.math("MULTIPLY", n.lisse(altitude.outputs["Z"], seuil_ecume * hs, (seuil_ecume + 0.06) * hs),
                          n.math("MULTIPLY", n.lisse(morcele, 0.30, 0.62),
                                 n.lisse(paquets.outputs["Fac"], 0.50, 0.62)), borne=True)
    sillages = n.nouveau("ShaderNodeMath", name="Sillages", operation="MAXIMUM")
    sillages.inputs[1].default_value = 0.0
    n.brancher(sillages.inputs[0], ecume_vagues)
    ecume = sillages.outputs[0]

    surface = n.nouveau("ShaderNodeBsdfPrincipled", name="Surface")
    n.brancher(surface.inputs["Base Color"], n.melange_couleur(ecume, corps, _couleur(0.84, 0.87, 0.87)))
    n.brancher(surface.inputs["Roughness"], n.melange(ecume, rugosite_eau, 0.75))
    surface.inputs["IOR"].default_value = 1.333
    n.brancher(surface.inputs["Specular IOR Level"], n.melange(ecume, 0.5, 0.15))
    n.brancher(surface.inputs["Normal"], bosse.outputs["Normal"])
    sortie = n.nouveau("ShaderNodeOutputMaterial")
    n.brancher(sortie.inputs["Surface"], surface.outputs["BSDF"])
    return mat


def creer_mer(etat=3, direction_vent_deg=250.0, duree_s=30.0, images_par_s=15, graine=0,
              rayon=30000.0, demi_angle_deg=52.0, pas_angulaire_deg=0.14):
    """Mer animée jusqu'à l'horizon : houle + clapot (modificateurs Ocean en mode déplacement).

    etat : échelle de Douglas, 2 (belle) à 4 (agitée). direction_vent_deg : d'où vient le vent
    (rose des vents, +Y = nord). Le secteur ±demi_angle_deg autour de +Y est maillé finement.
    Renvoie l'objet « Mer ».
    """
    ancien = bpy.data.objects.get(NOM_MER)
    if ancien is not None:
        _supprimer(ancien)
    n_images = max(2, int(round(duree_s * images_par_s)))
    parametres = _parametres_oceans(etat, direction_vent_deg, graine)
    mer = _lier(bpy.data.objects.new(NOM_MER, _maillage_mer(rayon, demi_angle_deg, pas_angulaire_deg)))
    mer.data.shade_smooth()
    for p in parametres:
        m = _ajouter_ocean(mer, p)
        _deux_cles(mer, f'modifiers["{m.name}"].time', 0.0, (n_images - 1) / images_par_s, n_images, m)
    e = _etat_mer(etat)
    mer.data.materials.append(_materiau_eau(e["hs"], e["ecume"], direction_vent_deg + 180.0, duree_s, n_images))
    mer["cerema_mer"] = json.dumps(dict(etat=etat, direction_vent_deg=direction_vent_deg,
                                        graine=graine, oceans=parametres))
    mer.cycles.use_deform_motion = False      # pas de flou de déformation : trop coûteux, invisible
    mer.visible_shadow = False
    return mer


# --------------------------------------------------------------------------- ciel

def _position_soleil(heure):
    """Hauteur et azimut (degrés) du soleil en Bretagne début octobre, `heure` légale d'été."""
    latitude, declinaison = math.radians(48.4), math.radians(-5.5)
    angle_horaire = math.radians((heure - 13.9) * 15.0)       # midi solaire vers 13 h 55 à Brest
    sin_h = (math.sin(latitude) * math.sin(declinaison)
             + math.cos(latitude) * math.cos(declinaison) * math.cos(angle_horaire))
    hauteur = math.asin(sin_h)
    azimut = math.atan2(math.sin(angle_horaire),
                        math.cos(angle_horaire) * math.sin(latitude)
                        - math.tan(declinaison) * math.cos(latitude)) + math.pi
    return math.degrees(hauteur), math.degrees(azimut) % 360.0


def _analyser_hdri(image):
    """Direction du soleil (pixel le plus lumineux) et couleur moyenne de l'horizon d'un HDRI."""
    largeur, hauteur = image.size
    pixels = np.empty(largeur * hauteur * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(hauteur, largeur, 4)[:, :, :3]
    pas = max(1, largeur // 1024)
    reduit = pixels[: hauteur // pas * pas, : largeur // pas * pas].reshape(
        hauteur // pas, pas, largeur // pas, pas, 3).mean(axis=(1, 3))
    lum = reduit @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    h2, l2 = lum.shape
    ligne, colonne = np.unravel_index(int(np.argmax(lum)), lum.shape)
    u, v = (colonne + 0.5) / l2, (ligne + 0.5) / h2
    phi = (u - 0.5) * 2 * math.pi                     # équirectangulaire Blender : u = 0,5 ↔ −X
    elevation = (v - 0.5) * math.pi
    angle_xy = math.atan2(math.sin(phi), -math.cos(phi))      # angle trigonométrique depuis +X
    i0, i1 = int(h2 * (0.5 + 1.0 / 180)), int(h2 * (0.5 + 5.0 / 180))
    horizon = reduit[i0:max(i1, i0 + 1)].reshape(-1, 3)
    horizon = np.median(horizon, axis=0)
    del pixels
    try:
        image.buffers_free()
    except Exception:
        pass
    return angle_xy, math.degrees(elevation), [float(c) for c in horizon]


def _fichier_hdri(couverture):
    for seuil, nom, intensite in CIELS_HDRI:
        if couverture < seuil:
            chemin = os.path.join(DOSSIER_RESSOURCES, nom)
            return (chemin, intensite) if os.path.isfile(chemin) else (None, 1.0)
    return None, 1.0


def _monde_hdri(monde, chemin, intensite, azimut_soleil_deg):
    """Ciel photographique, tourné pour placer son soleil à l'azimut demandé."""
    image = bpy.data.images.load(chemin, check_existing=True)
    angle_soleil, hauteur_soleil, horizon = _analyser_hdri(image)
    dx, dy = _cap_vers_xy(azimut_soleil_deg)
    rotation = math.atan2(dy, dx) - angle_soleil
    n = _Noeuds(_arbre(monde))
    coords = n.nouveau("ShaderNodeTexCoord")
    tourne = n.nouveau("ShaderNodeVectorRotate", rotation_type="Z_AXIS")
    n.brancher(tourne.inputs["Vector"], coords.outputs["Generated"])
    tourne.inputs["Angle"].default_value = -rotation
    env = n.nouveau("ShaderNodeTexEnvironment", name="HDRI")
    env.image = image
    n.brancher(env.inputs["Vector"], tourne.outputs["Vector"])
    fond = n.nouveau("ShaderNodeBackground", name="Fond")
    n.brancher(fond.inputs["Color"], env.outputs["Color"])
    fond.inputs["Strength"].default_value = intensite
    sortie = n.nouveau("ShaderNodeOutputWorld")
    n.brancher(sortie.inputs["Surface"], fond.outputs["Background"])
    return [c * intensite for c in horizon], hauteur_soleil


def _monde_procedural(monde, hauteur_soleil_deg, azimut_soleil_deg, couverture, graine):
    """Repli sans fichier : ciel physique de Blender + nuages en bruit projetés sur un plafond."""
    n = _Noeuds(_arbre(monde))
    coords = n.nouveau("ShaderNodeTexCoord")
    direction = n.nouveau("ShaderNodeVectorMath", operation="NORMALIZE")
    n.brancher(direction.inputs[0], coords.outputs["Generated"])
    xyz = n.nouveau("ShaderNodeSeparateXYZ")
    n.brancher(xyz.inputs[0], direction.outputs[0])
    z_haut = n.math("MAXIMUM", xyz.outputs["Z"], 0.0)
    vers_ciel = n.nouveau("ShaderNodeCombineXYZ")
    n.brancher(vers_ciel.inputs[0], xyz.outputs["X"])
    n.brancher(vers_ciel.inputs[1], xyz.outputs["Y"])
    n.brancher(vers_ciel.inputs[2], z_haut)

    ciel = n.nouveau("ShaderNodeTexSky", name="CielPhysique")
    for genre in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        try:
            ciel.sky_type = genre
            break
        except TypeError:
            continue
    hauteur = math.radians(max(hauteur_soleil_deg, 1.0))
    dx, dy = _cap_vers_xy(azimut_soleil_deg)
    for cle, valeur in (("sun_elevation", hauteur), ("sun_rotation", math.atan2(dx, dy)),
                        ("sun_disc", True), ("sun_intensity", 1.0),
                        ("aerosol_density", 1.5 + 3.0 * couverture), ("ozone_density", 1.0),
                        ("air_density", 1.0), ("altitude", 0.0)):
        try:
            setattr(ciel, cle, valeur)
        except (AttributeError, TypeError):
            pass
    if "Vector" in ciel.inputs:              # absent de certaines versions : le ciel suit alors la vue
        n.brancher(ciel.inputs["Vector"], vers_ciel.outputs[0])

    # nuages : bruit fractal sur un plafond plan vu en perspective
    profondeur = n.math("ADD", z_haut, 0.07)
    plafond = n.nouveau("ShaderNodeCombineXYZ")
    n.brancher(plafond.inputs[0], n.math("DIVIDE", xyz.outputs["X"], profondeur))
    n.brancher(plafond.inputs[1], n.math("DIVIDE", xyz.outputs["Y"], profondeur))
    plafond.inputs[2].default_value = 3.7 * (graine + 1)
    nuage = n.bruit(plafond.outputs[0], 0.9, detail=8.0, rugosite=0.58)
    epais = n.bruit(plafond.outputs[0], 0.35, detail=3.0, rugosite=0.5)
    centre = 0.66 - 0.34 * couverture
    densite = n.lisse(n.math("ADD", n.math("MULTIPLY", nuage.outputs["Fac"], 0.75),
                             n.math("MULTIPLY", epais.outputs["Fac"], 0.25)),
                      centre - 0.07, centre + 0.12)
    voile = max(0.0, (couverture - 0.55) / 0.45)
    opacite = n.math("MAXIMUM", n.math("MULTIPLY", densite, 0.93), 0.25 * couverture + 0.7 * voile,
                     borne=True)
    eclat = 0.25 + 0.75 * math.sin(hauteur) ** 0.6
    clair = [eclat * c * (1.0 - 0.45 * voile) for c in (2.6, 2.6, 2.7)]
    sombre = [eclat * c for c in (1.25, 1.30, 1.42)]
    teinte = n.melange_couleur(n.lisse(epais.outputs["Fac"], 0.35, 0.70), _couleur(*clair),
                               _couleur(*sombre))
    melange = n.melange_couleur(opacite, ciel.outputs["Color"], teinte)
    fond = n.nouveau("ShaderNodeBackground", name="Fond")
    n.brancher(fond.inputs["Color"], melange)
    fond.inputs["Strength"].default_value = 0.13
    sortie = n.nouveau("ShaderNodeOutputWorld")
    n.brancher(sortie.inputs["Surface"], fond.outputs["Background"])
    gris = 0.13 * eclat * (4.5 * (1.0 - couverture) + 2.2 * couverture)     # radiance estimée de l'horizon
    return [gris * 0.97, gris * 0.99, gris * 1.04], hauteur_soleil_deg


def _creer_brume(couleur, visibilite_m, epaisseur, demi_cote=40000.0):
    """Couche de brume basse : volume homogène absorbant + émissif (sans diffusion, donc sans bruit).
    La radiance d'un objet à la distance d devient L·exp(−σd) + couleur·(1 − exp(−σd))."""
    ancien = bpy.data.objects.get(NOM_BRUME)
    if ancien is not None:
        _supprimer(ancien)
    sigma = 3.912 / visibilite_m                   # définition de la visibilité météorologique
    s, z0, z1 = demi_cote, -20.0, epaisseur
    sommets = [(-s, -s, z0), (s, -s, z0), (s, s, z0), (-s, s, z0),
               (-s, -s, z1), (s, -s, z1), (s, s, z1), (-s, s, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    maillage = bpy.data.meshes.new(NOM_BRUME)
    maillage.from_pydata(sommets, [], faces)
    brume = _lier(bpy.data.objects.new(NOM_BRUME, maillage))
    mat = bpy.data.materials.get(NOM_BRUME) or bpy.data.materials.new(NOM_BRUME)
    n = _Noeuds(_arbre(mat))
    absorption = n.nouveau("ShaderNodeVolumeAbsorption")
    absorption.inputs["Color"].default_value = _couleur(0, 0, 0)
    absorption.inputs["Density"].default_value = sigma
    emission = n.nouveau("ShaderNodeEmission")
    emission.inputs["Color"].default_value = _couleur(*couleur)
    emission.inputs["Strength"].default_value = sigma
    somme = n.nouveau("ShaderNodeAddShader")
    n.brancher(somme.inputs[0], absorption.outputs[0])
    n.brancher(somme.inputs[1], emission.outputs[0])
    sortie = n.nouveau("ShaderNodeOutputMaterial")
    n.brancher(sortie.inputs["Volume"], somme.outputs[0])
    maillage.materials.append(mat)
    brume.visible_shadow = False
    brume.display_type = "WIRE"
    brume.hide_select = True
    return brume


def creer_cote(azimut_debut_deg=-75.0, azimut_fin_deg=-12.0, distance=3600.0, hauteur_max=38.0,
               graine=0):
    """Côte basse lointaine sur une partie de l'horizon (caps comptés depuis +Y, positifs vers +X)."""
    ancien = bpy.data.objects.get(NOM_COTE)
    if ancien is not None:
        _supprimer(ancien)
    alea = random.Random(1000 + graine)
    n = 260
    phases = [(alea.uniform(1.0, 3.0) * 2 ** k, alea.uniform(0, 6.28), 0.55 ** k) for k in range(6)]
    sommets, faces = [], []
    for i in range(n + 1):
        t = i / n
        a = math.radians(azimut_debut_deg + t * (azimut_fin_deg - azimut_debut_deg))
        relief = sum(amp * math.sin(f * t * 6.28 + ph) for f, ph, amp in phases)
        fondu = math.sin(math.pi * t) ** 0.5            # la côte meurt aux deux extrémités
        h = max(0.0, hauteur_max * fondu * (0.45 + 0.28 * relief))
        d = distance * (1.0 + 0.10 * math.sin(2.3 * t + 1.0))
        sommets += [(d * math.sin(a), d * math.cos(a), -3.0), (d * math.sin(a), d * math.cos(a), h)]
        if i:
            b = 2 * i
            faces.append((b - 2, b, b + 1, b - 1))
    maillage = bpy.data.meshes.new(NOM_COTE)
    maillage.from_pydata(sommets, [], faces)
    cote = _lier(bpy.data.objects.new(NOM_COTE, maillage))
    mat = bpy.data.materials.get(NOM_COTE) or bpy.data.materials.new(NOM_COTE)
    nd = _Noeuds(_arbre(mat))
    surface = nd.nouveau("ShaderNodeBsdfDiffuse")
    surface.inputs["Color"].default_value = _couleur(0.045, 0.055, 0.04)
    sortie = nd.nouveau("ShaderNodeOutputMaterial")
    nd.brancher(sortie.inputs["Surface"], surface.outputs[0])
    maillage.materials.append(mat)
    cote.visible_shadow = False
    return cote


def creer_ciel(heure=17.0, couverture=0.4, graine=0, azimut_soleil_deg=None, visibilite_m=None,
               epaisseur_brume=70.0, cote=True, ciel="auto", exposition=0.0):
    """Ciel, soleil, brume d'horizon et côte lointaine.

    couverture : 0 = ciel clair, 1 = couvert. azimut_soleil_deg : cap du soleil (+Y = 0°, +X = 90°) ;
    None = position astronomique à `heure` (heure légale, Bretagne, début octobre).
    ciel : "auto" (HDRI Poly Haven s'il est présent dans data/blender/ressources, sinon procédural),
    "hdri" ou "procedural". Avec un HDRI, la hauteur du soleil est celle de la photo ; `heure`
    ne règle alors que son azimut. visibilite_m : None = 11 km (clair) à 5 km (couvert).
    """
    couverture = min(1.0, max(0.0, couverture))
    hauteur_soleil, azimut = _position_soleil(heure)
    if azimut_soleil_deg is not None:
        azimut = azimut_soleil_deg
    scene = _scene()
    monde = bpy.data.worlds.get(NOM_MONDE) or bpy.data.worlds.new(NOM_MONDE)
    scene.world = monde

    chemin, intensite = _fichier_hdri(couverture) if ciel in ("auto", "hdri") else (None, 1.0)
    if chemin is None and ciel == "hdri":
        print("[mer] HDRI absent de", DOSSIER_RESSOURCES, ": ciel procédural")
    if chemin is not None:
        try:
            horizon, hauteur_soleil = _monde_hdri(monde, chemin, intensite, azimut)
        except Exception as erreur:                      # fichier illisible : repli
            print("[mer] HDRI inutilisable (", erreur, ") : ciel procédural")
            chemin = None
    if chemin is None:
        horizon, hauteur_soleil = _monde_procedural(monde, hauteur_soleil, azimut, couverture, graine)

    if visibilite_m is None:
        visibilite_m = 11000.0 - 6000.0 * couverture
    _creer_brume(horizon, visibilite_m, epaisseur_brume)
    if cote:
        creer_cote(graine=graine)
    elif bpy.data.objects.get(NOM_COTE) is not None:
        _supprimer(bpy.data.objects[NOM_COTE])

    scene["cerema_ciel"] = json.dumps(dict(heure=heure, couverture=couverture, azimut_soleil_deg=azimut,
                                           hauteur_soleil_deg=hauteur_soleil, visibilite_m=visibilite_m,
                                           hdri=os.path.basename(chemin) if chemin else None))
    scene.view_settings.exposure = exposition
    return None


# --------------------------------------------------------------------------- mouvements

def _somme_sinus(alea, t, periodes, amplitude_eff):
    """Somme de sinus de phases aléatoires, d'écart-type `amplitude_eff` : mouvement continu."""
    signal = np.zeros_like(t)
    for periode in periodes:
        signal += math.sqrt(2.0 / len(periodes)) * np.sin(2 * math.pi * t / periode
                                                         + alea.uniform(0, 2 * math.pi))
    return amplitude_eff * signal


def _resonateur(consigne, dt, periode, amortissement, gain=1.0, sous_pas=4):
    """Réponse d'un flotteur (second ordre amorti) à une consigne échantillonnée."""
    w = 2 * math.pi / periode
    x, v = float(consigne[0]) * gain, 0.0
    sortie = np.empty(len(consigne))
    h = dt / sous_pas
    for i in range(len(consigne)):
        suivant = consigne[min(i + 1, len(consigne) - 1)]
        for k in range(sous_pas):
            cible = gain * (consigne[i] + (suivant - consigne[i]) * k / sous_pas)
            v += h * (w * w * (cible - x) - 2 * amortissement * w * v)
            x += h * v
        sortie[i] = x
    return sortie


def _sonder_mer(mer, n_images, images_par_s, demi_base=0.9):
    """Hauteur et pentes de la surface à l'origine, image par image (plan ajusté sur ±demi_base)."""
    parametres = json.loads(mer["cerema_mer"])["oceans"]
    sonde = _grille("_sonde", 2 * demi_base, 7, centree=True)
    sonde.matrix_world = mer.matrix_world.copy()
    modifs = [_ajouter_ocean(sonde, p) for p in parametres]
    masques = [(m, m.show_viewport) for m in mer.modifiers]
    for m, _ in masques:
        m.show_viewport = False                   # inutile de recalculer la grande mer à chaque pas
    plans = np.empty((n_images, 3))
    try:
        for i in range(n_images):
            for m in modifs:
                m.time = i / images_par_s
            co = _positions_evaluees(sonde).astype(np.float64)
            A = np.column_stack([np.ones(len(co)), co[:, 0], co[:, 1]])
            plans[i] = np.linalg.lstsq(A, co[:, 2], rcond=None)[0]
    finally:
        for m, visible in masques:
            m.show_viewport = visible
        _supprimer(sonde)
    return plans[:, 0], plans[:, 1], plans[:, 2]


def creer_camera(hauteur=1.2, champ_horizontal_deg=66.0, duree_s=30.0, images_par_s=15, etat=3,
                 graine=0, assiette_deg=-2.0, longueur_drone=1.8):
    """Caméra d'un petit drone de surface à l'origine, regardant vers +Y.

    Si la mer existe déjà (creer_mer), le drone suit la vraie surface sous lui : pilonnement,
    roulis et tangage viennent de la hauteur et des pentes locales, filtrées par la réponse d'un
    flotteur de `longueur_drone`. Sinon, mouvement synthétique piloté par `etat`. Le lacet est
    toujours synthétique. `hauteur` : objectif au-dessus de la flottaison du drone.
    Renvoie la caméra (enfant de l'objet vide « Drone », qui porte l'animation).
    """
    for nom in (NOM_CAMERA, NOM_DRONE):
        ancien = bpy.data.objects.get(nom)
        if ancien is not None:
            bpy.data.objects.remove(ancien, do_unlink=True)
    scene = _scene()
    n_images = max(2, int(round(duree_s * images_par_s))) + 1
    dt = 1.0 / images_par_s
    t = np.arange(n_images) * dt
    alea = random.Random(7919 * (graine + 1))
    e = _etat_mer(etat)

    mer = bpy.data.objects.get(NOM_MER)
    if mer is not None and "cerema_mer" in mer.keys():
        z, pente_x, pente_y = _sonder_mer(mer, n_images, images_par_s, demi_base=longueur_drone / 2)
        pilonnement = _resonateur(z, dt, 1.1, 0.55)
        roulis = _resonateur(-np.arctan(pente_x), dt, 2.1, 0.20, gain=1.2)
        tangage = _resonateur(np.arctan(pente_y), dt, 2.6, 0.25, gain=1.5)
        garde = z + 0.45 - hauteur               # l'objectif reste au-dessus de l'eau
        pilonnement = np.maximum(pilonnement, garde)
    else:
        hs = e["hs"]
        pilonnement = _somme_sinus(alea, t, [e["periode_houle"], e["periode_clapot"] * 1.1,
                                             e["periode_clapot"] * 0.8, 2.3], 0.22 * hs)
        roulis = _somme_sinus(alea, t, [2.1, 2.45, 3.3, 4.6], math.radians(2.5 + 4.5 * hs))
        tangage = _somme_sinus(alea, t, [2.6, 3.1, 4.2, 4.9], math.radians(1.5 + 2.8 * hs))
    limite = math.radians(22.0)
    roulis = np.clip(roulis, -limite, limite)
    tangage = np.clip(tangage, -limite, limite)
    lacet = _somme_sinus(alea, t, [4.3, 6.7, 9.5, 17.0], math.radians(0.8 + 1.4 * e["hs"]))
    embardee = _somme_sinus(alea, t, [5.1, 8.3, 13.0], 0.10 + 0.12 * e["hs"])
    cavalement = _somme_sinus(alea, t, [4.7, 7.9, 12.0], 0.10 + 0.12 * e["hs"])

    drone = _lier(bpy.data.objects.new(NOM_DRONE, None))
    drone.empty_display_size = 0.5
    drone.rotation_mode = "ZXY"
    for indice, valeurs in enumerate((embardee, cavalement, pilonnement)):
        _poser_courbe(drone, "location", valeurs, indice)
    for indice, valeurs in enumerate((tangage, roulis, lacet)):
        _poser_courbe(drone, "rotation_euler", valeurs, indice)

    optique = bpy.data.cameras.new(NOM_CAMERA)
    optique.sensor_fit = "HORIZONTAL"
    optique.sensor_width = 6.287                   # capteur IMX500 (1/2,3"), 4:3
    optique.sensor_height = 4.712
    optique.lens = optique.sensor_width / 2 / math.tan(math.radians(champ_horizontal_deg) / 2)
    optique.clip_start = 0.05
    optique.clip_end = 80000.0
    camera = _lier(bpy.data.objects.new(NOM_CAMERA, optique))
    camera.parent = drone
    camera.location = (0.0, 0.0, hauteur)
    camera.rotation_euler = (math.radians(90.0 + assiette_deg), 0.0, 0.0)
    scene.camera = camera
    scene.frame_start = PREMIERE_IMAGE
    scene.frame_end = PREMIERE_IMAGE + n_images - 2
    return camera


def faire_flotter(objet, longueur=14.0, etat=3, duree_s=30.0, images_par_s=15, graine=0):
    """Pilonnement, roulis et tangage d'un navire de `longueur` mètres (étrave vers +X).

    Écrit uniquement les canaux « delta » (delta_location Z, delta_rotation_euler X et Y) : la
    position, le cap et toute animation de l'objet ou de son parent restent intacts. Hiérarchie
    conseillée : un parent qui porte la route (position, cap) ; faire_flotter sur le navire enfant.
    """
    n_images = max(2, int(round(duree_s * images_par_s))) + 1
    t = np.arange(n_images) / images_par_s
    alea = random.Random(104729 * (graine + 1) + sum(ord(c) for c in objet.name))
    e = _etat_mer(etat)
    hs = e["hs"]
    # un navire filtre les vagues plus courtes que lui
    suit_houle = 1.0 / (1.0 + (longueur / e["lambda_houle"]) ** 2)
    suit_clapot = 1.0 / (1.0 + (longueur / e["lambda_clapot"]) ** 2)
    periode_roulis = 2.4 + 0.13 * longueur
    periode_tangage = 1.9 + 0.11 * longueur
    th, tc = e["periode_houle"], e["periode_clapot"]
    pilonnement = (_somme_sinus(alea, t, [th * 0.9, th, th * 1.15], 0.25 * e["hs_houle"] * suit_houle)
                   + _somme_sinus(alea, t, [tc * 0.85, tc, tc * 1.2], 0.25 * e["hs_clapot"] * suit_clapot))
    roulis = _somme_sinus(alea, t, [periode_roulis * 0.9, periode_roulis, periode_roulis * 1.12, th],
                          math.radians(min(9.0, 3.6 * hs * (10.0 / longueur) ** 0.7)))
    tangage = _somme_sinus(alea, t, [periode_tangage * 0.88, periode_tangage, periode_tangage * 1.2, th],
                           math.radians(min(5.0, 1.7 * hs * (10.0 / longueur) ** 0.8)))
    _poser_courbe(objet, "delta_location", pilonnement, 2)
    _poser_courbe(objet, "delta_rotation_euler", roulis, 0)
    _poser_courbe(objet, "delta_rotation_euler", tangage, 1)
    return None


def creer_sillage(objet, longueur=14.0, largeur=4.0, vitesse_noeuds=8.0, mer=None):
    """Écume de sillage derrière `objet` (étrave vers +X), peinte dans le matériau de la mer.

    Aucun maillage : un masque calculé dans le repère de l'objet (remous derrière la poupe, frange
    le long de la coque, deux bras en V) s'ajoute à l'écume. Suit donc le navire et épouse les
    vagues. Le sillage est droit (pas de courbure en giration). À appeler après creer_mer.
    """
    mer = mer or bpy.data.objects.get(NOM_MER)
    if mer is None or not mer.data.materials:
        raise RuntimeError("creer_sillage : créer la mer d'abord (creer_mer)")
    mat = mer.data.materials[0]
    n = _Noeuds(mat.node_tree)
    collecteur = mat.node_tree.nodes["Sillages"]
    force = min(1.3, max(0.0, vitesse_noeuds / 8.0))
    portee = max(4.0, vitesse_noeuds * 0.514 * 9.0)      # ce que le navire parcourt en 9 s
    demi_l, demi_b = longueur / 2, largeur / 2

    coords = n.nouveau("ShaderNodeTexCoord")
    coords.object = objet
    metres = n.nouveau("ShaderNodeVectorMath", operation="MULTIPLY")     # annule une éventuelle échelle
    n.brancher(metres.inputs[0], coords.outputs["Object"])
    metres.inputs[1].default_value = tuple(objet.matrix_world.to_scale())
    xyz = n.nouveau("ShaderNodeSeparateXYZ")
    n.brancher(xyz.inputs[0], metres.outputs[0])
    x, y_abs = xyz.outputs["X"], n.math("ABSOLUTE", xyz.outputs["Y"])

    # remous turbulent derrière la poupe
    s = n.math("SUBTRACT", n.math("MULTIPLY", x, -1.0), demi_l * 0.8)
    s_pos = n.math("MAXIMUM", s, 0.0)
    demi_remous = n.math("ADD", n.math("MULTIPLY", s_pos, 0.09), demi_b * 0.85)
    lateral = n.math("SUBTRACT", 1.0, n.lisse(n.math("DIVIDE", y_abs, demi_remous), 0.55, 1.0))
    remous = n.math("MULTIPLY", n.math("MULTIPLY", lateral, n.lisse(s, -1.0, 1.0)),
                    n.math("EXPONENT", n.math("DIVIDE", s_pos, -portee)))
    # frange d'écume le long de la coque
    ex = n.math("POWER", n.math("DIVIDE", n.math("ABSOLUTE", x), demi_l + 0.9), 2.0)
    ey = n.math("POWER", n.math("DIVIDE", y_abs, demi_b + 0.8), 2.0)
    frange = n.math("MULTIPLY", n.math("SUBTRACT", 1.0, n.lisse(n.math("ADD", ex, ey), 0.7, 1.0)), 0.6)
    # bras de Kelvin partant de l'étrave
    sb = n.math("SUBTRACT", demi_l * 0.8, x)
    sb_pos = n.math("MAXIMUM", sb, 0.0)
    ecart = n.math("DIVIDE",
                   n.math("SUBTRACT", y_abs, n.math("ADD", n.math("MULTIPLY", sb_pos, 0.33), demi_b * 0.3)),
                   n.math("ADD", n.math("MULTIPLY", sb_pos, 0.045), 0.45))
    bras = n.math("MULTIPLY",
                  n.math("MULTIPLY", n.math("EXPONENT", n.math("MULTIPLY", n.math("POWER", ecart, 2.0), -1.0)),
                         n.math("EXPONENT", n.math("DIVIDE", sb_pos, -1.3 * portee))),
                  n.math("MULTIPLY", n.lisse(sb, 0.0, 1.5), 0.55))
    masque = n.math("MAXIMUM", n.math("MAXIMUM", remous, frange), bras)
    grain = n.bruit(metres.outputs[0], 1.3, detail=5.0, rugosite=0.7)
    masque = n.math("MULTIPLY", n.math("MULTIPLY", masque, n.lisse(grain.outputs["Fac"], 0.25, 0.60, 0.35, 1.25)),
                    force, borne=True)

    # insertion dans la chaîne des sillages (maximum avec les précédents)
    entree = collecteur.inputs[1]
    if entree.is_linked:
        precedent = entree.links[0].from_socket
        masque = n.math("MAXIMUM", precedent, masque)
    n.brancher(entree, masque)
    return None


# --------------------------------------------------------------------------- rendu

def _activer_gpu():
    """Cycles sur le GPU Metal seul (le processeur reste disponible pour le reste de la machine)."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.refresh_devices()
        gpu = False
        for appareil in prefs.devices:
            appareil.use = appareil.type == "METAL"
            gpu = gpu or appareil.use
        return gpu
    except Exception as erreur:
        print("[mer] GPU indisponible :", erreur)
        return False


def regler_rendu(largeur=2028, hauteur=1520, images_par_s=15, qualite="finale", moteur="CYCLES",
                 dossier_sortie=None, format_image="JPEG", flou_bouge=True, echantillons=None):
    """Réglages de rendu. qualite : "finale" ou "apercu". Sortie en suite d'images
    (`dossier_sortie`/image_####), jamais en film. moteur : "CYCLES" (retenu) ou "BLENDER_EEVEE".
    echantillons : nombre maximal d'échantillons Cycles par pixel (None = 40 en finale, 12 en
    aperçu) ; c'est le réglage à baisser si le temps par image dépasse le budget.
    """
    scene = _scene()
    r = scene.render
    finale = qualite == "finale"
    r.resolution_x, r.resolution_y, r.resolution_percentage = int(largeur), int(hauteur), 100
    r.fps, r.fps_base = int(images_par_s), 1.0
    r.film_transparent = False
    r.use_persistent_data = True
    r.threads_mode = "FIXED"
    r.threads = 4

    r.engine = moteur
    if moteur == "CYCLES":
        c = scene.cycles
        c.device = "GPU" if _activer_gpu() else "CPU"
        c.samples = int(echantillons) if echantillons else (40 if finale else 12)
        c.use_adaptive_sampling = True
        c.adaptive_threshold = 0.03 if finale else 0.08
        c.adaptive_min_samples = 12 if finale else 6
        c.use_denoising = True
        c.denoiser = "OPENIMAGEDENOISE"
        c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        c.denoising_prefilter = "FAST"
        try:
            c.denoising_use_gpu = True
        except Exception:
            pass
        c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 4, 1, 3
        c.transmission_bounces, c.volume_bounces, c.transparent_max_bounces = 2, 0, 4
        c.caustics_reflective = c.caustics_refractive = False
        c.sample_clamp_indirect = 6.0
        c.sample_clamp_direct = 0.0
        c.blur_glossy = 0.5
        c.use_light_tree = False
        c.pixel_filter_type = "BLACKMAN_HARRIS"
        c.filter_width = 1.5
        r.use_motion_blur = bool(flou_bouge)
        r.motion_blur_shutter = 0.12             # 1/125 s à 15 images/s : léger flou de bougé
    else:
        e = scene.eevee
        e.taa_render_samples = 32 if finale else 8
        e.use_raytracing = True
        e.use_shadows = True
        e.use_volume_custom_range = True
        e.volumetric_start, e.volumetric_end = 0.5, 6000.0
        e.volumetric_samples = 128
        r.use_motion_blur = False

    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.display_settings.display_device = "sRGB"

    im = r.image_settings
    try:
        im.media_type = "IMAGE"
    except (AttributeError, TypeError):
        pass
    im.file_format = "PNG" if format_image.upper() == "PNG" else "JPEG"
    im.color_mode = "RGB"
    if im.file_format == "JPEG":
        im.quality = 95
    else:
        im.color_depth = "8"
        im.compression = 30
    if dossier_sortie:
        os.makedirs(dossier_sortie, exist_ok=True)
        r.filepath = os.path.join(dossier_sortie, "image_")
    return None
