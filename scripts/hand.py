#!/usr/bin/env python3
"""Makes a math font from photos of the filled-in grid (scripts/grid.py, level 1).

1. Each photo is matched to its page of the grid, straightened, and every box is lined up again on
   its own, so that a page that is not flat still fits.
2. In each box, the pencil is what is dark in the photo and not printed on the grid.
3. Glyphs drawn on the grid are traced as they are. Sizes and pieces of tall delimiters are scaled
   to the sizes STIX Two Math gives them and stroked again as thick as the pencil, so that they
   match the letters; the pieces that repeat become straight strokes, so that they join.
4. The math alphabets level 1 does not ask for come from the drawn letters: bold is the letter drawn
   thicker, double-struck its outline, sans-serif the upright letter, monospace the upright letter
   on a fixed width. Greek capitals that look like Latin ones are the Latin ones.
5. Everything else is borrowed from Euler Math, Noto Sans Math or STIX Two Math and redrawn with the
   pencil: the outline is thinned to its centre line, bent a little the way a hand would draw it,
   and stroked as thick as the pencil line. These fonts are under the SIL Open Font License, so the
   font made here is too.

    python3 scripts/hand.py photos/*.jpg --name "Pencil Math" --out fonts/pencil-math/PencilMath-Regular.otf
    python3 scripts/hand.py photos/*.jpg --grid regular ...   # for the large grid
    python3 scripts/hand.py photos/*.jpg --debug some/folder  # also writes what was cut from each box

Needs numpy, opencv-python-headless, scikit-image, fonttools, skia-pathops, cffsubr, reportlab, and
the potrace program (brew install potrace, apt install potrace).
"""

import argparse
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import pathops
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from PIL import Image, ImageOps
from skimage.morphology import skeletonize

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import grid as G  # noqa: E402

PXMM = 16  # pixels per millimetre the boxes are cut at
PXPT = PXMM * 25.4 / 72
MM = 72 / 25.4
PAGE_W, PAGE_H = G.A4
U = 2.5  # font units per pixel of the glyph rasters
SB = 55  # side bearing, in font units


# ---------- 1. the grid: where every box of level 1 is

def boxes(layout):
    """Every box of level 1: its page, rectangle, and for characters the baseline and em, in points."""
    out = []

    class Recorder(G.Grid):
        def cells(self, items, columns, height, draw_sample):
            def record(item, x, top, width, label):
                self.current = {"page": self.page, "number": self.number, "x": x + 1, "top": top, "w": width - 2, "h": height, "label": label}
                if isinstance(item, str):
                    self.current["char"] = item
                else:
                    self.current["glyph"], self.current["what"] = item[0], item[1]
                draw_sample(item, x, top, width, label)
                out.append(self.current)

            super().cells(items, columns, height, record)

        def guides(self, x, top, width, height, label):
            base, em = super().guides(x, top, width, height, label)
            self.current.update(base=base, em=em)
            return base, em

    ref = G.Reference(G.REFERENCE)
    with tempfile.TemporaryDirectory() as t:
        grid = Recorder(Path(t) / "grid.pdf", ref, layout=layout)
        grid.page = 1  # the cover
        grid.level = "Level 1, the essentials"
        grid.new_page()
        for title, items, _ in G.level_one():
            grid.characters(title, items)
        tall, wide = G.size_cells(ref)
        grid.pieces("", tall, False, "")
        grid.pieces("", wide, True, "")
    return out


def render_page(pdf, page, dpi, folder):
    out = Path(folder) / f"page-{page}-{dpi}"
    if not out.with_suffix(".png").exists():
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile", "-gray", "-png", str(pdf), str(out)], check=True)
    return cv2.imread(str(out.with_suffix(".png")), cv2.IMREAD_GRAYSCALE)


# ---------- 2. photos to pencil

