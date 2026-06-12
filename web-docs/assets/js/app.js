/**
 * Holix site — marketing landing + documentation SPA.
 */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const SLUG_RE = /^[a-z0-9-]+$/;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isValidSlug(slug) {
  return typeof slug === "string" && SLUG_RE.test(slug);
}

function setTextError(main, prefix, detail) {
  main.replaceChildren();
  const p = document.createElement("p");
  p.className = "doc-error";
  p.textContent = `${prefix}${detail}`;
  main.appendChild(p);
}

function makeBreadcrumb(homeLabel, docsLabel, title) {
  const el = document.createElement("div");
  el.className = "breadcrumb";
  const home = document.createElement("a");
  home.href = "/";
  home.textContent = homeLabel;
  const docs = document.createElement("a");
  docs.href = "/docs";
  docs.textContent = docsLabel;
  el.append(home, document.createTextNode(" / "), docs, document.createTextNode(` / ${title}`));
  return el;
}

const GITHUB_URL = "https://github.com/javded-itres/Holix";
const PYPI_URL = "https://pypi.org/project/Holix/";
const DONATE_URL = "https://boosty.to/javded/single-payment/donation/805721/target?share=target_link";
const SITE_URL = "https://holix-agent.ru";
const TELEGRAM_CHANNEL_URL = "https://t.me/holix_agent";
const YANDEX_METRIKA_ID = 109712139;
const OG_IMAGE_URL = `${SITE_URL}/assets/logo.svg`;

/** Root-absolute path for static assets and content (safe under /docs/* routes). */
function rootUrl(path) {
  if (!path) return "/";
  return path.startsWith("/") ? path : `/${path}`;
}

let seoMeta = null;

function upsertMeta(attr, key, content) {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href, attrs = {}) {
  if (!href) return;
  const selector = [`link[rel="${rel}"]`];
  Object.entries(attrs).forEach(([name, value]) => selector.push(`[${name}="${value}"]`));
  let el = document.head.querySelector(selector.join(""));
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
  Object.entries(attrs).forEach(([name, value]) => el.setAttribute(name, value));
}

function updateHreflang(path) {
  const canonical = `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  document.head.querySelectorAll('link[rel="alternate"][data-seo-managed="1"]').forEach((el) => el.remove());
  ["ru", "en", "x-default"].forEach((lang) => {
    const el = document.createElement("link");
    el.setAttribute("rel", "alternate");
    el.setAttribute("hreflang", lang);
    el.setAttribute("href", canonical);
    el.dataset.seoManaged = "1";
    document.head.appendChild(el);
  });
}

function pagePath(type, slug) {
  if (type === "doc" && slug) return `/docs/${slug}`;
  if (type === "docs-hub") return "/docs";
  return "/";
}

function updatePageSeo({ title, description, path = "/", keywords }) {
  const canonical = `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  const locale = state.lang === "ru" ? "ru_RU" : "en_US";

  document.title = title;
  document.documentElement.lang = state.lang === "ru" ? "ru" : "en";
  upsertMeta("name", "description", description);
  if (keywords) upsertMeta("name", "keywords", keywords);
  upsertLink("canonical", canonical);
  updateHreflang(path);
  upsertMeta("property", "og:title", title);
  upsertMeta("property", "og:description", description);
  upsertMeta("property", "og:url", canonical);
  upsertMeta("property", "og:type", "website");
  upsertMeta("property", "og:site_name", "Holix");
  upsertMeta("property", "og:locale", locale);
  upsertMeta("property", "og:image", OG_IMAGE_URL);
  upsertMeta("name", "twitter:card", "summary");
  upsertMeta("name", "twitter:title", title);
  upsertMeta("name", "twitter:description", description);
}

function seoDefaults() {
  return seoMeta?.defaults?.[state.lang] ?? seoMeta?.defaults?.en ?? {
    title: "Holix",
    description: "Holix AI agent documentation",
    keywords: "Holix, AI agent",
  };
}

function seoForView(viewKey) {
  const view = seoMeta?.views?.[viewKey]?.[state.lang]
    ?? seoMeta?.views?.[viewKey]?.en;
  if (view) return view;
  return seoDefaults();
}

function seoForPage(slug) {
  const page = seoMeta?.pages?.[slug]?.[state.lang]
    ?? seoMeta?.pages?.[slug]?.en;
  const defaults = seoDefaults();
  if (!page) return defaults;
  return {
    title: page.title || `${page.heading} — Holix`,
    description: page.description || defaults.description,
    keywords: page.keywords || defaults.keywords,
  };
}

