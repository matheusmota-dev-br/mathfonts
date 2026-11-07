#!/usr/bin/env python3
"""Draws a math font in chalk: every outline of a base font gets a rough edge and the dry streaks
chalk leaves on a board, and the MATH table, the widths and the kerning stay as the base has them.

    scripts/chalk.py                        Fira Math -> fonts/lousa-math/LousaMath-Regular.otf
    scripts/chalk.py --base FILE --out FILE --name "Some Math"

The same seed gives the same font, byte for byte. Needs fontTools, numpy, skia-pathops and cffsubr.
"""

from __future__ import annotations

import argparse
import math
import pathlib

import cffsubr
import numpy as np
import pathops
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent

# all in font units, 1000 to the em
STEP = 14.0  # the outline is cut into segments this long before it is roughened
BOLD = 7.0  # chalk lays down a wider line than a pen: every edge moves out this far
ROUGH = 7.0  # how far the edge wanders over a long wave
GRIT = 3.0  # and over a short one
STREAK_ANGLE = math.radians(-10)  # the chalk is dragged slightly downhill, left to right
STREAKS = 1 / 2000  # streaks per unit of the glyph's box area
SPECKS = 1 / 5000  # round specks of board showing through, per unit of area
JOIN = 40.0  # the ends of a delimiter's pieces keep their outline, so the pieces join seamlessly


# ---------------------------------------------------------------- outlines as polygons


def cubic(p0, p1, p2, p3):
    length = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    n = max(2, math.ceil(length / STEP))
    t = np.linspace(0, 1, n + 1)[1:, None]
    p0, p1, p2, p3 = (np.array(p, float) for p in (p0, p1, p2, p3))
    u = 1 - t
    return u**3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t**3 * p3


def line(p0, p1):
    n = max(1, math.ceil(math.dist(p0, p1) / STEP))
    t = np.linspace(0, 1, n + 1)[1:, None]
    return (1 - t) * np.array(p0, float) + t * np.array(p1, float)


def polygons(recording):
    """The contours of a recorded outline, each as an (n, 2) array of points, closed implicitly."""
    out, current, start, last = [], [], None, None
    for op, args in recording:
        if op == "moveTo":
            start = last = args[0]
            current = [np.array([start], float)]
        elif op == "lineTo":
            current.append(line(last, args[0]))
            last = args[0]
        elif op == "curveTo":
            current.append(cubic(last, *args))
            last = args[-1]
        elif op == "qCurveTo":
            *offs, end = args
            pts = [np.array(p, float) for p in (last, *offs, end)]
            for i in range(1, len(pts) - 1):
                a = pts[0] if i == 1 else (pts[i - 1] + pts[i]) / 2
                c = pts[-1] if i == len(pts) - 2 else (pts[i] + pts[i + 1]) / 2
                b = pts[i]
                current.append(cubic(a, a + 2 / 3 * (b - a), c + 2 / 3 * (b - c), c))
            last = end
        elif op in ("closePath", "endPath"):
            if current:
                if math.dist(last, start) > 1e-6:
                    current.append(line(last, start))
                poly = np.concatenate(current)
                if np.allclose(poly[0], poly[-1]):
                    poly = poly[:-1]
                if len(poly) >= 3:
                    out.append(poly)
            current = []
    return out


def simplified(poly, tolerance=1.4):
    """The polygon with the points that bend it less than `tolerance` dropped (Douglas-Peucker)."""
    if len(poly) < 8:
        return poly
    # split the closed ring at its two farthest points and simplify each half
    far = int(np.argmax(np.linalg.norm(poly - poly[0], axis=1)))
    halves = [poly[: far + 1], np.vstack([poly[far:], poly[:1]])]
    out = []
    for half in halves:
        keep = np.zeros(len(half), bool)
        keep[0] = keep[-1] = True
        stack = [(0, len(half) - 1)]
        while stack:
            a, b = stack.pop()
            if b - a < 2:
                continue
            d = half[b] - half[a]
            seg = half[a + 1 : b] - half[a]
            norm = math.hypot(*d)
            dist = np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / norm if norm > 1e-9 else np.linalg.norm(seg, axis=1)
            i = int(np.argmax(dist))
            if dist[i] > tolerance:
                keep[a + 1 + i] = True
                stack += [(a, a + 1 + i), (a + 1 + i, b)]
        out.append(half[keep][:-1])
    return np.vstack(out)


def to_path(polys):
    path = pathops.Path()
    pen = path.getPen()
    for poly in polys:
        pen.moveTo(tuple(poly[0]))
        for p in poly[1:]:
            pen.lineTo(tuple(p))
        pen.closePath()
    return path


# ---------------------------------------------------------------- the chalk


