#!/usr/bin/env python3
"""Slants a math font's variables much further than its italic, as in old printed books, and keeps
the MATH table as the base has it.

What leans: the italic alphabets (Latin and Greek), the italic h, the gradient and the partial
derivative, about the baseline; and the integrals in every size, about the math axis, so that they
stay centred on it. Function names, digits, operators and delimiters stay upright. The integrals'
assemblies are dropped, since slanted pieces no longer meet when they are stacked: an integral taller
than the biggest size uses that size.

    scripts/slant.py                          Garamond-Math, 18 degrees -> fonts/inclinata-math/InclinataMath-Regular.otf
    scripts/slant.py --base FILE --angle 24 --out FILE --name "Some Math"

The same arguments give the same font, byte for byte. Needs fontTools and cffsubr.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import unicodedata

import cffsubr
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

ROOT = pathlib.Path(__file__).resolve().parent.parent

# the gradient and the partial derivative stand with the variables, and lean with them
WITH_THE_VARIABLES = (0x210E, 0x2207, 0x2202)
# room between an integral's foot and its lower limit, in font units per 1000 to the em
LIMIT_ROOM = 30


def rename(font, family, base_family, angle):
    """The new family's names, and a description that says where it comes from."""
    ps = family.replace(" ", "") + "-Regular"
    table = font["name"]
    for record in list(table.names):
        pid, eid, lid = record.platformID, record.platEncID, record.langID
        if record.nameID in (1, 16, 21):
            table.setName(family, record.nameID, pid, eid, lid)
        elif record.nameID == 4:
            table.setName(family + " Regular", 4, pid, eid, lid)
        elif record.nameID == 3:
            table.setName(f"{ps};slant", 3, pid, eid, lid)
        elif record.nameID == 6:
            table.setName(ps, 6, pid, eid, lid)
        elif record.nameID == 5:
            base_version = record.toUnicode().split(";")[0].removeprefix("Version ").strip()
            table.setName(f"Version 1.000; slanted from {base_family} {base_version}", 5, pid, eid, lid)
        elif record.nameID in (8, 9, 11, 12):  # the base's vendor and designer, and their URLs
            table.removeNames(nameID=record.nameID)
    table.setName(f"{family} is {base_family} with its variables and integrals slanted {angle:g} degrees more, by scripts/slant.py of mathfonts.", 10, 3, 1, 0x409)
    font["head"].fontRevision = 1.0
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    top = cff.topDictIndex[0]
    top.FullName = family
    top.FamilyName = family
    top.version = "1.000"
    if hasattr(top, "Notice"):
        top.Notice = f"{family}, slanted from {base_family} (OFL-1.1)."


def bounds(glyph_set, name):
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def redraw(top, cff, glyph_set, name, advance, matrix):
    pen = T2CharStringPen(advance, glyph_set)
    glyph_set[name].draw(TransformPen(pen, matrix))
    top.CharStrings[name] = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=ROOT / "fonts/garamond-math/Garamond-Math.otf", type=pathlib.Path)
    ap.add_argument("--out", default=ROOT / "fonts/inclinata-math/InclinataMath-Regular.otf", type=pathlib.Path)
    ap.add_argument("--name", default="Inclinata Math")
    ap.add_argument("--angle", default=18.0, type=float, help="degrees added to the slant of the italic")
    args = ap.parse_args()

    font = TTFont(args.base, recalcTimestamp=False)
    if "CFF " not in font:
        raise SystemExit("the base must be a CFF font (.otf)")
    base_family = font["name"].getBestFamilyName()
    cff = font["CFF "].cff
    cff.desubroutinize()
    top = cff.topDictIndex[0]
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    table = font["MATH"].table
    upm = font["head"].unitsPerEm
    t = math.tan(math.radians(args.angle))
    x_height = font["OS/2"].sxHeight
    axis = table.MathConstants.AxisHeight.Value

    italics = table.MathGlyphInfo.MathItalicsCorrectionInfo
    correction = {g: v.Value for g, v in zip(italics.Coverage.glyphs, italics.ItalicsCorrection)} if italics else {}
    accents = table.MathGlyphInfo.MathTopAccentAttachment
    attachment = dict(zip(accents.TopAccentCoverage.glyphs, accents.TopAccentAttachment)) if accents else {}

    # the variables: their glyphs and every alternate of them (script sizes and the like)
    variables = {g for c, g in cmap.items() if "ITALIC" in unicodedata.name(chr(c), "") or c in WITH_THE_VARIABLES}
    leaning = [g for g in font.getGlyphOrder() if g in variables or g.split(".")[0] in variables]
    shift = -t * x_height / 2  # keeps the middle of the x-height where it was
    for g in leaning:
        box = bounds(glyph_set, g)
        if not box:
            continue
        width = hmtx[g][0]
        redraw(top, cff, glyph_set, g, width, (1, 0, t, 1, shift, 0))
        x0, y0, x1, y1 = box
        left = min(x0 + t * y0, x0 + t * y1) + shift
        right = max(x1 + t * y0, x1 + t * y1) + shift
        hmtx[g] = (width, math.floor(left))
        correction[g] = max(correction.get(g, 0), round(right - width))
        if g in attachment:
            attachment[g].Value = round(attachment[g].Value + t * y1 + shift)

    # the integrals, in every size
    variants = table.MathVariants
    vertical = dict(zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction))
    integrals = set()
    for c, g in cmap.items():
        name = unicodedata.name(chr(c), "")
        if "INTEGRAL" in name or "INTEGRATION" in name:
            integrals.add(g)
            construction = vertical.get(g)
            if construction:
                integrals.update(r.VariantGlyph for r in construction.MathGlyphVariantRecord)
                construction.GlyphAssembly = None
    for g in sorted(integrals):
        box = bounds(glyph_set, g)
        if not box:
            continue
        width = hmtx[g][0]
        x0, y0, x1, y1 = box
        lean = lambda x, y: x + t * (y - axis)  # noqa: E731
        left = min(lean(x0, y0), lean(x0, y1))
        dx = max(0, x0 - left)  # the foot leaned left: back to the old side bearing
        # mathra sets an integral's upper limit at its advance and pulls the lower one left by the
        # italic correction: the advance follows the head, which leaned right, and the correction
        # grows by how far the foot went left of the head
        advance = round(width + dx + t * (y1 - axis))
        redraw(top, cff, glyph_set, g, advance, (1, 0, t, 1, dx - t * axis, 0))
        hmtx[g] = (advance, math.floor(left + dx))
        correction[g] = max(0, round(correction.get(g, 0) + t * (y1 - y0) - LIMIT_ROOM * upm / 1000))

    # the italic corrections again, in glyph order, as a coverage needs
    order = {g: i for i, g in enumerate(font.getGlyphOrder())}
    glyphs = sorted((g for g in correction if g in order), key=order.get)
    if italics is None:
        italics = otTables.MathItalicsCorrectionInfo()
        italics.Coverage = otTables.Coverage()
        table.MathGlyphInfo.MathItalicsCorrectionInfo = italics
    italics.Coverage.glyphs = glyphs
    records = []
    for g in glyphs:
        record = otTables.MathValueRecord()
        record.Value, record.DeviceTable = correction[g], None
        records.append(record)
    italics.ItalicsCorrection = records
    italics.ItalicsCorrectionCount = len(records)

    rename(font, args.name, base_family, args.angle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cffsubr.subroutinize(font)
    font.save(args.out)
    shown = args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out
    print(f"{shown}: {len(leaning)} glyphs of variables and {len(integrals)} of integrals slanted {args.angle:g} degrees more, {args.out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
