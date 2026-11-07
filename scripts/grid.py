#!/usr/bin/env python3
"""Builds the printable grid for drawing a math font by hand.

Every cell asks for one glyph: a character, a bigger size of a delimiter, or a piece that mathra
stacks to build a tall one. The grid is split in three levels, so that someone can print only the
first. A small grey sample from STIX Two Math shows what each cell is; it sits above the box, so
nobody traces over it.

Needs fontTools and reportlab (pip install fonttools reportlab).

    python3 scripts/grid.py            # writes the large and the compact grid, and a filled example of each, in site/grid/
    python3 scripts/grid.py --layout   # only site/grid/layout.json: every box in order, which the site reads

The example is level 1 filled in with Euler Math, the catalog's handwritten font, to show where
each glyph goes in its box.
"""

import argparse
import json
import unicodedata
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "fonts/stix-two-math/STIXTwoMath-Regular.otf"
EXAMPLE = ROOT / "fonts/euler-math/Euler-Math.otf"
INK = Color(0.08, 0.08, 0.1)

# The Unicode blocks the catalog measures coverage over (src/check.rs, BLOCKS).
BLOCKS = [(0x370, 0x3FF), (0x1D400, 0x1D7FF), (0x2200, 0x22FF), (0x2A00, 0x2AFF), (0x2190, 0x21FF), (0x27F0, 0x297F), (0x27C0, 0x27EF), (0x2980, 0x29FF), (0x2100, 0x214F)]

GUIDE = Color(0.35, 0.6, 0.9)  # light blue: a scanner can drop it
SAMPLE = Color(0.55, 0.55, 0.55)
TEXT = Color(0.25, 0.25, 0.25)

# Letters missing from the Mathematical Alphanumeric block: Unicode has them in Letterlike Symbols.
HOLES = {
    ("ITALIC SMALL", "H"): "ℎ",
    ("SCRIPT CAPITAL", "B"): "ℬ", ("SCRIPT CAPITAL", "E"): "ℰ", ("SCRIPT CAPITAL", "F"): "ℱ", ("SCRIPT CAPITAL", "H"): "ℋ",
    ("SCRIPT CAPITAL", "I"): "ℐ", ("SCRIPT CAPITAL", "L"): "ℒ", ("SCRIPT CAPITAL", "M"): "ℳ", ("SCRIPT CAPITAL", "R"): "ℛ",
    ("FRAKTUR CAPITAL", "C"): "ℭ", ("FRAKTUR CAPITAL", "H"): "ℌ", ("FRAKTUR CAPITAL", "I"): "ℑ", ("FRAKTUR CAPITAL", "R"): "ℜ", ("FRAKTUR CAPITAL", "Z"): "ℨ",
    ("DOUBLE-STRUCK CAPITAL", "C"): "ℂ", ("DOUBLE-STRUCK CAPITAL", "H"): "ℍ", ("DOUBLE-STRUCK CAPITAL", "N"): "ℕ", ("DOUBLE-STRUCK CAPITAL", "P"): "ℙ",
    ("DOUBLE-STRUCK CAPITAL", "Q"): "ℚ", ("DOUBLE-STRUCK CAPITAL", "R"): "ℝ", ("DOUBLE-STRUCK CAPITAL", "Z"): "ℤ",
}
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GREEK = ["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "ZETA", "ETA", "THETA", "IOTA", "KAPPA", "LAMDA", "MU", "NU", "XI", "OMICRON", "PI", "RHO", "SIGMA", "TAU", "UPSILON", "PHI", "CHI", "PSI", "OMEGA"]
DIGITS = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]


def alphabet(style, cases=("CAPITAL", "SMALL")):
    out = []
    for case in cases:
        for letter in UPPER:
            hole = HOLES.get((f"{style} {case}", letter))
            out.append(hole or unicodedata.lookup(f"MATHEMATICAL {style} {case} {letter}"))
    return out


def chars(text):
    return [c for c in text if not c.isspace()]