def periodic_noise(rng, n, wavelength):
    """Smooth noise in [-1, 1] at n points spaced STEP apart, closing on itself."""
    knots = max(3, round(n * STEP / wavelength))
    values = rng.uniform(-1, 1, knots)
    s = np.arange(n) * knots / n
    i = np.floor(s).astype(int)
    f = s - i
    f = f * f * (3 - 2 * f)
    return values[i % knots] * (1 - f) + values[(i + 1) % knots] * f


def roughen(poly, rng, frozen):
    """Moves each point along the outline's normal: out by BOLD, and by noise where not frozen.

    In a font the ink is on the left of every contour, so the right-hand normal points out of
    the ink for outer contours and holes alike."""
    n = len(poly)
    noise = ROUGH * periodic_noise(rng, n, 80) + GRIT * periodic_noise(rng, n, 18)
    shift = BOLD + noise * ~frozen
    tangent = np.roll(poly, -1, axis=0) - np.roll(poly, 1, axis=0)
    length = np.linalg.norm(tangent, axis=1, keepdims=True)
    normal = np.stack([tangent[:, 1], -tangent[:, 0]], axis=1) / np.maximum(length, 1e-9)
    return poly + normal * shift[:, None]


def ellipse(center, length, width, angle, k):
    t = np.linspace(0, 2 * math.pi, k, endpoint=False)
    x = length / 2 * np.cos(t)
    y = width / 2 * np.sin(t)
    c, s = math.cos(angle), math.sin(angle)
    return np.stack([center[0] + c * x - s * y, center[1] + s * x + c * y], axis=1)


def library(seed):
    """A fixed set of streak and speck shapes in whole units, centred on the origin. Every glyph
    draws its holes from it, so a hole inside the stroke is the same run of bytes wherever it is,
    and the CFF subroutines store each shape once."""
    rng = np.random.default_rng([seed, 7])
    streaks = [
        np.round(ellipse((0, 0), rng.uniform(16, 70), rng.uniform(2.5, 7.5), STREAK_ANGLE + rng.normal(0, 0.1), 8))
        for _ in range(48)
    ]
    specks = []
    for _ in range(16):
        r = rng.uniform(2.5, 6)
        specks.append(np.round(ellipse((0, 0), 2 * r, 2 * r * rng.uniform(0.6, 1), rng.uniform(0, math.pi), 6)))
    return streaks, specks


def texture(lo, hi, rng, avoid, shapes):
    """Where the board shows through, over the box lo..hi: (hole, radius) pairs."""
    streaks, specks = shapes
    area = float(np.prod(hi - lo))
    out = []
    for count, pool in ((rng.poisson(area * STREAKS), streaks), (rng.poisson(area * SPECKS), specks)):
        for _ in range(count):
            center = np.round(rng.uniform(lo, hi))
            if not avoid(center):
                shape = pool[rng.integers(len(pool))]
                out.append((shape + center, center, float(np.max(np.linalg.norm(shape, axis=1)))))
    return out


def signed_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def chalk(recording, rng, axis, shapes):
    """The chalk outline of a glyph, as contours to draw; axis is set for a delimiter's piece.

    A hole that crosses the edge is cut out of the ink. A hole wholly inside the stroke, clear of
    every other hole, is drawn as a contour of its own against the ink's direction instead, so its
    bytes repeat from glyph to glyph."""
    polys = polygons(recording)
    if not polys:
        return []
    allpts = np.concatenate(polys)
    lo, hi = allpts.min(axis=0), allpts.max(axis=0)
    if axis is None:
        frozen_of = lambda p: np.zeros(len(p), bool)  # noqa: E731
        avoid = lambda c: False  # noqa: E731
    else:
        a, b = lo[axis], hi[axis]
        frozen_of = lambda p: (p[:, axis] < a + JOIN) | (p[:, axis] > b - JOIN)  # noqa: E731
        avoid = lambda c: c[axis] < a + JOIN + 10 or c[axis] > b - JOIN - 10  # noqa: E731
    ink = to_path([simplified(roughen(p, rng, frozen_of(p))) for p in polys])
    ink.simplify(fix_winding=True)
    holes = texture(lo - BOLD, hi + BOLD, rng, avoid, shapes)
    inside, cut = [], []
    if holes:
        centers = np.array([c for _, c, _ in holes])
        radii = np.array([r for _, _, r in holes])
        gap = np.linalg.norm(centers[:, None] - centers[None], axis=2) - radii[:, None] - radii[None]
        np.fill_diagonal(gap, np.inf)
        alone = gap.min(axis=1) > 2
    for i, (hole, center, radius) in enumerate(holes):
        if alone[i] and all(ink.contains(tuple(q)) for q in ellipse(center, 2 * radius + 4, 2 * radius + 4, 0, 12)):
            inside.append(hole)
        elif any(ink.contains(tuple(q)) for q in hole):
            cut.append(hole)
    if cut:
        board = to_path(cut)
        board.simplify(fix_winding=True)
        ink = pathops.op(ink, board, pathops.PathOp.DIFFERENCE, fix_winding=True)
    rec = RecordingPen()
    ink.draw(rec)
    contours = [np.array(c) for c in split(rec.value)]
    if inside and contours:
        outer = max(contours, key=lambda c: abs(signed_area(c)))
        sign = signed_area(outer) > 0
        contours += [h if (signed_area(h) > 0) != sign else h[::-1] for h in inside]
    return contours