function trackMetrikaPageView() {
  if (typeof ym !== "function") return;
  ym(YANDEX_METRIKA_ID, "hit", location.href, { title: document.title });
}

const I18N = {
  en: {
    tagline: "Self-Improving Agent",
    nav_home: "Home",
    nav_docs: "Documentation",
    nav_api: "API Reference",
    section_api: "API",
    search_placeholder: "Search documentation…",
    loading: "Loading…",
    docs: "Documentation",
    getting_started: "Getting Started",
    interfaces: "Interfaces",
    operations: "Operations",
    architecture: "Architecture",
    no_results: "No results found",
    mkt_badge_ru: "🇷🇺 Made in Russia · Russian software",
    mkt_hero_title: "Self-improving",
    mkt_hero_accent: "AI agent",
    mkt_hero_lead:
      "Holix is a production-ready agent platform: persistent memory, skills, tool calling, MCP, and CLI, TUI, API gateway, and Telegram — deploy on your infrastructure with local or cloud LLMs.",
    mkt_ru_title: "Russian engineering",
    mkt_ru_text:
      "Holix is developed in Russia by the IT-RES team. Open source (MIT), on-premise deployment, support for Ollama and LiteLLM — your data stays under your control. Domestic software you can audit and extend.",
    mkt_adv_title: "Why Holix",
    mkt_adv_1_t: "Learns from work",
    mkt_adv_1_d: "Successful tasks become reusable skills — the agent improves over time, not just one-off chats.",
    mkt_adv_2_t: "Remembers context",
    mkt_adv_2_d: "SQLite + ChromaDB: conversations and semantic search across sessions and profiles.",
    mkt_adv_3_t: "Enterprise-ready",
    mkt_adv_3_d: "API keys, rate limits, command whitelist, gateway auth, Docker and systemd deployment.",
    mkt_adv_4_t: "Your models",
    mkt_adv_4_d: "Ollama, LiteLLM, OpenAI-compatible APIs — no vendor lock-in for inference.",
    mkt_adv_5_t: "Isolated profiles",
    mkt_adv_5_d: "Separate .env, memory, Telegram bot, and gateway per profile — several users on one host without overlap.",
    mkt_profiles_title: "Profiles & workspace jail",
    mkt_profiles_text:
      "Each profile is a sandbox: own API keys, bot, gateway port, and conversation memory. Optional workspace jail locks file and terminal tools to one directory — the agent cannot leave the folder but works freely inside.",
    mkt_profiles_cta: "Profiles guide",
    mkt_feat_title: "Capabilities",
    mkt_use_title: "How teams use Holix",
    mkt_use_1_t: "Developer copilot",
    mkt_use_1_d: "Repo-aware agent in TUI: files, shell, MCP tools, slash commands, subagents.",
    mkt_use_2_t: "Automation & cron",
    mkt_use_2_d: "Scheduled jobs, gateway API, `holix run` in scripts and CI pipelines.",
    mkt_use_3_t: "Telegram assistant",
    mkt_use_3_d: "Mobile access with voice notes, file handling, and the same agent brain.",
    mkt_use_4_t: "API gateway",
    mkt_use_4_d: "OpenAI-compatible HTTP API for apps, bots, and internal services.",
    mkt_use_5_t: "Multi-user host",
    mkt_use_5_d: "One server — many profiles: separate bots, gateways, and optional folder jail per person.",
    mkt_how_title: "Interfaces",
    mkt_how_tui: "Full-screen TUI — daily work, tools, hub, MCP",
    mkt_how_chat: "Terminal REPL — lightweight chat",
    mkt_how_run: "One-shot queries and scripting",
    mkt_how_gw: "Background HTTP gateway + optional docs site",
    install_pypi: "pipx install Holix",
    install_pypi_hint: "PyPI · CLI command: helix",
    install_pypi_link: "PyPI",
    cta_docs: "Read documentation",
    cta_install: "Installation guide",
    donate: "Support the project",
    telegram_channel: "Telegram",
    tg_callout_title: "Stay in the loop",
    tg_callout_lead:
      "Subscribe to our Telegram channel for release notes, roadmap updates, tips, and early news about Holix.",
    tg_callout_cta: "Subscribe to @holix_agent",
    github: "GitHub",
    docs_hub_lead: "Guides, CLI reference, deployment, and troubleshooting.",
    docs_hub_title: "Documentation",
    api_callout_lead: "110+ HTTP endpoints: Hermes, chat, sessions, jobs, /api/holix/ management, admin, metrics — with auth, parameters, and curl examples.",
    api_callout_cta: "Open full API reference",
    footer: "Holix · Russian software · MIT License",
    feat_tools: "Tool calling",
    feat_tools_desc: "Files, shell, web, code, optional Playwright browser.",
    feat_memory: "Memory",
    feat_memory_desc: "SQLite + ChromaDB semantic search.",
    feat_skills: "Skills",
    feat_skills_desc: "Markdown skills, Hub catalogs, auto-generation.",
    feat_mcp: "MCP",
    feat_mcp_desc: "Model Context Protocol per agent and profile.",
    feat_models: "Multi-provider",
    feat_models_desc: "Ollama, LiteLLM, OpenAI, Groq, compatible APIs.",
    feat_security: "Security",
    feat_security_desc: "Auth, rate limits, whitelist, confirmations.",
    feat_interfaces: "Interfaces",
    feat_interfaces_desc: "TUI, chat, run, gateway, Telegram.",
    feat_profiles: "Profile isolation",
    feat_profiles_desc: "Per-profile secrets, gateway, Telegram; optional directory jail for tools.",
  },
  ru: {
    tagline: "Самообучающийся агент",
    nav_home: "Главная",
    nav_docs: "Документация",
    nav_api: "Справочник API",
    section_api: "API",
    search_placeholder: "Поиск по документации…",
    loading: "Загрузка…",
    docs: "Документация",
    getting_started: "Начало работы",
    interfaces: "Интерфейсы",
    operations: "Эксплуатация",
    architecture: "Архитектура",
    no_results: "Ничего не найдено",
    mkt_badge_ru: "🇷🇺 Российская разработка · отечественное ПО",
    mkt_hero_title: "Самообучающийся",
    mkt_hero_accent: "AI-агент",
    mkt_hero_lead:
      "Holix — платформа AI-агентов для продакшена: память, навыки, инструменты, MCP и интерфейсы CLI, TUI, API gateway и Telegram. Развёртывание на своей инфраструктуре с локальными или облачными LLM.",
    mkt_ru_title: "Отечественная разработка",
    mkt_ru_text:
      "Holix разработан в России командой IT-RES. Открытый исходный код (MIT), установка on-premise, поддержка Ollama и LiteLLM — данные остаются под вашим контролем. Российское ПО, которое можно проверить и расширить.",
    mkt_adv_title: "Преимущества",
    mkt_adv_1_t: "Учится на задачах",
    mkt_adv_1_d: "Успешные сценарии превращаются в навыки — агент развивается, а не забывает контекст после чата.",
    mkt_adv_2_t: "Помнит контекст",
    mkt_adv_2_d: "SQLite + ChromaDB: диалоги и семантический поиск по сессиям и профилям.",
    mkt_adv_3_t: "Готов к продакшену",
    mkt_adv_3_d: "API-ключи, rate limit, whitelist команд, auth gateway, Docker и systemd.",
    mkt_adv_4_t: "Ваши модели",
    mkt_adv_4_d: "Ollama, LiteLLM, OpenAI-совместимые API — без привязки к одному вендору.",
    mkt_adv_5_t: "Изолированные профили",
    mkt_adv_5_d: "Свой .env, память, Telegram и gateway на профиль — несколько пользователей на одном хосте без пересечений.",
    mkt_profiles_title: "Профили и workspace jail",
    mkt_profiles_text:
      "Каждый профиль — отдельная песочница: свои ключи API, бот, порт gateway и память диалогов. Опциональный workspace jail ограничивает файловые и терминальные инструменты одной директорией — агент не выходит из папки, но внутри работает свободно.",
    mkt_profiles_cta: "Руководство по профилям",
    mkt_feat_title: "Возможности",
    mkt_use_title: "Сценарии использования",
    mkt_use_1_t: "Помощник разработчика",
    mkt_use_1_d: "TUI с доступом к репозиторию: файлы, shell, MCP, слэш-команды, субагенты.",
    mkt_use_2_t: "Автоматизация",
    mkt_use_2_d: "Cron-задачи, API gateway, `holix run` в скриптах и CI.",
    mkt_use_3_t: "Telegram-бот",
    mkt_use_3_d: "Мобильный доступ, голосовые сообщения, файлы — тот же агент.",
    mkt_use_4_t: "API gateway",
    mkt_use_4_d: "HTTP API в формате OpenAI для приложений и внутренних сервисов.",
    mkt_use_5_t: "Несколько пользователей",
    mkt_use_5_d: "Один сервер — много профилей: отдельные боты, gateway и опциональный jail по папке на человека.",
    mkt_how_title: "Как работать с Holix",
    mkt_how_tui: "Полноэкранный TUI — основной интерфейс",
    mkt_how_chat: "Чат в терминале — лёгкий REPL",
    mkt_how_run: "Одиночные запросы и скрипты",
    mkt_how_gw: "Фоновый HTTP gateway",
    install_pypi: "pipx install Holix",
    install_pypi_hint: "PyPI · команда: helix",
    install_pypi_link: "PyPI",
    cta_docs: "Открыть документацию",
    cta_install: "Руководство по установке",
    donate: "Поддержать проект",
    telegram_channel: "Telegram",
    tg_callout_title: "Следите за развитием",
    tg_callout_lead:
      "Telegram-канал Holix: анонсы релизов, планы развития, советы по использованию и свежие новости проекта.",
    tg_callout_cta: "Подписаться на @holix_agent",
    github: "GitHub",
    docs_hub_lead: "Установка, справочник CLI, развёртывание и решение проблем.",
    docs_hub_title: "Документация",
    api_callout_lead: "110+ HTTP-эндпоинтов: Hermes, chat, sessions, jobs, /api/holix/ management, admin, metrics — auth, параметры и curl-примеры.",
    api_callout_cta: "Открыть полный справочник API",
    footer: "Holix · Российское ПО · MIT License",
    feat_tools: "Инструменты",
    feat_tools_desc: "Файлы, shell, веб, код, браузер Playwright.",
    feat_memory: "Память",
    feat_memory_desc: "SQLite + семантический поиск ChromaDB.",
    feat_skills: "Навыки",
    feat_skills_desc: "Markdown-навыки, Hub, автогенерация.",
    feat_mcp: "MCP",
    feat_mcp_desc: "Model Context Protocol на агента и профиль.",
    feat_models: "Провайдеры",
    feat_models_desc: "Ollama, LiteLLM, OpenAI, Groq и др.",
    feat_security: "Безопасность",
    feat_security_desc: "Auth, лимиты, whitelist, подтверждения.",
    feat_interfaces: "Интерфейсы",
    feat_interfaces_desc: "TUI, chat, run, gateway, Telegram.",
    feat_profiles: "Изоляция профилей",
    feat_profiles_desc: "Секреты, gateway и Telegram на профиль; опциональный jail по директории.",
  },
};