def level_one():
    italic_greek = [unicodedata.lookup(f"MATHEMATICAL ITALIC SMALL {g}") for g in GREEK]
    italic_greek += [unicodedata.lookup(f"MATHEMATICAL ITALIC {n}") for n in ("EPSILON SYMBOL", "THETA SYMBOL", "PHI SYMBOL", "PI SYMBOL", "RHO SYMBOL", "SMALL FINAL SIGMA")]
    return [
        ("Digits", chars("0123456789"), "normal"),
        ("Upright letters: function names (sin, log) and text", chars(UPPER + UPPER.lower()), "normal"),
        ("Italic letters: variables (x, y, f)", alphabet("ITALIC"), "normal"),
        ("Greek, italic: variables, and the variant forms of epsilon, theta, phi, pi, rho and sigma", italic_greek, "normal"),
        ("Greek capitals that differ from Latin ones", chars("ΓΔΘΛΞΠΣΥΦΨΩ"), "normal"),
        ("Operators and relations", chars("+−±∓×÷·∘=≠<>≤≥≈≡∼≃∝∞∂∇′″!/\\∣…⋯⋮⋱,.:;'"), "normal"),
        ("Sets and logic", chars("∈∉⊂⊃⊆⊇∪∩∅∀∃¬∧∨⊕⊗"), "normal"),
        ("Arrows", chars("→←↔⇒⇐⇔↦↑↓"), "normal"),
        ("Letterlike symbols", chars("ℏℓℝℕℤℚℂ"), "normal"),
        ("Delimiters, text size", chars("()[]{}|‖⟨⟩⌊⌋⌈⌉"), "normal"),
        ("Big operators and the radical, text size", chars("∑∏∫∬∮√"), "normal"),
        ("Accents: hat, bar, tilde, dot, two dots, vector", ["̂", "̄", "̃", "̇", "̈", "⃗"], "normal"),
    ]


def level_two():
    upright_greek = [unicodedata.lookup(f"GREEK SMALL LETTER {g}") for g in GREEK]
    return [
        ("Bold letters: vectors and matrices", alphabet("BOLD"), "normal"),
        ("Bold digits", [unicodedata.lookup(f"MATHEMATICAL BOLD DIGIT {d}") for d in DIGITS], "normal"),
        ("Bold italic letters", alphabet("BOLD ITALIC"), "normal"),
        ("Script capitals", alphabet("SCRIPT", ("CAPITAL",)), "normal"),
        ("Fraktur letters", alphabet("FRAKTUR"), "normal"),
        ("Double-struck capitals not in level 1", [c for c in alphabet("DOUBLE-STRUCK", ("CAPITAL",)) if c not in "ℝℕℤℚℂ"], "normal"),
        ("Double-struck digits", [unicodedata.lookup(f"MATHEMATICAL DOUBLE-STRUCK DIGIT {d}") for d in DIGITS], "normal"),
        ("Upright Greek: constants and units", upright_greek, "normal"),
        ("Upright Greek capitals that differ from Latin ones", chars("ΓΔΘΛΞΠΣΥΦΨΩ"), "skip"),
    ]


class CanvasPen(BasePen):
    """Draws a glyph's outline into a reportlab canvas path."""

    def __init__(self, glyphs, path):
        super().__init__(glyphs)
        self.path = path

    def _moveTo(self, p):
        self.path.moveTo(*p)

    def _lineTo(self, p):
        self.path.lineTo(*p)

    def _curveToOne(self, p1, p2, p3):
        self.path.curveTo(*p1, *p2, *p3)

    def _closePath(self):
        self.path.close()


