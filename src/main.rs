//! mathfonts: checks the math fonts of the catalog and builds its site.
//!
//!   mathfonts check [fonts/<slug> …] [--report <file>]   check fonts, write the PR report
//!   mathfonts build [--out <dir>]                        check every font and build the site

mod catalog;
mod check;
mod draw;
mod glyphs;
mod render;
mod report;
mod site;

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const HELP: &str = "\
mathfonts — the math font catalog

USAGE
  mathfonts check [fonts/<slug> …] [--report <file>]
      check the fonts named (every font without one) and print what passed;
      --report writes the Markdown the CI comments on a pull request
  mathfonts build [--out <dir>]
      check every font and build the site in <dir> (default: dist)
";

fn main() -> ExitCode {
    match run() {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::FAILURE,
        Err(e) => {
            eprintln!("mathfonts: {e}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<bool, String> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let root = Path::new(".");
    let option = |name: &str| args.iter().position(|a| a == name).map(|i| args.get(i + 1).cloned().ok_or(format!("missing value after {name}"))).transpose();
    match args.first().map(String::as_str) {
        Some("check") => {
            let report = option("--report")?;
            let dirs: Vec<PathBuf> = args[1..].iter().filter(|a| !a.starts_with("--") && Some(*a) != report.as_ref()).map(PathBuf::from).collect();
            let results = checked(root, &dirs)?;
            for (entry, r) in &results {
                println!("{} {} ({}% of the math symbols)", if r.passed() { "ok  " } else { "FAIL" }, entry.meta.name, r.coverage());
                for c in r.checks.iter().filter(|c| !c.pass) {
                    println!("     {}: {}", c.label, c.detail);
                }
            }
            if let Some(file) = report {
                std::fs::write(&file, report::markdown(&results)).map_err(|e| format!("{file}: {e}"))?;
            }
            Ok(results.iter().all(|(_, r)| r.passed()))
        }
        Some("build") => {
            let out = PathBuf::from(option("--out")?.unwrap_or_else(|| "dist".into()));
            let results = checked(root, &[])?;
            let failed: Vec<&str> = results.iter().filter(|(_, r)| !r.passed()).map(|(e, _)| e.meta.name.as_str()).collect();
            if !failed.is_empty() {
                return Err(format!("these fonts fail their checks: {} (run mathfonts check)", failed.join(", ")));
            }
            site::build(root, &out, &results)?;
            println!("{} fonts, site in {}", results.len(), out.display());
            Ok(true)
        }
        _ => {
            print!("{HELP}");
            Ok(args.iter().any(|a| a == "-h" || a == "--help"))
        }
    }
}

/// The fonts in `dirs` (every font without any), each checked against the whole catalog.
fn checked(root: &Path, dirs: &[PathBuf]) -> Result<Vec<(catalog::Entry, check::Report)>, String> {
    let all = catalog::load_all(root)?;
    let entries = if dirs.is_empty() { all.clone() } else { dirs.iter().map(|d| catalog::load(d)).collect::<Result<Vec<_>, _>>()? };
    let equations = check::gallery(&std::fs::read_to_string(root.join("equations/gallery.json")).map_err(|e| format!("equations/gallery.json: {e}"))?)?;
    let reference = check::reference();
    Ok(entries
        .into_iter()
        .map(|entry| {
            // the names of the other fonts: a font must not take one
            let names: HashSet<String> = all.iter().filter(|o| o.slug != entry.slug).map(|o| o.meta.name.to_lowercase()).collect();
            let report = check::run(&entry, &equations, &reference, &names);
            (entry, report)
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A font folder in a scratch directory: the catalog's STIX Two Math, with `edit` applied.
    fn scratch(name: &str, edit: impl Fn(&Path, &mut Vec<u8>)) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("mathfonts-test-{}-{name}", std::process::id())).join(name);
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let src = Path::new("fonts/stix-two-math");
        let mut bytes = std::fs::read(src.join("STIXTwoMath-Regular.otf")).unwrap();
        std::fs::copy(src.join("LICENSE.txt"), dir.join("LICENSE.txt")).unwrap();
        std::fs::write(
            dir.join("font.toml"),
            format!("name = \"{name}\"\nfile = \"f.otf\"\nlicense = \"OFL-1.1\"\nstyle = \"serif\"\nbase = \"Times\"\nsource = \"https://example.org\"\n"),
        )
        .unwrap();
        edit(&dir, &mut bytes);
        std::fs::write(dir.join("f.otf"), bytes).unwrap();
        dir
    }

    fn failed(dir: &Path) -> Vec<String> {
        let (_, r) = checked(Path::new("."), &[dir.to_path_buf()]).unwrap().remove(0);
        r.checks.iter().filter(|c| !c.pass && c.blocking).map(|c| c.label.clone()).collect()
    }

    #[test]
    fn every_font_in_the_catalog_passes() {
        let results = checked(Path::new("."), &[]).unwrap();
        assert!(results.len() >= 22);
        for (e, r) in &results {
            assert!(r.passed(), "{}: {:?}", e.meta.name, r.checks.iter().filter(|c| !c.pass).collect::<Vec<_>>());
            assert_eq!(r.gallery.0, r.gallery.1, "{}", e.meta.name);
        }
    }

    #[test]
    fn a_font_without_a_math_table_is_refused() {
        let dir = scratch("No Math", |_, bytes| {
            let at = bytes.windows(4).position(|w| w == b"MATH").unwrap();
            bytes[at..at + 4].copy_from_slice(b"XATH");
        });
        assert_eq!(failed(&dir), ["It has a MATH table"]);
    }

    #[test]
    fn a_font_without_its_license_or_with_a_taken_name_is_refused() {
        let dir = scratch("No License", |dir, _| std::fs::remove_file(dir.join("LICENSE.txt")).unwrap());
        assert_eq!(failed(&dir), ["The license text is included"]);
        let dir = scratch("STIX Two Math", |_, _| {});
        assert_eq!(failed(&dir), ["The name is its own"]);
    }

    #[test]
    fn the_report_says_what_failed_and_what_is_missing() {
        let dir = scratch("No Math Report", |_, bytes| {
            let at = bytes.windows(4).position(|w| w == b"MATH").unwrap();
            bytes[at..at + 4].copy_from_slice(b"XATH");
        });
        let md = report::markdown(&checked(Path::new("."), &[dir]).unwrap());
        assert!(md.contains("✗ **It has a MATH table**") && md.contains("Some checks failed"), "{md}");
        let md = report::markdown(&checked(Path::new("."), &[PathBuf::from("fonts/fira-math")]).unwrap());
        assert!(md.contains("Every font passed") && md.contains("| Supplemental operators | 3/256 |"), "{md}");
    }
}
