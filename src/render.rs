//! Every example on the site is drawn by mathra, in the font it shows.

use mathra::font::MathFont;

/// The equations each font is shown with: an id (also the file name), a caption and the LaTeX.
pub const SPECIMENS: &[(&str, &str, &str)] = &[
    ("gaussian", "Gaussian integral", r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}"),
    ("quadratic", "Quadratic formula", r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}"),
    ("basel", "Basel problem", r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}"),
    ("maxwell", "Ampère–Maxwell law", r"\nabla \times \vec{B} = \mu_0 \vec{J} + \mu_0 \varepsilon_0 \frac{\partial \vec{E}}{\partial t}"),
    ("matrix", "Matrix", r"A = \begin{pmatrix} a_{11} & a_{12} \\ a_{21} & a_{22} \end{pmatrix}"),
    ("cases", "Absolute value", r"|x| = \begin{cases} x & \text{if } x \ge 0 \\ -x & \text{if } x < 0 \end{cases}"),
    ("greek", "Greek", r"\alpha\beta\gamma\delta\epsilon\zeta\eta\theta\iota\kappa\lambda\mu\nu\xi\pi\rho\sigma\tau\upsilon\varphi\chi\psi\omega"),
    ("letters", "Calligraphic, blackboard and fraktur", r"\mathcal{L}\,\mathcal{F}\,\mathcal{H} \quad \mathbb{R}\,\mathbb{C}\,\mathbb{N} \quad \mathfrak{g}\,\mathfrak{A}"),
];

/// The SVG of `tex` in `font`, without the metadata (source, tree, braille) that a page full of
/// specimens does not need. The speech stays in its `<title>`.
pub fn svg(tex: &str, font: MathFont) -> Result<String, String> {
    let options = mathra::Options { font, ..Default::default() };
    let svg = mathra::convert(tex, &options).map_err(|e| e.to_string())?.svg;
    Ok(strip(&svg))
}

/// The SVG of `tex` set inline, in mathra's own font: for the symbols a font lacks.
pub fn inline(tex: &str) -> Result<String, String> {
    let options = mathra::Options { display: false, ..Default::default() };
    Ok(strip(&mathra::convert(tex, &options).map_err(|e| e.to_string())?.svg))
}

fn strip(svg: &str) -> String {
    let mut s = svg.to_string();
    for (open, close) in [("<metadata>", "</metadata>"), ("<text ", "</text>")] {
        if let (Some(a), Some(b)) = (s.find(open), s.find(close)) {
            s.replace_range(a..b + close.len(), "");
        }
    }
    s.replace("<style>svg:root{color:#111}</style>", "")
}