class Reference:
    """STIX Two Math: the grey samples, and the list of sizes and pieces a math font needs."""

    def __init__(self, path):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        variants = self.font["MATH"].table.MathVariants
        self.vertical = dict(zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction))
        self.horizontal = dict(zip(variants.HorizGlyphCoverage.glyphs, variants.HorizGlyphConstruction))

    def name(self, char):
        return self.cmap.get(ord(char))

    def sizes(self, char, picks, horizontal=False, clip=False):
        """Bigger versions of `char` (`picks` index into STIX's list) and the pieces of its assembly, with where each goes."""
        table = self.horizontal if horizontal else self.vertical
        construction = table.get(self.name(char))
        if construction is None:
            return [], []
        records = [r.VariantGlyph for r in construction.MathGlyphVariantRecord]
        if clip:  # a font with fewer sizes: take its biggest instead
            sizes = [records[min(i, len(records) - 1)] for i in picks if len(records) > 1]
        else:
            sizes = [records[i] for i in picks if i < len(records)]
        records = construction.GlyphAssembly.PartRecords if construction.GlyphAssembly else []
        ends = ("left", "right") if horizontal else ("bottom", "top")
        parts = []
        for i, part in enumerate(records):
            if part.PartFlags & 1:
                where = "extender"
            else:
                where = ends[0] if i == 0 else ends[1] if i == len(records) - 1 else "middle"
            parts.append((part.glyph, where))
        return sizes, parts

    def bounds(self, glyph):
        from fontTools.pens.boundsPen import BoundsPen

        pen = BoundsPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        return pen.bounds

    def x_height(self):
        return self.font["OS/2"].sxHeight or 473

    def place(self, canvas, glyph, cx, base, scale):
        """Draws `glyph` centered on `cx`, its origin on the baseline `base`, `scale` points per unit."""
        bounds = self.bounds(glyph)
        if bounds is None:
            return
        x0, _, x1, _ = bounds
        x = cx - (x0 + x1) / 2 * scale
        path = canvas.beginPath()
        self.glyphs[glyph].draw(TransformPen(CanvasPen(self.glyphs, path), (scale, 0, 0, scale, x, base)))
        canvas.drawPath(path, stroke=0, fill=1, fillMode=1)

    def stretch(self, canvas, glyph, x, y, w, h, thickness, vertical):
        """Draws an extender: as long as the box along `vertical` (or across), `thickness` points per unit the other way."""
        x0, y0, x1, y1 = self.bounds(glyph)
        if vertical:
            sx, sy = thickness, h / max(y1 - y0, 1)
            ox, oy = x + (w - (x1 - x0) * sx) / 2 - x0 * sx, y - y0 * sy
        else:
            sx, sy = w / max(x1 - x0, 1), thickness
            ox, oy = x - x0 * sx, y + (h - (y1 - y0) * sy) / 2 - y0 * sy
        path = canvas.beginPath()
        self.glyphs[glyph].draw(TransformPen(CanvasPen(self.glyphs, path), (sx, 0, 0, sy, ox, oy)))
        canvas.drawPath(path, stroke=0, fill=1, fillMode=1)

    def draw(self, canvas, glyph, x, y, size, box=None):
        """Draws `glyph` at `size` points per em with its origin at (x, y), shrunk to fit `box` (w, h) if given."""
        scale = size / 1000
        bounds = self.bounds(glyph)
        if bounds is None:
            return
        x0, y0, x1, y1 = bounds
        if box:
            w, h = box
            scale = min(scale, w / max(x1 - x0, 1), h / max(y1 - y0, 1))
            x += (w - (x1 - x0) * scale) / 2 - x0 * scale
            y += (h - (y1 - y0) * scale) / 2 - y0 * scale
        path = canvas.beginPath()
        self.glyphs[glyph].draw(TransformPen(CanvasPen(self.glyphs, path), (scale, 0, 0, scale, x, y)))
        canvas.drawPath(path, stroke=0, fill=1, fillMode=1)


def size_specs(ref):
    """The glyphs mathra needs to set tall delimiters, display operators and wide accents, as STIX
    Two Math has them, each with what finds the same glyph in another font: the character, the
    direction, and either the size (`picks`, `k`: the k-th of the picked STIX sizes) or the piece's
    place in the assembly (`where`). Returns (tall, wide)."""
    tall, wide, seen = [], [], set()

    def add(cells, glyph, label, **spec):
        if glyph not in seen:
            seen.add(glyph)
            cells.append({"glyph": glyph, "label": label, **spec})

    def construction(cells, char, what, picks, horizontal=False, sizes_label=None, pieces=True):
        sizes, parts = ref.sizes(char, picks, horizontal)
        for k, g in enumerate(sizes):
            add(cells, g, sizes_label(k) if sizes_label else f"{what}, size {k + 2}", char=char, horizontal=horizontal, picks=picks, k=k)
        if pieces:
            for g, where in parts:
                add(cells, g, f"{what}, {where} piece", char=char, horizontal=horizontal, where=where)

    for char, what in [("(", "left parenthesis"), (")", "right parenthesis"), ("[", "left bracket"), ("]", "right bracket"), ("{", "left brace"), ("}", "right brace"), ("⟨", "left angle"), ("⟩", "right angle"), ("|", "bar"), ("‖", "double bar"), ("⌊", "left floor"), ("⌋", "right floor"), ("⌈", "left ceiling"), ("⌉", "right ceiling")]:
        construction(tall, char, what, [3, 6])
    construction(tall, "√", "radical", [2, 3])
    for char, what in [("∑", "sum"), ("∏", "product"), ("∫", "integral"), ("∬", "double integral"), ("∮", "contour integral")]:
        construction(tall, char, what, [1], sizes_label=lambda k, what=what: f"{what}, display")
    for char, what in [("̂", "hat"), ("̃", "tilde")]:
        construction(wide, char, what, [2, 4], True, sizes_label=lambda k, what=what: f"wide {what} {k + 2}", pieces=False)
    for char, what in [("→", "long arrow"), ("⏟", "underbrace"), ("⏞", "overbrace")]:
        construction(wide, char, what, [], True)
    return tall, wide


