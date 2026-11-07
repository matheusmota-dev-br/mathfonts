#!/usr/bin/env python3
"""Redraws a math font with squared shapes or on a pixel grid, and keeps everything else of the base:
the glyph order, the widths, the cmap, the MATH table, and the substitutions and kerning.

Five styles, each a font of the catalog:

    quadra       every run of curves between two extrema becomes a corner, pulled nearly square
    octa         every run of curves between two extrema becomes a chamfer: two straight cuts
    pixel-retro  on a grid of big cells, about 6 to the x-height: the cells the centre line of each
                 stroke goes through, so strokes are one pixel wide and nearby strokes stay apart
    pixel        the same on a grid of about 9 cells to the x-height
    dot-matrix   the grid of pixel, each cell a round dot

The grid is anchored at the origin, so that cells line up from one glyph to the next and sit on the
baseline. A squared glyph whose ink grows or shrinks too much (a counter closing up, a contour
crossing itself) is left as the base draws it.

    scripts/blocky.py                 all five, from Noto Sans Math, into fonts/<style>-math/
    scripts/blocky.py --style pixel   one of them

The same base gives the same fonts, byte for byte. Needs fontTools, numpy, opencv-python-headless,
scikit-image, skia-pathops and cffsubr.
"""

from __future__ import annotations

import argparse
import pathlib

import cffsubr
import cv2
import numpy as np
import pathops
from skimage.morphology import skeletonize
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.basePen import BasePen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / "fonts/noto-sans-math/NotoSansMath-Regular.ttf"

# style: (family, how, cell in font units or pull toward the corner, coverage that fills a cell)
STYLES = {
    "quadra": ("Quadra Math", "square", 0.9, None),
    "octa": ("Octa Math", "chamfer", 0.55, None),
    "pixel-retro": ("Pixel Retro Math", "line", 89, None),
    "pixel": ("Pixel Math", "pixel", 60, 0.33),
    "dot-matrix": ("Dot Matrix Math", "dots", 60, 0.33),
}
SAMPLES = 6  # samples along each side of a cell, to measure how much of it the glyph covers


# ---------- squared shapes

class Segments(BasePen):
    """Every contour as a list of segments: ("line", p0, p1) or ("curve", p0, c1, c2, p3)."""

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.contours, self.segments, self.start, self.last = [], [], None, None

    def _moveTo(self, p):
        self.segments, self.start, self.last = [], p, p

    def _lineTo(self, p):
        if p != self.last:
            self.segments.append(("line", self.last, p))
        self.last = p

    def _curveToOne(self, c1, c2, p):
        self.segments.append(("curve", self.last, c1, c2, p))
        self.last = p

    def _qCurveToOne(self, q, p):
        p0 = self.last
        c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]), p0[1] + 2 / 3 * (q[1] - p0[1]))
        c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
        self._curveToOne(c1, c2, p)

    def _closePath(self):
        if self.last != self.start:
            self.segments.append(("line", self.last, self.start))
        if self.segments:
            self.contours.append(self.segments)
        self.segments = []

    _endPath = _closePath


def direction(a, b):
    v = np.subtract(b, a)
    n = np.hypot(*v)
    return v / n if n > 1e-6 else None


def tangents(segment):
    """The direction a segment leaves its start in, and arrives at its end in."""
    if segment[0] == "line":
        t = direction(segment[1], segment[2])
        return t, t
    p0, c1, c2, p3 = segment[1:]
    start = direction(p0, c1)
    end = direction(c2, p3)
    return (start if start is not None else direction(p0, c2)), (end if end is not None else direction(c1, p3))


def at_extremum(t, tolerance=0.06):
    return t is not None and (abs(t[0]) < tolerance or abs(t[1]) < tolerance)


def corner(a, ta, b, tb):
    """Where the line leaving a along ta meets the line arriving at b along tb, if it lies ahead of a,
    behind b and not far off: a corner much further away than the curve is long would stretch it."""
    m = np.array([[ta[0], tb[0]], [ta[1], tb[1]]])
    if abs(np.linalg.det(m)) < 1e-4:
        return None
    s, u = np.linalg.solve(m, np.subtract(b, a))
    chord = np.hypot(*np.subtract(b, a))
    if s <= 0 or u <= 0 or s > 1.5 * chord or u > 1.5 * chord:
        return None
    return np.add(a, np.multiply(s, ta))


def runs(contour):
    """The contour as runs: a line alone, or curves joined smoothly up to the next extremum."""
    out, run = [], []
    for segment in contour:
        if segment[0] == "curve":
            if run:
                end, start = tangents(run[-1])[1], tangents(segment)[0]
                smooth = end is not None and start is not None and np.dot(end, start) > 0.98
                if not smooth or at_extremum(start):
                    out.append(run)
                    run = []
            run.append(segment)
        else:
            if run:
                out.append(run)
                run = []
            out.append([segment])
    if run:
        out.append(run)
    return out