const NAV_SECTIONS = {
  getting_started: ["installation", "start-here", "quickstart", "configuration", "profiles"],
  api: ["gateway-api", "gateway"],
  interfaces: ["cli", "slash-commands", "execution-modes", "tui", "hub", "telegram", "telegram-multi-profile", "browser-tools"],
  operations: ["security", "terminal-security", "deployment", "doctor", "logs", "pypi", "troubleshooting", "user-guide"],
  architecture: ["architecture", "readme"],
};

let state = {
  lang: localStorage.getItem("helix-docs-lang") || "ru",
  viewMode: "marketing",
  nav: [],
  searchIndex: [],
  activeSlug: null,
};

marked.setOptions({ gfm: true, breaks: false });

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
  const chrome = $("#site-chrome");
  const header = $(".header");
  const target = chrome || header;
  if (!target) return;
  document.documentElement.style.setProperty("--header-h", `${Math.ceil(target.getBoundingClientRect().height)}px`);
}

function setupHeaderHeightSync() {
  const header = $(".header");
  if (!header) return;
  syncHeaderHeight();
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => syncHeaderHeight()).observe(header);
  } else {
    window.addEventListener("resize", syncHeaderHeight);
  }
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

/** `/` marketing · `/docs` hub · `/docs/slug` doc · `#anchor` in-page */
function migrateLegacyHash() {
  const hash = location.hash.slice(1);
  if (!hash.startsWith("/")) return;
  history.replaceState(null, "", hash);
  location.hash = "";
}