def split(recording):
    """The contours of a recording made only of lines, as lists of points."""
    out, current = [], []
    for op, args in recording:
        if op == "moveTo":
            current = [args[0]]
        elif op == "lineTo":
            current.append(args[0])
        elif op in ("curveTo", "qCurveTo"):
            current.extend(args)
        elif op in ("closePath", "endPath"):
            if len(current) >= 3:
                out.append(current)
            current = []
    return out


# ---------------------------------------------------------------- the font


def assembly_parts(font):
    """Glyphs that are pieces of a tall delimiter or a wide accent, and the axis they join on."""
    parts = {}
    variants = font["MATH"].table.MathVariants
    for coverage, constructions, axis in (
        (variants.VertGlyphCoverage, variants.VertGlyphConstruction, 1),
        (variants.HorizGlyphCoverage, variants.HorizGlyphConstruction, 0),
    ):
        if coverage:
            for construction in constructions:
                if construction.GlyphAssembly:
                    for part in construction.GlyphAssembly.PartRecords:
                        parts[part.glyph] = axis
    return parts


def rename(font, family, base_family):
    ps = family.replace(" ", "") + "-Regular"
    table = font["name"]
    for record in list(table.names):
        pid, eid, lid = record.platformID, record.platEncID, record.langID
        if record.nameID in (1, 16, 21):
            table.setName(family, record.nameID, pid, eid, lid)
        elif record.nameID == 4:
            table.setName(family + " Regular", 4, pid, eid, lid)
        elif record.nameID == 3:
            table.setName(f"{ps};chalk", 3, pid, eid, lid)
        elif record.nameID == 6:
            table.setName(ps, 6, pid, eid, lid)
        elif record.nameID == 5:
            base_version = record.toUnicode().split(";")[0].removeprefix("Version ").strip()
            table.setName(f"Version 1.000; chalk from {base_family} {base_version}", 5, pid, eid, lid)
        elif record.nameID in (8, 9, 11, 12):  # the base's vendor and designer, and their URLs
            table.removeNames(nameID=record.nameID)
    table.setName(f"{family} is {base_family} redrawn in chalk by scripts/chalk.py of mathfonts.", 10, 3, 1, 0x409)
    font["head"].fontRevision = 1.0
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    top = cff.topDictIndex[0]
    top.FullName = family
    top.FamilyName = family
    top.version = "1.000"
    if hasattr(top, "Notice"):
        top.Notice = f"{family}, drawn in chalk from {base_family} (OFL-1.1)."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=ROOT / "fonts/fira-math/FiraMath-Regular.otf", type=pathlib.Path)
    ap.add_argument("--out", default=ROOT / "fonts/lousa-math/LousaMath-Regular.otf", type=pathlib.Path)
    ap.add_argument("--name", default="Lousa Math")
    ap.add_argument("--seed", default=1814, type=int)
    args = ap.parse_args()

    font = TTFont(args.base, recalcTimestamp=False)  # the same seed gives the same file
    if "CFF " not in font:
        raise SystemExit("the base must be a CFF font (.otf)")
    base_family = font["name"].getBestFamilyName()
    cff = font["CFF "].cff
    cff.desubroutinize()
    top = cff.topDictIndex[0]
    glyph_set = font.getGlyphSet()
    parts = assembly_parts(font)
    hmtx = font["hmtx"]
    shapes = library(args.seed)

    for name in font.getGlyphOrder():
        rng = np.random.default_rng([args.seed, *name.encode()])
        recording = RecordingPen()
        glyph_set[name].draw(recording)
        width = hmtx[name][0]
        pen = T2CharStringPen(width, glyph_set)
        contours = chalk(recording.value, rng, parts.get(name), shapes)
        for contour in contours:
            pts = np.round(contour).astype(int)
            pts = pts[np.any(pts != np.roll(pts, 1, axis=0), axis=1)]
            if len(pts) < 3:
                continue
            pen.moveTo(tuple(map(int, pts[0])))
            for q in pts[1:]:
                pen.lineTo(tuple(map(int, q)))
            pen.closePath()
        if contours:
            hmtx[name] = (width, int(math.floor(min(c[:, 0].min() for c in contours))))
        top.CharStrings[name] = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)

    rename(font, args.name, base_family)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cffsubr.subroutinize(font)
    font.save(args.out)
    shown = args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out
    print(f"{shown}: {len(font.getGlyphOrder())} glyphs, {args.out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
