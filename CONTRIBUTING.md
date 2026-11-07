# Adding a font

If you made an OpenType math font, finished or not, you can add it with a pull request. A check runs on it with mathra and comments a report: what passed, how many math symbols the font has and which ones it lacks. A draft pull request gets the report too, so you can use it to test a font you are still drawing.

## 1. A folder

Create `fonts/<slug>/`, where the slug is the font's name in lowercase with hyphens (`euler-math`). Put three files in it:

- **the font**, `.otf` or `.ttf`, as you publish it. Do not subset or convert it: under the OFL, a changed file cannot keep a reserved font name.
- **`LICENSE.txt`**, the license's full text with your copyright notice.
- **`font.toml`**:

```toml
name     = "Euler Math"
file     = "Euler-Math.otf"
license  = "OFL-1.1"       # OFL-1.1, GUST-Font-License, Apache-2.0 or MIT
style    = "handwritten"   # serif, sans, tex or handwritten
base     = "Euler"         # the text family it goes with
designer = "Hermann Zapf"  # optional
source   = "https://ctan.org/pkg/euler-math"
sample   = '\nabla \times \vec{B} = \mu_0 \vec{J}'   # optional: shown first on its page

[upstream]                 # optional: where the file can be downloaded again
url  = "https://mirrors.ctan.org/fonts/euler-math.zip"
path = "euler-math/Euler-Math.otf"   # the file inside the zip; leave it out for a font URL
```

With `[upstream]`, a weekly job downloads the file again and tells the maintainers when you publish a new version.

## 2. The pull request

Open it against `main`. You can do everything on GitHub's website: add the files with "Add file → Upload files" in your fork.

## 3. The report

In a few minutes, the check comments on the pull request. These must pass:

- the file opens as a font and has a **MATH table** (a text font cannot set a fraction or a radical);
- the license is one of those above, and `LICENSE.txt` is there;
- mathra loads the font;
- no other font in the catalog has its name.

These are information, not requirements:

- whether mathra draws the 44 equations of its gallery in your font;
- how many of the 2101 math symbols mathra draws it has, block by block, with examples of the missing ones.

Each new commit runs the check again and updates the same comment.

## 4. The merge

When it passes and a maintainer merges it, the font gets its own page with your name and joins the grid and the comparison.

## Checking locally

```sh
cargo run --release -- check fonts/<slug>
cargo run --release -- check fonts/<slug> --report report.md   # the same Markdown the check comments
cargo run --release -- build && python3 -m http.server -d dist  # the site, with your font
```
