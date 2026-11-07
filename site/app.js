// mathfonts: the theme switch, the grid's filters and equation, the compare selection and page.
// Every equation is an SVG mathra drew at build time: the page only swaps files.
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
    // the equation every card shows
    $$("[data-equation]").forEach((chip, _, all) =>
      chip.addEventListener("click", async () => {
        all.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
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
})();
