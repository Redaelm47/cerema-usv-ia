"""Visual check -> public/data/preview.png

Top: far area (ortho over hillshade on land, depth-tinted hillshade on sea, 0 m coastline
in yellow, near bbox, lanes, places). Middle: near area, same rendering. Bottom: two
full-resolution insets (2 m ortho with the 4 m DEM coastline and 10 m contour) where any
DEM / ortho misregistration would be obvious.

Run after build.py and places.py:  python3 tools/preview.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import FAR, FAR_ORTHO_RES, NEAR, NEAR_ORTHO_RES, OUT, Grid, ll_to_local  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
WIDTH = 1800
LANE_COLOURS = [(255, 60, 60), (255, 150, 0), (230, 60, 255)]
INSETS = [  # (title, lon_w, lat_s, lon_e, lat_n)
    ("Pointe du Petit Minou (2 m ortho + 4 m DEM coastline / 10 m contour)", -4.6245, 48.3315, -4.6005, 48.3415),
    ("Brest harbour jetties (2 m ortho + 4 m DEM coastline / 10 m contour)", -4.5000, 48.3655, -4.4760, 48.3755),
]


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def load_dem(name, grid):
    return np.fromfile(OUT / name, "<i2").reshape(grid.height, grid.width).astype(np.float32) / 10.0


def hillshade(z, res, exag=2.0):
    gy, gx = np.gradient(z * exag, res)
    # light from the north-west
    nx, ny, nz = -gx, gy, np.ones_like(z)
    lx, ly, lz = -0.5, 0.5, 0.7071
    return np.clip((nx * lx + ny * ly + nz * lz) / np.sqrt(nx * nx + ny * ny + nz * nz), 0, 1)


def sea_colour(depth):
    stops = np.array([0, 5, 15, 30, 50], float)
    cols = np.array([[150, 215, 220], [80, 170, 200], [40, 110, 170], [20, 60, 130], [10, 30, 80]], float)
    d = np.clip(depth, 0, 50)
    return np.stack([np.interp(d, stops, cols[:, k]) for k in range(3)], -1)


def render(z, res, ortho_rgb):
    """z and ortho already on the same pixel grid."""
    hs = hillshade(z, res)
    land = z > 0
    o = np.asarray(ortho_rgb).astype(np.float32)
    out = np.empty(z.shape + (3,), np.float32)
    out[land] = o[land] * (0.45 + 0.75 * hs[land, None])
    sc = sea_colour(-z)
    out[~land] = sc[~land] * (0.75 + 0.35 * hs[~land, None])
    edge = land & ~ndimage.binary_erosion(land)
    out[edge] = (255, 230, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def resample_dem(z, grid: Grid, xs, ns):
    r, c = grid.local_to_pixel(xs[None, :], ns[:, None])
    r = np.broadcast_to(r, (len(ns), len(xs)))
    c = np.broadcast_to(c, (len(ns), len(xs)))
    return ndimage.map_coordinates(z, [r.ravel(), c.ravel()], order=1, mode="nearest").reshape(r.shape)


class Panel:
    """Maps local metres to pixels of a rendered panel."""

    def __init__(self, x0, x1, n0, n1, w, h, oy=0):
        self.x0, self.x1, self.n0, self.n1, self.w, self.h, self.oy = x0, x1, n0, n1, w, h, oy

    def px(self, x, n):
        return ((x - self.x0) / (self.x1 - self.x0) * self.w,
                self.oy + (self.n1 - n) / (self.n1 - self.n0) * self.h)


def draw_overlays(draw, panel: Panel, places, lanes, f, show_labels=True, near_box=False):
    if near_box:
        a = panel.px(NEAR.xWest, NEAR.nNorth)
        b = panel.px(NEAR.xEast, NEAR.nSouth)
        draw.rectangle([a, b], outline=(255, 255, 255), width=2)
        draw.text((a[0] + 4, a[1] + 2), "near bbox (dem_near / ortho_near)", fill=(255, 255, 255), font=f,
                  stroke_width=2, stroke_fill=(0, 0, 0))
    for k, lane in enumerate(lanes):
        col = LANE_COLOURS[k % len(LANE_COLOURS)]
        pts = [panel.px(w["x"], w["n"]) for w in lane["waypoints"]]
        width = max(2, 7 - 2 * k)   # later lanes drawn thinner on top so overlaps stay visible
        draw.line(pts, fill=col, width=width, joint="curve")
        tail = [pts[-1]] + [panel.px(h["x"], h["n"]) for h in lane["harbourApproach"]]
        draw.line(tail, fill=col, width=1)
        for p in pts:
            draw.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=col, outline=(0, 0, 0))
    for p in places:
        q = panel.px(p["x"], p["n"])
        if not (0 <= q[0] <= panel.w and panel.oy <= q[1] <= panel.oy + panel.h):
            continue
        draw.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        if show_labels and p["kind"] != "approach":
            draw.text((q[0] + 6, q[1] - 7), p["name"].split(" (")[0], fill=(255, 255, 255), font=f,
                      stroke_width=2, stroke_fill=(0, 0, 0))


def main():
    pl = json.loads((OUT / "places.json").read_text())
    places, lanes = pl["places"], pl["lanes"]
    f_small, f_big = font(13), font(18)

    # ---- far panel
    zf = load_dem("dem_far.bin", FAR)
    hf = int(round(WIDTH * FAR.height / FAR.width))
    pxf = (FAR.xEast - FAR.xWest) / WIDTH
    xs = FAR.xWest + (np.arange(WIDTH) + 0.5) * pxf
    ns = FAR.nNorth - (np.arange(hf) + 0.5) * pxf
    zfr = resample_dem(zf, FAR, xs, ns)
    of = Image.open(OUT / "ortho_far.jpg").convert("RGB").resize((WIDTH, hf), Image.LANCZOS)
    far_img = Image.fromarray(render(zfr, pxf, of))

    # ---- near panel
    zn = load_dem("dem_near.bin", NEAR)
    hn = int(round(WIDTH * NEAR.height / NEAR.width))
    pxn = (NEAR.xEast - NEAR.xWest) / WIDTH
    xs = NEAR.xWest + (np.arange(WIDTH) + 0.5) * pxn
    ns = NEAR.nNorth - (np.arange(hn) + 0.5) * pxn
    znr = resample_dem(zn, NEAR, xs, ns)
    on = Image.open(OUT / "ortho_near.jpg").convert("RGB")
    near_img = Image.fromarray(render(znr, pxn, on.resize((WIDTH, hn), Image.LANCZOS)))

    # ---- insets at ortho resolution
    og = NEAR.with_res(NEAR_ORTHO_RES)
    insets = []
    for title, lw, ls, le, ln in INSETS:
        x0, n0 = ll_to_local(lw, ls)
        x1, n1 = ll_to_local(le, ln)
        r0, c0 = og.local_to_pixel(x0, n1)
        r1, c1 = og.local_to_pixel(x1, n0)
        r0, c0, r1, c1 = int(r0), int(c0), int(r1), int(c1)
        crop = on.crop((c0, r0, c1, r1))
        xs = og.xWest + (np.arange(c0, c1) + 0.5) * og.res
        ns = og.nNorth - (np.arange(r0, r1) + 0.5) * og.res
        zz = resample_dem(zn, NEAR, xs, ns)
        a = np.asarray(crop).copy()
        land = zz > 0
        a[land & ~ndimage.binary_erosion(land)] = (255, 40, 40)
        c10 = zz > 10
        a[c10 & ~ndimage.binary_erosion(c10)] = (255, 230, 0)
        im = Image.fromarray(a)
        im.thumbnail((WIDTH // 2, 10000), Image.LANCZOS)
        insets.append((title, im, Panel(float(xs[0] - og.res / 2), float(xs[-1] + og.res / 2),
                                        float(ns[-1] - og.res / 2), float(ns[0] + og.res / 2),
                                        im.size[0], im.size[1])))
    ih = max(im.size[1] for _, im, _ in insets)

    head = 34
    H = head + hf + head + hn + head + ih
    canvas = Image.new("RGB", (WIDTH, H), (25, 25, 30))
    d = ImageDraw.Draw(canvas)
    y = 0
    d.text((8, y + 8), f"dem_far + ortho_far  ({FAR.width}x{FAR.height} @ {FAR.res:g} m; ortho "
                       f"{FAR.with_res(FAR_ORTHO_RES).width}x{FAR.with_res(FAR_ORTHO_RES).height} @ "
                       f"{FAR_ORTHO_RES:g} m)  -  yellow: 0 m coastline; red/orange/violet: shipping lanes",
           fill=(255, 255, 255), font=f_big)
    y += head
    canvas.paste(far_img, (0, y))
    draw_overlays(d, Panel(FAR.xWest, FAR.xEast, FAR.nSouth, FAR.nNorth, WIDTH, hf, y), places, lanes, f_small,
                  near_box=True)
    y += hf
    d.text((8, y + 8), f"dem_near + ortho_near  ({NEAR.width}x{NEAR.height} @ {NEAR.res:g} m; ortho "
                       f"{NEAR.with_res(NEAR_ORTHO_RES).width}x{NEAR.with_res(NEAR_ORTHO_RES).height} @ "
                       f"{NEAR_ORTHO_RES:g} m)", fill=(255, 255, 255), font=f_big)
    y += head
    canvas.paste(near_img, (0, y))
    draw_overlays(d, Panel(NEAR.xWest, NEAR.xEast, NEAR.nSouth, NEAR.nNorth, WIDTH, hn, y), places, lanes, f_small)
    y += hn
    x = 0
    for title, im, pan in insets:
        d.text((x + 8, y + 8), title, fill=(255, 255, 255), font=f_small)
        canvas.paste(im, (x, y + head))
        sub = ImageDraw.Draw(canvas)
        pan.oy = y + head
        shifted = Panel(pan.x0, pan.x1, pan.n0, pan.n1, pan.w, pan.h, pan.oy)
        # draw only places/lanes inside the inset, offset horizontally
        tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        td = ImageDraw.Draw(tmp)
        draw_overlays(td, shifted, places, lanes, f_small)
        tmp = tmp.crop((0, pan.oy, pan.w, pan.oy + pan.h))
        canvas.paste(tmp, (x, pan.oy), tmp)
        x += WIDTH // 2
        del sub
    canvas.save(OUT / "preview.png", optimize=True)
    print(f"[preview] preview.png {canvas.size[0]}x{canvas.size[1]}")


if __name__ == "__main__":
    main()