function parseRoute() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const hash = location.hash.slice(1);

  if (path === "/" && hash && !hash.startsWith("/")) {
    return { type: "anchor", anchor: hash };
  }
  if (path === "/") return { type: "marketing" };
  if (path === "/docs") return { type: "docs-hub" };
  if (path.startsWith("/docs/")) {
    const slug = path.slice(6);
    if (!slug || !isValidSlug(slug)) return { type: "docs-hub" };
    const anchor = hash && !hash.startsWith("/") ? hash : null;
    return { type: "doc", slug, anchor };
  }
  return { type: "marketing" };
}

function docHref(slug) {
  return `/docs/${slug}`;
}

function navigateTo(path, { replace = false } = {}) {
  const target = path.startsWith("/") ? path : `/${path}`;
  const current = `${location.pathname}${location.search}`;
  if (current === target) {
    route();
    return;
  }
  if (replace) history.replaceState(null, "", target);
  else history.pushState(null, "", target);
  route();
}

function openDocPage(slug) {
  if (!isValidSlug(slug)) return;
  navigateTo(docHref(slug));
}

function isInternalAppPath(pathname) {
  const path = pathname.replace(/\/+$/, "") || "/";
  return path === "/" || path === "/docs" || path.startsWith("/docs/");
}

function setupClientNavigation() {
  document.addEventListener("click", (ev) => {
    const link = ev.target.closest("a[href]");
    if (!link || link.target === "_blank" || ev.defaultPrevented) return;
    const url = new URL(link.href, location.origin);
    if (url.origin !== location.origin || !isInternalAppPath(url.pathname)) return;
    ev.preventDefault();
    navigateTo(`${url.pathname}${url.search}${url.hash}`);
  });
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

function footerHtml() {
  return `${t("footer")} · <a href="${SITE_URL}">holix-agent.ru</a> · <a href="${TELEGRAM_CHANNEL_URL}" target="_blank" rel="noopener noreferrer">${t("telegram_channel")}</a> · <a href="${GITHUB_URL}" target="_blank" rel="noopener noreferrer">${t("github")}</a>`;
}

function telegramCalloutHtml() {
  return `
    <section class="telegram-callout">
      <div class="telegram-callout-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="32" height="32"><path fill="currentColor" d="M9.78 15.28 9.5 19.8c.55 0 .79-.24 1.08-.52l2.59-2.48 5.37 3.94c.99.55 1.7.26 1.97-.9l3.53-16.57h.01c.32-1.48-.53-2.06-1.5-1.7L2.2 9.74c-1.45.57-1.43 1.39-.25 1.76l5.26 1.64L19.5 6.3c.66-.44 1.26-.2.77.26"/></svg>
      </div>
      <div class="telegram-callout-body">
        <h2>${t("tg_callout_title")}</h2>
        <p>${t("tg_callout_lead")}</p>
        <a href="${TELEGRAM_CHANNEL_URL}" class="btn btn-telegram" target="_blank" rel="noopener noreferrer">${t("tg_callout_cta")} ↗</a>
      </div>
    </section>`;
}

function setViewMode(mode) {
  state.viewMode = mode;
  const app = $(".app");
  app?.classList.toggle("marketing-layout", mode === "marketing");
  app?.classList.toggle("docs-layout", mode === "docs");
  $("#search-wrap")?.classList.toggle("is-hidden", mode === "marketing");
  $("#menu-toggle")?.classList.toggle("is-hidden", mode === "marketing");
  if (mode === "marketing") closeMobileSidebar();
  updateSiteNav();
}

function updateSiteNav() {
  $$(".site-nav-link").forEach((link) => {
    const view = link.dataset.view;
    let active = false;
    if (view === "marketing") {
      active = state.viewMode === "marketing";
    } else if (view === "api") {
      active = state.viewMode === "docs" && state.activeSlug === "gateway-api";
    } else if (view === "docs") {
      active = state.viewMode === "docs" && state.activeSlug !== "gateway-api";
    }
    link.classList.toggle("active", active);
  });
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
  const [navRes, indexRes, seoRes] = await Promise.all([
    fetch(rootUrl("nav.json")),
    fetch(rootUrl("search-index.json")),
    fetch(rootUrl("seo-meta.json")),
  ]);
  state.nav = await navRes.json();
  state.searchIndex = await indexRes.json();
  if (seoRes.ok) seoMeta = await seoRes.json();
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
      html += `<a href="${docHref(item.slug)}" class="nav-link${active}" data-slug="${item.slug}">${item.label}</a>`;
    }
    html += "</div>";
  };

  html += `<div class="sidebar-section"><div class="sidebar-label">${t("docs")}</div>`;
  html += `<a href="/docs" class="nav-link${state.activeSlug === null && state.viewMode === "docs" ? " active" : ""}">${t("docs_hub_title")}</a>`;
  html += "</div>";

  addSection("getting_started", NAV_SECTIONS.getting_started);
  addSection("section_api", NAV_SECTIONS.api);
  addSection("interfaces", NAV_SECTIONS.interfaces);
  addSection("operations", NAV_SECTIONS.operations);
  addSection("architecture", NAV_SECTIONS.architecture);

  nav.innerHTML = html;
}