def squared(glyph_set, name, pull, chamfer):
    """The glyph with each run of curves turned into a corner (a curve pulled toward it) or a
    chamfer (straight cuts `pull` of the way to it). None to keep the base's glyph."""
    segments = Segments(glyph_set)
    glyph_set[name].draw(segments)
    if not segments.contours:
        return None
    path = pathops.Path()
    pen = path.getPen()
    for contour in segments.contours:
        parts = runs(contour)
        pen.moveTo(tuple(parts[0][0][1]))
        for run in parts:
            if run[0][0] == "line":
                pen.lineTo(tuple(run[0][2]))
                continue
            a, b = run[0][1], run[-1][4]
            ta, tb = tangents(run[0])[0], tangents(run[-1])[1]
            c = corner(a, ta, b, tb) if ta is not None and tb is not None else None
            if c is None:
                for segment in run:
                    pen.curveTo(tuple(segment[2]), tuple(segment[3]), tuple(segment[4]))
            elif chamfer:
                pen.lineTo(tuple(np.add(a, pull * np.subtract(c, a))))
                pen.lineTo(tuple(np.add(b, pull * np.subtract(c, b))))
                pen.lineTo(tuple(b))
            else:
                pen.curveTo(tuple(np.add(a, pull * np.subtract(c, a))), tuple(np.add(b, pull * np.subtract(c, b))), tuple(b))
        pen.closePath()
    try:
        path.simplify(fix_winding=True)
        before = pathops.Path()
        glyph_set[name].draw(before.getPen(glyphSet=glyph_set))
        before.simplify(fix_winding=True)
    except pathops.PathOpsError:
        return None
    # squaring adds a little ink at the corners; much more or less means a counter closed up or a
    # contour crossed itself
    if before.area and not 0.85 <= path.area / before.area <= 1.3:
        return None
    return path


# ---------- the grid

