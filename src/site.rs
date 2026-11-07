//! The site, built to plain files: the grid of fonts, a page per font, the comparison and how to
//! add a font. Every equation is an SVG mathra drew in that font.

use std::fmt::Write;
use std::path::Path;

use crate::catalog::{Entry, STYLES};
use crate::check::Report;
use crate::render::{self, SPECIMENS};

const ICONS: &[(&str, &str)] = &[
    ("download", r#"<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>"#),
    ("columns", r#"<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>"#),
    ("check", r#"<path d="m5 12 5 5 9-10"/>"#),
    ("alert", r#"<circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16h.01"/>"#),
    ("back", r#"<path d="m15 18-6-6 6-6"/>"#),
    ("external", r#"<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>"#),
    ("sun", r#"<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>"#),
    ("moon", r#"<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>"#),
    ("monitor", r#"<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>"#),
];

fn icon(name: &str, class: &str) -> String {
    let path = ICONS.iter().find(|(n, _)| *n == name).map_or("", |(_, p)| p);
    format!(r#"<svg viewBox="0 0 24 24" class="ic {class}" aria-hidden="true">{path}</svg>"#)
}

pub fn escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

/// The repository the site sends contributors to, when it is known (`MATHFONTS_REPOSITORY`).
fn repository() -> Option<String> {
    std::env::var("MATHFONTS_REPOSITORY").ok().filter(|s| !s.is_empty())
}

/// A whole page. `base` leads from the page back to the site's root ("" or "../").
fn page(title: &str, description: &str, base: &str, current: &str, body: &str) -> String {
    let nav = [("index.html", "Fonts"), ("compare.html", "Compare"), ("draw.html", "Draw a font"), ("contribute.html", "Add your font")]
        .iter()
        .map(|(href, label)| format!(r#"<a href="{base}{href}"{}>{label}</a>"#, if *href == current { r#" aria-current="page""# } else { "" }))
        .collect::<String>();
    format!(
        r##"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{description}">
<script>try {{ const t = localStorage.getItem("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }} catch {{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{base}style.css">
</head>
<body data-base="{base}">
<header class="top"><div class="wrap">
  <a class="logo" href="{base}index.html">math<em>fonts</em></a>
  <nav class="nav" aria-label="Site">{nav}</nav>
  <button class="iconbtn" id="theme" type="button" data-mode="system" title="Theme: same as the system" aria-label="Theme: same as the system">{}{}{}</button>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
  <span>Every equation on this site is drawn by <a href="https://github.com/matheusmota-dev-br/mathra">mathra</a> {}, in the font it shows.</span>
  <span>Each font belongs to its authors and comes with its license; the files are as they published them.</span>
</div></footer>
<script src="{base}app.js"></script>
</body>
</html>
"##,
        icon("monitor", "i-system"),
        icon("sun", "i-light"),
        icon("moon", "i-dark"),
        mathra::VERSION,
    )
}

fn style_chips() -> String {
    let mut s = String::from(r#"<button class="chip" type="button" data-style-filter="all" aria-pressed="true">All</button>"#);
    for (k, v) in STYLES {
        let _ = write!(s, r#"<button class="chip" type="button" data-style-filter="{k}" aria-pressed="false">{v}</button>"#);
    }
    s
}

fn equation_chips() -> String {
    SPECIMENS
        .iter()
        .enumerate()
        .map(|(i, (id, caption, _))| format!(r#"<button class="chip" type="button" data-equation="{id}" aria-pressed="{}">{caption}</button>"#, i == 0))
        .collect()
}

fn index(results: &[(Entry, Report)], first: &[String]) -> String {
    let mut cards = String::new();
    for ((e, r), svg) in results.iter().zip(first) {
        let name = escape(&e.meta.name);
        let _ = write!(
            cards,
            r#"<article class="card" data-slug="{slug}" data-style="{style}" data-name="{name}" data-coverage="{cov}">
  <a class="spec" href="fonts/{slug}.html" tabindex="-1" aria-hidden="true">{svg}</a>
  <div class="meta">
    <div class="who"><a href="fonts/{slug}.html" title="{name}">{name}</a><span class="sub">{base} · {style_label}</span></div>
    <span class="meter" style="--v:{cov}" title="Has {cov}% of the math symbols mathra draws"></span>
    <button class="iconbtn" type="button" data-pick="{slug}" aria-pressed="false" title="Compare {name} with other fonts" aria-label="Compare {name}">{columns}</button>
    <a class="iconbtn" href="files/{slug}/{file}" download title="Download {name} ({kb} KB, {license})" aria-label="Download {name}">{download}</a>
  </div>
</article>
"#,
            slug = e.slug,
            style = e.meta.style,
            cov = r.coverage(),
            base = escape(&e.meta.base),
            style_label = e.style_label(),
            file = escape(&e.meta.file),
            kb = r.size / 1024,
            license = e.meta.license,
            columns = icon("columns", ""),
            download = icon("download", ""),
        );
    }
    let body = format!(
        r#"<section class="intro">
  <h1>Math fonts, drawn</h1>
  <p>{n} OpenType math fonts, each one checked and every equation drawn by mathra in that font. Pick a font by what it does to a fraction, a sum or a Greek letter, then download it as its authors published it.</p>
  <p>No math font of your own yet? <a href="draw.html">Draw one by hand</a>: print a grid, fill it and photograph it.</p>
</section>
<div class="toolbar">
  <div class="group"><span>Equation</span><div class="chips" role="group" aria-label="Equation shown">{eqs}</div></div>
</div>
<div class="toolbar">
  <div class="group"><span>Style</span><div class="chips" role="group" aria-label="Filter by style">{styles}</div></div>
  <div class="group"><span>Order</span><select id="sort" aria-label="Order"><option value="name">By name</option><option value="coverage">Most symbols first</option></select></div>
  <span class="count" id="count">{n} fonts</span>
</div>
<div class="grid" id="grid">
{cards}</div>
<div class="comparebar" id="comparebar" hidden><span id="compare-count"></span><button type="button" id="compare-clear">Clear</button><a id="compare-go" href="compare.html">Compare</a></div>"#,
        n = results.len(),
        eqs = equation_chips(),
        styles = style_chips(),
    );
    page("mathfonts", "A catalog of OpenType math fonts, every equation drawn by mathra.", "", "index.html", &body)
}

fn font_page(e: &Entry, r: &Report, specs: &[(String, String)], hero: &str, sample_caption: &str) -> Result<String, String> {
    let name = escape(&e.meta.name);
    let mut figures = String::new();
    for (caption, svg) in specs {
        let _ = write!(figures, r#"<figure><div>{svg}</div><figcaption>{}</figcaption></figure>"#, escape(caption));
    }
    let mut checks = String::new();
    for c in &r.checks {
        let (class, ic) = if c.pass { ("pass", icon("check", "")) } else { ("warn", icon("alert", "")) };
        let _ = write!(checks, r#"<li class="{class}" title="{}">{ic}<span>{}</span></li>"#, escape(&c.detail), escape(&c.label));
    }
    let mut blocks = String::new();
    for b in &r.blocks {
        let missing = if b.missing.is_empty() {
            "nothing".to_string()
        } else {
            let tex: Vec<String> = b.missing.iter().take(8).map(|c| c.to_string()).collect();
            render::inline(&tex.join(r"\;")).unwrap_or_else(|_| escape(&tex.join(" ")))
        };
        let _ = write!(blocks, r#"<tr><td>{}</td><td class="num">{}/{}</td><td class="missing">{missing}</td></tr>"#, escape(b.name), b.have, b.total);
    }
    let designer = e.meta.designer.as_deref().map(|d| format!("{} · ", escape(d))).unwrap_or_default();
    let file = escape(&e.meta.file);
    let body = format!(
        r#"<a class="back" href="../index.html">{back} All fonts</a>
<div class="fontpage">
  <div>
    <section class="intro"><h1>{name}</h1><p class="sub">{designer}{base} · {style}</p></section>
    <figure class="hero" style="margin:0" aria-label="{sample_caption}">{hero}</figure>
    <div class="specs">{figures}</div>
    <section class="panel">
      <h2>Math symbols</h2>
      <p class="sub">{name} has {cov}% of the {total} math symbols mathra draws. What it lacks, an equation cannot use in this font. The missing symbols are shown in STIX Two Math.</p>
      <div class="tablewrap"><table><thead><tr><th>Block</th><th class="num">Has</th><th>Lacks, for example</th></tr></thead><tbody>{blocks}</tbody></table></div>
    </section>
    <section class="panel">
      <h2>Use it with mathra</h2>
<pre>mathra '\frac{{a}}{{b}}' --font {file} -o fraction.svg</pre>
<pre>const font = loadFont(await readFile("{file}"));
texToSvg(String.raw`\frac{{a}}{{b}}`, {{ font }});</pre>
<pre>font = mathra.load_font("{file}")
mathra.tex_to_svg(r"\frac{{a}}{{b}}", font=font)</pre>
    </section>
  </div>
  <aside>
    <a class="btn" href="../files/{slug}/{file}" download>{download} Download {file}</a>
    <a class="btn ghost" href="../compare.html?fonts=stix-two-math,{slug}">{columns} Compare with STIX Two Math</a>
    <dl>
      <dt>License</dt><dd><a href="../files/{slug}/LICENSE.txt">{license}</a></dd>
      <dt>Version</dt><dd>{version}</dd>
      <dt>Glyphs</dt><dd>{glyphs}</dd>
      <dt>File</dt><dd>{file}, {kb} KB</dd>
      <dt>SHA-256</dt><dd title="{sha}"><code>{sha_short}…</code></dd>
      <dt>Source</dt><dd><a href="{source}">{source_host} {external}</a></dd>
    </dl>
    <ul class="checks">{checks}</ul>
  </aside>
</div>"#,
        back = icon("back", ""),
        base = escape(&e.meta.base),
        style = e.style_label(),
        sample_caption = escape(sample_caption),
        cov = r.coverage(),
        total = r.blocks.iter().map(|b| b.total).sum::<usize>(),
        slug = e.slug,
        download = icon("download", ""),
        columns = icon("columns", ""),
        license = escape(e.license_label()),
        version = escape(&r.version),
        glyphs = r.glyphs,
        kb = r.size / 1024,
        sha = r.sha256,
        sha_short = &r.sha256[..16.min(r.sha256.len())],
        source = escape(&e.meta.source),
        source_host = escape(e.meta.source.split('/').nth(2).unwrap_or(&e.meta.source)),
        external = icon("external", ""),
    );
    Ok(page(&format!("{} · mathfonts", e.meta.name), &format!("{} drawn by mathra: specimens, symbols and download.", e.meta.name), "../", "", &body))
}

fn compare(results: &[(Entry, Report)]) -> String {
    let data: Vec<serde_json::Value> =
        results.iter().map(|(e, r)| serde_json::json!({ "slug": e.slug, "name": e.meta.name, "base": e.meta.base, "style": e.style_label(), "coverage": r.coverage() })).collect();
    let equations: Vec<(&str, &str)> = SPECIMENS.iter().map(|(id, caption, _)| (*id, *caption)).collect();
    // `</` cannot appear inside a script element
    let json = |v: String| v.replace("</", "<\\/");
    let body = format!(
        r#"<section class="intro"><h1>Compare</h1><p>The same equations in up to three fonts, side by side.</p></section>
<div class="pickers">
  <label class="group"><span>First</span><select data-column="0"></select></label>
  <label class="group"><span>Second</span><select data-column="1"></select></label>
  <label class="group"><span>Third</span><select data-column="2"></select></label>
</div>
<div class="compare" id="compare"></div>
<script type="application/json" id="fonts-data">{}</script>
<script type="application/json" id="equations-data">{}</script>"#,
        json(serde_json::to_string(&data).unwrap_or_default()),
        json(serde_json::to_string(&equations).unwrap_or_default()),
    );
    page("Compare · mathfonts", "Math fonts side by side, drawn by mathra.", "", "compare.html", &body)
}

fn contribute() -> String {
    let repo = repository();
    let link = |text: &str, path: &str| match &repo {
        Some(r) => format!(r#"<a href="{r}{path}">{text}</a>"#),
        None => text.to_string(),
    };
    let body = format!(
        r#"<section class="intro"><span class="eyebrow">For type designers</span><h1>Add your font with a pull request</h1>
<p>If you made an OpenType math font, finished or not, add a folder and open a pull request on {repo}. A check runs on it with mathra: in a few minutes it comments what passed, how many math symbols the font has and which ones it lacks. A draft pull request gets the report too, so you can use it to test a font you are still drawing.</p></section>
<ol class="steps">
  <li><b>A folder</b><span><code>fonts/your-font/</code> with the font file, its license as <code>LICENSE.txt</code>, and a <code>font.toml</code>.</span></li>
  <li><b>The pull request</b><span>A draft is fine. Everything can be done on GitHub's website, with nothing to install.</span></li>
  <li><b>The report</b><span>The check comments on the pull request: the checks, the coverage of math symbols by block, and what is missing.</span></li>
  <li><b>The merge</b><span>Your font gets its own page with your name, and joins the grid and the comparison.</span></li>
</ol>
<div class="prose">
<h2>font.toml</h2>
<pre>name     = "Euler Math"
file     = "Euler-Math.otf"
license  = "OFL-1.1"       # OFL-1.1, GUST-Font-License, Apache-2.0 or MIT
style    = "handwritten"   # serif, sans, tex or handwritten
base     = "Euler"         # the text family it goes with
designer = "Hermann Zapf"  # optional
source   = "https://ctan.org/pkg/euler-math"
sample   = '\nabla \times \vec{{B}} = \mu_0 \vec{{J}}'   # optional: shown first on its page

[upstream]                 # optional: where the file can be downloaded again
url  = "https://mirrors.ctan.org/fonts/euler-math.zip"
path = "euler-math/Euler-Math.otf"</pre>
<h2>What the check requires</h2>
<ul>
  <li>An OpenType or TrueType file with a <b>MATH table</b>. A text font, however good, cannot set a fraction or a radical.</li>
  <li>A license that lets the catalog share the file: OFL 1.1, GUST, Apache 2.0 or MIT, with its text in <code>LICENSE.txt</code>.</li>
  <li>The file <b>as you published it</b>: not subset, not converted. Under the OFL, a changed file cannot keep a reserved font name.</li>
  <li>A name no other font in the catalog has.</li>
</ul>
<p>The coverage of math symbols is information, not a requirement: a font with few symbols is welcome, and its page says which ones it lacks.</p>
<p>The details are in {contributing}.</p>
<p>No font yet? You can <a href="draw.html">draw one by hand</a> on a printed grid.</p>
</div>"#,
        repo = link("the catalog's repository", ""),
        contributing = link("CONTRIBUTING.md", "/blob/main/CONTRIBUTING.md"),
    );
    page("Add your font · mathfonts", "How to add an OpenType math font to mathfonts with a pull request.", "", "contribute.html", &body)
}

fn write(path: &Path, text: &str) -> Result<(), String> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    std::fs::write(path, text).map_err(|e| format!("{}: {e}", path.display()))
}

fn copy(from: &Path, to: &Path) -> Result<(), String> {
    if let Some(dir) = to.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    std::fs::copy(from, to).map(|_| ()).map_err(|e| format!("{}: {e}", from.display()))
}

pub fn build(root: &Path, out: &Path, results: &[(Entry, Report)]) -> Result<(), String> {
    if out.exists() {
        std::fs::remove_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
    }
    let mut first = Vec::new();
    for (e, r) in results {
        let font = r.font.ok_or_else(|| format!("{}: not loaded", e.meta.name))?;
        // every specimen, as a file for the grid's equation switch and the comparison
        let mut specs = Vec::new();
        for (id, caption, tex) in SPECIMENS {
            let svg = render::svg(tex, font).map_err(|err| format!("{}, {id}: {err}", e.meta.name))?;
            write(&out.join(format!("specimens/{}/{id}.svg", e.slug)), &svg)?;
            if *id == "gaussian" {
                first.push(svg.clone());
            }
            specs.push((caption.to_string(), svg));
        }
        // the page's large equation: the author's sample, or the Ampère–Maxwell law
        let (hero, caption) = match &e.meta.sample {
            Some(tex) => (render::svg(tex, font).map_err(|err| format!("{}, sample: {err}", e.meta.name))?, "The designer's sample".to_string()),
            None => {
                let i = SPECIMENS.iter().position(|(id, _, _)| *id == "maxwell").unwrap_or(0);
                let (caption, svg) = specs.remove(i);
                (svg, caption)
            }
        };
        write(&out.join(format!("fonts/{}.html", e.slug)), &font_page(e, r, &specs, &hero, &caption)?)?;
        copy(&e.font_path(), &out.join(format!("files/{}/{}", e.slug, e.meta.file)))?;
        copy(&e.dir.join("LICENSE.txt"), &out.join(format!("files/{}/LICENSE.txt", e.slug)))?;
    }
    write(&out.join("index.html"), &index(results, &first))?;
    write(&out.join("compare.html"), &compare(results))?;
    write(&out.join("contribute.html"), &contribute())?;
    let hand = results.iter().find(|(e, _)| e.slug == "euler-math").ok_or("draw.html needs Euler Math in the catalog")?;
    let font = hand.1.font.ok_or("Euler Math: not loaded")?;
    let draw = crate::draw::body(root, (&hand.0.font_path(), font), &icon("check", "i-ok"), &icon("alert", "i-bad"), &icon("download", ""))?;
    write(
        &out.join("draw.html"),
        &page("Draw a math font · mathfonts", "Print a grid, draw every glyph of a math font by hand, and see a filled example.", "", "draw.html", &draw),
    )?;
    for asset in ["style.css", "app.js", "grid/mathfonts-grid.pdf", "grid/mathfonts-grid-example.pdf", "grid/mathfonts-grid-compact.pdf", "grid/mathfonts-grid-compact-example.pdf"] {
        copy(&root.join("site").join(asset), &out.join(asset))?;
    }
    Ok(())
}