function featureCardsHtml() {
  const feats = [
    ["feat_tools", "feat_tools_desc", "⚡"],
    ["feat_memory", "feat_memory_desc", "🧠"],
    ["feat_skills", "feat_skills_desc", "📚"],
    ["feat_mcp", "feat_mcp_desc", "🔌"],
    ["feat_models", "feat_models_desc", "🌐"],
    ["feat_security", "feat_security_desc", "🛡️"],
    ["feat_interfaces", "feat_interfaces_desc", "🖥️"],
    ["feat_profiles", "feat_profiles_desc", "🗂️"],
  ];
  return feats
    .map(
      ([title, desc, icon]) => `
      <div class="feature-card">
        <div class="feature-icon">${icon}</div>
        <h3>${t(title)}</h3>
        <p>${t(desc)}</p>
      </div>`,
    )
    .join("");
}

function renderMarketing() {
  state.activeSlug = null;
  setViewMode("marketing");
  renderSidebar();
  const main = $("#main-content");
  main.className = "content marketing-content";

  main.innerHTML = `
    <section class="hero marketing-hero">
      <div class="hero-badge hero-badge-ru">${t("mkt_badge_ru")}</div>
      <h1>${t("mkt_hero_title")} <span>${t("mkt_hero_accent")}</span></h1>
      <p class="hero-lead">${t("mkt_hero_lead")}</p>
      <div class="hero-install">
        <code class="hero-install-cmd">${t("install_pypi")}</code>
        <span class="hero-install-hint">${t("install_pypi_hint")}</span>
        <a href="${PYPI_URL}" class="hero-install-link" target="_blank" rel="noopener noreferrer">${t("install_pypi_link")} ↗</a>
      </div>
      <div class="hero-actions">
        <a href="/docs" class="btn btn-primary">${t("cta_docs")}</a>
        <a href="${docHref("gateway-api")}" class="btn btn-ghost">${t("nav_api")}</a>
        <a href="${docHref("installation")}" class="btn btn-ghost">${t("cta_install")}</a>
        <a href="${TELEGRAM_CHANNEL_URL}" class="btn btn-telegram" target="_blank" rel="noopener noreferrer">${t("tg_callout_cta")} ↗</a>
        <a href="${DONATE_URL}" class="btn btn-donate" target="_blank" rel="noopener noreferrer">♥ ${t("donate")}</a>
      </div>
    </section>

    ${telegramCalloutHtml()}

    <section class="ru-callout">
      <div class="ru-callout-flag" aria-hidden="true">🇷🇺</div>
      <div>
        <h2>${t("mkt_ru_title")}</h2>
        <p>${t("mkt_ru_text")}</p>
      </div>
    </section>

    <h2 class="section-title">${t("mkt_adv_title")}</h2>
    <div class="advantages-grid">
      <article class="advantage-card"><h3>${t("mkt_adv_1_t")}</h3><p>${t("mkt_adv_1_d")}</p></article>
      <article class="advantage-card"><h3>${t("mkt_adv_2_t")}</h3><p>${t("mkt_adv_2_d")}</p></article>
      <article class="advantage-card"><h3>${t("mkt_adv_3_t")}</h3><p>${t("mkt_adv_3_d")}</p></article>
      <article class="advantage-card"><h3>${t("mkt_adv_4_t")}</h3><p>${t("mkt_adv_4_d")}</p></article>
      <article class="advantage-card"><h3>${t("mkt_adv_5_t")}</h3><p>${t("mkt_adv_5_d")}</p></article>
    </div>

    <section class="profiles-callout">
      <div class="profiles-callout-icon" aria-hidden="true">🗂️</div>
      <div>
        <h2>${t("mkt_profiles_title")}</h2>
        <p>${t("mkt_profiles_text")}</p>
        <a href="${docHref("profiles")}" class="btn btn-ghost profiles-callout-link">${t("mkt_profiles_cta")} →</a>
      </div>
    </section>

    <h2 class="section-title">${t("mkt_feat_title")}</h2>
    <section class="features-grid">${featureCardsHtml()}</section>

    <h2 class="section-title">${t("mkt_use_title")}</h2>
    <div class="use-cases-grid">
      <article class="use-case-card"><span class="use-case-num">01</span><h3>${t("mkt_use_1_t")}</h3><p>${t("mkt_use_1_d")}</p></article>
      <article class="use-case-card"><span class="use-case-num">02</span><h3>${t("mkt_use_2_t")}</h3><p>${t("mkt_use_2_d")}</p></article>
      <article class="use-case-card"><span class="use-case-num">03</span><h3>${t("mkt_use_3_t")}</h3><p>${t("mkt_use_3_d")}</p></article>
      <article class="use-case-card"><span class="use-case-num">04</span><h3>${t("mkt_use_4_t")}</h3><p>${t("mkt_use_4_d")}</p></article>
      <article class="use-case-card"><span class="use-case-num">05</span><h3>${t("mkt_use_5_t")}</h3><p>${t("mkt_use_5_d")}</p></article>
    </div>

    <h2 class="section-title">${t("mkt_how_title")}</h2>
    <div class="how-grid">
      <div class="how-card"><code>holix tui</code><p>${t("mkt_how_tui")}</p></div>
      <div class="how-card"><code>holix chat-command</code><p>${t("mkt_how_chat")}</p></div>
      <div class="how-card"><code>holix run "…"</code><p>${t("mkt_how_run")}</p></div>
      <div class="how-card"><code>holix gateway start</code><p>${t("mkt_how_gw")}</p></div>
    </div>

    <section class="cta-band">
      <p>${t("install_pypi")}</p>
      <a href="/docs" class="btn btn-primary">${t("cta_docs")}</a>
    </section>

    <footer class="footer">${footerHtml()}</footer>
  `;

  const seo = seoForView("home");
  updatePageSeo({
    title: seo.title,
    description: seo.description,
    keywords: seo.keywords,
    path: "/",
  });
  trackMetrikaPageView();
}