def size_cells(ref, hand=None):
    """The cells of size_specs, each as (STIX glyph, label, the same glyph in `hand` or None)."""

    def theirs(spec):
        if hand is None:
            return None
        sizes, parts = hand.sizes(spec["char"], spec.get("picks", []), spec["horizontal"], clip=True)
        if "where" in spec:
            return next((g for g, w in parts if w == spec["where"]), None)
        return sizes[spec["k"]] if spec["k"] < len(sizes) else None

    return tuple([(spec["glyph"], spec["label"], theirs(spec)) for spec in cells] for cells in size_specs(ref))


def level_three(listed):
    """Every other symbol in the catalog's coverage list: what STIX Two Math has in those blocks."""
    ref = TTFont(REFERENCE).getBestCmap()
    rest = [chr(c) for a, b in BLOCKS for c in range(a, b + 1) if c in ref and chr(c) not in listed]
    groups = {}
    for c in rest:
        name = unicodedata.name(c, "")
        if name.startswith("MATHEMATICAL"):
            key = "Other math alphabets: sans-serif, monospace, bold Greek…"
        elif 0x370 <= ord(c) <= 0x3FF:
            key = "Other Greek"
        elif "ARROW" in name or "HARPOON" in name:
            key = "Other arrows"
        elif 0x2100 <= ord(c) <= 0x214F:
            key = "Other letterlike symbols"
        else:
            key = "Other operators and symbols"
        groups.setdefault(key, []).append(c)
    order = ["Other math alphabets: sans-serif, monospace, bold Greek…", "Other Greek", "Other letterlike symbols", "Other operators and symbols", "Other arrows"]
    return [(k, groups[k], "normal") for k in order if k in groups]


class Layout:
    """The size of the boxes. The regular grid gives room to draw big; the compact one is closer to
    handwriting size (an x-height of about 4 mm) and fits more on a page."""

    def __init__(self, name, cols, cell, label, tall_cols, tall, wide_cols, wide, small, sample):
        self.name = name
        self.cols, self.cell, self.label = cols, cell, label
        self.tall_cols, self.tall, self.wide_cols, self.wide = tall_cols, tall, wide_cols, wide
        self.small = small  # points, for codes and numbers
        self.sample = sample  # (w, h) of the grey sample in the strip
        self.inset = min(3 * mm, cell / 10)


REGULAR = Layout("regular", 6, 34 * mm, 7 * mm, 4, 62 * mm, 3, 30 * mm, 5.5, (8 * mm, 4.6 * mm))
COMPACT = Layout("compact", 12, 17 * mm, 4 * mm, 8, 34 * mm, 6, 15 * mm, 3.8, (4.5 * mm, 2.8 * mm))