class Polygons(BasePen):
    """Outlines as polygons, curves cut into short lines, to fill a raster."""

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.polygons, self.points = [], []

    def _moveTo(self, p):
        self.points = [p]

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.points[-1]
        for t in np.linspace(0, 1, 10)[1:]:
            u = 1 - t
            self.points.append(tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self.points[-1]
        for t in np.linspace(0, 1, 8)[1:]:
            u = 1 - t
            self.points.append(tuple(u * u * a + 2 * u * t * b + t * t * c for a, b, c in zip(p0, p1, p2)))

    def _closePath(self):
        if len(self.points) > 2:
            self.polygons.append(self.points)
        self.points = []

    _endPath = _closePath


def grid(glyph_set, name, cell, threshold):
    """The cells the glyph covers enough, or, with no threshold, the cells its strokes' centre line
    goes through: (rows top first, column of the first cell, row of the last)."""
    pen = Polygons(glyph_set)
    glyph_set[name].draw(pen)
    if not pen.polygons:
        return None
    points = np.vstack([np.array(p) for p in pen.polygons])
    c0, r0 = int(np.floor(points[:, 0].min() / cell)) - 1, int(np.floor(points[:, 1].min() / cell)) - 1
    c1, r1 = int(np.ceil(points[:, 0].max() / cell)) + 1, int(np.ceil(points[:, 1].max() / cell)) + 1
    w, h = (c1 - c0) * SAMPLES, (r1 - r0) * SAMPLES
    image = np.zeros((h, w), np.uint8)
    unit = cell / SAMPLES
    polygons = [np.round(np.column_stack([(np.array(p)[:, 0] - c0 * cell) / unit, h - (np.array(p)[:, 1] - r0 * cell) / unit]) * 8).astype(np.int32) for p in pen.polygons]
    cv2.fillPoly(image, polygons, 1, shift=3)
    if threshold is None:
        line = skeletonize(image > 0)
        return line.reshape(h // SAMPLES, SAMPLES, w // SAMPLES, SAMPLES).any(axis=(1, 3)), c0, r0
    coverage = image.reshape(h // SAMPLES, SAMPLES, w // SAMPLES, SAMPLES).mean(axis=(1, 3))
    return coverage > threshold, c0, r0


def squares(cells, c0, r0, size):
    path = pathops.Path()
    pen = path.getPen()
    rows = cells.shape[0]
    for i in range(rows):
        y = (r0 + rows - 1 - i) * size
        row = cells[i]
        j = 0
        while j < len(row):
            if not row[j]:
                j += 1
                continue
            k = j
            while k < len(row) and row[k]:
                k += 1
            x0, x1 = (c0 + j) * size, (c0 + k) * size
            pen.moveTo((x0, y))
            pen.lineTo((x0, y + size))
            pen.lineTo((x1, y + size))
            pen.lineTo((x1, y))
            pen.closePath()
            j = k
    path.simplify(fix_winding=True)
    return path


def dots(cells, c0, r0, size):
    path = pathops.Path()
    pen = path.getPen()
    rows = cells.shape[0]
    r, k = size * 0.42, 0.5523
    for i, j in zip(*np.nonzero(cells)):
        cx, cy = (c0 + j + 0.5) * size, (r0 + rows - 1 - i + 0.5) * size
        pen.moveTo((cx + r, cy))
        pen.curveTo((cx + r, cy + k * r), (cx + k * r, cy + r), (cx, cy + r))
        pen.curveTo((cx - k * r, cy + r), (cx - r, cy + k * r), (cx - r, cy))
        pen.curveTo((cx - r, cy - k * r), (cx - k * r, cy - r), (cx, cy - r))
        pen.curveTo((cx + k * r, cy - r), (cx + r, cy - k * r), (cx + r, cy))
        pen.closePath()
    return path


# ---------- the font

def build(style, base_path, out):
    family, how, size, threshold = STYLES[style]
    base = TTFont(base_path)
    glyph_set = base.getGlyphSet()
    order = base.getGlyphOrder()
    charstrings, metrics, kept = {}, {}, 0
    for name in order:
        advance = base["hmtx"][name][0]
        pen = T2CharStringPen(advance, glyph_set)
        if how in ("square", "chamfer"):
            path = squared(glyph_set, name, size, how == "chamfer")
            if path is None:
                kept += 1
        else:
            got = grid(glyph_set, name, size, threshold)
            path = None if got is None else (dots if how == "dots" else squares)(*got, size)
        if path is None:
            glyph_set[name].draw(pen)
        else:
            path.draw(pen)
        charstrings[name] = pen.getCharString()
        bounds = path.bounds if path is not None else None
        metrics[name] = (advance, int(bounds[0]) if bounds else base["hmtx"][name][1])

    fb = FontBuilder(base["head"].unitsPerEm, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(base.getBestCmap())
    ps = family.replace(" ", "") + "-Regular"
    base_family = base["name"].getBestFamilyName()
    fb.setupCFF(ps, {"FullName": f"{family} Regular", "Notice": f"{family}, redrawn from {base_family} (OFL-1.1)."}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=base["hhea"].ascent, descent=base["hhea"].descent)
    fb.setupNameTable({
        "familyName": family, "styleName": "Regular", "uniqueFontIdentifier": f"{ps};blocky", "version": "Version 1.000",
        "description": f"{family} is {base_family} redrawn by scripts/blocky.py of mathfonts ({style}).",
        "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.", "licenseInfoURL": "https://openfontlicense.org",
    })
    os2 = base["OS/2"]
    fb.setupOS2(sTypoAscender=os2.sTypoAscender, sTypoDescender=os2.sTypoDescender, sTypoLineGap=os2.sTypoLineGap, usWinAscent=os2.usWinAscent,
                usWinDescent=os2.usWinDescent, sxHeight=os2.sxHeight, sCapHeight=os2.sCapHeight, fsType=0)
    fb.setupPost()
    for tag in ("MATH", "GSUB", "GPOS", "GDEF"):  # by glyph name, and the glyph order is the base's
        if tag in base:
            fb.font[tag] = base[tag]
    head = fb.font["head"]
    head.created = head.modified = base["head"].created  # the same base gives the same file
    fb.font.recalcTimestamp = False
    out.parent.mkdir(parents=True, exist_ok=True)
    cffsubr.subroutinize(fb.font)
    fb.font.save(out)
    note = f", {kept} left as the base draws them" if how in ("square", "chamfer") else ""
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"{shown}: {len(order)} glyphs{note}, {out.stat().st_size // 1024} KB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--style", choices=list(STYLES), action="append", help="one style (repeat for more); all five when left out")
    ap.add_argument("--base", default=BASE, type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, help="the file, for one style; fonts/<style>-math/ otherwise")
    args = ap.parse_args()
    styles = args.style or list(STYLES)
    if args.out and len(styles) != 1:
        raise SystemExit("--out needs exactly one --style")
    for style in styles:
        family = STYLES[style][0]
        out = args.out or ROOT / "fonts" / f"{style}-math" / (family.replace(" ", "") + "-Regular.otf")
        build(style, args.base, out)


if __name__ == "__main__":
    main()
