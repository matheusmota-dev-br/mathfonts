//! What the catalog checks for each font, and what it measures: whether the file opens, has a
//! MATH table and a license that lets it be shared, whether mathra draws the gallery with it, and
//! how many of the math symbols mathra knows it has.

use std::collections::HashSet;

use mathra::font::MathFont;
use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::catalog::{Entry, LICENSES, STYLES};

/// One equation of mathra's gallery (equations/gallery.json).
#[derive(Debug, Clone, Deserialize)]
pub struct Equation {
    #[serde(default)]
    pub name: Option<String>,
    pub tex: String,
    #[serde(default)]
    pub locale: Option<String>,
    #[serde(default)]
    pub input: Option<String>,
}

#[derive(Deserialize)]
struct Group {
    rows: Vec<Equation>,
}

pub fn gallery(json: &str) -> Result<Vec<Equation>, String> {
    let groups: Vec<Group> = serde_json::from_str(json).map_err(|e| format!("equations/gallery.json: {e}"))?;
    Ok(groups.into_iter().flat_map(|g| g.rows).collect())
}

/// The Unicode blocks of math symbols the coverage is counted in.
pub const BLOCKS: &[(&str, u32, u32)] = &[
    ("Greek", 0x370, 0x3FF),
    ("Math letters (𝑥, 𝔸, 𝓛)", 0x1D400, 0x1D7FF),
    ("Operators", 0x2200, 0x22FF),
    ("Supplemental operators", 0x2A00, 0x2AFF),
    ("Arrows", 0x2190, 0x21FF),
    ("Supplemental arrows", 0x27F0, 0x297F),
    ("Miscellaneous symbols A", 0x27C0, 0x27EF),
    ("Miscellaneous symbols B", 0x2980, 0x29FF),
    ("Letterlike (ℝ, ℏ, ℒ)", 0x2100, 0x214F),
];

#[derive(Debug, Clone)]
pub struct Check {
    pub label: String,
    pub pass: bool,
    /// A failed blocking check keeps the font out of the catalog.
    pub blocking: bool,
    pub detail: String,
}

#[derive(Debug, Clone)]
pub struct Block {
    pub name: &'static str,
    pub have: usize,
    pub total: usize,
    /// Some of the symbols it lacks, in order.
    pub missing: Vec<char>,
}

#[derive(Debug, Clone)]
pub struct Report {
    pub checks: Vec<Check>,
    pub font: Option<MathFont>,
    pub glyphs: u16,
    pub version: String,
    pub size: u64,
    pub sha256: String,
    pub blocks: Vec<Block>,
    pub gallery: (usize, usize),
    pub gallery_failures: Vec<String>,
}

impl Report {
    pub fn passed(&self) -> bool {
        self.checks.iter().all(|c| c.pass || !c.blocking)
    }

    /// The share of the math symbols mathra knows that the font has, in percent.
    pub fn coverage(&self) -> u32 {
        let (have, total) = self.blocks.iter().fold((0, 0), |(h, t), b| (h + b.have, t + b.total));
        if total == 0 {
            0
        } else {
            (100.0 * have as f64 / total as f64).round() as u32
        }
    }
}

/// The math symbols mathra can draw: those its embedded STIX Two Math has, in the blocks above.
pub fn reference() -> Vec<Vec<char>> {
    let stix = MathFont::StixTwo.get();
    BLOCKS.iter().map(|&(_, a, b)| (a..=b).filter_map(char::from_u32).filter(|c| stix.glyph(*c).is_some()).collect()).collect()
}

fn check(out: &mut Vec<Check>, label: &str, blocking: bool, result: Result<String, String>) -> bool {
    let pass = result.is_ok();
    let detail = result.unwrap_or_else(|e| e);
    out.push(Check { label: label.into(), pass, blocking, detail });
    pass
}

fn name_string(face: &ttf_parser::Face, id: u16) -> Option<String> {
    face.names().into_iter().filter(|n| n.name_id == id && n.is_unicode()).find_map(|n| n.to_string())
}