class Grid:
    MARGIN = 12 * mm
    HEADER = 14 * mm

    def __init__(self, path, ref, hand=None, layout=REGULAR):
        self.c = Canvas(str(path), pagesize=A4)
        self.c.setTitle("mathfonts: a filled example of the grid" if hand else "mathfonts: a grid for drawing a math font by hand")
        self.ref = ref
        self.hand = hand  # the font that fills the boxes, in the example
        self.layout = layout
        self.empty = 0
        self.page = 0
        self.level = ""
        self.y = None
        self.number = 0
        self.dirty = False

    def new_page(self):
        if self.dirty:
            self.c.showPage()
        self.dirty = True
        self.page += 1
        w, h = A4
        self.c.setFillColor(black)
        for x, y in [(6 * mm, h - 12 * mm), (w - 12 * mm, h - 12 * mm), (6 * mm, 6 * mm), (w - 12 * mm, 6 * mm)]:
            self.c.rect(x, y, 6 * mm, 6 * mm, stroke=0, fill=1)  # corner marks, to straighten a photo
        self.c.setFont("Helvetica", 8)
        self.c.setFillColor(TEXT)
        kind = "filled example" if self.hand else "grid"
        self.c.drawString(self.MARGIN + 4 * mm, h - 10 * mm, f"mathfonts {kind}  ·  {self.level}")
        self.c.drawRightString(w - self.MARGIN - 4 * mm, h - 10 * mm, f"page {self.page}")
        self.y = h - self.MARGIN - self.HEADER

    def heading(self, text, count, row):
        if self.y - 8 * mm - row < self.MARGIN:
            self.new_page()
        self.c.setFont("Helvetica-Bold", 10)
        self.c.setFillColor(black)
        self.c.drawString(self.MARGIN, self.y - 5 * mm, f"{text}  ({count})")
        self.y -= 8 * mm

    def cells(self, items, columns, height, draw_sample):
        """Lays out `items` in rows of `columns` boxes `height` tall. `draw_sample(item, x, y, w)` labels a box."""
        w, _ = A4
        width = (w - 2 * self.MARGIN) / columns
        for start in range(0, len(items), columns):
            if self.y - height < self.MARGIN:
                self.new_page()
            for i, item in enumerate(items[start : start + columns]):
                self.number += 1
                x = self.MARGIN + i * width
                top = self.y
                self.c.setStrokeColor(black)
                self.c.setLineWidth(0.4)
                self.c.rect(x + 1, top - height, width - 2, height, stroke=1, fill=0)
                label = self.layout.label
                self.c.setLineWidth(0.3)
                self.c.line(x + 1, top - label, x + width - 1, top - label)
                draw_sample(item, x, top, width, label)
                self.c.setFont("Helvetica", self.layout.small)
                self.c.setFillColor(TEXT)
                self.c.drawRightString(x + width - self.layout.inset * 0.8, top - height + self.layout.small * 0.3, f"{self.number:04d}")
            self.y -= height

    def guides(self, x, top, width, height, label):
        """Baseline, x-height and cap-height lines in the drawing area, in STIX's proportions."""
        gap = self.layout.inset * 2 / 3
        area = height - label - 2 * gap
        em = area / 1.25  # room for a descender of a quarter em
        base = top - label - gap - em
        side = self.layout.inset
        self.c.setStrokeColor(GUIDE)
        self.c.setLineWidth(0.35)
        self.c.line(x + side, base, x + width - side, base)
        self.c.setDash(1.5, 1.5)
        for ratio in (0.473, 0.657):
            self.c.line(x + side, base + em * ratio, x + width - side, base + em * ratio)
        self.c.setDash()
        return base, em

    def characters(self, title, items):
        L = self.layout
        height = L.cell

        def sample(char, x, top, width, label):
            name = self.ref.name(char)
            self.c.setFillColor(SAMPLE)
            if name:
                self.ref.draw(self.c, name, x + L.inset, top - label + (label - L.sample[1]) / 2, 12, box=L.sample)
            self.c.setFont("Helvetica", L.small)
            self.c.setFillColor(TEXT)
            self.c.drawRightString(x + width - L.inset * 0.8, top - label / 2 - L.small * 0.35, f"U+{ord(char):04X}")
            base, em = self.guides(x, top, width, height, label)
            if self.hand:
                theirs = self.hand.name(char)
                if theirs and self.hand.bounds(theirs):
                    self.c.setFillColor(INK)
                    self.hand.place(self.c, theirs, x + width / 2, base, em * 0.473 / self.hand.x_height())
                else:
                    self.empty += 1

        self.heading(title, len(items), height)
        self.cells(items, L.cols, height, sample)

    def pieces(self, title, items, wide, note):
        L = self.layout
        columns, height = (L.wide_cols, L.wide) if wide else (L.tall_cols, L.tall)

        def sample(item, x, top, width, label):
            glyph, text, theirs = item
            if self.hand:
                if theirs and self.hand.bounds(theirs):
                    self.c.setFillColor(INK)
                    pad = L.inset
                    bw, bh = width - 2 * pad, height - label - 2 * pad
                    if "extender" in text:
                        # the same stroke weight as the other pieces: one em across the box's short side
                        vertical = bh > bw
                        self.hand.stretch(self.c, theirs, x + pad, top - height + pad, bw, bh, (bw if vertical else bh) / 1000 * (0.9 if vertical else 1.6), vertical)
                    else:
                        self.hand.draw(self.c, theirs, x + pad, top - height + pad, 10_000, box=(bw, bh))
                else:
                    self.empty += 1
            self.c.setFillColor(SAMPLE)
            self.ref.draw(self.c, glyph, x + L.inset, top - label + (label - L.sample[1]) / 2, 12, box=L.sample)
            self.c.setFont("Helvetica", L.small)
            self.c.setFillColor(TEXT)
            short = text if L is REGULAR else text.replace(" piece", "").replace("left ", "l. ").replace("right ", "r. ").replace("parenthesis", "paren.").replace("extender", "ext.")
            self.c.drawRightString(x + width - L.inset * 0.8, top - label / 2 - L.small * 0.35, short)

        self.heading(title, len(items), height)
        self.c.setFont("Helvetica", 7.5)
        self.c.setFillColor(TEXT)
        self.c.drawString(self.MARGIN, self.y - 1 * mm, note)
        self.y -= 4 * mm
        self.cells(items, columns, height, sample)


