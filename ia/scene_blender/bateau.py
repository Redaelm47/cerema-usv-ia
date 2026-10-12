"""Navire de pêche côtier immatriculé, pour les vidéos de test de vision embarquée.

Le navire part d'un modèle libre (« Sjark », Ocean Autonomy Cluster / NTNU,
CC BY 4.0, voir RESSOURCES.md) que ce script met à l'échelle, repeint et
complète : peinture de coque procédurale (antifouling, salissure, rouille),
immatriculation française plaquée sur les deux bords de l'étrave, nom du navire,
radar, antennes, feux, vire-filet, caisses et bouées.

Utilisation depuis un autre script :

    import sys
    sys.path.append("/chemin/vers/ia/scene_blender")
    import bateau
    navire = bateau.creer_bateau(nom="MARIE-LOUISE", immatriculation="GV 642410")
    navire.location = (30.0, 5.0, 0.0)

Aperçu seul :

    blender -b -P bateau.py -- --apercu /chemin/sortie.png [--vue etrave] [--moteur EEVEE]

Conventions : origine au centre du navire à la flottaison (z = 0 = surface de
l'eau), étrave vers +X, bâbord vers +Y, Z vers le haut, unités en mètres.
"""

import math
import os
import random
import sys
import time

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# --------------------------------------------------------------------------
# Réglages
# --------------------------------------------------------------------------

_ICI = os.path.dirname(os.path.abspath(__file__))

# Modèle source (non versionné, voir RESSOURCES.md pour le télécharger).
CHEMIN_MODELE = os.environ.get("BATEAU_MODELE") or os.path.normpath(os.path.join(
    _ICI, "..", "..", "data", "blender", "ressources", "sjark_ntnu", "sjark.blend"))

POLICE_GRASSE = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

HAUTEUR_IMMATRICULATION = 0.45   # mètres, hauteur réelle des caractères
HAUTEUR_NOM = 0.20

# Dans le fichier source : nom de l'objet coque et des matériaux à repeindre.
_OBJET_COQUE = "skrog"
_OBJET_TIMONERIE = "styrehus"
_OBJET_ABRI = "lagerrom"            # abri arrière
_OBJETS_DEFENSES = ("fender", "fender.001", "fender.002")
_MAT_PEINTURE_BLANCHE = "hvitmalt metall"
_MAT_CARENE = "mørkt tre"
_MAT_ACCENT = "gulmalt metall"
_COLLECTION_SOURCE = "_bateau_source"

# Hauteur (dans le repère du fichier source) de la ligne de flottaison.
_Z_FLOTTAISON_SOURCE = 0.45

# Port d'attache correspondant aux lettres du quartier maritime.
_QUARTIERS = {
    "GV": "LE GUILVINEC", "CC": "CONCARNEAU", "LO": "LORIENT", "DZ": "DOUARNENEZ",
    "BR": "BREST", "AD": "AUDIERNE", "SM": "SAINT-MALO", "PL": "PAIMPOL",
    "SB": "SAINT-BRIEUC", "MX": "MORLAIX", "CM": "CAMARET", "AY": "AURAY",
    "VA": "VANNES", "SN": "SAINT-NAZAIRE", "NO": "NOIRMOUTIER", "LS": "LES SABLES",
    "LR": "LA ROCHELLE", "CH": "CHERBOURG", "CN": "CAEN", "BL": "BOULOGNE",
    "DP": "DIEPPE", "FC": "FECAMP", "BA": "BAYONNE", "ST": "SETE", "MA": "MARSEILLE",
}


# --------------------------------------------------------------------------
# Matériaux procéduraux
# --------------------------------------------------------------------------

def _arbre(nom):
    """Crée un matériau vide de nœuds et renvoie (matériau, arbre, fonctions utilitaires)."""
    mat = bpy.data.materials.new(nom)
    if mat.node_tree is None:           # versions de Blender antérieures à 5.0
        mat.use_nodes = True
    arbre = mat.node_tree
    arbre.nodes.clear()

    def noeud(type_noeud, **proprietes):
        n = arbre.nodes.new(type_noeud)
        for cle, valeur in proprietes.items():
            setattr(n, cle, valeur)
        return n

    def lier(sortie, entree):
        arbre.links.new(sortie, entree)

    return mat, arbre, noeud, lier


def _bruit(noeud, lier, vecteur, echelle, graine, detail=4.0, etirement=None):
    """Bruit 4D (W = graine) ; `etirement` déforme les coordonnées (coulures verticales)."""
    if etirement is not None:
        m = noeud("ShaderNodeMapping")
        m.inputs["Scale"].default_value = etirement
        lier(vecteur, m.inputs["Vector"])
        vecteur = m.outputs[0]
    b = noeud("ShaderNodeTexNoise", noise_dimensions='4D')
    b.inputs["Scale"].default_value = echelle
    b.inputs["Detail"].default_value = detail
    b.inputs["W"].default_value = graine
    lier(vecteur, b.inputs["Vector"])
    return b.outputs[0]


def _seuil(noeud, lier, valeur, bas, haut, mini=0.0, maxi=1.0):
    """Transition douce de `mini` à `maxi` quand `valeur` passe de `bas` à `haut`."""
    r = noeud("ShaderNodeMapRange", interpolation_type='SMOOTHSTEP')
    r.inputs[1].default_value = bas
    r.inputs[2].default_value = haut
    r.inputs[3].default_value = mini
    r.inputs[4].default_value = maxi
    lier(valeur, r.inputs[0])
    return r.outputs[0]


def _melange(noeud, lier, facteur, a, b, mode='MIX'):
    """Mélange de couleurs ; `facteur`, `a` et `b` sont des sorties de nœud ou des valeurs."""
    m = noeud("ShaderNodeMix", data_type='RGBA', blend_type=mode)
    for indice, valeur in ((0, facteur), (6, a), (7, b)):
        if hasattr(valeur, "is_output"):
            lier(valeur, m.inputs[indice])
        elif indice == 0:
            m.inputs[0].default_value = valeur
        else:
            m.inputs[indice].default_value = (*valeur[:3], 1.0)
    return m.outputs[2]


def _produit(noeud, lier, a, b):
    m = noeud("ShaderNodeMath", operation='MULTIPLY')
    for indice, valeur in ((0, a), (1, b)):
        if hasattr(valeur, "is_output"):
            lier(valeur, m.inputs[indice])
        else:
            m.inputs[indice].default_value = valeur
    return m.outputs[0]


