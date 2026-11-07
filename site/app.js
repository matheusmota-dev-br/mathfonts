// mathfonts: the theme switch, the grid's filters and equation, the compare selection and page.
// Every equation is an SVG mathra drew at build time: the page only swaps files. The Write page is
// the exception: it loads mathra's browser module and draws what the reader types.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const base = document.body.dataset.base || "";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode: the choice lasts for this page */ } },
  };

  // theme: system, light, dark, in turn
  const theme = $("#theme");
  if (theme) {
    const names = { system: "Theme: same as the system", light: "Theme: light", dark: "Theme: dark" };
    const show = (mode) => {
      theme.dataset.mode = mode;
      theme.title = names[mode];
      theme.setAttribute("aria-label", names[mode]);
      if (mode === "system") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", mode);
    };
    show(store.get("theme") || "system");
    theme.addEventListener("click", () => {
      const next = { system: "light", light: "dark", dark: "system" }[theme.dataset.mode];
      store.set("theme", next);
      show(next);
    });
  }

  const cache = new Map();
  const specimen = (slug, id) => {
    const key = `${slug}/${id}`;
    if (!cache.has(key)) cache.set(key, fetch(`${base}specimens/${key}.svg`).then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.status)))));
    return cache.get(key);
  };

  // mathra in the browser, for what the reader types: loaded the first time, each font once
  let mathraModule = null;
  const loadMathra = () =>
    (mathraModule ??= import(document.body.dataset.mathra).then(async (m) => {
      await m.init();
      return m;
    }));
  const fontIds = new Map();
  const loadFontOnce = (key, bytes) => {
    if (!fontIds.has(key)) {
      const id = Promise.all([loadMathra(), bytes()]).then(([m, b]) => m.loadFont(new Uint8Array(b)).id);
      id.catch(() => fontIds.delete(key)); // a failed download can be tried again
      fontIds.set(key, id);
    }
    return fontIds.get(key);
  };
  const fetchBytes = (url) => () => fetch(url).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`${url}: ${r.status}`))));

  // the grid
  const grid = $("#grid");
  if (grid) {
    const cards = $$(".card", grid);
    const count = $("#count");
    let style = "all";
    const filter = () => {
      let n = 0;
      for (const c of cards) {
        const show = style === "all" || c.dataset.style === style;
        c.hidden = !show;
        if (show) n++;
      }
      count.textContent = `${n} ${n === 1 ? "font" : "fonts"}`;
    };
    $$("[data-style-filter]").forEach((chip, _, all) =>
      chip.addEventListener("click", () => {
        all.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
        style = chip.dataset.styleFilter;
        filter();
      }),
    );
    $("#sort")?.addEventListener("change", (e) => {
      const by = e.target.value;
      const sorted = [...cards].sort((a, b) => (by === "coverage" ? b.dataset.coverage - a.dataset.coverage : 0) || a.dataset.name.localeCompare(b.dataset.name));
      grid.append(...sorted);
    });
    // the equation every card shows: one of the chips, drawn at build time, or what the reader
    // types, drawn here in every font as its file arrives
    const input = $("#grid-tex");
    const status = $("#grid-status");
    let round = 0; // a newer equation makes the renders still waiting for a font drop theirs
    let timer = 0;
    const live = async () => {
      const tex = input.value;
      const mine = ++round;
      $$("[data-equation]").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.tex === tex)));
      let m;
      try {
        m = await loadMathra();
      } catch (e) {
        status.textContent = `mathra did not load: ${e.message || e}`;
        return;
      }
      let done = 0;
      const waiting = cards.filter((c) => !fontIds.has(c.dataset.slug)).length;
      const progress = () => (status.textContent = done < waiting && mine === round ? `Loading the fonts: ${done} of ${waiting}…` : "");
      progress();
      await Promise.all(
        cards.map(async (card) => {
          const box = $(".spec", card);
          const fresh = !fontIds.has(card.dataset.slug);
          if (fresh) box.classList.add("loading");
          try {
            const font = await loadFontOnce(card.dataset.slug, fetchBytes(base + card.dataset.file));
            if (mine === round) box.innerHTML = m.texToSvg(tex, { font });
          } catch {
            /* the font did not load: keep the equation shown */
          }
          box.classList.remove("loading");
          if (fresh) done++;
          progress();
        }),
      );
    };
    input?.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(live, 150);
    });
    $$("[data-equation]").forEach((chip, _, all) =>
      chip.addEventListener("click", async () => {
        all.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
        clearTimeout(timer);
        round++;
        if (input) input.value = chip.dataset.tex;
        const id = chip.dataset.equation;
        await Promise.all(
          cards.map(async (card) => {
            const box = $(".spec", card);
            box.classList.add("loading");
            try {
              box.innerHTML = await specimen(card.dataset.slug, id);
            } catch {
              /* the file is missing: keep the one shown */
            }
            box.classList.remove("loading");
          }),
        );
      }),
    );
    // picking fonts to compare
    const picked = [];
    const bar = $("#comparebar");
    const update = () => {
      for (const b of $$("[data-pick]")) b.setAttribute("aria-pressed", String(picked.includes(b.dataset.pick)));
      bar.hidden = picked.length === 0;
      $("#compare-count").textContent = `${picked.length} of 3 picked`;
      $("#compare-go").href = `${base}compare.html?fonts=${picked.join(",")}`;
    };
    $$("[data-pick]").forEach((b) =>
      b.addEventListener("click", () => {
        const slug = b.dataset.pick;
        const i = picked.indexOf(slug);
        if (i >= 0) picked.splice(i, 1);
        else {
          if (picked.length === 3) picked.shift();
          picked.push(slug);
        }
        update();
      }),
    );
    $("#compare-clear")?.addEventListener("click", () => {
      picked.length = 0;
      update();
    });
  }

  // the compare page
  const table = $("#compare");
  if (table) {
    const data = JSON.parse($("#fonts-data").textContent);
    const equations = JSON.parse($("#equations-data").textContent);
    const asked = (new URLSearchParams(location.search).get("fonts") || "").split(",").filter((s) => data.some((f) => f.slug === s));
    const chosen = asked.length ? asked : ["stix-two-math", "euler-math", "fira-math"].filter((s) => data.some((f) => f.slug === s));
    const pickers = $$("select[data-column]");
    pickers.forEach((sel, i) => {
      sel.innerHTML = `<option value="">None</option>` + data.map((f) => `<option value="${f.slug}">${f.name}</option>`).join("");
      sel.value = chosen[i] || "";
      sel.addEventListener("change", draw);
    });
    function draw() {
      const slugs = pickers.map((s) => s.value).filter(Boolean);
      history.replaceState(null, "", `?fonts=${slugs.join(",")}`);
      table.style.setProperty("--n", Math.max(slugs.length, 1));
      const fonts = slugs.map((s) => data.find((f) => f.slug === s));
      let html = `<div class="head label"></div>` + fonts.map((f) => `<div class="head cell"><div><a href="${base}fonts/${f.slug}.html"><b>${f.name}</b></a><div class="sub">${f.base} · ${f.style}</div></div></div>`).join("");
      for (const [id, caption] of equations) {
        html += `<div class="label">${caption}</div>` + fonts.map((f) => `<div class="cell" data-cell="${f.slug}/${id}"></div>`).join("");
      }
      table.innerHTML = html;
      for (const cell of $$("[data-cell]", table)) {
        const [slug, id] = cell.dataset.cell.split("/");
        specimen(slug, id).then((svg) => (cell.innerHTML = svg), () => (cell.textContent = "not available"));
      }
    }
    draw();
  }

  // the Write page: mathra in the browser, in a font of the catalog or a file of the reader's
  const out = $("#write-out");
  if (out) {
    const fonts = JSON.parse($("#write-fonts").textContent);
    const examples = JSON.parse($("#write-examples-data").textContent);
    const select = $("#write-font");
    const fileGroup = $("#write-file-group");
    const fileInput = $("#write-file");
    const tex = $("#write-tex");
    const status = $("#write-status");
    const download = $("#write-download");
    const params = new URLSearchParams(location.search);
    let mathra = null;
    let font = null; // the id of the font in use; null while none is ready
    let fontName = "";
    let svg = "";
    let timer = 0;

    select.value = fonts.some((f) => f.slug === params.get("font")) ? params.get("font") : "stix-two-math";
    const start = fonts.find((f) => f.slug === select.value);
    tex.value = params.get("tex") ?? start?.sample ?? examples[0][1];
    $("#write-examples").innerHTML = examples.map(([caption], i) => `<button class="chip" type="button" data-example="${i}">${caption}</button>`).join("");
    $$("[data-example]").forEach((chip) =>
      chip.addEventListener("click", () => {
        tex.value = examples[chip.dataset.example][1];
        draw();
      }),
    );

    const remember = () => {
      const q = new URLSearchParams();
      if (select.value) q.set("font", select.value);
      q.set("tex", tex.value);
      history.replaceState(null, "", `?${q}`);
    };

    const say = (text, warn) => {
      status.textContent = text;
      status.classList.toggle("warn", Boolean(warn));
    };

    function draw() {
      clearTimeout(timer);
      remember();
      if (!mathra || font === null) return;
      try {
        const r = mathra.render(tex.value, { font });
        svg = r.svg;
        out.innerHTML = svg;
        const warnings = r.warnings || [];
        say(warnings.length ? warnings.join(" · ") : `In ${fontName}.`, warnings.length > 0);
        download.disabled = false;
      } catch (e) {
        say(String(e.message || e), true);
      }
    }

    async function use(key, name, bytes) {
      font = await loadFontOnce(key, bytes);
      fontName = name;
      draw();
    }

    async function chooseFile() {
      const file = fileInput.files[0];
      if (!file || !mathra) return;
      try {
        await use(`file:${file.name}:${file.size}:${file.lastModified}`, file.name, () => file.arrayBuffer());
      } catch (e) {
        font = null;
        out.innerHTML = "";
        say(`${file.name}: ${e.message || e}`, true);
        download.disabled = true;
      }
    }

    async function pick() {
      fileGroup.hidden = select.value !== "";
      if (!mathra) return;
      if (select.value === "") {
        font = null;
        if (fileInput.files[0]) return chooseFile();
        out.innerHTML = `<span class="sub">Choose a font file.</span>`;
        say("");
        download.disabled = true;
        return remember();
      }
      const f = fonts.find((x) => x.slug === select.value);
      out.classList.add("loading");
      say(`Loading ${f.name}…`);
      try {
        await use(f.slug, f.name, fetchBytes(base + f.file));
      } catch (e) {
        say(String(e.message || e), true);
      }
      out.classList.remove("loading");
    }

    select.addEventListener("change", pick);
    fileInput.addEventListener("change", chooseFile);
    tex.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(draw, 120);
    });
    download.addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
      a.download = "equation.svg";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });

    loadMathra()
      .then(async (m) => {
        mathra = m;
        await pick();
      })
      .catch((e) => {
        out.innerHTML = "";
        say(`mathra did not load: ${e.message || e}`, true);
      });
  }
})();
