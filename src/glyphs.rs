//! A page of every glyph of a font, laid out as the printed grid is (scripts/grid.py): the same
//! levels, sections and boxes, each with the grey STIX sample in its strip, the guides, and the
//! font's glyph on them. A box the font has nothing for is marked, so that what is missing, or
//! drawn badly, shows at a glance.
//!
//! Characters are set as text in the font itself (loaded with @font-face), which keeps the page
//! small; the sizes and pieces have no character of their own, so they are drawn from their outlines.

use std::fmt::Write;

use serde::Deserialize;
use ttf_parser::{Face, GlyphId, OutlineBuilder, Rect};

use crate::catalog::Entry;
use crate::site::escape;

/// Every box of the grid, in order: written by `scripts/grid.py --layout`.
const LAYOUT: &str = include_str!("../site/grid/layout.json");

#[derive(Deserialize)]
struct Layout {
    levels: Vec<Level>,
}

#[derive(Deserialize)]
struct Level {
    name: String,
    sections: Vec<Section>,
    #[serde(default)]
    tall: Vec<Piece>,
    #[serde(default)]
    wide: Vec<Piece>,
}

#[derive(Deserialize)]
struct Section {
    title: String,
    chars: Vec<(String, String)>,
}

/// A size or a piece of an assembly, as STIX Two Math has it, and how to find it in another font.
#[derive(Deserialize)]
struct Piece {
    glyph: String,
    label: String,
    char: String,
    horizontal: bool,
    #[serde(default)]
    picks: Vec<u16>,
    k: Option<usize>,
    #[serde(rename = "where")]
    place: Option<String>,
}

// The compact grid's box, in tenths of a millimetre.
const STRIP: f32 = 40.0;
const INSET: f32 = 17.0;
const CHAR_W: f32 = 155.0;
const CHAR_H: f32 = 170.0;
const TALL: (f32, f32) = (232.5, 340.0);
const WIDE: (f32, f32) = (310.0, 150.0);

/// Where the baseline and the em of a character box are: as grid.py's `guides`.
fn guides() -> (f32, f32) {
    let gap = INSET * 2.0 / 3.0;
    let em = (CHAR_H - STRIP - 2.0 * gap) / 1.25;
    (STRIP + gap + em, em)
}

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