function renderDocsHub() {
  state.activeSlug = null;
  setViewMode("docs");
  renderSidebar();
  const main = $("#main-content");
  main.className = "content";
  const aspects = navItemsForLang().filter((i) => i.slug !== "readme");
  const apiRef = aspects.find((a) => a.slug === "gateway-api");
  const hubAspects = aspects.filter((a) => a.slug !== "gateway-api");

  main.innerHTML = `
    <section class="docs-hub">
      <h1>${t("docs_hub_title")}</h1>
      <p class="docs-hub-lead">${t("docs_hub_lead")}</p>
      <div class="hero-install">
        <code class="hero-install-cmd">${t("install_pypi")}</code>
        <a href="${PYPI_URL}" class="hero-install-link" target="_blank" rel="noopener noreferrer">${t("install_pypi_link")} ↗</a>
      </div>
    </section>
    ${apiRef ? `
    <section class="api-callout">
      <div class="api-callout-body">
        <h2>${t("nav_api")}</h2>
        <p>${t("api_callout_lead")}</p>
        <a href="${docHref("gateway-api")}" class="btn btn-primary">${t("api_callout_cta")} →</a>
      </div>
    </section>` : ""}
    ${telegramCalloutHtml()}
    <div class="aspects-grid">
      ${hubAspects.map((a) => `
        <a href="${docHref(a.slug)}" class="aspect-link">
          <span>${a.label}</span>
          <span class="arrow">→</span>
        </a>
      `).join("")}
    </div>
    <footer class="footer">${footerHtml()}</footer>
  `;

  const seo = seoForView("docs-hub");
  updatePageSeo({
    title: seo.title,
    description: seo.description,
    keywords: seo.keywords,
    path: "/docs",
  });
  trackMetrikaPageView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function renderDoc(slug, scrollAnchor = null) {
  state.activeSlug = slug;
  setViewMode("docs");
  renderSidebar();
  const main = $("#main-content");
  main.className = "content";
  const entry = state.searchIndex.find((e) => e.lang === state.lang && e.slug === slug);

  if (!entry) {
    setTextError(main, "Page not found: ", slug);
    return;
  }

  main.replaceChildren(
    makeBreadcrumb(t("nav_home"), t("nav_docs"), entry.title),
    Object.assign(document.createElement("div"), { className: "doc-loading", textContent: t("loading") }),
  );

  try {
    const res = await fetch(rootUrl(entry.file));
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
        a.setAttribute("href", docHref(name));
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

    const footer = document.createElement("footer");
    footer.className = "footer";
    footer.innerHTML = footerHtml();
    main.replaceChildren(makeBreadcrumb(t("nav_home"), t("nav_docs"), entry.title), container, footer);

    const seo = seoForPage(slug);
    updatePageSeo({
      title: seo.title || `${entry.heading} — Holix`,
      description: seo.description,
      keywords: seo.keywords,
      path: `/docs/${slug}`,
    });
    trackMetrikaPageView();
    if (scrollAnchor && scrollToAnchor(scrollAnchor)) {
      history.replaceState(null, "", `#${scrollAnchor}`);
    } else if (!scrollAnchor) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } catch (err) {
    setTextError(main, "Failed to load: ", err?.message || "unknown error");
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
  migrateLegacyHash();
  closeMobileSidebar();
  closeSearch();
  const parsed = parseRoute();

  if (parsed.type === "marketing") {
    renderMarketing();
    return;
  }
  if (parsed.type === "docs-hub") {
    renderDocsHub();
    return;
  }
  if (parsed.type === "anchor") {
    setViewMode(state.viewMode === "marketing" ? "marketing" : "docs");
    handleAnchor(parsed.anchor);
    return;
  }
  renderDoc(parsed.slug, parsed.anchor);
}

function tokenize(text) {
  return text.toLowerCase().split(/[^a-zа-яё0-9]+/i).filter((w) => w.length > 1);
}

function search(query) {
  if (!query.trim()) return [];
  const q = query.toLowerCase().trim();
  const words = tokenize(q);
  const langEntries = state.searchIndex.filter((e) => e.lang === state.lang);

  return langEntries
    .map((entry) => {
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
    })
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12)
    .map((s) => s.entry);
}

function highlightSnippet(body, query) {
  const idx = body.toLowerCase().indexOf(query.toLowerCase().split(" ")[0]);
  if (idx < 0) return `${body.slice(0, 120)}…`;
  const start = Math.max(0, idx - 40);
  return `${start > 0 ? "…" : ""}${body.slice(start, start + 140)}…`;
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
        <div class="search-result${i === activeIdx ? " active" : ""}" role="option" data-slug="${escapeHtml(e.slug)}" data-idx="${i}">
          <div class="search-result-title">${escapeHtml(e.title)}</div>
          <div class="search-result-snippet">${escapeHtml(highlightSnippet(e.body, input.value))}</div>
        </div>`,
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
      navigateTo(docHref(items[activeIdx].dataset.slug));
      setSearchOpen(false);
      input.blur();
    } else if (ev.key === "Escape") {
      setSearchOpen(false);
    }
  });

  results.addEventListener("click", (ev) => {
    const el = ev.target.closest(".search-result");
    if (!el) return;
    navigateTo(docHref(el.dataset.slug));
    setSearchOpen(false);
    input.value = "";
  });

  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".search-wrap")) setSearchOpen(false);
  });

  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === "k" && state.viewMode === "docs") {
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
      notifyLangChange();
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
    if (isMobileLayout() && !ev.target.closest(".sidebar") && !ev.target.closest(".menu-toggle")) {
      setMobileSidebarOpen(false);
    }
  });

  $("#sidebar-nav")?.addEventListener("click", (ev) => {
    if (ev.target.closest(".nav-link") && isMobileLayout()) setMobileSidebarOpen(false);
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") setMobileSidebarOpen(false);
  });
}

function notifyLangChange() {
  document.dispatchEvent(new CustomEvent("helix-lang-change"));
}

async function init() {
  applyI18n();
  setupHeaderHeightSync();
  await loadData();
  setupSearch();
  setupLangToggle();
  setupMobileMenu();
  setupClientNavigation();
  window.addEventListener("popstate", route);
  window.addEventListener("hashchange", route);
  document.addEventListener("helix-open-doc", (ev) => {
    openDocPage(ev.detail?.slug);
  });
  route();
  try {
    const { initChatWidget } = await import("./chat-widget.js");
    await initChatWidget({ getLang: () => state.lang });
  } catch (err) {
    /* optional when static hosting without API */
    console.warn("Docs chat widget failed to load:", err);
  }
}

init().catch((err) => {
  const main = $("#main-content");
  if (main) setTextError(main, "Failed to initialize: ", err?.message || "unknown error");
});