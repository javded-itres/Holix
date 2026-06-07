/**
 * Helix Documentation Site — SPA with search, i18n, markdown rendering.
 */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const I18N = {
  en: {
    tagline: "Self-Improving Agent",
    search_placeholder: "Search documentation…",
    loading: "Loading…",
    home: "Home",
    docs: "Documentation",
    getting_started: "Getting Started",
    interfaces: "Interfaces",
    operations: "Operations",
    architecture: "Architecture",
    no_results: "No results found",
    hero_title: "Self-Improving",
    hero_title_accent: "AI Agent",
    hero_lead: "Persistent memory, skills, tool calling, MCP integration, and multiple interfaces — CLI, TUI, API gateway, and Telegram.",
    get_started: "Get Started",
    architecture_link: "Architecture",
    features_title: "Core Capabilities",
    docs_title: "Explore Documentation",
    footer: "Helix Agent · MIT License · Built from docs/en & docs/ru",
    feat_tools: "Tool Calling",
    feat_tools_desc: "Files, shell, web search, code execution, optional Playwright browser tools.",
    feat_memory: "Persistent Memory",
    feat_memory_desc: "SQLite conversations + ChromaDB semantic search across sessions.",
    feat_skills: "Skills System",
    feat_skills_desc: "Markdown skills with auto-generation and hub catalogs (ClawHub, Hermes).",
    feat_mcp: "MCP Integration",
    feat_mcp_desc: "Configure Model Context Protocol servers per agent and profile.",
    feat_models: "Multi-Provider",
    feat_models_desc: "Ollama, LiteLLM, OpenAI, Groq, and any OpenAI-compatible API.",
    feat_security: "Security",
    feat_security_desc: "API keys, rate limits, command whitelist, confirmation prompts.",
    feat_interfaces: "Interfaces",
    feat_interfaces_desc: "TUI, chat REPL, one-shot run, HTTP gateway, Telegram bot.",
  },
  ru: {
    tagline: "Самообучающийся агент",
    search_placeholder: "Поиск по документации…",
    loading: "Загрузка…",
    home: "Главная",
    docs: "Документация",
    getting_started: "Начало работы",
    interfaces: "Интерфейсы",
    operations: "Эксплуатация",
    architecture: "Архитектура",
    no_results: "Ничего не найдено",
    hero_title: "Самообучающийся",
    hero_title_accent: "AI-агент",
    hero_lead: "Постоянная память, навыки, вызов инструментов, MCP и несколько интерфейсов — CLI, TUI, API gateway и Telegram.",
    get_started: "Начать",
    architecture_link: "Архитектура",
    features_title: "Возможности",
    docs_title: "Разделы документации",
    footer: "Helix Agent · MIT License · Собрано из docs/en и docs/ru",
    feat_tools: "Инструменты",
    feat_tools_desc: "Файлы, shell, веб-поиск, выполнение кода, браузер Playwright.",
    feat_memory: "Память",
    feat_memory_desc: "SQLite + ChromaDB для семантического поиска по сессиям.",
    feat_skills: "Навыки",
    feat_skills_desc: "Markdown-навыки, автогенерация, каталоги Hub.",
    feat_mcp: "MCP",
    feat_mcp_desc: "Model Context Protocol серверы на агента и профиль.",
    feat_models: "Провайдеры",
    feat_models_desc: "Ollama, LiteLLM, OpenAI, Groq и OpenAI-совместимые API.",
    feat_security: "Безопасность",
    feat_security_desc: "API-ключи, rate limit, whitelist команд, подтверждения.",
    feat_interfaces: "Интерфейсы",
    feat_interfaces_desc: "TUI, chat REPL, run, HTTP gateway, Telegram.",
  },
};

const NAV_SECTIONS = {
  getting_started: ["installation", "start-here", "quickstart", "configuration"],
  interfaces: ["cli", "slash-commands", "tui", "hub", "gateway", "telegram", "browser-tools"],
  operations: ["security", "deployment", "doctor", "logs", "pypi", "troubleshooting", "user-guide"],
  architecture: ["architecture", "readme"],
};

let state = {
  lang: localStorage.getItem("helix-docs-lang") || "en",
  nav: [],
  searchIndex: [],
  activeSlug: null,
};

marked.setOptions({
  gfm: true,
  breaks: false,
});

/** GitHub-compatible heading slug (matches TOC anchors in USER_GUIDE.md). */
function githubSlug(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\u0400-\u04FF\s-]/g, "")
    .trim()
    .replace(/\s/g, "-");
}

function addHeadingIds(root) {
  root.querySelectorAll("h1,h2,h3,h4,h5,h6").forEach((h) => {
    if (!h.id) h.id = githubSlug(h.textContent);
  });
}