def match(photo, pages, pdf, folder):
    """For every page: how many points of it were found in `photo`, and the homography from the page
    (at PXMM) to the photo."""
    sift = cv2.SIFT_create(8000)
    k = 1600 / max(photo.shape)
    small = cv2.resize(photo, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    kp, dp = sift.detectAndCompute(small, None)
    found = {}
    for page in pages:
        tpl = render_page(pdf, page, 120, folder)
        kt, dt = sift.detectAndCompute(tpl, None)
        pairs = [a for a, b in cv2.BFMatcher().knnMatch(dt, dp, k=2) if a.distance < 0.75 * b.distance]
        if len(pairs) < 12:
            continue
        src = np.float32([kt[a.queryIdx].pt for a in pairs]) * (PXMM * 25.4 / 120)
        dst = np.float32([kp[a.trainIdx].pt for a in pairs]) / k
        H, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 12.0)
        if H is not None:
            found[page] = (int(inliers.sum()), H)
    return found


def cut(photo, H, template, box):
    """The box with 3 mm around it, from the photo, lined up again on the grid's lines. Returns
    (photo, template), both as floats, 1 for white."""
    pad = 3 * MM
    X0, Y0 = round((box["x"] - pad) * PXPT), round((PAGE_H - box["top"] - pad) * PXPT)
    W, Hh = round((box["w"] + 2 * pad) * PXPT), round((box["h"] + 2 * pad) * PXPT)
    tpl = np.full((Hh, W), 255, np.uint8)
    src = template[max(Y0, 0) : Y0 + Hh, max(X0, 0) : X0 + W]
    tpl[: src.shape[0], : src.shape[1]] = src
    T = np.array([[1, 0, X0], [0, 1, Y0], [0, 0, 1]], float)
    patch = cv2.warpPerspective(photo, H @ T, (W, Hh), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR, borderValue=255)
    background = cv2.medianBlur(patch, 51).astype(np.float32)
    patch = np.clip(patch.astype(np.float32) / np.maximum(background, 1), 0, 1)
    # coarse to fine: the box's printed lines against the photo, blurred less each time
    warp = np.eye(2, 3, dtype=np.float32)
    for sigma, motion in [(9, cv2.MOTION_TRANSLATION), (5, cv2.MOTION_AFFINE), (2.5, cv2.MOTION_AFFINE)]:
        a = cv2.GaussianBlur(255 - tpl, (0, 0), sigma).astype(np.float32) / 255
        b = cv2.GaussianBlur(1 - patch, (0, 0), sigma).astype(np.float32)
        try:
            _, warp = cv2.findTransformECC(a, b, warp.copy(), motion, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
        except cv2.error:
            pass
    patch = cv2.warpAffine(patch, warp, (W, Hh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=1)
    return patch, tpl


def pencil(patch, tpl, box):
    """What is dark and not printed, inside the drawing area of the box."""
    pad = 3 * MM
    printed = cv2.dilate((tpl < 200).astype(np.uint8), np.ones((7, 7), np.uint8))
    margin = round(0.7 * PXMM)
    area = np.zeros_like(tpl, np.uint8)
    top, left = round((pad + box["label"]) * PXPT) + margin, round(pad * PXPT) + margin
    area[top : round((pad + box["h"]) * PXPT) - margin, left : round((pad + box["w"]) * PXPT) - margin] = 1
    ink = (cv2.GaussianBlur(1 - patch, (0, 0), 1.2) > 0.16).astype(np.uint8) & area
    # where a stroke crosses a printed line, keep the crossing: ink on both sides closes over it
    free = ink & (1 - printed)
    closed = cv2.morphologyEx(free, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    ink = (free | (closed & ink)) & area
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.isin(labels, [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 40])
    return keep


# ---------- glyph rasters: (mask, x0, y0), U font units per pixel, (x0, y0) the bottom-left corner in font units

def crop(mask, x0, y0):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    a, b, c, d = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return mask[a:b, c:d], x0 + c * U, y0 + (mask.shape[0] - b) * U


def pad(g, p):
    m, x0, y0 = g
    return np.pad(m, p), x0 - p * U, y0 - p * U


def disk(r):
    r = max(1, round(r))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def bounds(g):
    m, x0, y0 = g
    return x0, y0, x0 + m.shape[1] * U, y0 + m.shape[0] * U


def move(g, dx, dy):
    m, x0, y0 = g
    return m, x0 + dx, y0 + dy


def scale(g, sx, sy=None):
    sy = sx if sy is None else sy
    m, x0, y0 = g
    h, w = m.shape
    out = cv2.resize(m.astype(np.float32), (max(1, round(w * sx)), max(1, round(h * sy))), interpolation=cv2.INTER_AREA if sx < 1 else cv2.INTER_LINEAR) > 0.5
    return crop(out, x0 * sx, y0 * sy)


def stroke_width(g):
    m = g[0].astype(np.uint8)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)[skeletonize(m > 0)]
    return float(np.median(dist[dist > 0.5])) * 2 * U if dist.size else 0


def restroke(g, thickness):
    """The centre line of `g`, stroked `thickness` units thick with a round pen."""
    m, x0, y0 = pad(g, int(thickness / U) + 4)
    line = cv2.dilate(skeletonize(m).astype(np.uint8), disk(thickness / 2 / U)) > 0
    return crop(cv2.GaussianBlur(line.astype(np.float32), (0, 0), 1.0) > 0.5, x0, y0)


def thicken(g, r):
    m, x0, y0 = pad(g, int(r / U) + 3)
    return crop(cv2.dilate(m.astype(np.uint8), disk(r / U)) > 0, x0, y0)


def outline(g, thickness):
    """Double-struck: the outside edge of a thick version of the letter, drawn as a line."""
    m, x0, y0 = pad(g, int(2 * thickness / U) + 4)
    thick = cv2.dilate(m.astype(np.uint8), disk(0.85 * thickness / U))
    inner = cv2.erode(thick, disk(0.55 * thickness / U))
    return crop((thick > 0) & ~(inner > 0), x0, y0)


def wobble(g, seed, amount=7.0, reach=70.0):
    """Bends the raster a little, as a hand never draws a straight line: a smooth random shift of
    at most `amount` units that changes over `reach` units. The same seed bends the same way."""
    m, x0, y0 = pad(g, int(amount / U) + 2)
    rng = np.random.default_rng(seed)
    h, w = m.shape
    shift = []
    for _ in range(2):
        n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), reach / U)
        shift.append(n * (amount / U) / (np.abs(n).max() + 1e-9))
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return crop(cv2.remap(m.astype(np.float32), gx + shift[0], gy + shift[1], cv2.INTER_LINEAR, borderValue=0) > 0.5, x0, y0)


