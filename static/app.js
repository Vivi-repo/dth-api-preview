// Small, framework-free client for the DTH App Preview API.
//
// This file is intentionally simple: plain fetch() calls, plain DOM
// manipulation, no build step, no state management library. The real app
// will be native SwiftUI -- this page exists only to prove the backend
// works, so it favors clarity over structure a bigger app would want.

// Base URL for API calls. Empty string means "same origin as this page"
// (relative paths like `/sections` resolve against wherever index.html is
// served from). Set by the inline script in index.html -- see the comment
// there for when to change it.
const API_BASE_URL = window.API_BASE_URL || "";

// ---- Element references -------------------------------------------------

const sectionTabsEl = document.getElementById("section-tabs");
const articleListEl = document.getElementById("article-list");
const feedStatusEl = document.getElementById("feed-status");
const loadMoreBtn = document.getElementById("load-more-btn");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");

const feedViewEl = document.getElementById("feed-view");
const articleViewEl = document.getElementById("article-view");
const articleContentEl = document.getElementById("article-content");
const backBtn = document.getElementById("back-btn");

// ---- App state ------------------------------------------------------------
// `activeSectionId` and `searchQuery` are mutually exclusive: picking a
// section tab clears any active search, and submitting a search clears the
// active section tab. That keeps the feed's meaning unambiguous ("either
// browsing a section or looking at search results", never both at once).

const state = {
  page: 1,
  perPage: 10,
  totalPages: 1,
  activeSectionId: null, // null means the "All" tab
  searchQuery: null,
};

// ---- Small DOM helpers ------------------------------------------------
// We build elements with createElement/textContent (not innerHTML) for any
// text that came from the API, so nothing an article's title/author/excerpt
// contains can be interpreted as HTML. The one deliberate exception is the
// article body, which the backend has already stripped of scripts/styles
// specifically so it's safe to render as HTML (see app/transform.py).

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ---- Sections (top tab bar) --------------------------------------------

async function loadSections() {
  try {
    const response = await fetch(`${API_BASE_URL}/sections`);
    if (!response.ok) throw new Error("bad status");
    const data = await response.json();
    renderSectionTabs(data.sections);
  } catch (err) {
    // Section tabs are a nice-to-have; if they fail to load we just show
    // "All" and let the feed itself report any real connectivity problem.
    renderSectionTabs([]);
  }
}

function renderSectionTabs(sections) {
  sectionTabsEl.innerHTML = "";

  const allBtn = el("button", "active", "All");
  allBtn.addEventListener("click", () => selectSection(null, allBtn));
  sectionTabsEl.appendChild(allBtn);

  // A news app's tab bar only has room for a handful of sections. DTH's
  // WordPress site has 200+ top-level categories (many are old one-off
  // special-coverage tags), so we only show the ones with the most
  // articles -- in practice that reliably surfaces the real sections
  // (Sports, Opinion, University, ...) since they dominate by volume.
  const topSections = sections.slice(0, 8);

  for (const section of topSections) {
    const btn = el("button", "", section.name);
    btn.addEventListener("click", () => selectSection(section.id, btn));
    sectionTabsEl.appendChild(btn);
  }
}

function selectSection(sectionId, clickedBtn) {
  state.activeSectionId = sectionId;
  state.searchQuery = null;
  searchInput.value = "";

  for (const btn of sectionTabsEl.children) {
    btn.classList.toggle("active", btn === clickedBtn);
  }

  resetAndLoadFeed();
}

// ---- Search -------------------------------------------------------------

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  state.searchQuery = query || null;
  state.activeSectionId = null;
  for (const btn of sectionTabsEl.children) {
    btn.classList.toggle("active", btn.textContent === "All");
  }
  resetAndLoadFeed();
});

// ---- Feed (home screen) -------------------------------------------------

function resetAndLoadFeed() {
  state.page = 1;
  state.totalPages = 1;
  articleListEl.innerHTML = "";
  loadArticlesPage();
}