function wrapScrollableTables(root) {
  root.querySelectorAll("table").forEach((table) => {
    if (table.parentElement?.classList.contains("table-scroll")) return;
    const wrap = document.createElement("div");
    wrap.className = "table-scroll";
    table.replaceWith(wrap);
    wrap.appendChild(table);
  });
}

const MOBILE_BREAKPOINT = 900;

function isMobileLayout() {
  return window.innerWidth <= MOBILE_BREAKPOINT;
}

function syncHeaderHeight() {
  const header = $(".header");
  if (!header) return;
  const height = Math.ceil(header.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--header-h", `${height}px`);
}

function setupHeaderHeightSync() {
  const header = $(".header");
  if (!header) return;

  syncHeaderHeight();

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => syncHeaderHeight());
    observer.observe(header);
    return;
  }

  window.addEventListener("resize", syncHeaderHeight);
}

function setMobileSidebarOpen(open) {
  const sidebar = $("#sidebar");
  const backdrop = $("#sidebar-backdrop");
  const toggle = $("#menu-toggle");
  if (!sidebar) return;

  sidebar.classList.toggle("open", open);
  backdrop?.classList.toggle("open", open);
  document.body.classList.toggle("sidebar-open", open);
  if (backdrop) backdrop.hidden = !open;

  if (toggle) {
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "✕" : "☰";
  }
}

function closeMobileSidebar() {
  if (isMobileLayout()) setMobileSidebarOpen(false);
}

/** `#/page` → route; `#/` or `#` → home; `#anchor` → in-page scroll. */
function parseHash() {
  const raw = location.hash.slice(1);
  if (!raw || raw === "/") return { type: "home" };
  if (raw.startsWith("/")) {
    const path = raw.slice(1);
    if (!path) return { type: "home" };
    const slash = path.indexOf("/");
    const slug = slash >= 0 ? path.slice(0, slash) : path;
    const anchor = slash >= 0 ? path.slice(slash + 1) : null;
    if (!slug) return { type: "home" };
    return { type: "page", slug, anchor };
  }
  return { type: "anchor", anchor: raw };
}

function scrollToAnchor(anchor) {
  const el = document.getElementById(anchor);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  }
  return false;
}

function t(key) {
  return I18N[state.lang]?.[key] ?? I18N.en[key] ?? key;
}

function applyI18n() {
  $$("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (I18N[state.lang][key]) el.textContent = t(key);
  });
  const searchInput = $("#search-input");
  if (searchInput) searchInput.placeholder = t("search_placeholder");
  $$(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === state.lang);
  });
}

async function loadData() {
  const [navRes, indexRes] = await Promise.all([
    fetch("nav.json"),
    fetch("search-index.json"),
  ]);
  state.nav = await navRes.json();
  state.searchIndex = await indexRes.json();
}

function navItemsForLang() {
  return state.nav.map((item) => ({
    ...item,
    label: item[state.lang] || item.en,
    slug: item.slug,
  }));
}

function renderSidebar() {
  const nav = $("#sidebar-nav");
  const items = navItemsForLang();
  const bySlug = Object.fromEntries(items.map((i) => [i.slug, i]));

  let html = "";

  const addSection = (key, slugs) => {
    const sectionItems = slugs.map((s) => bySlug[s]).filter(Boolean);
    if (!sectionItems.length) return;
    html += `<div class="sidebar-section"><div class="sidebar-label">${t(key)}</div>`;
    for (const item of sectionItems) {
      const active = state.activeSlug === item.slug ? " active" : "";
      html += `<a href="#/${item.slug}" class="nav-link${active}" data-slug="${item.slug}">${item.label}</a>`;
    }
    html += "</div>";
  };

  html += `<div class="sidebar-section"><div class="sidebar-label">${t("docs")}</div>`;
  html += `<a href="#/" class="nav-link${!state.activeSlug ? " active" : ""}" data-slug="">${t("home")}</a>`;
  html += "</div>";

  addSection("getting_started", NAV_SECTIONS.getting_started);
  addSection("interfaces", NAV_SECTIONS.interfaces);
  addSection("operations", NAV_SECTIONS.operations);
  addSection("architecture", NAV_SECTIONS.architecture);

  nav.innerHTML = html;
}

