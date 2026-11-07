//! The page about drawing a math font by hand: the grid to download, and a filled example.
//!
//! The example cells look like the printed grid's: a strip with the grey STIX sample on top, the
//! blue guides below, and in them the glyph as someone would draw it. The "drawn" glyphs come from
//! Euler Math, the catalog's handwritten font, read straight from its outlines.

use std::fmt::Write;
use std::path::Path;

use mathra::font::MathFont;
use ttf_parser::{Face, GlyphId, OutlineBuilder, Rect};

/// Font units of a cell: the sample strip on top, the drawing area below.
const W: f32 = 1000.0;
const STRIP: f32 = 240.0;
const BODY: f32 = 1300.0;
const BASELINE: f32 = STRIP + 860.0;
const X_HEIGHT: f32 = 473.0;
const CAP_HEIGHT: f32 = 657.0;

struct Path2 {
    d: String,
}

impl OutlineBuilder for Path2 {
    fn move_to(&mut self, x: f32, y: f32) {
        let _ = write!(self.d, "M{x} {y}");
    }
    fn line_to(&mut self, x: f32, y: f32) {
        let _ = write!(self.d, "L{x} {y}");
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        let _ = write!(self.d, "Q{x1} {y1} {x} {y}");
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        let _ = write!(self.d, "C{x1} {y1} {x2} {y2} {x} {y}");
    }
    fn close(&mut self) {
        self.d.push('Z');
    }
}

/// A glyph's outline in font units (y up), with its bounding box.
fn outline(face: &Face, glyph: GlyphId) -> Option<(String, Rect)> {
    let mut p = Path2 { d: String::new() };
    let rect = face.outline_glyph(glyph, &mut p)?;
    Some((p.d, rect))
}

fn glyph_of(face: &Face, chars: &[char]) -> Option<GlyphId> {
    chars.iter().find_map(|c| face.glyph_index(*c))
}

/// Places an outline: `scale`, then its origin at (x, y) in the cell, y growing down.
fn place(d: &str, x: f32, y: f32, scale: f32, class: &str) -> String {
    format!(r#"<path class="{class}" transform="translate({x} {y}) scale({scale} {neg})" d="{d}"/>"#, neg = -scale)
}

/// Places an outline so that its box fits (and is centered in) the box `(x, y, w, h)` of the cell.
fn fit(d: &str, r: Rect, x: f32, y: f32, w: f32, h: f32, class: &str) -> String {
    let (gw, gh) = (f32::from(r.x_max - r.x_min).max(1.0), f32::from(r.y_max - r.y_min).max(1.0));
    let s = (w / gw).min(h / gh);
    let ox = x + (w - gw * s) / 2.0 - f32::from(r.x_min) * s;
    let oy = y + (h - gh * s) / 2.0 + f32::from(r.y_max) * s;
    place(d, ox, oy, s, class)
}

struct Fonts<'a> {
    stix: Face<'a>,
    hand: Face<'a>,
}

