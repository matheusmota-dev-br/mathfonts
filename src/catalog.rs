//! The catalog: one folder per font under `fonts/`, with the font file, its license and a
//! `font.toml` that says what it is and where it comes from.

use std::path::{Path, PathBuf};

use serde::Deserialize;

/// Licenses that let the catalog redistribute the file as its author published it.
pub const LICENSES: &[(&str, &str)] =
    &[("OFL-1.1", "SIL Open Font License 1.1"), ("GUST-Font-License", "GUST Font License"), ("Apache-2.0", "Apache License 2.0"), ("MIT", "MIT License")];

/// How a font looks, for the filters.
pub const STYLES: &[(&str, &str)] = &[("serif", "Serif"), ("sans", "Sans"), ("tex", "TeX style"), ("handwritten", "Handwritten")];

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Meta {
    pub name: String,
    pub file: String,
    pub license: String,
    pub style: String,
    /// The text family the math font goes with ("Times", "Computer Modern").
    pub base: String,
    pub designer: Option<String>,
    /// A page about the font: its author's site or its CTAN page.
    pub source: String,
    /// An equation of the author's choosing, shown first on the font's page.
    pub sample: Option<String>,
    #[allow(dead_code)]
    pub upstream: Option<Upstream>,
}

/// Where the file can be downloaded again: a font file, or a zip and the path inside it.
/// scripts/refresh.py reads it; here it is only checked to be well formed.
#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Upstream {
    pub url: String,
    pub path: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Entry {
    /// The folder's name, also the font's address on the site.
    pub slug: String,
    pub dir: PathBuf,
    pub meta: Meta,
}

impl Entry {
    pub fn font_path(&self) -> PathBuf {
        self.dir.join(&self.meta.file)
    }

    pub fn style_label(&self) -> &'static str {
        STYLES.iter().find(|(k, _)| *k == self.meta.style).map_or("Other", |(_, v)| v)
    }

    pub fn license_label(&self) -> &str {
        LICENSES.iter().find(|(k, _)| *k == self.meta.license).map_or(self.meta.license.as_str(), |(_, v)| v)
    }
}

/// One font folder.
pub fn load(dir: &Path) -> Result<Entry, String> {
    let slug = dir.file_name().and_then(|n| n.to_str()).ok_or_else(|| format!("{}: not a folder name", dir.display()))?.to_string();
    let path = dir.join("font.toml");
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let meta: Meta = toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(Entry { slug, dir: dir.to_path_buf(), meta })
}

/// Every font folder under `root/fonts`, by name.
pub fn load_all(root: &Path) -> Result<Vec<Entry>, String> {
    let fonts = root.join("fonts");
    let mut out = Vec::new();
    for item in std::fs::read_dir(&fonts).map_err(|e| format!("{}: {e}", fonts.display()))? {
        let dir = item.map_err(|e| e.to_string())?.path();
        if dir.is_dir() {
            out.push(load(&dir)?);
        }
    }
    out.sort_by_key(|e| e.meta.name.to_lowercase());
    Ok(out)
}