def size_note(layout):
    if layout is COMPACT:
        return "Compact grid: the boxes are about the size of handwriting, with an x-height near 4 mm."
    return "Regular grid: big boxes, to draw slowly. A compact grid, at handwriting size, is also available."


def cover(c, counts, total, layout):
    w, h = A4
    x = 22 * mm
    y = h - 34 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawString(x, y, "Draw your own math font")
    y -= 12 * mm
    c.setFont("Helvetica", 10.5)
    lines = [
        "Each box on the following pages asks for one glyph. The small grey sample above the box shows",
        "which one; draw yours inside the box, without tracing it. A font made from this grid is all yours:",
        "it has the glyphs you draw and nothing else.",
        "",
        size_note(layout),
        "",
        "The grid comes in three levels. Print only what you want to draw:",
    ]
    for line in lines:
        c.drawString(x, y, line)
        y -= 5.5 * mm
    y -= 2 * mm
    for name, pages, count, what in counts:
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(x + 4 * mm, y, f"{name}: {count} glyphs, pages {pages}")
        y -= 5 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(x + 8 * mm, y, what)
        y -= 7 * mm
    c.setFont("Helvetica", 10.5)
    c.drawString(x, y, f"All three levels: {total} glyphs, as many as STIX Two Math has in the blocks the catalog measures.")
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "How to fill it")
    y -= 7 * mm
    c.setFont("Helvetica", 10.5)
    tips = [
        "Print at 100% (no \"fit to page\"), on white paper.",
        "Use a black pen or marker; a thick line scans better than a thin one.",
        "Sit letters on the solid blue baseline. The dashed lines are x-height and cap height.",
        "Stay inside the box. Leave the black squares in the corners: they straighten the photo.",
        "Pieces (in level 1) are parts mathra stacks to build a tall delimiter: draw them so that",
        "    they join when stacked, with the stroke touching the top and bottom of the box.",
        "Want chalk? Draw with chalk on dark paper and say so: the photo gets inverted.",
        "Then photograph or scan every page, flat and well lit.",
    ]
    for tip in tips:
        c.drawString(x, y, ("•  " if not tip.startswith("    ") else "   ") + tip.strip())
        y -= 6 * mm
    c.showPage()


def example_cover(c, pages, empty, layout):
    w, h = A4
    x = 22 * mm
    y = h - 34 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawString(x, y, "A filled example")
    y -= 12 * mm
    c.setFont("Helvetica", 10.5)
    lines = [
        "These are the pages of level 1 of the grid, filled in as someone drawing a font would fill them.",
        "The glyphs come from Euler Math, Hermann Zapf's handwritten math font (SIL Open Font License),",
        f"which is in the catalog. Pages {pages}.",
        "",
        size_note(layout),
        "",
        "What to look at:",
        "•  letters sit on the solid blue baseline; small letters reach the lower dashed line (x-height),",
        "   capitals and digits the upper one (cap height); g, p, y go below the baseline;",
        "•  every glyph is drawn in the area under the sample strip, never over the grey sample;",
        "•  sizes and pieces of tall delimiters fill their whole box, so that pieces join when stacked.",
    ]
    if empty:
        lines += ["", f"{empty} boxes are empty: Euler Math does not have those glyphs."]
    for line in lines:
        c.drawString(x, y, line)
        y -= 5.5 * mm
    c.showPage()