function buildFeedUrl() {
  const params = new URLSearchParams({
    page: state.page,
    per_page: state.perPage,
  });

  if (state.searchQuery) {
    params.set("q", state.searchQuery);
    return `${API_BASE_URL}/search?${params.toString()}`;
  }
  if (state.activeSectionId !== null) {
    params.set("section", state.activeSectionId);
  }
  return `${API_BASE_URL}/articles?${params.toString()}`;
}

async function loadArticlesPage() {
  loadMoreBtn.hidden = true;
  feedStatusEl.textContent = "Loading...";
  feedStatusEl.classList.remove("error");

  try {
    const response = await fetch(buildFeedUrl());
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Something went wrong.");
    }

    for (const article of data.articles) {
      articleListEl.appendChild(renderArticleCard(article));
    }

    state.totalPages = data.total_pages;

    if (data.articles.length === 0 && state.page === 1) {
      feedStatusEl.textContent = "No articles found.";
    } else {
      feedStatusEl.textContent = "";
    }

    loadMoreBtn.hidden = state.page >= state.totalPages;
  } catch (err) {
    feedStatusEl.textContent =
      "Couldn't load articles right now. Please try again in a moment.";
    feedStatusEl.classList.add("error");
  }
}

loadMoreBtn.addEventListener("click", () => {
  state.page += 1;
  loadArticlesPage();
});

function renderArticleCard(article) {
  const card = el("li", "article-card");
  card.tabIndex = 0;
  card.setAttribute("role", "button");

  if (article.image_url) {
    const img = el("img");
    img.src = article.image_url;
    img.alt = "";
    card.appendChild(img);
  }

  const body = el("div", "card-body");
  if (article.section) {
    body.appendChild(el("span", "section-label", article.section));
  }
  body.appendChild(el("h2", "", article.title));
  if (article.excerpt) {
    body.appendChild(el("p", "excerpt", article.excerpt));
  }

  const byline = [article.author, formatDate(article.published_at)]
    .filter(Boolean)
    .join(" · "); // " · "
  body.appendChild(el("p", "byline", byline));

  card.appendChild(body);
  card.addEventListener("click", () => openArticle(article.id));
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") openArticle(article.id);
  });

  return card;
}

// ---- Article detail screen ----------------------------------------------

async function openArticle(articleId) {
  showArticleView();
  articleContentEl.innerHTML = "";
  articleContentEl.appendChild(el("p", "status", "Loading..."));

  try {
    const response = await fetch(`${API_BASE_URL}/articles/${articleId}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Something went wrong.");
    }

    renderArticleDetail(data);
  } catch (err) {
    articleContentEl.innerHTML = "";
    articleContentEl.appendChild(
      el("p", "status error", "Couldn't load this article. Please try again.")
    );
  }
}

function renderArticleDetail(article) {
  articleContentEl.innerHTML = "";
  const wrapper = el("div", "article-detail");

  if (article.image_url) {
    const img = el("img");
    img.src = article.image_url;
    img.alt = "";
    wrapper.appendChild(img);
  }
  if (article.section) {
    wrapper.appendChild(el("span", "section-label", article.section));
  }
  wrapper.appendChild(el("h1", "", article.title));

  const byline = [article.author, formatDate(article.published_at)]
    .filter(Boolean)
    .join(" · ");
  wrapper.appendChild(el("p", "byline", byline));

  // The backend has already stripped scripts/styles/embedded widgets from
  // this HTML (see transform._clean_content_html), so it's safe to render
  // directly -- this is the one place in the app that uses innerHTML with
  // API-sourced content.
  const body = el("div", "body-text");
  body.innerHTML = article.content_html;
  wrapper.appendChild(body);

  articleContentEl.appendChild(wrapper);
}

backBtn.addEventListener("click", showFeedView);

function showArticleView() {
  feedViewEl.hidden = true;
  articleViewEl.hidden = false;
  // Hide the search bar/section tabs while reading so the article feels
  // like its own screen, not the feed with an overlay on top.
  searchForm.hidden = true;
  sectionTabsEl.hidden = true;
}

function showFeedView() {
  articleViewEl.hidden = true;
  feedViewEl.hidden = false;
  searchForm.hidden = false;
  sectionTabsEl.hidden = false;
}

// ---- Boot -----------------------------------------------------------------

loadSections();
loadArticlesPage();