function renderHome() {
  state.activeSlug = null;
  renderSidebar();
  const main = $("#main-content");

  const aspects = navItemsForLang().filter((i) => i.slug !== "readme");

  main.innerHTML = `
    <section class="hero">
      <div class="hero-badge">🧬 DNA-inspired · Agent Platform</div>
      <h1>${t("hero_title")} <span>${t("hero_title_accent")}</span></h1>
      <p class="hero-lead">${t("hero_lead")}</p>
      <div class="hero-actions">
        <a href="#/installation" class="btn btn-primary">${t("get_started")}</a>
        <a href="#/architecture" class="btn btn-ghost">${t("architecture_link")}</a>
      </div>
    </section>

    <section class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">⚡</div>
        <h3>${t("feat_tools")}</h3>
        <p>${t("feat_tools_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🧠</div>
        <h3>${t("feat_memory")}</h3>
        <p>${t("feat_memory_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📚</div>
        <h3>${t("feat_skills")}</h3>
        <p>${t("feat_skills_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔌</div>
        <h3>${t("feat_mcp")}</h3>
        <p>${t("feat_mcp_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🌐</div>
        <h3>${t("feat_models")}</h3>
        <p>${t("feat_models_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🛡️</div>
        <h3>${t("feat_security")}</h3>
        <p>${t("feat_security_desc")}</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🖥️</div>
        <h3>${t("feat_interfaces")}</h3>
        <p>${t("feat_interfaces_desc")}</p>
      </div>
    </section>

    <h2 class="section-title">${t("docs_title")}</h2>
    <div class="aspects-grid">
      ${aspects.map((a) => `
        <a href="#/${a.slug}" class="aspect-link">
          <span>${a.label}</span>
          <span class="arrow">→</span>
        </a>
      `).join("")}
    </div>

    <footer class="footer">${t("footer")}</footer>
  `;
}

async function renderDoc(slug, scrollAnchor = null) {
  state.activeSlug = slug;
  renderSidebar();
  const main = $("#main-content");
  const entry = state.searchIndex.find((e) => e.lang === state.lang && e.slug === slug);

  if (!entry) {
    main.innerHTML = `<p class="doc-error">Page not found: ${slug}</p>`;
    return;
  }

  main.innerHTML = `
    <div class="breadcrumb"><a href="#/">${t("home")}</a> / ${entry.title}</div>
    <div class="doc-loading">${t("loading")}</div>
  `;

  try {
    const res = await fetch(entry.file);
    if (!res.ok) throw new Error(res.statusText);
    const md = await res.text();
    const container = document.createElement("div");
    container.className = "doc-content";
    container.innerHTML = marked.parse(md);
    addHeadingIds(container);
    wrapScrollableTables(container);
    container.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href");
      if (!href || href.startsWith("http")) return;
      if (href.endsWith(".md")) {
        const name = href.replace(/^\.\//, "").replace(".md", "").toLowerCase().replace(/_/g, "-");
        a.setAttribute("href", `#/${name}`);
        return;
      }
      if (href.startsWith("#") && !href.startsWith("#/")) {
        a.addEventListener("click", (ev) => {
          ev.preventDefault();
          const id = href.slice(1);
          if (scrollToAnchor(id)) history.replaceState(null, "", `#${id}`);
        });
      }
    });

    main.replaceChildren();
    const breadcrumb = document.createElement("div");
    breadcrumb.className = "breadcrumb";
    breadcrumb.innerHTML = `<a href="#/">${t("home")}</a> / ${entry.title}`;
    const footer = document.createElement("footer");
    footer.className = "footer";
    footer.textContent = t("footer");
    main.append(breadcrumb, container, footer);

    document.title = `${entry.heading} — Helix Docs`;
    if (scrollAnchor && scrollToAnchor(scrollAnchor)) {
      history.replaceState(null, "", `#${scrollAnchor}`);
    } else if (!scrollAnchor) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } catch (err) {
    main.innerHTML = `<p class="doc-error">Failed to load: ${err.message}</p>`;
  }
}

async function handleAnchor(anchor) {
  if (scrollToAnchor(anchor)) return;

  if (state.activeSlug) {
    requestAnimationFrame(() => scrollToAnchor(anchor));
    return;
  }

  await renderDoc("user-guide", anchor);
}

function route() {
  closeMobileSidebar();
  closeSearch();
  const parsed = parseHash();
  if (parsed.type === "home") {
    renderHome();
    document.title = "Helix — Agent Documentation";
    return;
  }
  if (parsed.type === "anchor") {
    handleAnchor(parsed.anchor);
    return;
  }
  renderDoc(parsed.slug, parsed.anchor);
}

/* ─── Search ─── */

function tokenize(text) {
  return text.toLowerCase().split(/[^a-zа-яё0-9]+/i).filter((w) => w.length > 1);
}

