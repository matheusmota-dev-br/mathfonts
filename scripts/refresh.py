#!/usr/bin/env python3
"""Downloads each font again from where its font.toml says it comes from ([upstream]) and compares
it with the file in the catalog. Prints what changed; with --update, replaces the files.

    scripts/refresh.py                  compare every font, exit 1 if any changed or failed
    scripts/refresh.py euler-math       only these fonts
    scripts/refresh.py --update         also write the new files (then run mathfonts check)
    scripts/refresh.py --markdown FILE  also write the result as Markdown, for an issue

Standard library only.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import tomllib
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENT = "mathfonts-refresh"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def upstream_file(upstream: dict, cache: dict[str, bytes]) -> bytes:
    url = upstream["url"]
    if url not in cache:
        cache[url] = fetch(url)
    data = cache[url]
    path = upstream.get("path")
    if not path:
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(path)


def main(argv: list[str]) -> int:
    update = "--update" in argv
    markdown = argv[argv.index("--markdown") + 1] if "--markdown" in argv else None
    names = [a for a in argv if not a.startswith("--") and a != markdown]
    folders = sorted(p for p in (ROOT / "fonts").iterdir() if p.is_dir() and (not names or p.name in names))
    cache: dict[str, bytes] = {}
    rows = []
    for folder in folders:
        meta = tomllib.loads((folder / "font.toml").read_text())
        upstream = meta.get("upstream")
        if not upstream:
            rows.append((folder.name, "no upstream", ""))
            continue
        ours = (folder / meta["file"]).read_bytes()
        try:
            theirs = upstream_file(upstream, cache)
        except Exception as error:  # a download or a zip that changed shape: report it, go on
            rows.append((folder.name, "failed", str(error)))
            continue
        if theirs == ours:
            rows.append((folder.name, "same", ""))
            continue
        old, new = hashlib.sha256(ours).hexdigest()[:12], hashlib.sha256(theirs).hexdigest()[:12]
        rows.append((folder.name, "changed", f"{len(ours)} → {len(theirs)} bytes, {old} → {new}"))
        if update:
            (folder / meta["file"]).write_bytes(theirs)

    for name, state, detail in rows:
        print(f"{state:12} {name} {detail}".rstrip())
    changed = [r for r in rows if r[1] in ("changed", "failed")]
    if markdown:
        lines = ["## Upstream check", ""]
        if not changed:
            lines.append(f"All {len(rows)} fonts are the same as their upstream files.")
        else:
            lines += ["| Font | State | Detail |", "|---|---|---|"]
            lines += [f"| `{n}` | {s} | {d} |" for n, s, d in changed]
            lines += ["", "Run `scripts/refresh.py --update` and `mathfonts check`, then open a pull request with the new files."]
        pathlib.Path(markdown).write_text("\n".join(lines) + "\n")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
