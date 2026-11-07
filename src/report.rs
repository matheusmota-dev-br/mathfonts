//! The report the CI comments on a pull request: what passed, how much of the math symbols the
//! font has, and what it lacks. Markdown, for GitHub.

use std::fmt::Write;

use crate::catalog::Entry;
use crate::check::Report;

pub fn markdown(results: &[(Entry, Report)]) -> String {
    let mut s = String::new();
    let ok = results.iter().all(|(_, r)| r.passed());
    let _ = writeln!(s, "## Font check\n");
    let _ = writeln!(
        s,
        "{}\n",
        if ok {
            "Every font passed the checks that keep a font out of the catalog. The coverage below is information, not a requirement."
        } else {
            "Some checks failed: the fonts marked below cannot join the catalog until they pass."
        }
    );
    for (entry, r) in results {
        let _ = writeln!(s, "### {} `fonts/{}`\n", entry.meta.name, entry.slug);
        for c in &r.checks {
            let mark = if c.pass {
                "✓"
            } else if c.blocking {
                "✗"
            } else {
                "!"
            };
            let _ = writeln!(s, "- {mark} **{}**: {}", c.label, c.detail);
        }
        if !r.blocks.is_empty() {
            let _ = writeln!(s, "\n**Math symbols: {}%** of the {} that mathra draws.\n", r.coverage(), r.blocks.iter().map(|b| b.total).sum::<usize>());
            let _ = writeln!(s, "| Block | Has | Lacks, for example |\n|---|---:|---|");
            for b in &r.blocks {
                let missing: String = b.missing.iter().take(12).map(|c| format!("{c} ")).collect();
                let _ = writeln!(s, "| {} | {}/{} | {} |", b.name, b.have, b.total, if missing.is_empty() { "nothing".to_string() } else { missing.trim_end().to_string() });
            }
        }
        let _ = writeln!(s);
    }
    let _ = writeln!(s, "<sub>Drawn and measured with mathra {}.</sub>", mathra::VERSION);
    s
}