def layout():
    """Every box of the grid, in order, for the site's page of every glyph of a font: the levels,
    their sections with each character and its Unicode name, and the sizes and pieces."""
    one = level_one()
    two = [s for s in level_two() if s[2] != "skip"]
    listed = {c for _, items, _ in one + two for c in items}
    tall, wide = size_specs(Reference(REFERENCE))

    def sections(level):
        return [{"title": title, "chars": [[c, unicodedata.name(c, "")] for c in items]} for title, items, _ in level]

    return {
        "levels": [
            {"name": "Level 1, the essentials", "sections": sections(one), "tall": tall, "wide": wide},
            {"name": "Level 2, the math alphabets", "sections": sections(two)},
            {"name": "Level 3, everything else", "sections": sections(level_three(listed))},
        ]
    }


LAYOUT = ROOT / "site/grid/layout.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "site/grid/mathfonts-grid.pdf"))
    parser.add_argument("--layout", action="store_true", help=f"only write {LAYOUT.relative_to(ROOT)}, the list of boxes the site reads")
    args = parser.parse_args()
    LAYOUT.write_text(json.dumps(layout(), ensure_ascii=False, separators=(",", ":")) + "\n")
    if args.layout:
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out, REGULAR)
    build(out.with_name(out.stem + "-compact.pdf"), COMPACT)


def build(out, layout):
    ref = Reference(REFERENCE)

    one = level_one()
    two = [s for s in level_two() if s[2] != "skip"]
    listed = {c for _, items, _ in one + two for c in items}
    three = level_three(listed)
    tall, wide = size_cells(ref)

    # A first pass counts pages, so that the cover can say where each level starts.
    plans = [
        ("Level 1, the essentials", one, (tall, wide), "Letters, digits, Greek, the usual symbols, and the sizes and pieces of tall delimiters."),
        ("Level 2, the math alphabets", two, None, "Bold, script, Fraktur and double-struck letters, and upright Greek."),
        ("Level 3, everything else", three, None, "The rarer operators, arrows and alphabets."),
    ]

    def render(path, counts):
        grid = Grid(path, ref, layout=layout)
        if counts:
            cover(grid.c, counts, sum(n for _, _, n, _ in counts), layout)
            grid.page = 1
        pages = []
        for name, sections, extra, _ in plans:
            grid.level = name
            grid.new_page()
            first = grid.page
            count = 0
            for title, items, _ in sections:
                grid.characters(title, items)
                count += len(items)
            if extra:
                t, w = extra
                grid.pieces("Sizes and pieces of tall delimiters, display operators", t, False, "Draw each one as tall as its box. Pieces are drawn separately and stacked by mathra.")
                grid.pieces("Wide accents and pieces of long arrows and braces", w, True, "Draw each one as wide as its box.")
                count += len(t) + len(w)
            pages.append((name, f"{first}–{grid.page}", count))
        grid.c.save()
        return pages

    pages = render(out, None)
    counts = [(name, span, n, what) for (name, span, n), (_, _, _, what) in zip(pages, plans)]
    # The real document has the cover first, so every page moves one forward.
    counts = [(name, "–".join(str(int(p) + 1) for p in span.split("–")), n, what) for name, span, n, what in counts]
    render(out, counts)
    for name, span, n, _ in counts:
        print(f"{layout.name}, {name}: {n} glyphs, pages {span}")
    print(f"total: {sum(n for _, _, n, _ in counts)} glyphs -> {out}")

    # The example: level 1 filled in with Euler Math.
    hand = Reference(EXAMPLE)
    tall, wide = size_cells(ref, hand)
    example = out.with_name(out.stem + "-example.pdf")

    def filled(cover_args):
        grid = Grid(example, ref, hand, layout)
        if cover_args:
            example_cover(grid.c, *cover_args, layout)
            grid.page = 1
        grid.level = "Level 1, the essentials"
        grid.new_page()
        first = grid.page
        for title, items, _ in one:
            grid.characters(title, items)
        grid.pieces("Sizes and pieces of tall delimiters, display operators", tall, False, "Each one fills its box. Pieces are drawn separately and stacked by mathra.")
        grid.pieces("Wide accents and pieces of long arrows and braces", wide, True, "Each one fills the width of its box.")
        last = grid.page
        grid.c.save()
        return f"{first + 1}–{last + 1}" if cover_args is None else None, grid.empty

    span, empty = filled(None)
    filled((span, empty))
    print(f"example: level 1 filled with Euler Math, {empty} empty boxes -> {example}")



if __name__ == "__main__":
    main()