function search(query) {
  if (!query.trim()) return [];
  const q = query.toLowerCase().trim();
  const words = tokenize(q);
  const langEntries = state.searchIndex.filter((e) => e.lang === state.lang);

  const scored = langEntries.map((entry) => {
    const title = entry.title.toLowerCase();
    const heading = (entry.heading || "").toLowerCase();
    const body = (entry.body || "").toLowerCase();
    let score = 0;

    if (title.includes(q)) score += 50;
    if (heading.includes(q)) score += 30;
    for (const w of words) {
      if (title.includes(w)) score += 15;
      if (heading.includes(w)) score += 8;
      if (body.includes(w)) score += 3;
    }
    return { entry, score };
  });

  return scored
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12)
    .map((s) => s.entry);
}

function highlightSnippet(body, query) {
  const idx = body.toLowerCase().indexOf(query.toLowerCase().split(" ")[0]);
  if (idx < 0) return body.slice(0, 120) + "…";
  const start = Math.max(0, idx - 40);
  return (start > 0 ? "…" : "") + body.slice(start, start + 140) + "…";
}

let closeSearch = () => {};

function setupSearch() {
  const input = $("#search-input");
  const results = $("#search-results");
  let activeIdx = -1;

  closeSearch = () => {
    results.classList.remove("open");
    results.innerHTML = "";
    activeIdx = -1;
    input.value = "";
    input.blur();
    requestAnimationFrame(() => requestAnimationFrame(syncHeaderHeight));
  };

  const setSearchOpen = (open) => {
    if (!open) {
      closeSearch();
      return;
    }
    results.classList.add("open");
    requestAnimationFrame(syncHeaderHeight);
  };

  const renderResults = (items) => {
    if (!items.length) {
      results.innerHTML = `<div class="search-empty">${t("no_results")}</div>`;
      setSearchOpen(true);
      return;
    }
    results.innerHTML = items
      .map(
        (e, i) => `
        <div class="search-result${i === activeIdx ? " active" : ""}" role="option" data-slug="${e.slug}" data-idx="${i}">
          <div class="search-result-title">${e.title}</div>
          <div class="search-result-snippet">${highlightSnippet(e.body, input.value)}</div>
        </div>
      `,
      )
      .join("");
    setSearchOpen(true);
  };

  input.addEventListener("input", () => {
    activeIdx = -1;
    const q = input.value;
    if (!q.trim()) {
      setSearchOpen(false);
      return;
    }
    renderResults(search(q));
  });

  input.addEventListener("keydown", (ev) => {
    const items = $$(".search-result", results);
    if (!items.length) return;

    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      items.forEach((el, i) => el.classList.toggle("active", i === activeIdx));
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      items.forEach((el, i) => el.classList.toggle("active", i === activeIdx));
    } else if (ev.key === "Enter" && activeIdx >= 0) {
      ev.preventDefault();
      const slug = items[activeIdx].dataset.slug;
      location.hash = `#/${slug}`;
      setSearchOpen(false);
      input.blur();
    } else if (ev.key === "Escape") {
      setSearchOpen(false);
    }
  });

  results.addEventListener("click", (ev) => {
    const el = ev.target.closest(".search-result");
    if (!el) return;
    location.hash = `#/${el.dataset.slug}`;
    setSearchOpen(false);
    input.value = "";
  });

  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".search-wrap")) setSearchOpen(false);
  });

  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === "k") {
      ev.preventDefault();
      input.focus();
      input.select();
    }
  });
}

function setupLangToggle() {
  $$(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.lang = btn.dataset.lang;
      localStorage.setItem("helix-docs-lang", state.lang);
      applyI18n();
      route();
    });
  });
}

function setupMobileMenu() {
  const toggle = $("#menu-toggle");
  const backdrop = $("#sidebar-backdrop");

  window.addEventListener("resize", () => {
    if (!isMobileLayout()) setMobileSidebarOpen(false);
  });

  toggle?.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const sidebar = $("#sidebar");
    const opening = !sidebar?.classList.contains("open");
    if (opening) closeSearch();
    setMobileSidebarOpen(opening);
  });

  backdrop?.addEventListener("click", () => setMobileSidebarOpen(false));

  document.addEventListener("click", (ev) => {
    if (
      isMobileLayout()
      && !ev.target.closest(".sidebar")
      && !ev.target.closest(".menu-toggle")
    ) {
      setMobileSidebarOpen(false);
    }
  });

  $("#sidebar-nav")?.addEventListener("click", (ev) => {
    if (ev.target.closest(".nav-link") && isMobileLayout()) {
      setMobileSidebarOpen(false);
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") setMobileSidebarOpen(false);
  });
}

async function init() {
  applyI18n();
  setupHeaderHeightSync();
  await loadData();
  setupSearch();
  setupLangToggle();
  setupMobileMenu();
  window.addEventListener("hashchange", route);
  route();
}

init().catch((err) => {
  $("#main-content").innerHTML = `<p class="doc-error">Failed to initialize: ${err.message}</p>`;
});