def _materiau_coque(nom, couleur, racine, graine, alea):
    """Peinture marine de coque : antifouling rouge sous la flottaison, liseré clair,
    salissure près de l'eau, coulures de rouille et peinture inégalement passée.

    Les coordonnées sont prises dans le repère de l'objet racine : z = 0 est la
    flottaison quelle que soit la position du navire dans la scène.
    """
    mat, arbre, noeud, lier = _arbre(nom)
    w = graine * 7.31 + 1.7
    usure = alea.uniform(0.7, 1.3)

    coord = noeud("ShaderNodeTexCoord")
    coord.object = racine
    pos = coord.outputs["Object"]
    sep = noeud("ShaderNodeSeparateXYZ")
    lier(pos, sep.inputs[0])
    z = sep.outputs["Z"]

    # Peinture de base, passée par endroits.
    passe = _seuil(noeud, lier, _bruit(noeud, lier, pos, 0.9, w), 0.40, 0.72, 0.0, 0.30 * usure)
    terne = [min(1.0, c * 0.80 + 0.04) for c in couleur]
    teinte = _melange(noeud, lier, passe, couleur, terne)

    # Liseré clair puis antifouling rouge sous la flottaison.
    ondule = noeud("ShaderNodeMath", operation='ADD')
    lier(z, ondule.inputs[0])
    lier(_seuil(noeud, lier, _bruit(noeud, lier, pos, 2.5, w + 3.0), 0.3, 0.7, -0.012, 0.012),
         ondule.inputs[1])
    zo = ondule.outputs[0]
    teinte = _melange(noeud, lier, _seuil(noeud, lier, zo, 0.200, 0.185), teinte, (0.78, 0.78, 0.74))
    rouge = _melange(noeud, lier, _bruit(noeud, lier, pos, 3.0, w + 5.0),
                     (0.30, 0.035, 0.025), (0.20, 0.04, 0.03))
    teinte = _melange(noeud, lier, _seuil(noeud, lier, zo, 0.125, 0.110), teinte, rouge)

    # Salissure verdâtre qui remonte de la flottaison.
    pres_eau = _seuil(noeud, lier, z, 0.05, 0.85, 1.0, 0.0)
    taches = _seuil(noeud, lier, _bruit(noeud, lier, pos, 2.2, w + 9.0, 6.0,
                                        etirement=(1.0, 1.0, 0.35)), 0.35, 0.75)
    sale = _produit(noeud, lier, _produit(noeud, lier, pres_eau, taches), 0.55 * usure)
    teinte = _melange(noeud, lier, sale, teinte, (0.075, 0.085, 0.055))

    # Coulures de rouille : bruit très étiré verticalement, seuillé.
    coulure = _seuil(noeud, lier, _bruit(noeud, lier, pos, 1.0, w + 13.0, 3.0,
                                         etirement=(4.5, 4.5, 0.22)), 0.60, 0.78)
    zones = _seuil(noeud, lier, _bruit(noeud, lier, pos, 0.45, w + 17.0, 2.0), 0.36, 0.60)
    rouille = _produit(noeud, lier, _produit(noeud, lier, coulure, zones), 0.55 * usure)
    teinte = _melange(noeud, lier, rouille, teinte, (0.20, 0.09, 0.04))

    grain = _bruit(noeud, lier, pos, 30.0, w + 21.0, 5.0)
    bsdf = noeud("ShaderNodeBsdfPrincipled")
    lier(teinte, bsdf.inputs["Base Color"])
    lier(_seuil(noeud, lier, grain, 0.2, 0.8, 0.32, 0.55), bsdf.inputs["Roughness"])
    relief = noeud("ShaderNodeBump")
    relief.inputs["Strength"].default_value = 0.08
    relief.inputs["Distance"].default_value = 0.01
    lier(grain, relief.inputs["Height"])
    lier(relief.outputs[0], bsdf.inputs["Normal"])
    sortie = noeud("ShaderNodeOutputMaterial")
    lier(bsdf.outputs[0], sortie.inputs[0])
    return mat