/// The outline of `glyph`, fitted into and centered in the box (x, y, w, h), y growing down.
fn fitted(face: &Face, glyph: GlyphId, x: f32, y: f32, w: f32, h: f32, class: &str) -> Option<String> {
    let mut p = Path2 { d: String::new() };
    let r: Rect = face.outline_glyph(glyph, &mut p)?;
    let (gw, gh) = (f32::from(r.x_max - r.x_min).max(1.0), f32::from(r.y_max - r.y_min).max(1.0));
    let s = (w / gw).min(h / gh);
    let ox = x + (w - gw * s) / 2.0 - f32::from(r.x_min) * s;
    let oy = y + (h - gh * s) / 2.0 + f32::from(r.y_max) * s;
    Some(format!(r#"<path class="{class}" transform="translate({ox:.2} {oy:.2}) scale({s:.5} {:.5})" d="{}"/>"#, -s, p.d))
}

/// The outline of `glyph` at `scale`, centered on `cx`, its origin on the baseline `base`: as text
/// would set it.
fn placed(face: &Face, glyph: GlyphId, cx: f32, base: f32, scale: f32) -> Option<String> {
    let mut p = Path2 { d: String::new() };
    let r: Rect = face.outline_glyph(glyph, &mut p)?;
    let x = cx - f32::from(r.x_min + r.x_max) / 2.0 * scale;
    Some(format!(r#"<path class="g" transform="translate({x:.2} {base:.2}) scale({scale:.5} {:.5})" d="{}"/>"#, -scale, p.d))
}

/// The same size or piece in `face`, found the way grid.py finds it for the filled example.
fn counterpart(face: &Face, piece: &Piece) -> Option<GlyphId> {
    let base = face.glyph_index(piece.char.chars().next()?)?;
    let variants = face.tables().math?.variants?;
    let construction = if piece.horizontal { variants.horizontal_constructions } else { variants.vertical_constructions }.get(base)?;
    if let Some(k) = piece.k {
        // a font with fewer sizes than STIX: its biggest stands in, as on the filled example
        let n = construction.variants.len();
        if n <= 1 {
            return None;
        }
        let i = (*piece.picks.get(k)?).min(n - 1);
        return construction.variants.get(i).map(|v| v.variant_glyph);
    }
    let place = piece.place.as_deref()?;
    let parts: Vec<_> = construction.assembly?.parts.into_iter().collect();
    let (first, last) = if piece.horizontal { ("left", "right") } else { ("bottom", "top") };
    parts.iter().enumerate().find_map(|(i, p)| {
        let here = if p.part_flags.extender() {
            "extender"
        } else if i == 0 {
            first
        } else if i == parts.len() - 1 {
            last
        } else {
            "middle"
        };
        (here == place).then_some(p.glyph_id)
    })
}

/// Combining marks are drawn from their outlines: set alone as text, a browser may put them on a
/// dotted circle.
fn combining(c: char) -> bool {
    matches!(u32::from(c), 0x300..=0x36F | 0x20D0..=0x20FF)
}

fn short(label: &str) -> String {
    label.replace(" piece", "").replace("left ", "l. ").replace("right ", "r. ").replace("parenthesis", "paren.").replace("extender", "ext.")
}

struct Counts {
    boxes: usize,
    missing: usize,
}

/// The page's body. `font` and `stix` are the font files' bytes.
pub fn body(e: &Entry, font: &[u8], stix: &[u8], back: &str) -> Result<String, String> {
    let layout: Layout = serde_json::from_str(LAYOUT).map_err(|err| format!("site/grid/layout.json: {err}"))?;
    let face = Face::parse(font, 0).map_err(|err| format!("{}: {err}", e.meta.file))?;
    let reference = Face::parse(stix, 0).map_err(|err| format!("STIX Two Math: {err}"))?;
    let upm = f32::from(face.units_per_em());
    let x_height = face.x_height().map(f32::from).filter(|h| *h > 0.0).unwrap_or(upm * 0.45);
    let (base, em) = guides();
    // the font's x-height sits on the grid's x-height line, as on the filled example
    let size = em * 0.473 * upm / x_height;
    let name = escape(&e.meta.name);

    let mut levels = String::new();
    let mut total = Counts { boxes: 0, missing: 0 };
    let mut number = 0;
    for level in &layout.levels {
        let mut sections = String::new();
        for section in &level.sections {
            let mut cells = String::new();
            let mut missing = 0;
            for (s, unicode) in &section.chars {
                number += 1;
                let c = s.chars().next().unwrap_or(' ');
                let code = format!("U+{:04X}", u32::from(c));
                let text = escape(s);
                let sample = if reference.glyph_index(c).is_some() { format!(r#"<text class="s" x="{INSET}" y="31">{text}</text>"#) } else { String::new() };
                let glyph = match face.glyph_index(c) {
                    None => {
                        missing += 1;
                        None
                    }
                    Some(g) if combining(c) => placed(&face, g, CHAR_W / 2.0, base, size / upm),
                    Some(_) => Some(format!(r#"<text class="g" x="{}" y="{base:.2}">{text}</text>"#, CHAR_W / 2.0)),
                };
                let _ = write!(
                    cells,
                    r##"<figure class="gl-box{miss}" title="{code} {unicode}{gone}"><svg viewBox="0 0 {CHAR_W} {CHAR_H}"><use href="#gl-c"/>{sample}<text class="u" x="{ux}" y="27">{code}</text><text class="n" x="{ux}" y="{ny}">{number:04}</text>{glyph}</svg></figure>"##,
                    miss = if glyph.is_none() { " missing" } else { "" },
                    unicode = escape(unicode),
                    gone = if glyph.is_none() { ", missing" } else { "" },
                    ux = CHAR_W - 12.0,
                    ny = CHAR_H - 6.0,
                    glyph = glyph.unwrap_or_default(),
                );
            }
            total.boxes += section.chars.len();
            total.missing += missing;
            let _ = write!(sections, "{}", section_html(&section.title, section.chars.len(), missing, "gl-chars", &cells));
        }
        for (pieces, (w, h), title, class) in [(&level.tall, TALL, "Sizes and pieces of tall delimiters, display operators", "gl-tall"), (&level.wide, WIDE, "Wide accents and pieces of long arrows and braces", "gl-wide")] {
            if pieces.is_empty() {
                continue;
            }
            let mut cells = String::new();
            let mut missing = 0;
            for piece in pieces {
                number += 1;
                let sample = reference.glyph_index_by_name(&piece.glyph).and_then(|g| fitted(&reference, g, INSET, 6.0, 45.0, 28.0, "s")).unwrap_or_default();
                let glyph = counterpart(&face, piece).and_then(|g| fitted(&face, g, INSET, STRIP + INSET, w - 2.0 * INSET, h - STRIP - 2.0 * INSET, "g"));
                if glyph.is_none() {
                    missing += 1;
                }
                let _ = write!(
                    cells,
                    r##"<figure class="gl-box{miss}" title="{label}{gone}"><svg viewBox="0 0 {w} {h}"><use href="#{symbol}"/>{sample}<text class="u" x="{ux}" y="27">{short}</text><text class="n" x="{ux}" y="{ny}">{number:04}</text>{glyph}</svg></figure>"##,
                    miss = if glyph.is_none() { " missing" } else { "" },
                    label = escape(&piece.label),
                    gone = if glyph.is_none() { ", missing" } else { "" },
                    symbol = if piece.horizontal { "gl-w" } else { "gl-t" },
                    short = escape(&short(&piece.label)),
                    ux = w - 12.0,
                    ny = h - 6.0,
                    glyph = glyph.unwrap_or_default(),
                );
            }
            total.boxes += pieces.len();
            total.missing += missing;
            let _ = write!(sections, "{}", section_html(title, pieces.len(), missing, class, &cells));
        }
        let _ = write!(levels, r#"<section class="gl-level"><h2>{}</h2>{sections}</section>"#, escape(&level.name));
    }

    let frame = |id: &str, w: f32, h: f32, lines: bool| {
        // a <use> copy is out of reach of the page's selectors: the frame and the guides carry their
        // own style, and the theme's colours reach them through the custom properties
        const FRAME: &str = r#"style="fill:none;stroke:var(--ink);stroke-width:1.2""#;
        let mut s = format!(r#"<symbol id="{id}" viewBox="0 0 {w} {h}"><rect {FRAME} x="0.6" y="0.6" width="{}" height="{}"/><line {FRAME} x1="0" y1="{STRIP}" x2="{w}" y2="{STRIP}"/>"#, w - 1.2, h - 1.2);
        if lines {
            const DASH: &str = r#"style="stroke:var(--guide);stroke-width:0.8;stroke-dasharray:4 4;opacity:0.7""#;
            let _ = write!(
                s,
                r#"<line style="stroke:var(--guide);stroke-width:1" x1="{INSET}" y1="{base:.2}" x2="{x2}" y2="{base:.2}"/><line {DASH} x1="{INSET}" y1="{xh:.2}" x2="{x2}" y2="{xh:.2}"/><line {DASH} x1="{INSET}" y1="{cap:.2}" x2="{x2}" y2="{cap:.2}"/>"#,
                x2 = w - INSET,
                xh = base - em * 0.473,
                cap = base - em * 0.657,
            );
        }
        s.push_str("</symbol>");
        s
    };
    let filled = total.boxes - total.missing;
    Ok(format!(
        r##"<style>
@font-face {{ font-family: "gl-font"; src: url("../files/{slug}/{file}"); font-display: block; }}
@font-face {{ font-family: "gl-stix"; src: url("../files/stix-two-math/STIXTwoMath-Regular.otf"); font-display: block; }}
.gl-head h1 {{ margin-bottom: 12px; }}
.gl-head p {{ max-width: 70ch; color: var(--muted); }}
.gl-bar {{ display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; margin: 16px 0 8px; }}
.gl-level h2 {{ font-family: var(--display); font-size: 1.5rem; margin: 40px 0 4px; }}
.gl-section h3 {{ font: 600 0.95rem var(--body); margin: 20px 0 8px; }}
.gl-section h3 .miss {{ color: var(--fail); font-weight: 500; }}
.gl-grid {{ display: grid; gap: 0; }}
.gl-chars {{ grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); }}
.gl-tall {{ grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); }}
.gl-wide {{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }}
.gl-box {{ margin: 0; background: var(--surface); }}
.gl-box svg {{ display: block; width: 100%; height: auto; overflow: hidden; }}
.gl-box .s {{ fill: var(--muted); font: 26px "gl-stix"; }}
.gl-box path.s {{ font: inherit; }}
.gl-box .u, .gl-box .n {{ fill: var(--muted); font: 8px var(--body); text-anchor: end; }}
.gl-box .g {{ fill: var(--ink); font: {size:.2}px "gl-font"; text-anchor: middle; }}
.gl-box.missing {{ background: repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in srgb, var(--fail) 12%, transparent) 6px 7px), var(--surface); }}
.gl-box.missing .u {{ fill: var(--fail); }}
body.gl-only-missing .gl-box:not(.missing), body.gl-only-missing .gl-section:not(.has-missing) {{ display: none; }}
</style>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">{c}{t}{w}</svg>
<a class="back" href="{slug}.html">{back} {name}</a>
<div class="gl-head">
  <h1>Every glyph of {name}</h1>
  <p>The boxes of the printed grid, in its order, with {name}'s glyph in each: the grey sample on top is STIX Two Math, and the blue lines are the baseline, the x-height and the cap height. Each glyph is scaled so that its x-height meets the line, as on the filled example. A box with red stripes is one the font has nothing for.</p>
</div>
<div class="gl-bar">
  <strong>{filled} of {boxes} boxes filled{missing_note}</strong>
  <label><input type="checkbox" id="gl-only-missing"{disabled}> Show only what is missing</label>
</div>
{levels}
<script>document.getElementById("gl-only-missing").addEventListener("change", e => document.body.classList.toggle("gl-only-missing", e.target.checked));</script>"##,
        slug = e.slug,
        file = escape(&e.meta.file),
        c = frame("gl-c", CHAR_W, CHAR_H, true),
        t = frame("gl-t", TALL.0, TALL.1, false),
        w = frame("gl-w", WIDE.0, WIDE.1, false),
        boxes = total.boxes,
        missing_note = if total.missing > 0 { format!(", {} missing", total.missing) } else { String::new() },
        disabled = if total.missing == 0 { " disabled" } else { "" },
    ))
}

fn section_html(title: &str, n: usize, missing: usize, class: &str, cells: &str) -> String {
    let note = if missing > 0 { format!(r#" <span class="miss">· {missing} missing</span>"#) } else { String::new() };
    format!(
        r#"<section class="gl-section{has}"><h3>{title} ({n}){note}</h3><div class="gl-grid {class}">{cells}</div></section>"#,
        has = if missing > 0 { " has-missing" } else { "" },
        title = escape(title),
    )
}