/// Every check and measure of one font. `names` are the other fonts' names, which it must not take.
pub fn run(entry: &Entry, equations: &[Equation], reference: &[Vec<char>], names: &HashSet<String>) -> Report {
    let mut checks = Vec::new();
    let mut report =
        Report { checks: vec![], font: None, glyphs: 0, version: String::new(), size: 0, sha256: String::new(), blocks: vec![], gallery: (0, 0), gallery_failures: vec![] };

    let license = entry.dir.join("LICENSE.txt");
    check(
        &mut checks,
        "The license text is included",
        true,
        match std::fs::read_to_string(&license) {
            Ok(t) if t.trim().len() > 200 => Ok(format!("LICENSE.txt, {} lines", t.lines().count())),
            Ok(_) => Err("LICENSE.txt is too short to be a license".into()),
            Err(_) => Err("no LICENSE.txt next to the font".into()),
        },
    );
    check(
        &mut checks,
        "The license allows sharing the file",
        true,
        match LICENSES.iter().find(|(k, _)| *k == entry.meta.license) {
            Some((_, label)) => Ok(label.to_string()),
            None => Err(format!("{} is not one of {}", entry.meta.license, LICENSES.iter().map(|(k, _)| *k).collect::<Vec<_>>().join(", "))),
        },
    );
    check(
        &mut checks,
        "The style is one the filters know",
        true,
        match STYLES.iter().any(|(k, _)| *k == entry.meta.style) {
            true => Ok(entry.style_label().to_string()),
            false => Err(format!("{} is not one of {}", entry.meta.style, STYLES.iter().map(|(k, _)| *k).collect::<Vec<_>>().join(", "))),
        },
    );
    check(
        &mut checks,
        "The name is its own",
        true,
        match names.contains(&entry.meta.name.to_lowercase()) {
            false => Ok(entry.meta.name.clone()),
            true => Err(format!("another font in the catalog is already called {}", entry.meta.name)),
        },
    );

    let bytes = match std::fs::read(entry.font_path()) {
        Ok(b) => b,
        Err(e) => {
            check(&mut checks, "The font file is there", true, Err(format!("{}: {e}", entry.meta.file)));
            report.checks = checks;
            return report;
        }
    };
    report.size = bytes.len() as u64;
    report.sha256 = Sha256::digest(&bytes).iter().map(|b| format!("{b:02x}")).collect();

    let face = match ttf_parser::Face::parse(&bytes, 0) {
        Ok(f) => f,
        Err(e) => {
            check(&mut checks, "The file opens as a font", true, Err(format!("not an OpenType or TrueType font: {e}")));
            report.checks = checks;
            return report;
        }
    };
    report.glyphs = face.number_of_glyphs();
    report.version = name_string(&face, 5).unwrap_or_default().trim_start_matches("Version ").to_string();
    check(&mut checks, "The file opens as a font", true, Ok(format!("{} glyphs, version {}", report.glyphs, report.version)));
    let has_math = face.tables().math.and_then(|m| m.constants).is_some();
    check(
        &mut checks,
        "It has a MATH table",
        true,
        if has_math {
            Ok("constants, variants and assemblies for fractions, radicals and delimiters".into())
        } else {
            Err("no OpenType MATH table: this is a text font, not a math font".into())
        },
    );

    report.blocks = BLOCKS
        .iter()
        .zip(reference)
        .map(|(&(name, _, _), wanted)| {
            let missing: Vec<char> = wanted.iter().copied().filter(|c| face.glyph_index(*c).is_none()).collect();
            Block { name, have: wanted.len() - missing.len(), total: wanted.len(), missing }
        })
        .collect();

    if !has_math {
        report.checks = checks;
        return report;
    }
    let font = match MathFont::load(bytes.clone()) {
        Ok(f) => f,
        Err(e) => {
            check(&mut checks, "mathra loads it", true, Err(e.to_string()));
            report.checks = checks;
            return report;
        }
    };
    check(&mut checks, "mathra loads it", true, Ok(font.name().to_string()));
    report.font = Some(font);

    // the gallery: every equation the embedded font draws, this one should draw too
    let (mut passed, mut total) = (0, 0);
    for eq in equations {
        let options = mathra::Options {
            locale: eq.locale.as_deref().unwrap_or("en").parse().unwrap_or_default(),
            input: eq.input.as_deref().unwrap_or("latex").parse().unwrap_or_default(),
            ..Default::default()
        };
        if mathra::convert(&eq.tex, &options).is_err() {
            continue;
        }
        total += 1;
        match mathra::convert(&eq.tex, &mathra::Options { font, ..options }) {
            Ok(_) => passed += 1,
            Err(e) => report.gallery_failures.push(format!("{}: {e}", eq.name.as_deref().unwrap_or(&eq.tex))),
        }
    }
    report.gallery = (passed, total);
    check(
        &mut checks,
        "mathra draws the gallery",
        false,
        if passed == total { Ok(format!("{passed}/{total} equations")) } else { Err(format!("{passed}/{total} equations: {}", report.gallery_failures.join("; "))) },
    );
    report.checks = checks;
    report
}