def largest_parts(g, share=0.06):
    """Drops specks: bits of pencil much smaller than the biggest one."""
    m, x0, y0 = g
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    if n <= 2:
        return g
    big = stats[1:, cv2.CC_STAT_AREA].max()
    return crop(np.isin(labels, [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= share * big]), x0, y0)


def to_units(ink, box, em):
    """A box's pencil as a glyph raster, the box's baseline at y=0 (pieces: the bottom of the box)."""
    k = 1000 / em / PXPT / U
    soft = cv2.GaussianBlur(cv2.resize(ink.astype(np.float32), None, fx=k, fy=k, interpolation=cv2.INTER_AREA), (0, 0), 1.6)
    mask = soft > 0.42
    pad_pt = 3 * MM
    top = (box["top"] + pad_pt - box.get("base", box["top"] - box["h"])) * 1000 / em
    return crop(mask, -pad_pt * 1000 / em, top - mask.shape[0] * U)


class FlatPen(BasePen):
    """Glyph outlines as polygons, to fill a raster."""

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.polygons, self.points = [], []

    def _moveTo(self, p):
        self.points = [p]

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.points[-1]
        for t in np.linspace(0, 1, 12)[1:]:
            u = 1 - t
            self.points.append(tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self.points[-1]
        for t in np.linspace(0, 1, 10)[1:]:
            u = 1 - t
            self.points.append(tuple(u * u * a + 2 * u * t * b + t * t * c for a, b, c in zip(p0, p1, p2)))

    def _closePath(self):
        if len(self.points) > 2:
            self.polygons.append(self.points)
        self.points = []

    _endPath = _closePath


class Borrowed:
    """A font of the catalog that lends the glyphs nobody drew."""

    def __init__(self, slug):
        folder = ROOT / "fonts" / slug
        file = next(line.split('"')[1] for line in (folder / "font.toml").read_text().splitlines() if line.startswith("file"))
        self.font = TTFont(folder / file)
        self.name = self.font["name"].getDebugName(1)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.x_height = self.font["OS/2"].sxHeight
        self.axis = self.font["MATH"].table.MathConstants.AxisHeight.Value

    def raster(self, glyph, k):
        pen = FlatPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        if not pen.polygons:
            return None
        polygons = [np.array(p) * k for p in pen.polygons]
        everything = np.vstack(polygons)
        x0, y0 = everything.min(0) - 4 * U
        x1, y1 = everything.max(0) + 4 * U
        w, h = int((x1 - x0) / U) + 1, int((y1 - y0) / U) + 1
        image = np.zeros((h, w), np.uint8)
        cv2.fillPoly(image, [np.round(np.column_stack([(p[:, 0] - x0) / U, h - (p[:, 1] - y0) / U]) * 8).astype(np.int32) for p in polygons], 1, lineType=cv2.LINE_8, shift=3)
        return crop(image > 0, x0, y0)


def trace(g):
    """The raster's outline as curves (potrace), in font units."""
    m, x0, y0 = g
    with tempfile.TemporaryDirectory() as t:
        bitmap = Path(t) / "glyph.pbm"
        cv2.imwrite(str(bitmap), np.where(m, 0, 255).astype(np.uint8))
        svg = subprocess.run(["potrace", "-b", "svg", "--flat", "-t", "4", "-a", "1.1", "-O", "0.3", "-u", "10", "-o", "-", str(bitmap)], capture_output=True, text=True, check=True).stdout
    path = pathops.Path()
    pen = TransformPen(path.getPen(), (0.1 * U, 0, 0, 0.1 * U, x0, y0))  # potrace: tenths of a pixel, y up from the bottom
    for d in re.findall(r' d="([^"]+)"', svg):
        parse_path(d, pen)
    path.simplify(fix_winding=True)
    return path


# ---------- 3–5. the font

LIKE_LATIN = {"ALPHA": "A", "BETA": "B", "EPSILON": "E", "ZETA": "Z", "ETA": "H", "IOTA": "I", "KAPPA": "K", "MU": "M", "NU": "N", "OMICRON": "O", "RHO": "P", "TAU": "T", "CHI": "X"}
SYMBOLS = {"EPSILON SYMBOL": "MATHEMATICAL ITALIC EPSILON SYMBOL", "THETA SYMBOL": "MATHEMATICAL ITALIC THETA SYMBOL", "PHI SYMBOL": "MATHEMATICAL ITALIC PHI SYMBOL", "PI SYMBOL": "MATHEMATICAL ITALIC PI SYMBOL", "RHO SYMBOL": "MATHEMATICAL ITALIC RHO SYMBOL", "NABLA": "∇", "PARTIAL DIFFERENTIAL": "∂"}
STYLES = {  # style: (from the italic letters?, how)
    "BOLD": (False, "bold"), "BOLD ITALIC": (True, "bold"), "ITALIC": (True, "same"),
    "SANS-SERIF": (False, "same"), "SANS-SERIF BOLD": (False, "bold"), "SANS-SERIF ITALIC": (True, "same"), "SANS-SERIF BOLD ITALIC": (True, "bold"),
    "MONOSPACE": (False, "mono"), "DOUBLE-STRUCK": (False, "outline"), "DOUBLE-STRUCK ITALIC": (True, "outline"),
}
LENDERS = ["euler-math", "noto-sans-math", "stix-two-math"]


def lookup(name):
    try:
        return unicodedata.lookup(name)
    except KeyError:
        return None


class Font:
    def __init__(self, drawn, pieces, em):
        self.hand = drawn  # char -> raster
        self.pieces = pieces  # STIX glyph name -> raster, at the box's own scale
        self.glyphs = {}  # name -> (raster, advance)
        self.cmap = {}
        self.ref = G.Reference(G.REFERENCE)
        self.T = float(np.median([stroke_width(drawn[c]) for c in "0123456789abcdefghijklmnopqrstuvwxyz" if c in drawn]))
        top = lambda c: bounds(drawn[c])[3]
        self.x_height = float(np.median([top(c) for c in "acemnorsuvwxz" if c in drawn]))
        self.cap_height = float(np.median([top(c) for c in "EFHIKLMNTXZ" if c in drawn]))
        minus = bounds(drawn["−"])
        self.axis = (minus[1] + minus[3]) / 2
        self.vert_variants, self.vert_assembly, self.horiz_variants, self.horiz_assembly, self.extended = {}, {}, {}, {}, set()

    @staticmethod
    def name(ch):
        return f"uni{ord(ch):04X}" if ord(ch) < 0x10000 else f"u{ord(ch):05X}"

    def add(self, name, g, ch=None, advance=None, mono=None, keep_x=False):
        if g is None:
            return None
        x0, _, x1, _ = bounds(g)
        if mono:
            if x1 - x0 > mono - 2 * SB:
                g = scale(g, (mono - 2 * SB) / (x1 - x0), 1)
                x0, _, x1, _ = bounds(g)
            g, advance = move(g, (mono - (x1 - x0)) / 2 - x0, 0), mono
        elif not keep_x:
            g = move(g, SB - x0, 0)
            advance = (x1 - x0) + 2 * SB if advance is None else advance
        self.glyphs[name] = (g, advance)
        if ch:
            self.cmap[ord(ch)] = name
        return name

    def fit(self, stix_glyph, horizontal=False, like=None):
        """A drawn size or piece, scaled so that its ink spans what STIX Two Math's does (or what its
        glyph `like` spans), and stroked as thick as the letters."""
        g = largest_parts(self.pieces[stix_glyph])
        x0, y0, x1, y1 = bounds(g)
        tx0, ty0, tx1, ty1 = self.ref.bounds(like or stix_glyph)
        g = restroke(scale(g, (tx1 - tx0) / (x1 - x0) if horizontal else (ty1 - ty0) / (y1 - y0)), self.T)
        x0, y0, x1, y1 = bounds(g)
        if horizontal:
            return move(g, tx0 - x0, (ty0 + ty1) / 2 - (y0 + y1) / 2)
        return move(g, (tx0 + tx1) / 2 - (x0 + x1) / 2, ty0 - y0)

    def styled_source(self, rest, italic):
        """The drawn glyph a styled letter comes from; `rest` is its name after the style ('CAPITAL A')."""
        words = rest.split()
        if words[0] == "DIGIT":
            return self.hand.get(str(G.DIGITS.index(words[1])))
        case, letter = words[0], " ".join(words[1:])
        if case not in ("CAPITAL", "SMALL"):
            target = SYMBOLS.get(rest)
            return self.hand.get(target if target is None or len(target) == 1 else lookup(target))
        if len(letter) == 1:
            if italic:
                return self.hand.get((G.HOLES.get(("ITALIC SMALL", letter)) if case == "SMALL" else None) or lookup(f"MATHEMATICAL ITALIC {case} {letter}"))
            return self.hand.get(letter if case == "CAPITAL" else letter.lower())
        if case == "CAPITAL":
            return self.greek_capital("THETA" if letter == "THETA SYMBOL" else letter)
        return self.hand.get(lookup(f"MATHEMATICAL ITALIC SMALL {letter}"))

    def greek_capital(self, letter):
        if letter in LIKE_LATIN:
            return self.hand.get(LIKE_LATIN[letter])
        return self.hand.get(lookup(f"GREEK CAPITAL LETTER {letter}"))

    def derive(self, ch):
        """A glyph made from the drawn ones, as (how, raster), or None. `how` is "mono" for monospace."""
        name = unicodedata.name(ch, "")
        if name.startswith("GREEK CAPITAL LETTER ") and " WITH " not in name:
            return "", self.greek_capital(name[21:])
        if name.startswith("GREEK SMALL LETTER ") and " WITH " not in name:
            return "", self.hand.get(lookup(f"MATHEMATICAL ITALIC SMALL {name[19:]}"))
        if name.startswith("GREEK ") and name[6:] in SYMBOLS:
            return "", self.styled_source(name[6:], True)
        if name.startswith("MATHEMATICAL "):
            rest = name[13:]
            for style in sorted(STYLES, key=len, reverse=True):
                if rest.startswith(style + " ") and " DOTLESS " not in rest:
                    italic, how = STYLES[style]
                    g = self.styled_source(rest[len(style) + 1 :], italic)
                    if g is None:
                        return None
                    if how == "bold":
                        return "", thicken(g, 0.25 * self.T)
                    if how == "outline":
                        return "", outline(g, self.T)
                    return how, g
        return None

    def build_glyphs(self, wanted):
        for ch, g in self.hand.items():
            self.add(self.name(ch), g, ch)
        derived, borrowed = 0, []
        for ch in wanted:
            if ord(ch) in self.cmap:
                continue
            how, made = self.derive(ch) or ("", None)
            if made is None:
                borrowed.append(ch)
                continue
            self.add(self.name(ch), made, ch, mono=620 if how == "mono" else None)
            derived += 1
        lenders = [Borrowed(slug) for slug in LENDERS]
        lent = {}
        for ch in borrowed:
            for lender in lenders:
                glyph = lender.cmap.get(ord(ch))
                if not glyph:
                    continue
                k = self.x_height / lender.x_height
                g = lender.raster(glyph, k)
                if g is not None:
                    g = restroke(wobble(g, ord(ch)), self.T * (1.6 if "BOLD" in unicodedata.name(ch, "") else 1.1))
                    if unicodedata.category(ch)[0] not in "LN":  # symbols sit on the drawn math axis
                        g = move(g, 0, self.axis - lender.axis * k)
                    self.add(self.name(ch), g, ch)
                    lent[lender.name] = lent.get(lender.name, 0) + 1
                break
        return derived, lent

    def construct(self, ch, picks, horizontal=False):
        """Bigger sizes and the assembly of `ch`, from the drawn sizes and pieces, in STIX Two Math's structure."""
        construction = (self.ref.horizontal if horizontal else self.ref.vertical).get(self.ref.name(ch))
        base = self.cmap.get(ord(ch))
        if construction is None or base is None:
            return
        records = [r.VariantGlyph for r in construction.MathGlyphVariantRecord]
        names = [base] + [self.add(f"{base}.s{i}", self.fit(records[i], horizontal)) for i in picks if i < len(records) and records[i] in self.pieces]
        sizes = []
        for name in names:
            x0, y0, x1, y1 = bounds(self.glyphs[name][0])
            sizes.append((name, (x1 - x0) if horizontal else (y1 - y0)))
        if len(sizes) > 1:
            (self.horiz_variants if horizontal else self.vert_variants)[base] = sizes
            if not horizontal:
                self.extended.update(sizes_name for sizes_name, _ in sizes)
        assembly = construction.GlyphAssembly
        # the radical's pieces are drawn as a slanted check mark that does not stand on a vertical
        # extender: tall radicals use the biggest drawn size instead
        if not assembly or ch == "√" or not all(p.glyph in self.pieces for p in assembly.PartRecords):
            return
        records = assembly.PartRecords
        parts = [self.fit(p.glyph, horizontal) for p in records]
        for i, p in enumerate(records):
            if p.PartFlags & 1:  # what repeats: a straight stroke where the drawn line was
                x0, y0, x1, y1 = bounds(parts[i])
                length = (x1 - x0) if horizontal else (y1 - y0)
                t, n = max(2, round(self.T / U)), max(2, round(length / U))
                bar = np.ones((t, n) if horizontal else (n, t), bool)
                parts[i] = (bar, x0, (y0 + y1) / 2 - t * U / 2) if horizontal else (bar, (x0 + x1) / 2 - t * U / 2, y0)

        def joint(g, end):
            """Where the stroke crosses the piece's start or end edge, across the direction of growth."""
            m, x0, y0 = g
            if horizontal:
                ys = np.nonzero(m[:, 0] if end == "start" else m[:, -1])[0]
                return y0 + (m.shape[0] - ys.mean()) * U if len(ys) else 0
            xs = np.nonzero(m[-1] if end == "start" else m[0])[0]
            return x0 + xs.mean() * U if len(xs) else 0

        extender = next(i for i, p in enumerate(records) if p.PartFlags & 1)
        anchor = joint(parts[extender], "start")
        lined = []
        for i, g in enumerate(parts):
            d = anchor - joint(g, "end" if i < extender and not records[i].PartFlags & 1 else "start")
            lined.append(move(g, 0, d) if horizontal else move(g, d, 0))
        left = min(bounds(g)[0] for g in lined)
        width = max(bounds(g)[2] for g in lined) - left + 2 * SB
        out = []
        for i, (p, g) in enumerate(zip(records, lined)):
            name = f"{base}.p{i}"
            if horizontal:
                g = move(g, -bounds(g)[0], 0)
                full = bounds(g)[2]
                self.add(name, g, advance=full, keep_x=True)
            else:
                g = move(g, SB - left, self.ref.bounds(p.glyph)[1] - bounds(g)[1])
                self.add(name, g, advance=width, keep_x=True)
                full = bounds(g)[3] - bounds(g)[1]
            overlap = min(150, full / 3)
            out.append((name, p.PartFlags, 0 if i == 0 else overlap, 0 if i == len(records) - 1 else overlap, full))
        (self.horiz_assembly if horizontal else self.vert_assembly)[base] = (out, 0)

    def save(self, out, family):
        paths = {name: trace(g) for name, (g, _) in self.glyphs.items()}
        order = [".notdef", "space"] + list(self.glyphs)
        charstrings, metrics = {}, {}
        for name in order:
            pen = T2CharStringPen(0, None)
            box = None
            if name in paths:
                paths[name].draw(pen)
                bp = BoundsPen(None)
                paths[name].draw(bp)
                box = bp.bounds
            charstrings[name] = pen.getCharString()
            advance = self.glyphs[name][1] if name in self.glyphs else (300 if name == "space" else 600)
            metrics[name] = (round(advance), round(box[0]) if box else 0)

        fb = FontBuilder(1000, isTTF=False)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({**self.cmap, 0x20: "space", 0xA0: "space"})
        fb.setupCFF(family.replace(" ", "") + "-Regular", {"FullName": f"{family} Regular"}, charstrings, {})
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=900, descent=-300)
        lenders = ", ".join(Borrowed(s).name for s in LENDERS)
        fb.setupNameTable({"familyName": family, "styleName": "Regular", "designer": "Drawn by hand on the mathfonts grid", "version": "Version 0.1",
                           "description": f"Drawn by hand on the mathfonts grid. Glyphs that were not drawn are redrawn from {lenders}.",
                           "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.", "licenseInfoURL": "https://openfontlicense.org"})
        fb.setupOS2(sTypoAscender=900, sTypoDescender=-300, usWinAscent=1100, usWinDescent=400, sxHeight=round(self.x_height), sCapHeight=round(self.cap_height), fsType=0)
        fb.setupPost()

        # MATH constants: Euler Math's, the catalog's handwritten font, scaled to the drawn x-height,
        # with what can be measured from the drawing: the axis, the rules, the accent heights
        euler = Borrowed("euler-math")
        source = euler.font["MATH"].table.MathConstants
        k = self.x_height / euler.x_height
        constants = {}
        for key, value in vars(source).items():
            value = value.Value if hasattr(value, "Value") else value
            constants[key] = value if "Percent" in key else round(value * k)
        rule = round(self.T * 0.9)
        integral = bounds(self.hand["∫"])
        constants.update({
            "AxisHeight": round(self.axis), "AccentBaseHeight": round(self.x_height), "FlattenedAccentBaseHeight": round(self.cap_height),
            "FractionRuleThickness": rule, "OverbarRuleThickness": rule, "UnderbarRuleThickness": rule, "RadicalRuleThickness": rule,
            "RadicalExtraAscender": rule, "OverbarExtraAscender": rule, "UnderbarExtraDescender": rule,
            # the text integral is drawn tall: a display operator must be taller than it to be picked
            "DisplayOperatorMinHeight": round(1.25 * (integral[3] - integral[1])),
        })
        accents = {name: round((p.bounds[0] + p.bounds[2]) / 2) for name, p in paths.items() if p.bounds}
        buildMathTable(fb.font, constants=constants, topAccentAttachments=accents, extendedShapes=self.extended, minConnectorOverlap=20,
                       vertGlyphVariants=self.vert_variants, horizGlyphVariants=self.horiz_variants, vertGlyphAssembly=self.vert_assembly, horizGlyphAssembly=self.horiz_assembly)
        out.parent.mkdir(parents=True, exist_ok=True)
        fb.font.save(out)
        try:
            import cffsubr

            font = TTFont(out)
            cffsubr.subroutinize(font)
            font.save(out)
        except ImportError:
            pass
        return len(order)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--name", required=True, help='the family name, e.g. "Pencil Math"')
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--grid", choices=["compact", "regular"], default="compact")
    parser.add_argument("--debug", type=Path, help="a folder for the pencil cut from each box")
    args = parser.parse_args()

    layout = G.COMPACT if args.grid == "compact" else G.REGULAR
    pdf = ROOT / "site/grid" / ("mathfonts-grid-compact.pdf" if args.grid == "compact" else "mathfonts-grid.pdf")
    every = boxes(layout)
    pages = sorted({b["page"] for b in every})
    em = next(b["em"] for b in every if "char" in b)
    drawn, pieces, missing = {}, {}, []
    with tempfile.TemporaryDirectory() as folder:
        # every page header looks the same, so a photo may match several pages a little: each page
        # goes to the photo that matches it best, best matches first
        images = [np.array(ImageOps.exif_transpose(Image.open(photo)).convert("L")) for photo in args.photos]
        scores = [match(image, pages, pdf, folder) for image in images]
        pairs = sorted(((n, i, page) for i, found in enumerate(scores) for page, (n, _) in found.items()), reverse=True)
        seen, taken = {}, set()
        for n, i, page in pairs:
            if i not in taken and page not in seen:
                seen[page] = i
                taken.add(i)
        for i, photo in enumerate(args.photos):
            if i not in taken:
                print(f"{photo.name}: no page of level 1 found in it")
        for page, i in sorted(seen.items()):
            image, (inliers, H) = images[i], scores[i][page]
            print(f"{args.photos[i].name}: page {page} ({inliers} points matched)")
            template = render_page(pdf, page, round(PXMM * 25.4), folder)
            for box in (b for b in every if b["page"] == page):
                patch, tpl = cut(image, H, template, box)
                ink = pencil(patch, tpl, box)
                if args.debug:
                    args.debug.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(args.debug / f"{box['number']:04d}.png"), np.where(ink, 0, 255).astype(np.uint8))
                g = to_units(ink, box, em) if ink.sum() >= 150 else None
                if g is None:
                    missing.append(box)
                elif "char" in box:
                    drawn[box["char"]] = g
                else:
                    pieces[box["glyph"]] = g
        for page in pages:
            if page not in seen:
                print(f"page {page}: no photo of it")
    for box in missing:
        print(f"box {box['number']:04d} ({box.get('char') or box['what']}) is empty")

    font = Font(drawn, pieces, em)
    # the text radical: the box asks for the check mark, and a hand often adds the bar that mathra draws itself
    size2 = next((b["glyph"] for b in every if b.get("what") == "radical, size 2"), None)
    if size2 in pieces:
        font.hand["√"] = font.fit(size2, like=font.ref.name("√"))
    if "'" not in font.hand and "′" in font.hand:
        font.hand["'"] = font.hand["′"]
    print(f"pencil line: {font.T:.0f} units; x-height {font.x_height:.0f}, cap height {font.cap_height:.0f}, axis {font.axis:.0f}")

    listed = [c for _, items, _ in G.level_one() + G.level_two() for c in items]
    rest = [c for _, items, _ in G.level_three(set(listed)) for c in items]
    wanted = list(dict.fromkeys(listed + rest + [chr(c) for c in range(0x21, 0x7F)] + list("⏜⏝⏞⏟⎴⎵□■◇◆△▲▽▼○●◯★∎")))  # with the horizontal braces, and the shapes diagrams use
    derived, lent = font.build_glyphs(wanted)
    print(f"drawn: {len(font.hand)}; made from the drawing: {derived}; redrawn from " + ", ".join(f"{n} ({k})" for n, k in lent.items()))

    for ch in "()[]{}⟨⟩|‖⌊⌋⌈⌉":
        font.construct(ch, [3, 6])
    font.construct("√", [2, 3])
    for ch in "∑∏∫∬∮":
        font.construct(ch, [1])
    for ch in "̂̃":  # the combining hat and tilde
        font.construct(ch, [2, 4], horizontal=True)
    for ch in "→⏟⏞":
        font.construct(ch, [], horizontal=True)
    n = font.save(args.out, args.name)
    print(f"{n} glyphs, {len(font.cmap)} characters -> {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