def _materiau_simple(nom, couleur, rugosite=0.5, metal=0.0, emission=0.0):
    mat, arbre, noeud, lier = _arbre(nom)
    bsdf = noeud("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*couleur[:3], 1.0)
    bsdf.inputs["Roughness"].default_value = rugosite
    bsdf.inputs["Metallic"].default_value = metal
    if emission > 0.0:
        bsdf.inputs["Emission Color"].default_value = (*couleur[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    sortie = noeud("ShaderNodeOutputMaterial")
    lier(bsdf.outputs[0], sortie.inputs[0])
    mat.diffuse_color = (*couleur[:3], 1.0)
    return mat


def _materiau_use(nom, couleur, graine, rugosite=0.45, rouille=0.5):
    """Peinture un peu usée (pièces ajoutées : vire-filet, caisses, mâtereau...)."""
    mat, arbre, noeud, lier = _arbre(nom)
    w = graine * 3.17 + 0.5
    coord = noeud("ShaderNodeTexCoord")
    pos = coord.outputs["Object"]
    taches = _seuil(noeud, lier, _bruit(noeud, lier, pos, 6.0, w, 5.0), 0.55, 0.75, 0.0, rouille)
    teinte = _melange(noeud, lier, taches, couleur, (0.22, 0.09, 0.04))
    bsdf = noeud("ShaderNodeBsdfPrincipled")
    lier(teinte, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rugosite
    sortie = noeud("ShaderNodeOutputMaterial")
    lier(bsdf.outputs[0], sortie.inputs[0])
    mat.diffuse_color = (*couleur[:3], 1.0)
    return mat


def _teinter(materiau, nom, couleur):
    """Copie un matériau texturé du modèle et multiplie sa couleur de base par `couleur`."""
    mat = materiau.copy()
    mat.name = nom
    arbre = mat.node_tree
    for n in arbre.nodes:
        if n.bl_idname != "ShaderNodeBsdfPrincipled":
            continue
        entree = n.inputs["Base Color"]
        if entree.is_linked:
            source = entree.links[0].from_socket
            m = arbre.nodes.new("ShaderNodeMix")
            m.data_type = 'RGBA'
            m.blend_type = 'MULTIPLY'
            m.inputs[0].default_value = 1.0
            m.inputs[7].default_value = (*couleur[:3], 1.0)
            arbre.links.new(source, m.inputs[6])
            arbre.links.new(m.outputs[2], entree)
        else:
            entree.default_value = (*couleur[:3], 1.0)
    return mat


def _decaler_teinte(materiau, nom, decalage):
    """Copie un matériau texturé du modèle en décalant sa teinte (0 = inchangée)."""
    mat = materiau.copy()
    mat.name = nom
    arbre = mat.node_tree
    for n in arbre.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled" and n.inputs["Base Color"].is_linked:
            entree = n.inputs["Base Color"]
            source = entree.links[0].from_socket
            t = arbre.nodes.new("ShaderNodeHueSaturation")
            t.inputs["Hue"].default_value = 0.5 + decalage
            arbre.links.new(source, t.inputs["Color"])
            arbre.links.new(t.outputs[0], entree)
    return mat


def _luminance(couleur):
    return 0.2126 * couleur[0] + 0.7152 * couleur[1] + 0.0722 * couleur[2]


# --------------------------------------------------------------------------
# Texte
# --------------------------------------------------------------------------

def _police():
    """Police bâton grasse du système, sinon police par défaut de Blender (None)."""
    if os.path.isfile(POLICE_GRASSE):
        for f in bpy.data.fonts:
            if bpy.path.abspath(f.filepath) == POLICE_GRASSE:
                return f
        try:
            return bpy.data.fonts.load(POLICE_GRASSE)
        except RuntimeError:
            pass
    return None


def _texte_2d(chaine, hauteur, maille=0.05):
    """Triangule `chaine` et renvoie (points [(a, b)], faces, largeur).

    a croît dans le sens de lecture, b vers le haut ; le texte est centré et sa
    hauteur de capitale vaut `hauteur`. Les arêtes sont recoupées à `maille`
    près pour que le texte puisse épouser une surface courbe.
    """
    police = _police()

    def courbe_vers_maillage(texte):
        courbe = bpy.data.curves.new("_texte_tmp", 'FONT')
        courbe.body = texte
        courbe.size = 1.0
        courbe.resolution_u = 5
        courbe.space_character = 1.06
        if police is not None:
            courbe.font = police
        else:
            courbe.offset = 0.012        # épaissit la police par défaut, qui est maigre
        objet = bpy.data.objects.new("_texte_tmp", courbe)
        maillage = bpy.data.meshes.new_from_object(objet)
        bpy.data.objects.remove(objet)
        bpy.data.curves.remove(courbe)
        return maillage

    # La hauteur de référence est celle d'une capitale droite.
    ref = courbe_vers_maillage("H")
    h_ref = max(v.co.y for v in ref.vertices) - min(v.co.y for v in ref.vertices)
    bpy.data.meshes.remove(ref)
    echelle = hauteur / h_ref

    maillage = courbe_vers_maillage(chaine)
    bm = bmesh.new()
    bm.from_mesh(maillage)
    bpy.data.meshes.remove(maillage)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    limite = maille / echelle
    for _ in range(4):
        longues = [e for e in bm.edges if e.calc_length() > limite]
        if not longues:
            break
        bmesh.ops.subdivide_edges(bm, edges=longues, cuts=1)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])

    xs = [v.co.x for v in bm.verts]
    x0, x1 = min(xs), max(xs)
    points = [((v.co.x - 0.5 * (x0 + x1)) * echelle, (v.co.y - 0.5 * h_ref) * echelle)
              for v in bm.verts]
    bm.verts.index_update()
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return points, faces, (x1 - x0) * echelle


def _objet_maillage(nom, sommets, faces, materiau, racine, collection, ombre=True):
    maillage = bpy.data.meshes.new(nom)
    maillage.from_pydata(sommets, [], faces)
    maillage.materials.append(materiau)
    objet = bpy.data.objects.new(nom, maillage)
    collection.objects.link(objet)
    objet.parent = racine
    if not ombre:
        objet.visible_shadow = False
    return objet


def _plaquer_texte(nom, chaine, hauteur, arbre_bvh, centre, lecture, vers_surface,
                   materiau, racine, collection, decollement=0.012, largeur_max=None):
    """Projette un texte sur une surface et renvoie l'objet créé (ou None si hors surface).

    centre       : point de visée du centre du texte (repère du navire)
    lecture      : vecteur unitaire horizontal du sens de lecture
    vers_surface : vecteur unitaire, direction de projection (du lecteur vers la surface)
    Le texte est projeté parallèlement à `vers_surface` : il n'est donc pas
    déformé pour un observateur placé en face, même si la surface est galbée.
    """
    points, faces, largeur = _texte_2d(chaine, hauteur)
    reduction = 1.0
    if largeur_max is not None and largeur > largeur_max:
        reduction = largeur_max / largeur
    lecture = Vector(lecture).normalized()
    vers_surface = Vector(vers_surface).normalized()
    haut = Vector((0.0, 0.0, 1.0))
    depart = Vector(centre) - vers_surface * 30.0

    sommets = []
    manques = 0
    for a, b in points:
        origine = depart + lecture * (a * reduction) + haut * (b * reduction)
        impact, _normale, _indice, _dist = arbre_bvh.ray_cast(origine, vers_surface)
        if impact is None:
            manques += 1
            sommets.append(None)
        else:
            sommets.append(impact - vers_surface * decollement)
    if manques > 0.02 * len(points):
        print(f"[bateau] attention : le texte « {chaine} » déborde de la surface "
              f"({manques}/{len(points)} points), il n'est pas posé.")
        return None
    # Les rares points sans impact sont retirés avec leurs faces.
    faces = [f for f in faces if all(sommets[i] is not None for i in f)]
    sommets = [s if s is not None else Vector(centre) for s in sommets]
    # Faces orientées vers le lecteur.
    if faces:
        i, j, k = faces[0]
        n = (sommets[j] - sommets[i]).cross(sommets[k] - sommets[i])
        if n.dot(vers_surface) > 0.0:
            faces = [list(reversed(f)) for f in faces]
    return _objet_maillage(nom, sommets, faces, materiau, racine, collection, ombre=False)


# --------------------------------------------------------------------------
# Petites pièces ajoutées au modèle
# --------------------------------------------------------------------------

class _Atelier:
    """Accumule des volumes simples dans un seul maillage à plusieurs matériaux."""

    def __init__(self):
        self.bm = bmesh.new()
        self.materiaux = []

    def _indice(self, materiau):
        if materiau not in self.materiaux:
            self.materiaux.append(materiau)
        return self.materiaux.index(materiau)

    def _finir(self, sommets, materiau, lisse):
        indice = self._indice(materiau)
        for f in {f for v in sommets for f in v.link_faces}:
            f.material_index = indice
            f.smooth = lisse and len(f.verts) <= 4

    def boite(self, materiau, centre, taille, rotation_z=0.0):
        m = (Matrix.Translation(centre) @ Matrix.Rotation(rotation_z, 4, 'Z')
             @ Matrix.Diagonal((*taille, 1.0)))
        r = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        self._finir(r["verts"], materiau, False)

    def cylindre(self, materiau, p1, p2, rayon, rayon2=None, segments=12):
        p1, p2 = Vector(p1), Vector(p2)
        axe = p2 - p1
        rot = Vector((0.0, 0.0, 1.0)).rotation_difference(axe.normalized()).to_matrix().to_4x4()
        m = Matrix.Translation((p1 + p2) * 0.5) @ rot
        r = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segments, radius1=rayon,
                                  radius2=rayon if rayon2 is None else rayon2,
                                  depth=axe.length, matrix=m)
        self._finir(r["verts"], materiau, True)

    def sphere(self, materiau, centre, rayon, echelle=(1.0, 1.0, 1.0)):
        m = Matrix.Translation(centre) @ Matrix.Diagonal((*echelle, 1.0))
        r = bmesh.ops.create_uvsphere(self.bm, u_segments=16, v_segments=10, radius=rayon, matrix=m)
        self._finir(r["verts"], materiau, True)

    def objet(self, nom, racine, collection):
        maillage = bpy.data.meshes.new(nom)
        self.bm.to_mesh(maillage)
        self.bm.free()
        for mat in self.materiaux:
            maillage.materials.append(mat)
        objet = bpy.data.objects.new(nom, maillage)
        collection.objects.link(objet)
        objet.parent = racine
        return objet


def _equiper(racine, collection, prefixe, e, graine, alea, bvh_coque):
    """Ajoute l'armement de pêche et de navigation absent du modèle.

    Les cotes sont celles d'un navire de 14 m, multipliées par `e`.
    """
    a = _Atelier()
    blanc = _materiau_use(f"{prefixe}.blanc", (0.85, 0.85, 0.82), graine, rouille=0.25)
    acier = _materiau_use(f"{prefixe}.acier_peint", (0.16, 0.24, 0.30), graine + 1, rouille=0.6)
    noir = _materiau_simple(f"{prefixe}.caoutchouc", (0.02, 0.02, 0.02), 0.8)
    alu = _materiau_simple(f"{prefixe}.alu", (0.55, 0.57, 0.58), 0.35, metal=1.0)
    orange = _materiau_simple(f"{prefixe}.orange", (0.95, 0.20, 0.02), 0.45)
    rose = _materiau_simple(f"{prefixe}.rose", (0.90, 0.10, 0.25), 0.45)
    feu_rouge = _materiau_simple(f"{prefixe}.feu_rouge", (0.9, 0.02, 0.02), 0.3, emission=1.5)
    feu_vert = _materiau_simple(f"{prefixe}.feu_vert", (0.02, 0.8, 0.15), 0.3, emission=1.5)
    feu_blanc = _materiau_simple(f"{prefixe}.feu_blanc", (0.95, 0.95, 0.85), 0.3, emission=1.5)
    plastiques = [
        _materiau_simple(f"{prefixe}.caisse_{n}", c, 0.5)
        for n, c in (("blanche", (0.80, 0.80, 0.76)), ("verte", (0.03, 0.30, 0.12)),
                     ("rouge", (0.55, 0.04, 0.03)), ("bleue", (0.03, 0.12, 0.45)),
                     ("jaune", (0.85, 0.60, 0.03)))]
    sombre = _materiau_simple(f"{prefixe}.fond_caisse", (0.03, 0.035, 0.04), 0.7)

    def p(x, y, z):
        return Vector((x * e, y * e, z * e))

    def pont(x, y):
        """Hauteur du pont (en cotes 14 m) à la verticale du point."""
        impact = bvh_coque.ray_cast(Vector((x * e, y * e, 1.0 * e)), Vector((0.0, 0.0, -1.0)))[0]
        return impact.z / e if impact is not None else 0.3

    toit, toit_abri = 3.78, 3.03

    # Radar à antenne tournante, sur une console en avant du grand mât.
    z_radar = 4.95
    a.boite(blanc, p(2.33, 0.0, z_radar - 0.05), (0.60 * e, 0.34 * e, 0.06 * e))
    a.cylindre(blanc, p(2.10, 0.0, z_radar - 0.45), p(2.52, 0.0, z_radar - 0.08), 0.03 * e, segments=8)
    a.boite(blanc, p(2.42, 0.0, z_radar + 0.10), (0.30 * e, 0.30 * e, 0.24 * e))
    a.boite(blanc, p(2.42, 0.0, z_radar + 0.28), (0.11 * e, 1.25 * e, 0.09 * e),
            rotation_z=alea.uniform(0.0, math.pi))

    # Antennes fouet (VHF, BLU) et antenne GPS sur le toit de la timonerie.
    for y, haut in ((0.85, 2.6), (-0.78, 2.1)):
        a.cylindre(alu, p(0.45, y, toit), p(0.45, y, toit + 0.25), 0.022 * e, segments=8)
        a.cylindre(blanc, p(0.45, y, toit + 0.25), p(0.40, y, toit + haut), 0.013 * e, 0.007 * e, 6)
    a.cylindre(alu, p(3.55, 0.70, toit), p(3.55, 0.70, toit + 0.45), 0.015 * e, segments=8)
    a.sphere(blanc, p(3.55, 0.70, toit + 0.47), 0.08 * e, (1.0, 1.0, 0.55))

    # Feux de navigation : rouge à bâbord (+Y), vert à tribord, blancs de mât et de poupe.
    for y, feu in ((1.09, feu_rouge), (-1.01, feu_vert)):
        a.boite(noir, p(3.30, y, 3.50), (0.22 * e, 0.06 * e, 0.20 * e))
        a.boite(feu, p(3.32, y + math.copysign(0.03, y), 3.50), (0.10 * e, 0.06 * e, 0.11 * e))
    a.cylindre(feu_blanc, p(2.13, 0.0, 5.90), p(2.13, 0.0, 6.02), 0.055 * e, segments=10)
    a.cylindre(feu_rouge, p(2.0, 0.0, 7.72), p(2.0, 0.0, 7.84), 0.06 * e, segments=10)
    a.cylindre(feu_blanc, p(2.0, 0.22, 7.30), p(2.0, 0.22, 7.42), 0.06 * e, segments=10)
    a.cylindre(alu, p(2.0, 0.0, 7.33), p(2.0, 0.22, 7.33), 0.015 * e, segments=6)
    a.cylindre(feu_blanc, p(-4.20, 0.75, 2.80), p(-4.28, 0.75, 2.80), 0.05 * e, segments=10)

    # Radeau de survie en conteneur, sur le toit de l'abri arrière.
    a.cylindre(blanc, p(-2.55, 0.30, toit_abri + 0.30), p(-2.55, 1.20, toit_abri + 0.30),
               0.25 * e, segments=16)
    for y in (0.48, 1.02):
        a.cylindre(noir, p(-2.55, y - 0.02, toit_abri + 0.30), p(-2.55, y + 0.02, toit_abri + 0.30),
                   0.257 * e, segments=16)
        a.boite(alu, p(-2.55, y, toit_abri + 0.04), (0.50 * e, 0.06 * e, 0.08 * e))

    # Vire-filet à tribord : fût, tête et poulie caoutchoutée débordant du pavois.
    xv, yv = -0.95, -1.70
    zp = pont(xv, yv)
    a.cylindre(acier, p(xv, yv, zp), p(xv, yv, zp + 1.30), 0.11 * e, segments=12)
    a.boite(acier, p(xv, yv - 0.10, zp + 1.42), (0.34 * e, 0.62 * e, 0.30 * e))
    a.cylindre(noir, p(xv - 0.13, yv - 0.42, zp + 1.42), p(xv + 0.13, yv - 0.42, zp + 1.42),
               0.27 * e, segments=20)
    for dx in (-0.15, 0.15):
        a.cylindre(acier, p(xv + dx - 0.012, yv - 0.42, zp + 1.42),
                   p(xv + dx + 0.012, yv - 0.42, zp + 1.42), 0.31 * e, segments=20)
    a.boite(alu, p(xv + 0.75, yv + 0.10, zp + 0.45), (0.90 * e, 0.70 * e, 0.90 * e))   # bac à filet
    a.boite(sombre, p(xv + 0.75, yv + 0.10, zp + 0.905), (0.82 * e, 0.62 * e, 0.01 * e))

    # Panneau de cale sur le pont arrière.
    xc, yc = -3.05, -0.95
    zc = pont(xc, yc)
    a.boite(blanc, p(xc, yc, zc + 0.15), (1.10 * e, 1.00 * e, 0.30 * e))
    a.boite(alu, p(xc, yc, zc + 0.32), (1.18 * e, 1.08 * e, 0.05 * e))

    # Caisses à poisson empilées.
    for x0, y0, n_max in ((-4.45, -0.85, 4), (-4.45, -0.30, 3), (-1.45, -0.55, 3)):
        z0 = pont(x0, y0)
        angle = alea.uniform(-0.12, 0.12)
        for i in range(alea.randint(1, n_max)):
            mat = alea.choice(plastiques)
            zc = z0 + 0.13 + 0.26 * i
            decal = alea.uniform(-0.02, 0.02)
            a.boite(mat, p(x0 + decal, y0, zc), (0.78 * e, 0.48 * e, 0.25 * e), rotation_z=angle)
            a.boite(sombre, p(x0 + decal, y0, zc + 0.126), (0.70 * e, 0.40 * e, 0.01 * e),
                    rotation_z=angle)

    # Bouées de filet sur le toit et perches à pavillon amarrées contre l'abri.
    for i in range(alea.randint(2, 4)):
        mat = alea.choice((orange, orange, rose))
        r = alea.uniform(0.21, 0.27)
        a.sphere(mat, p(0.75 + 0.50 * (i // 2), -0.55 + 0.52 * (i % 2), toit + r * 0.95), r * e,
                 (1.0, 1.0, 1.1))
    for i in range(alea.randint(2, 4)):
        x, y = -2.05 - 0.16 * i, -0.16
        z0 = pont(x, y)
        haut = alea.uniform(3.3, 3.9)
        a.cylindre(alu, p(x, y, z0), p(x + 0.05, y - 0.10, z0 + haut), 0.016 * e, segments=6)
        a.cylindre(orange, p(x + 0.012, y - 0.024, z0 + 0.75), p(x + 0.019, y - 0.038, z0 + 1.15),
                   0.085 * e, segments=10)
        a.boite(alea.choice((noir, orange, rose)), p(x + 0.05 - 0.14, y - 0.10, z0 + haut - 0.14),
                (0.28 * e, 0.012 * e, 0.22 * e))

    return a.objet(f"{prefixe}.armement", racine, collection)


# --------------------------------------------------------------------------
# Modèle source
# --------------------------------------------------------------------------

def _collection_source():
    """Charge une seule fois les objets du modèle dans une collection hors scène."""
    col = bpy.data.collections.get(_COLLECTION_SOURCE)
    if col is not None and len(col.objects) > 0:
        return col
    if not os.path.isfile(CHEMIN_MODELE):
        raise FileNotFoundError(
            f"Modèle introuvable : {CHEMIN_MODELE}\n"
            "Téléchargez-le comme indiqué dans ia/scene_blender/RESSOURCES.md "
            "ou donnez son chemin dans la variable d'environnement BATEAU_MODELE.")
    with bpy.data.libraries.load(CHEMIN_MODELE, link=False) as (source, cible):
        cible.objects = list(source.objects)
    if col is None:
        col = bpy.data.collections.new(_COLLECTION_SOURCE)
    col.use_fake_user = True
    for objet in cible.objects:
        if objet is None:
            continue
        if objet.type == 'MESH':
            objet["nom_source"] = objet.name
            col.objects.link(objet)
        else:                           # lampes et repères du fichier d'origine
            bpy.data.objects.remove(objet)
    return col


def _figer(objet, depsgraph, nom):
    """Applique les modificateurs de l'objet et renvoie son nouveau maillage."""
    maillage = bpy.data.meshes.new_from_object(objet.evaluated_get(depsgraph))
    maillage.name = nom
    objet.modifiers.clear()
    objet.data = maillage
    return maillage


def _raccourcir(objet, z_base, facteur):
    """Comprime verticalement tout ce qui dépasse `z_base` (mâts, haubans, échappement)."""
    monde = objet.matrix_world.copy()
    inverse = monde.inverted()
    for v in objet.data.vertices:
        p = monde @ v.co
        if p.z > z_base:
            p.z = z_base + (p.z - z_base) * facteur
            v.co = inverse @ p


def _bvh(objet):
    monde = objet.matrix_world.copy()
    sommets = [monde @ v.co for v in objet.data.vertices]
    return BVHTree.FromPolygons(sommets, [tuple(p.vertices) for p in objet.data.polygons])


def _maillage_evalue(objet, depsgraph):
    """Sommets (repère monde) et faces de l'objet après modificateurs."""
    evalue = objet.evaluated_get(depsgraph)
    maillage = evalue.to_mesh()
    monde = objet.matrix_world
    sommets = [monde @ v.co for v in maillage.vertices]
    faces = [tuple(p.vertices) for p in maillage.polygons]
    evalue.to_mesh_clear()
    return sommets, faces


# --------------------------------------------------------------------------
# Fonction principale
# --------------------------------------------------------------------------

def creer_bateau(nom="MARIE-LOUISE", immatriculation="GV 642410", longueur=14.0,
                 couleur_coque=(0.05, 0.18, 0.45), couleur_superstructure=(0.9, 0.9, 0.87),
                 graine=0) -> bpy.types.Object:
    """Crée un navire de pêche et renvoie l'objet vide parent de toutes ses pièces.

    nom                    : nom du navire (timonerie et arrière)
    immatriculation        : « GV 642410 », peinte sur les deux bords de l'étrave
    longueur               : longueur hors tout de la coque, en mètres
    couleur_coque          : couleur RVB linéaire de la coque au-dessus de la flottaison
    couleur_superstructure : couleur RVB linéaire de la timonerie et de l'intérieur du pavois
    graine                 : fait varier usure, rouille et petit matériel de pont
    """
    alea = random.Random(graine)
    scene = bpy.context.scene
    prefixe = f"{nom}"

    collection = bpy.data.collections.new(f"Bateau {nom}")
    scene.collection.children.link(collection)

    racine = bpy.data.objects.new(f"{prefixe}", None)
    racine.empty_display_type = 'ARROWS'
    racine.empty_display_size = 1.0
    collection.objects.link(racine)

    # ---- copie des pièces du modèle ------------------------------------
    pieces = {}
    for source in _collection_source().objects:
        copie = source.copy()
        copie.data = source.data.copy()
        copie.name = f"{prefixe}.{source['nom_source']}"
        collection.objects.link(copie)
        copie.parent = racine
        copie.matrix_parent_inverse = Matrix.Identity(4)
        pieces[source["nom_source"]] = copie
    coque = pieces[_OBJET_COQUE]
    for mod in coque.modifiers:
        if mod.type == 'SUBSURF':
            mod.render_levels = mod.levels

    # ---- mise à l'échelle : étrave vers +X, origine au centre à la flottaison ----
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    sommets, _ = _maillage_evalue(coque, depsgraph)
    x_min, x_max = min(s.x for s in sommets), max(s.x for s in sommets)
    y_min, y_max = min(s.y for s in sommets), max(s.y for s in sommets)
    k = longueur / (x_max - x_min)
    normalisation = (Matrix.Scale(k, 4) @ Matrix.Translation(
        (-0.5 * (x_min + x_max), -0.5 * (y_min + y_max), -_Z_FLOTTAISON_SOURCE)))
    for piece in pieces.values():
        piece.matrix_basis = normalisation @ piece.matrix_basis

    # ---- coque figée (modificateurs appliqués) pour la repeindre face par face ----
    depsgraph.update()
    e = longueur / 14.0                 # les cotes ci-dessous sont données pour 14 m
    maillage_coque = _figer(coque, depsgraph, f"{prefixe}.coque")

    # Les mâts du modèle sont démesurés (11 m) : on les raccourcit de moitié.
    timonerie = pieces[_OBJET_TIMONERIE]
    _figer(timonerie, depsgraph, f"{prefixe}.timonerie")
    _raccourcir(timonerie, 3.80 * e, 0.5)
    if _OBJET_ABRI in pieces:
        _figer(pieces[_OBJET_ABRI], depsgraph, f"{prefixe}.abri")
        _raccourcir(pieces[_OBJET_ABRI], 3.06 * e, 0.5)
    monde = coque.matrix_world.copy()
    sommets = [monde @ v.co for v in maillage_coque.vertices]
    faces = [tuple(p.vertices) for p in maillage_coque.polygons]
    bvh_coque = BVHTree.FromPolygons(sommets, faces)

    mat_coque = _materiau_coque(f"{prefixe}.peinture_coque", couleur_coque, racine, graine, alea)
    blanc_source = bpy.data.materials.get(_MAT_PEINTURE_BLANCHE)
    for slot in coque.material_slots:
        if slot.material and slot.material.name.split(".")[0] == _MAT_PEINTURE_BLANCHE:
            blanc_source = slot.material
    mat_super = _teinter(blanc_source, f"{prefixe}.peinture_superstructure", couleur_superstructure)

    # Extérieur de coque : faces peintes ou de carène dont la normale s'écarte de
    # l'axe du navire. Le reste (pont, intérieur du pavois) garde la peinture claire.
    maillage_coque.materials.append(mat_coque)
    indice_coque = len(maillage_coque.materials) - 1
    a_repeindre = {i for i, m in enumerate(maillage_coque.materials)
                   if m and m.name.split(".")[0] in (_MAT_PEINTURE_BLANCHE, _MAT_CARENE)}
    rotation = monde.to_3x3()
    for poly in maillage_coque.polygons:
        if poly.material_index not in a_repeindre:
            continue
        centre = monde @ poly.center
        normale = (rotation @ poly.normal).normalized()
        if normale.z > 0.75 and centre.z > 0.1:
            continue                                    # pont, dessus de lisse
        axe = Vector((max(-0.3 * longueur, min(0.3 * longueur, centre.x)), 0.0, centre.z))
        if normale.z < -0.4 or normale.dot(centre - axe) > 0.0:
            poly.material_index = indice_coque

    # Peinture claire teintée partout où le modèle utilise sa peinture blanche.
    for piece in pieces.values():
        for slot in piece.material_slots:
            if slot.material and slot.material.name.split(".")[0] == _MAT_PEINTURE_BLANCHE:
                slot.material = mat_super

    # Couleur d'accent (mâts, toits) : jaune d'origine pour la graine 0, sinon variable.
    decalage = 0.0 if graine == 0 else alea.choice((0.0, -0.06, -0.11, 0.20, 0.42))
    if decalage != 0.0:
        accents = {}
        for piece in pieces.values():
            for slot in piece.material_slots:
                m = slot.material
                if m and m.name.split(".")[0] == _MAT_ACCENT:
                    if m.name not in accents:
                        accents[m.name] = _decaler_teinte(m, f"{prefixe}.accent", decalage)
                    slot.material = accents[m.name]

    # Défenses : toutes présentes pour la graine 0, sinon certaines sont rentrées.
    if graine != 0:
        for nom_defense in _OBJETS_DEFENSES:
            if nom_defense in pieces and alea.random() < 0.35:
                bpy.data.objects.remove(pieces.pop(nom_defense))

    # ---- immatriculation sur les deux bords de l'étrave ----------------
    clair = _luminance(couleur_coque) < 0.25
    couleur_texte = (0.92, 0.92, 0.90) if clair else (0.015, 0.015, 0.02)
    mat_texte = _materiau_simple(f"{prefixe}.marquage", couleur_texte, rugosite=0.55)
    hauteur = HAUTEUR_IMMATRICULATION
    x_centre = longueur * 0.265
    # Centrée entre le liseré de flottaison et le liston noir du modèle.
    demi = 0.36 * hauteur * len(immatriculation)
    z_liston = [(monde @ maillage_coque.vertices[i].co).z
                for poly in maillage_coque.polygons
                if poly.material_index not in a_repeindre and poly.material_index != indice_coque
                and abs(poly.normal.z) < 0.5 and abs((monde @ poly.center).x - x_centre) < demi
                for i in poly.vertices]
    z_haut = min(z_liston) if z_liston else 0.22 + hauteur + 0.5
    z_centre = max(0.22 + 0.5 * hauteur + 0.06, 0.5 * (0.22 + z_haut))
    for cote, suffixe in ((1.0, "babord"), (-1.0, "tribord")):
        # Vu de bâbord (+Y), on lit vers l'arrière (-X) ; vu de tribord, vers l'avant.
        _plaquer_texte(f"{prefixe}.immatriculation_{suffixe}", immatriculation, hauteur,
                       bvh_coque, (x_centre, 0.0, z_centre), (-cote, 0.0, 0.0),
                       (0.0, -cote, 0.0), mat_texte, racine, collection,
                       largeur_max=longueur * 0.30)

    # ---- nom du navire : flancs de timonerie et arrière ----------------
    sombre = _luminance(couleur_superstructure) > 0.25
    mat_nom = _materiau_simple(f"{prefixe}.marquage_nom",
                               (0.02, 0.03, 0.06) if sombre else (0.92, 0.92, 0.90), rugosite=0.55)
    bvh_timonerie = _bvh(timonerie)
    for cote, suffixe in ((1.0, "babord"), (-1.0, "tribord")):
        _plaquer_texte(f"{prefixe}.nom_{suffixe}", nom, HAUTEUR_NOM * e, bvh_timonerie,
                       (2.15 * e, 0.0, 2.20 * e), (-cote, 0.0, 0.0), (0.0, -cote, 0.0),
                       mat_nom, racine, collection, decollement=0.008, largeur_max=2.4 * e)
    port = _QUARTIERS.get(immatriculation.strip()[:2].upper())
    _plaquer_texte(f"{prefixe}.nom_arriere", nom, 0.17 * e, bvh_coque,
                   (0.0, 0.0, 0.98 * e), (0.0, -1.0, 0.0), (1.0, 0.0, 0.0),
                   mat_texte, racine, collection, largeur_max=1.9 * e)
    if port:
        _plaquer_texte(f"{prefixe}.port_arriere", port, 0.11 * e, bvh_coque,
                       (0.0, 0.0, 0.70 * e), (0.0, -1.0, 0.0), (1.0, 0.0, 0.0),
                       mat_texte, racine, collection, largeur_max=1.5 * e)

    _equiper(racine, collection, prefixe, e, graine, alea, bvh_coque)

    racine["longueur"] = longueur
    racine["immatriculation"] = immatriculation
    racine["nom"] = nom
    return racine


# --------------------------------------------------------------------------
# Aperçu (exécution directe)
# --------------------------------------------------------------------------

VUES = {
    # nom : (position caméra, point visé, champ horizontal en degrés)
    "trois_quarts": ((19.0, -17.0, 5.0), (0.3, 0.0, 1.8), 36.0),
    "babord": ((17.0, 19.0, 4.0), (0.3, 0.0, 1.8), 36.0),
    "profil": ((0.0, -30.0, 2.2), (0.0, 0.0, 3.0), 36.0),
    "arriere": ((-23.0, -6.0, 3.5), (0.0, 0.0, 1.8), 34.0),
    "dessus": ((0.0, -0.01, 34.0), (0.0, 0.0, 0.0), 30.0),
    "etrave": ((9.0, -11.0, 1.6), (3.6, -1.5, 1.0), 26.0),
    "etrave_babord": ((9.0, 11.0, 1.6), (3.6, 1.5, 1.0), 26.0),
    "lointain": ((60.0, -80.0, 1.2), (0.0, 0.0, 2.5), 66.0),
}


def _vider_scene():
    for objet in list(bpy.data.objects):
        if objet.users_scene:
            bpy.data.objects.remove(objet)


def _decor_apercu():
    """Plan d'eau et ciel sommaires, uniquement pour juger le navire."""
    scene = bpy.context.scene
    monde = bpy.data.worlds.new("ciel_apercu")
    if monde.node_tree is None:
        monde.use_nodes = True
    arbre = monde.node_tree
    arbre.nodes.clear()
    fond = arbre.nodes.new("ShaderNodeBackground")
    sortie = arbre.nodes.new("ShaderNodeOutputWorld")
    arbre.links.new(fond.outputs[0], sortie.inputs[0])
    try:
        ciel = arbre.nodes.new("ShaderNodeTexSky")
        ciel.sky_type = 'HOSEK_WILKIE'
        ciel.sun_direction = Vector((0.5, -0.6, 0.6)).normalized()
        ciel.turbidity = 3.0
        arbre.links.new(ciel.outputs[0], fond.inputs[0])
        fond.inputs[1].default_value = 2.2
    except (TypeError, AttributeError, RuntimeError):
        fond.inputs[0].default_value = (0.45, 0.62, 0.85, 1.0)
        fond.inputs[1].default_value = 1.0
    scene.world = monde

    soleil = bpy.data.lights.new("soleil_apercu", 'SUN')
    soleil.energy = 3.5
    soleil.angle = math.radians(1.5)
    objet = bpy.data.objects.new("soleil_apercu", soleil)
    objet.rotation_euler = Vector((0.5, -0.6, 0.6)).to_track_quat('Z', 'Y').to_euler()
    scene.collection.objects.link(objet)

    eau, arbre, noeud, lier = _arbre("eau_apercu")
    bsdf = noeud("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.012, 0.045, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.12
    coord = noeud("ShaderNodeTexCoord")
    vagues = _bruit(noeud, lier, coord.outputs["Object"], 0.6, 0.0, 3.0)
    relief = noeud("ShaderNodeBump")
    relief.inputs["Strength"].default_value = 0.25
    lier(vagues, relief.inputs["Height"])
    lier(relief.outputs[0], bsdf.inputs["Normal"])
    sortie = noeud("ShaderNodeOutputMaterial")
    lier(bsdf.outputs[0], sortie.inputs[0])
    maillage = bpy.data.meshes.new("eau_apercu")
    d = 2000.0
    maillage.from_pydata([(-d, -d, 0), (d, -d, 0), (d, d, 0), (-d, d, 0)], [], [(0, 1, 2, 3)])
    maillage.materials.append(eau)
    scene.collection.objects.link(bpy.data.objects.new("eau_apercu", maillage))


def _rendre(chemin, vue, moteur, largeur=960, hauteur=720):
    scene = bpy.context.scene
    position, cible, champ = VUES[vue]
    camera = scene.camera
    if camera is None:
        donnees = bpy.data.cameras.new("camera_apercu")
        camera = bpy.data.objects.new("camera_apercu", donnees)
        scene.collection.objects.link(camera)
        scene.camera = camera
    camera.data.sensor_fit = 'HORIZONTAL'
    camera.data.angle = math.radians(champ)
    camera.data.clip_start = 0.5
    camera.data.clip_end = 5000.0
    camera.location = position
    camera.rotation_euler = (Vector(cible) - Vector(position)).to_track_quat('-Z', 'Y').to_euler()

    rendu = scene.render
    rendu.resolution_x = min(largeur, 960)
    rendu.resolution_y = min(hauteur, 720)
    rendu.resolution_percentage = 100
    rendu.image_settings.file_format = 'PNG'
    rendu.filepath = chemin
    if moteur == "EEVEE":
        moteurs = [e.identifier for e in
                   bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        rendu.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in moteurs else "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 32
        try:
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass
    else:
        rendu.engine = "CYCLES"
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 32
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
    bpy.ops.render.render(write_still=True)


def _statistiques(racine):
    """Dimensions (m) et nombre de triangles du navire, après modificateurs."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    triangles = 0
    mini = Vector((1e9, 1e9, 1e9))
    maxi = -mini
    par_objet = {}
    for objet in racine.children_recursive:
        if objet.type != 'MESH':
            continue
        evalue = objet.evaluated_get(depsgraph)
        maillage = evalue.to_mesh()
        maillage.calc_loop_triangles()
        triangles += len(maillage.loop_triangles)
        zs = []
        for v in maillage.vertices:
            p = objet.matrix_world @ v.co
            zs.append(p.z)
            for i in range(3):
                mini[i] = min(mini[i], p[i])
                maxi[i] = max(maxi[i], p[i])
        par_objet[objet.name] = (len(maillage.loop_triangles), min(zs), max(zs))
        evalue.to_mesh_clear()
    return triangles, mini, maxi, par_objet


def _principal():
    import argparse
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    analyseur = argparse.ArgumentParser(description="Aperçu du navire de pêche")
    analyseur.add_argument("--apercu", help="image PNG à écrire")
    analyseur.add_argument("--vue", default="trois_quarts",
                           help="une vue, plusieurs séparées par des virgules, ou « toutes » : "
                                + ", ".join(VUES))
    analyseur.add_argument("--moteur", default="CYCLES", choices=("CYCLES", "EEVEE"))
    analyseur.add_argument("--nom", default="MARIE-LOUISE")
    analyseur.add_argument("--immatriculation", default="GV 642410")
    analyseur.add_argument("--longueur", type=float, default=14.0)
    analyseur.add_argument("--couleur", type=float, nargs=3, default=(0.05, 0.18, 0.45))
    analyseur.add_argument("--graine", type=int, default=0)
    options = analyseur.parse_args(arguments)

    _vider_scene()
    debut = time.time()
    racine = creer_bateau(nom=options.nom, immatriculation=options.immatriculation,
                          longueur=options.longueur, couleur_coque=tuple(options.couleur),
                          graine=options.graine)
    duree = time.time() - debut
    triangles, mini, maxi, par_objet = _statistiques(racine)
    print(f"[bateau] création : {duree:.2f} s, {triangles} triangles")
    print(f"[bateau] encombrement x [{mini.x:.2f}, {maxi.x:.2f}]  y [{mini.y:.2f}, {maxi.y:.2f}]"
          f"  z [{mini.z:.2f}, {maxi.z:.2f}]")
    if os.environ.get("BATEAU_DETAIL"):
        for nom_objet, (n, z0, z1) in sorted(par_objet.items()):
            print(f"[bateau]   {nom_objet:45s} {n:6d} tri  z [{z0:.2f}, {z1:.2f}]")

    if options.apercu:
        _decor_apercu()
        vues = list(VUES) if options.vue == "toutes" else options.vue.split(",")
        base, extension = os.path.splitext(options.apercu)
        for vue in vues:
            chemin = options.apercu if len(vues) == 1 else f"{base}_{vue}{extension or '.png'}"
            t0 = time.time()
            _rendre(chemin, vue, options.moteur)
            print(f"[bateau] {vue} -> {chemin} ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    _principal()
