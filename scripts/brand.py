#!/usr/bin/env python3
"""Draws the banner and the favicon from the catalog's own fonts.

The logo is written in Euler Math on a notebook line, with the red margin, and the Gaussian integral
under it is mathra's specimen in Euler Math. Every letter is an outline, so the banner looks the
same wherever it is shown, with no font to load.

Needs fontTools, and Chrome or Chromium for the PNGs. Run `mathfonts build` first: the integral
comes from dist/specimens.

    python3 scripts/brand.py   # writes site/brand/banner.svg and .png, site/favicon.svg, site/apple-touch-icon.png
"""

import re
import subprocess
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
PAPER, INK, MUTED, GUIDE, MARGIN = "#fdfdfb", "#111214", "#8a8f99", "#3b78d8", "#d24a5c"
W, H = 1280, 640
TAG = "OpenType math fonts, each one checked, every equation drawn by mathra"

_fonts = {}


def font(slug):
    if slug not in _fonts:
        d = ROOT / "fonts" / slug
        file = next(line.split('"')[1] for line in (d / "font.toml").read_text().splitlines() if line.startswith("file"))
        f = TTFont(d / file)
        _fonts[slug] = (f, f.getGlyphSet(), f.getBestCmap())
    return _fonts[slug]


def place(slug, char, x, base, xheight, fill, center=None):
    """`char` with its origin at (x, base), scaled so that the font's x-height is `xheight` px. Returns (svg, advance)."""
    f, glyphs, cmap = font(slug)
    name = cmap[ord(char)]
    pen = SVGPathPen(glyphs)
    glyphs[name].draw(pen)
    s = xheight / (f["OS/2"].sxHeight or 450)
    if center is not None:
        bounds = BoundsPen(glyphs)
        glyphs[name].draw(bounds)
        x0, _, x1, _ = bounds.bounds
        x = center - (x0 + x1) / 2 * s
    return f'<path d="{pen.getCommands()}" transform="translate({x:.1f} {base:.1f}) scale({s:.5f} {-s:.5f})" fill="{fill}"/>', glyphs[name].width * s


def text(slug, string, x, base, xheight, fill):
    out = []
    for ch in string:
        if ch == " ":
            x += xheight * 0.55
            continue
        path, advance = place(slug, ch, x, base, xheight, fill)
        out.append(path)
        x += advance
    return "".join(out), x


def flatten(svg, x, y, height, fill):
    """mathra's SVG as a group at (x, y), `height` px tall, with every <use> replaced by its path."""
    defs = dict(re.findall(r'<path id="([^"]+)" d="([^"]+)"', svg))
    vx, vy, vw, vh = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())

    def use(m):
        attrs = m.group(1)
        d = defs[re.search(r'href="#([^"]+)"', attrs).group(1)]
        tx = re.search(r'\bx="([^"]+)"', attrs)
        ty = re.search(r'\by="([^"]+)"', attrs)
        tr = re.search(r'transform="([^"]+)"', attrs)
        transform = f"translate({tx.group(1) if tx else 0} {ty.group(1) if ty else 0})" + (f" {tr.group(1)}" if tr else "")
        return f'<path d="{d}" transform="{transform}"/>'

    body = svg[svg.index("</defs>") + 7 : svg.rindex("</svg>")] if "</defs>" in svg else svg[svg.index(">") + 1 : svg.rindex("</svg>")]
    body = re.sub(r"<use ([^>]*)/>", use, body)
    body = re.sub(r"<title[^>]*>.*?</title>|<desc[^>]*>.*?</desc>", "", body).replace("currentColor", fill)
    k = height / vh
    return f'<g fill="{fill}" transform="translate({x} {y}) scale({k:.5f}) translate({-vx} {-vy})">{body}</g>'


def guides(base, xheight, cap, weight):
    return (
        f'<line x1="0" y1="{base}" x2="{W}" y2="{base}" stroke="{GUIDE}" stroke-width="{weight}"/>'
        f'<line x1="0" y1="{base - xheight}" x2="{W}" y2="{base - xheight}" stroke="{GUIDE}" stroke-opacity=".45" stroke-width="{weight * .75}" stroke-dasharray="{weight * 4} {weight * 3}"/>'
        f'<line x1="0" y1="{base - cap}" x2="{W}" y2="{base - cap}" stroke="{GUIDE}" stroke-opacity=".3" stroke-width="{weight * .75}" stroke-dasharray="{weight * 4} {weight * 3}"/>'
    )


def banner():
    body = []
    for y in range(64, H, 64):  # the site's background: faint guides every 64 px
        body.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{GUIDE}" stroke-opacity=".13"/>')
        body.append(f'<line x1="0" y1="{y - 22}" x2="{W}" y2="{y - 22}" stroke="{GUIDE}" stroke-opacity=".06"/>')
    body.append(f'<line x1="120" y1="0" x2="120" y2="{H}" stroke="{MARGIN}" stroke-width="3" stroke-opacity=".75"/>')
    base = 340
    body.append(guides(base, 92, 128, 2.4))
    math, end = text("euler-math", "math", 170, base, 92, INK)
    fonts, _ = text("euler-math", "fonts", end, base, 92, GUIDE)
    tag, _ = text("fira-math", TAG, 172, 420, 15.5, MUTED)
    gauss = (ROOT / "dist/specimens/euler-math/gaussian.svg").read_text()
    body += [math, fonts, tag, flatten(gauss, 168, 452, 100, INK)]
    for x, y in [(26, 26), (W - 48, 26), (26, H - 48), (W - 48, H - 48)]:  # the corner marks of the printed grid
        body.append(f'<rect x="{x}" y="{y}" width="22" height="22" fill="{INK}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"><title>mathfonts</title><rect width="{W}" height="{H}" fill="{PAPER}"/>{"".join(body)}</svg>\n'


def favicon():
    body = [
        f'<rect width="64" height="64" rx="6" fill="{PAPER}"/>',
        f'<line x1="14" y1="0" x2="14" y2="64" stroke="{MARGIN}" stroke-width="3"/>',
        f'<line x1="0" y1="50" x2="64" y2="50" stroke="{GUIDE}" stroke-width="3"/>',
        f'<line x1="0" y1="27" x2="64" y2="27" stroke="{GUIDE}" stroke-opacity=".45" stroke-width="2"/>',
        place("euler-math", "∂", 0, 50, 21, INK, center=38)[0],
    ]
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{"".join(body)}</svg>\n'


CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]


def png(svg, out, width, height):
    """Rasterizes with headless Chrome: ImageMagick's own SVG renderer gets strokes and positions wrong."""
    page = out.with_suffix(".tmp.html")
    page.write_text(f'<!doctype html><style>html,body{{margin:0;background:transparent}}img{{display:block;width:{width}px;height:{height}px}}</style><img src="{svg.name}">')
    try:
        for chrome in CHROME:
            try:
                subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000", f"--window-size={width},{height}", f"--screenshot={out}", page.resolve().as_uri()], check=True, capture_output=True)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        raise SystemExit("needs Chrome or Chromium to make the PNGs")
    finally:
        page.unlink()


def main():
    brand = ROOT / "site/brand"
    brand.mkdir(parents=True, exist_ok=True)
    (brand / "banner.svg").write_text(banner())
    (ROOT / "site/favicon.svg").write_text(favicon())
    png(brand / "banner.svg", brand / "banner.png", W, H)
    png(ROOT / "site/favicon.svg", ROOT / "site/apple-touch-icon.png", 180, 180)
    print("site/brand/banner.svg, site/brand/banner.png, site/favicon.svg, site/apple-touch-icon.png")


if __name__ == "__main__":
    main()
