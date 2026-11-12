#!/usr/bin/env python3
"""Grows leaves on a math font: along the outside of every stroke, a short stalk comes out of the
ink and opens into a leaf with its midrib, turned upward, as a vine grows toward the light. The
glyph order, the widths, the cmap, the MATH table, and the substitutions and kerning stay as the
base has them.

A leaf grows only where it has room: clear of the glyph's own ink and of the other leaves, inside
the glyph's advance, and not out of the ends of a delimiter's pieces, so the pieces still join.
Dots, accents and other small glyphs stay bare.

    scripts/leaves.py                        Noto Sans Math -> fonts/hera-math/HeraMath-Regular.otf
    scripts/leaves.py --base FILE --out FILE --name "Some Math"

The same seed gives the same font, byte for byte. Needs fontTools, numpy, skia-pathops and cffsubr.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys
import unicodedata

import cffsubr
import numpy as np
import pathops
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

sys.dont_write_bytecode = True  # chalk is imported from this folder; leave no __pycache__ in it
from chalk import assembly_parts, polygons  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# all in font units, 1000 to the em
LEAF = (150.0, 210.0)  # the length of a leaf, from its base to its tip
WIDE = (0.42, 0.52)  # its width, as a share of its length
STALK = (20.0, 40.0)  # how far the stalk carries the leaf out of the stroke
STALK_WIDTH = 14.0
VEIN = 8.0  # the midrib, cut out of the leaf, at its widest
SPACING = 380.0  # along the outline, between the places a leaf may grow
GROW = 0.8  # the chance that a leaf grows at each of them
UP = 0.6  # how strongly leaves turn upward
SMALL = 300.0  # a glyph whose ink is smaller than this, both ways, stays bare
JOIN = 80.0  # the ends of a delimiter's pieces stay bare, so the pieces join seamlessly
ROOM = 45.0  # how far a leaf may reach past the advance on either side
# besides letters and digits: the n-ary operators, the integrals and the radicals
GROWING = set("∑∏∐⋀⋁⋂⋃⨀⨁⨂⨄⨆√∛∜") | {chr(c) for c in range(0x222B, 0x2234)} | {chr(c) for c in range(0x2A0B, 0x2A1D)}


def unit(v):
    n = math.hypot(*v)
    return np.array(v, float) / n if n > 1e-9 else None


def inside_polygon(point, poly):
    x, y = point
    xs, ys = poly[:, 0], poly[:, 1]
    xn, yn = np.roll(xs, -1), np.roll(ys, -1)
    crosses = (ys > y) != (yn > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = xs + (y - ys) * (xn - xs) / (yn - ys)
    return bool(np.count_nonzero(crosses & (x < at)) % 2)


class Leaf:
    """A leaf in the glyph's coordinates: its outline as cubic segments, a few points along its edge
    to test where it reaches, and its midrib."""

    def __init__(self, base, direction, length, width, curl):
        self.base, self.length = base, length
        side = np.array([-direction[1], direction[0]])
        at = lambda x, y: tuple(base + direction * x + side * y)  # noqa: E731
        tip = (length, curl * length)
        self.upper = (at(0, 0), at(0.22 * length, 0.62 * width), at(0.72 * length, 0.50 * width + 0.5 * tip[1]), at(*tip))
        self.lower = (at(*tip), at(0.72 * length, -0.46 * width + 0.5 * tip[1]), at(0.22 * length, -0.58 * width), at(0, 0))
        self.edge = np.array([bezier(c, t) for c in (self.upper, self.lower) for t in np.linspace(0, 1, 9)])
        self.center = np.array(at(0.5 * length, 0.25 * tip[1]))
        rib = []
        for t in np.linspace(0.08, 0.86, 10):
            w = VEIN / 2 * (1 - t) / 0.92
            rib.append((t * length, curl * length * t * t, w))
        self.rib = [at(x, y + w) for x, y, w in rib] + [at(x, y - w) for x, y, w in reversed(rib)]

    def path(self):
        path = pathops.Path()
        pen = path.getPen()
        pen.moveTo(self.upper[0])
        pen.curveTo(*self.upper[1:])
        pen.curveTo(*self.lower[1:])
        pen.closePath()
        rib = pathops.Path()
        pen = rib.getPen()
        pen.moveTo(self.rib[0])
        for p in self.rib[1:]:
            pen.lineTo(p)
        pen.closePath()
        return pathops.op(path, rib, pathops.PathOp.DIFFERENCE, fix_winding=True)


def bezier(c, t):
    p0, p1, p2, p3 = (np.array(p, float) for p in c)
    u = 1 - t
    return u**3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t**3 * p3


def stalk(root, tip):
    d = unit(tip - root)
    n = np.array([-d[1], d[0]]) * STALK_WIDTH / 2
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(tuple(root + n))
    pen.lineTo(tuple(tip + n * 0.8))
    pen.lineTo(tuple(tip - n * 0.8))
    pen.lineTo(tuple(root - n))
    pen.closePath()
    return path


def sprouts(polys, rng):
    """Places along the outlines where a leaf may grow: (point, tangent, contour)."""
    out = []
    for poly in polys:
        seg = np.linalg.norm(np.roll(poly, -1, axis=0) - poly, axis=1)
        arc = np.concatenate([[0], np.cumsum(seg)])
        total = arc[-1]
        s = rng.uniform(0, SPACING)
        while s < total:
            i = min(int(np.searchsorted(arc, s, side="right")) - 1, len(poly) - 1)
            t = unit(poly[(i + 2) % len(poly)] - poly[i - 2])
            if t is not None:
                out.append((poly[i], t, poly))
            s += SPACING * rng.uniform(0.75, 1.25)
    return out


def grow(ink, polys, rng, advance, axis):
    """The leaves of a glyph whose ink is `ink`, as one path (empty when none fit)."""
    allpts = np.concatenate(polys)
    lo, hi = allpts.min(axis=0), allpts.max(axis=0)
    size = hi - lo
    if max(size) < SMALL:
        return None
    box_lo = np.array([-ROOM, lo[1] - 30])
    box_hi = np.array([advance + ROOM, hi[1] + 50])  # above the glyph a leaf would read as an accent
    if axis is not None:  # a delimiter's piece: nothing past or near its ends along the join
        box_lo[axis], box_hi[axis] = lo[axis] + JOIN, hi[axis] - JOIN
    leaves = []
    for point, tangent, poly in sprouts(polys, rng):
        if rng.random() > GROW:
            continue
        normal = np.array([tangent[1], -tangent[0]])
        if ink.contains(tuple(point + normal * 6)):
            normal = -normal
        if ink.contains(tuple(point + normal * 6)) or inside_polygon(point + normal * 6, poly):
            continue  # a corner, or the inside of a counter
        if normal[1] < -0.35:
            continue  # leaves do not hang from the underside of a stroke
        side = rng.choice((-1.0, 1.0))
        direction = unit(normal + UP * np.array([0.0, 1.0]) + 0.45 * side * tangent)
        length = min(rng.uniform(*LEAF), 0.55 * max(size))
        reach = rng.uniform(*STALK)
        root = point - normal * 8
        tip = point + direction * reach
        leaf = Leaf(tip, direction, length, length * rng.uniform(*WIDE), rng.uniform(-0.12, 0.12) * side)
        pts = np.vstack([leaf.edge, tip])
        if np.any(pts < box_lo) or np.any(pts > box_hi):
            continue
        if axis is not None and (root[axis] < box_lo[axis] or root[axis] > box_hi[axis]):
            continue
        if any(ink.contains(tuple(q)) for q in leaf.edge[2:-2]):
            continue
        if any(math.dist(leaf.center, other.center) < 0.5 * (leaf.length + other.length) * 0.85 for other, _ in leaves):
            continue
        leaves.append((leaf, stalk(root, tip + direction * 6)))
    if not leaves:
        return None
    out = pathops.Path()
    for leaf, stem in leaves:
        out = pathops.op(out, stem, pathops.PathOp.UNION, fix_winding=True)
        out = pathops.op(out, leaf.path(), pathops.PathOp.UNION, fix_winding=True)
    return out


def growing(font):
    """The glyphs leaves grow on: letters, digits, the big operators, integrals and radicals, with
    their alternates and their larger sizes. Operators, relations, arrows, delimiters and
    punctuation stay bare, so a leaf never reads as a mark that changes a symbol."""
    alive = set()
    for code, name in font.getBestCmap().items():
        char = chr(code)
        if unicodedata.category(char)[0] in "LN" or char in GROWING:
            alive.add(name)
    singles = []
    if "GSUB" in font:
        for lookup in font["GSUB"].table.LookupList.Lookup:
            for sub in lookup.SubTable:
                sub = getattr(sub, "ExtSubTable", sub)
                if hasattr(sub, "mapping"):
                    singles.append(sub.mapping)
                elif hasattr(sub, "alternates"):
                    singles.append({k: v for k, vs in sub.alternates.items() for v in vs})
    variants = font["MATH"].table.MathVariants
    for coverage, constructions in (
        (variants.VertGlyphCoverage, variants.VertGlyphConstruction),
        (variants.HorizGlyphCoverage, variants.HorizGlyphConstruction),
    ):
        if coverage:
            more = {}
            for glyph, construction in zip(coverage.glyphs, constructions):
                grown = [v.VariantGlyph for v in construction.MathGlyphVariantRecord or []]
                if construction.GlyphAssembly:
                    grown += [part.glyph for part in construction.GlyphAssembly.PartRecords]
                more[glyph] = grown
            singles.append(more)
    changed = True
    while changed:
        changed = False
        for mapping in singles:
            for source, target in mapping.items():
                for t in target if isinstance(target, list) else [target]:
                    if source in alive and t not in alive:
                        alive.add(t)
                        changed = True
    return alive


def build(base_path, out, family, seed):
    base = TTFont(base_path)
    glyph_set = base.getGlyphSet()
    order = base.getGlyphOrder()
    parts = assembly_parts(base)
    alive = growing(base)
    charstrings, metrics, grown = {}, {}, 0
    for name in order:
        rng = np.random.default_rng([seed, *name.encode()])
        advance = base["hmtx"][name][0]
        recording = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(recording)
        ink = pathops.Path()
        recording.replay(ink.getPen())
        ink.simplify(fix_winding=True)
        polys = polygons(recording.value)
        leaves = grow(ink, polys, rng, advance, parts.get(name)) if polys and name in alive else None
        if leaves is not None:
            ink = pathops.op(ink, leaves, pathops.PathOp.UNION, fix_winding=True)
            grown += 1
        pen = T2CharStringPen(advance, glyph_set)
        ink.draw(pen)
        charstrings[name] = pen.getCharString()
        bounds = ink.bounds if polys else None
        metrics[name] = (advance, math.floor(bounds[0]) if bounds else base["hmtx"][name][1])

    fb = FontBuilder(base["head"].unitsPerEm, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(base.getBestCmap())
    ps = family.replace(" ", "") + "-Regular"
    base_family = base["name"].getBestFamilyName()
    fb.setupCFF(ps, {"FullName": f"{family} Regular", "Notice": f"{family}, leaves grown on {base_family} (OFL-1.1)."}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=base["hhea"].ascent, descent=base["hhea"].descent)
    fb.setupNameTable({
        "familyName": family, "styleName": "Regular", "uniqueFontIdentifier": f"{ps};leaves", "version": "Version 1.000",
        "description": f"{family} is {base_family} with leaves grown on it by scripts/leaves.py of mathfonts.",
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
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"{shown}: {len(order)} glyphs, {grown} with leaves, {out.stat().st_size // 1024} KB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=ROOT / "fonts/noto-sans-math/NotoSansMath-Regular.ttf", type=pathlib.Path)
    ap.add_argument("--out", default=ROOT / "fonts/hera-math/HeraMath-Regular.otf", type=pathlib.Path)
    ap.add_argument("--name", default="Hera Math")
    ap.add_argument("--seed", default=1817, type=int)
    args = ap.parse_args()
    build(args.base, args.out, args.name, args.seed)


if __name__ == "__main__":
    main()