impl Fonts<'_> {
    /// One cell of the grid: the sample of `chars[0]` in STIX, and `drawn` (SVG) in the drawing area.
    fn cell(&self, chars: &[char], label: &str, body: f32, guides: bool, drawn: &str) -> String {
        let mut s = String::new();
        let h = STRIP + body;
        let _ = write!(s, r#"<svg class="cell" viewBox="-10 -10 {} {}" overflow="visible" role="img" aria-label="{label}">"#, W + 20.0, h + 20.0);
        let _ = write!(s, r#"<rect class="box" x="0" y="0" width="{W}" height="{h}"/><path class="box" d="M0 {STRIP}H{W}"/>"#);
        if let Some((d, r)) = glyph_of(&self.stix, &chars[..1]).and_then(|g| outline(&self.stix, g)) {
            s += &fit(&d, r, 40.0, 40.0, 220.0, STRIP - 80.0, "sample");
        }
        let _ = write!(s, r#"<text class="code" x="{}" y="{}" text-anchor="end">{label}</text>"#, W - 40.0, STRIP - 80.0);
        if guides {
            let _ = write!(s, r#"<path class="guide" d="M60 {BASELINE}H940"/><path class="guide dash" d="M60 {}H940M60 {}H940"/>"#, BASELINE - X_HEIGHT, BASELINE - CAP_HEIGHT);
        }
        s += drawn;
        s += "</svg>";
        s
    }

    /// The handwritten font's scale to the grid: its x-height on the grid's x-height line.
    fn unit(&self) -> f32 {
        self.hand.x_height().filter(|h| *h > 0).map_or(1.0, |h| X_HEIGHT / f32::from(h))
    }

    /// The handwritten glyph for `chars`, sitting on the baseline, `scale` times the size it should have.
    fn written(&self, chars: &[char], scale: f32, dx: f32, dy: f32) -> String {
        let scale = scale * self.unit();
        let Some((d, r)) = glyph_of(&self.hand, chars).and_then(|g| outline(&self.hand, g)) else {
            return String::new();
        };
        let x = W / 2.0 - f32::from(r.x_min + r.x_max) / 2.0 * scale + dx;
        place(&d, x, BASELINE + dy, scale, "ink")
    }

    /// The pieces of the left parenthesis' assembly in the handwritten font, bottom first.
    fn pieces(&self) -> Vec<(String, Rect, bool)> {
        let Some(paren) = self.hand.glyph_index('(') else { return Vec::new() };
        let Some(variants) = self.hand.tables().math.and_then(|m| m.variants) else { return Vec::new() };
        let Some(assembly) = variants.vertical_constructions.get(paren).and_then(|c| c.assembly) else { return Vec::new() };
        assembly.parts.into_iter().filter_map(|p| outline(&self.hand, p.glyph_id).map(|(d, r)| (d, r, p.part_flags.extender()))).collect()
    }
}

fn figure(svg: &str, ok: bool, caption: &str, check: &str, alert: &str) -> String {
    format!(
        r#"<figure class="example {cls}">{svg}<figcaption>{mark}<span>{caption}</span></figcaption></figure>"#,
        cls = if ok { "ok" } else { "bad" },
        mark = if ok { check } else { alert }
    )
}

/// The body of draw.html. `hand` is the catalog's handwritten font, as a file and as loaded by mathra.
pub fn body(root: &Path, hand: (&Path, MathFont), check: &str, alert: &str, download: &str) -> Result<String, String> {
    let stix_bytes = std::fs::read(root.join("fonts/stix-two-math/STIXTwoMath-Regular.otf")).map_err(|e| format!("STIX Two Math: {e}"))?;
    let hand_bytes = std::fs::read(hand.0).map_err(|e| format!("{}: {e}", hand.0.display()))?;
    let fonts = Fonts {
        stix: Face::parse(&stix_bytes, 0).map_err(|e| format!("STIX Two Math: {e}"))?,
        hand: Face::parse(&hand_bytes, 0).map_err(|e| format!("{}: {e}", hand.0.display()))?,
    };

    // A few cells as they should be filled.
    let good: &[(&[char], &str, &str)] = &[
        (&['2'], "U+0032", "A digit sits on the baseline and reaches about the cap height."),
        (&['\u{1D465}', 'x'], "U+1D465", "A small letter fills the space up to the x-height."),
        (&['\u{1D454}', 'g'], "U+1D454", "A descender goes below the baseline, still inside the box."),
        (&['A'], "U+0041", "A capital reaches the upper dashed line, the cap height."),
        (&['\u{1D6FC}', 'α'], "U+1D6FC", "Greek is drawn the same way as Latin."),
        (&['+'], "U+002B", "An operator sits centered, about halfway to the x-height."),
    ];
    let mut filled = String::new();
    for (chars, code, caption) in good {
        let svg = fonts.cell(chars, code, BODY, true, &fonts.written(chars, 1.0, 0.0, 0.0));
        filled += &figure(&svg, true, caption, check, alert);
    }

    // The parenthesis' pieces, each drawn as tall as its box, and the tall parenthesis they build.
    let mut pieces = String::new();
    let names = |i: usize, n: usize, ext: bool| {
        if ext {
            "extender piece"
        } else if i == 0 {
            "bottom piece"
        } else if i + 1 == n {
            "top piece"
        } else {
            "middle piece"
        }
    };
    let parts = fonts.pieces();
    for (i, (d, r, ext)) in parts.iter().enumerate().rev() {
        let tall = 2200.0;
        let drawn = fit(d, *r, 120.0, STRIP + 60.0, W - 240.0, tall - 120.0, "ink");
        let svg = fonts.cell(&['('], names(i, parts.len(), *ext), tall, false, &drawn);
        pieces += &format!(r#"<figure class="example ok piece">{svg}<figcaption><span>{}</span></figcaption></figure>"#, names(i, parts.len(), *ext));
    }
    let tall = crate::render::svg(r"\left( \begin{matrix} a \\ b \\ c \\ d \\ e \end{matrix} \right)", hand.1)?;

    // The usual mistakes.
    let x = ['\u{1D465}', 'x'];
    let bad = [
        (fonts.cell(&x, "U+1D465", BODY, true, &fonts.written(&x, 0.4, 0.0, 0.0)), "Too small: the font gets the size you draw, so the letter would be tiny next to the others."),
        (fonts.cell(&x, "U+1D465", BODY, true, &fonts.written(&x, 1.0, 0.0, -420.0)), "Floating: off the baseline, the letter would jump up in every equation."),
        (fonts.cell(&x, "U+1D465", BODY, true, &fonts.written(&x, 1.0, 420.0, 0.0)), "Across the edge: whatever is outside the box is cut off."),
        (fonts.cell(&x, "U+1D465", BODY, true, &fonts.written(&x, 0.5, -310.0, -STRIP - 640.0)), "In the sample strip: only the area under the line is read."),
    ];
    let mut mistakes = String::new();
    for (svg, caption) in &bad {
        mistakes += &figure(svg, false, caption, check, alert);
    }

    Ok(format!(
        r##"<section class="intro"><span class="eyebrow">Make your own</span><h1>Draw a math font by hand</h1>
<p>Print the grid, draw each glyph in its box with a pen, a marker or chalk, and photograph the pages. The grid lists everything a math font needs, so a font made from it has only your drawing, nothing borrowed from another font.</p>
</section>
<div class="sizes">
  <div class="size"><b>Compact</b><span>Boxes at handwriting size, about 4 mm for a small letter. Level 1 fits in 4 pages, everything in 17.</span><p class="actions"><a class="btn" href="grid/mathfonts-grid-compact.pdf" download>{download}Compact grid (PDF, 17 pages)</a><a class="btn ghost" href="grid/mathfonts-grid-compact-example.pdf">Filled example</a></p></div>
  <div class="size"><b>Large</b><span>Big boxes, about twice the size, to draw slowly or with a marker. Level 1 takes 12 pages, everything 61.</span><p class="actions"><a class="btn" href="grid/mathfonts-grid.pdf" download>{download}Large grid (PDF, 61 pages)</a><a class="btn ghost" href="grid/mathfonts-grid-example.pdf">Filled example</a></p></div>
</div>
<ol class="steps levels">
  <li><b>Level 1 · 322 glyphs</b><span>Letters, digits, Greek, the usual symbols, and the sizes and pieces of tall parentheses, brackets, radicals and integrals. Enough for the equations of school and university.</span></li>
  <li><b>Level 2 · 247 glyphs</b><span>Bold, script, Fraktur and double-struck letters, and upright Greek.</span></li>
  <li><b>Level 3 · 1704 glyphs</b><span>The rarer operators, arrows and alphabets: up to the 2273 glyphs of STIX Two Math in the blocks the catalog measures.</span></li>
</ol>
<div class="prose">
<h2>A filled example</h2>
<p>Every box has a strip on top with a small grey sample of what to draw, and its code. Draw yours below the line, without tracing the sample. The solid blue line is the baseline; the dashed ones are the x-height and the cap height. The examples here are drawn with Euler Math, Hermann Zapf's handwritten font.</p>
</div>
<div class="examples">{filled}</div>
<div class="prose">
<h2>Pieces of tall delimiters</h2>
<p>A parenthesis around a matrix is taller than any single drawing. mathra builds it from pieces: a top, a bottom, and an extender it repeats in between. In the grid each piece has its own box: draw it as tall as the box, with the stroke touching the top and the bottom edges, so that the pieces join when they are stacked.</p>
</div>
<div class="pieces">{pieces}<figure class="example result"><div class="built">{tall}</div><figcaption><span>What mathra builds from them</span></figcaption></figure></div>
<div class="prose">
<h2>Common mistakes</h2>
</div>
<div class="examples">{mistakes}</div>
<div class="prose">
<h2>Then</h2>
<ul>
  <li>Print at 100% (no "fit to page"), on white paper, and keep the black squares in the corners: they straighten the photo.</li>
  <li>A thick black line scans better than a thin one. For chalk, draw on dark paper: the photo gets inverted.</li>
  <li>Photograph or scan every page you filled, flat and well lit.</li>
</ul>
<p>The step that turns the photos of a filled grid into a font file is not ready yet.</p>
</div>"##
    ))
}
