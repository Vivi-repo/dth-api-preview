# DTH App Preview — Backend

A small FastAPI backend that wraps [The Daily Tar Heel](https://www.dailytarheel.com)'s
public WordPress REST API and exposes a clean, mobile-app-friendly API on top of
it, plus a static HTML/CSS/JS page (served at `/`) that previews what an iOS
app built on this backend could look like.

**This is an unofficial, independent prototype.** It is not affiliated with,
endorsed by, or built in partnership with The Daily Tar Heel. It only reads
their public WordPress API, the same data their own website renders from.

---

## 1. Running it locally

Requires Python 3.11+.

```bash
python -m venv .venv

# macOS/Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/** in a browser for the app preview, or
**http://127.0.0.1:8000/docs** for the interactive (Swagger) API docs.

Run the tests with:

```bash
pytest
```

The test suite never calls the real DTH website — see [section 5](#5-testing).

---

## 2. Endpoints

All responses are JSON. All list endpoints accept `page` (default `1`) and
`per_page` (default `10`, max `50`).

### `GET /articles`

Latest articles, newest first. Optional `?section={id}` filters to one
section (see `GET /sections` for ids).

```
GET /articles?per_page=2
```
```json
{
  "page": 1,
  "per_page": 2,
  "total": 81947,
  "total_pages": 40974,
  "articles": [
    {
      "id": 484388,
      "title": "Singer-songwriter and UNC alumna Tift Merritt awarded 2026 Thomas Wolfe Prize",
      "author": "Harper Senff",
      "published_at": "2026-10-06T19:55:37",
      "section": "Lifestyle",
      "section_id": 6975,
      "excerpt": "Merritt, a Grammy nominee and former UNC creative writing student, delivered the Thomas Wolfe Lecture in Hill Hall on Sept. 29.",
      "image_url": "https://dailytarheel.com/wp-content/uploads/2026/09/C36A2054.jpg",
      "url": "https://dailytarheel.com/484388/lifestyle/lifestyle-thomas-wolfe-tift-merritt/"
    }
  ]
}
```

### `GET /articles/{id}`

A single article, including full cleaned HTML content.

```
GET /articles/484388
```
```json
{
  "id": 484388,
  "title": "Singer-songwriter and UNC alumna Tift Merritt awarded 2026 Thomas Wolfe Prize",
  "author": "Harper Senff",
  "published_at": "2026-10-06T19:55:37",
  "section": "Lifestyle",
  "section_id": 6975,
  "excerpt": "Merritt, a Grammy nominee and former UNC creative writing student...",
  "image_url": "https://dailytarheel.com/wp-content/uploads/2026/09/C36A2054.jpg",
  "url": "https://dailytarheel.com/484388/lifestyle/lifestyle-thomas-wolfe-tift-merritt/",
  "content_html": "<p>Tift Merritt has traveled from small clubs in Chapel Hill and Raleigh to stages around the world...</p>"
}
```

A nonexistent id returns a clean `404`:
```json
{ "error": "The requested article does not exist." }
```

### `GET /sections`

The list of top-level sections, for a tab bar.

```
GET /sections
```
```json
{
  "sections": [
    { "id": 6962, "name": "Sports", "slug": "sports", "article_count": 15587 },
    { "id": 6983, "name": "Opinion", "slug": "opinion", "article_count": 10210 },
    { "id": 6996, "name": "PageOne", "slug": "pageone", "article_count": 7188 },
    { "id": 6951, "name": "University", "slug": "university", "article_count": 6682 }
  ]
}
```

### `GET /search?q=`

Keyword search across articles, same shape as `GET /articles`.

```
GET /search?q=basketball&per_page=1
```
```json
{
  "page": 1,
  "per_page": 1,
  "total": 6777,
  "total_pages": 6777,
  "articles": [
    {
      "id": 484389,
      "title": "Column: UNC’s overenrollment is not sustainable for a college education",
      "author": "Lily Galapon",
      "published_at": "2026-10-05T19:06:37",
      "section": "Columns",
      "section_id": 6985,
      "excerpt": "“With all the cuts we are making, UNC is apparently “saving” more than 85 million dollars...",
      "image_url": "https://dailytarheel.com/wp-content/uploads/2026/10/Opinion-column.jpg",
      "url": "https://dailytarheel.com/484389/opinion/columns/column-uncs-overenrollment/"
    }
  ]
}
```

---

## 3. Verifying the upstream API before writing any code

Before building anything, I confirmed the API was actually reachable:

```
GET https://www.dailytarheel.com/wp-json/wp/v2/posts  ->  200 OK
```

It returns standard WordPress post objects (`id`, `title.rendered`,
`content.rendered`, `excerpt.rendered`, `date`, `link`, `categories`,
`featured_media`), plus `X-WP-Total` / `X-WP-TotalPages` response headers for
pagination. That part matched the generic WordPress REST API docs. Two things
didn't, and both shaped the design:

**The standard `author` endpoint is disabled.** `/wp-json/wp/v2/users/*`
returns a 404 (`rest_no_route`), so the usual `?_embed` trick of pulling the
author's display name from `_embedded.author` doesn't work here. Instead, DTH
tags every post with a **custom taxonomy called `staff_name`** holding the
byline — it shows up embedded alongside categories and tags inside
`_embedded['wp:term']`. `app/transform.py`'s `_extract_author` reads it from
there. This was the single biggest surprise in the whole project, and worth
knowing: don't assume a WordPress site's REST API follows the textbook shape
just because it's WordPress.

**Categories include internal, non-editorial ones.** DTH has 300+ categories
total; most posts are tagged with a real section (Sports, University, ...)
*plus* an invisible one named `weight-N` that their CMS appears to use for
manually ranking stories on the homepage. Left alone, a post's "section"
could come back as `"weight-3"`, which means nothing to a reader. `/sections`
only returns top-level categories and filters out anything whose slug starts
with `weight-`; article summaries do the same when picking a primary section
(see `wp_client.fetch_top_level_sections` and `transform._extract_section`).

---

## 4. Design decisions

**Caching (in-memory, TTL-based).** `app/cache.py` is a small per-process
dict cache, no Redis or database. Two different TTLs:

- **Articles (list + detail): 3 minutes.** DTH publishes at most a few
  stories a day, so a few minutes of staleness is invisible to a reader, but
  it means a burst of app users opening the feed at the same moment causes
  at most one upstream request per unique query per 3-minute window, not one
  per user. *Tradeoff:* a brand-new story can take up to 3 minutes to appear
  in the app. That's an acceptable tradeoff for a student newspaper's
  publishing cadence; a breaking-news wire service would need a much shorter
  TTL (or a push-based invalidation strategy instead of polling at all).
- **Sections: 30 minutes.** Categories almost never change, and fetching the
  full list costs several sequential requests (WordPress caps `per_page` at
  100, and there are 300+ categories). A long TTL means that cost is paid
  rarely.

The cache also uses a lock per cache key (`TTLCache.get_or_fetch`) so that if
many requests arrive at once for data that isn't cached yet, only the first
one calls WordPress — the rest wait for it and reuse its result, instead of
firing off duplicate upstream requests at the same moment.

*Caveat:* this cache is per-process and in-memory. Running multiple worker
processes (e.g. `uvicorn --workers 4`) means each worker has its own
independent cache, so the *effective* request rate to WordPress scales with
worker count. For this project's scale that's fine; a bigger deployment
would swap in a shared cache (Redis) instead.

**Error handling.** `app/wp_client.py` translates every upstream failure
(timeout, connection refused, 5xx) into one of two typed exceptions —
`UpstreamError` or `NotFoundError` — which FastAPI exception handlers in
`app/main.py` turn into clean JSON: `503` with a human-readable message if
DTH is slow/down, `404` if a specific article doesn't exist. The app never
crashes or returns a raw stack trace to the caller.

**Being a respectful API consumer.**
- A descriptive `User-Agent` identifying this as a project and giving a
  contact email (`app/config.py`), so DTH's ops team can identify and reach
  out about this traffic if needed, rather than it looking like anonymous
  scraping.
- Caching (above) means normal app usage results in occasional requests to
  DTH, not one per mobile user per screen view.
- The cache-stampede lock (above) prevents bursts of simultaneous duplicate
  requests.
- `_embed=1` is used on every post request so related data (author taxonomy,
  categories, featured image) comes back in the *same* request instead of
  requiring a separate round trip per related object.

**Content cleaning.** DTH's article HTML comes straight out of their editor —
`<span style="font-weight: 400;">` wrapping ordinary text, embedded widget
`<div>`s, the works. `transform._clean_content_html` strips scripts, styles,
iframes, and known embedded-widget containers entirely, drops every
HTML attribute except `href`/`src`/`alt`, and unwraps `<span>` tags — leaving
a small, safe subset of HTML (paragraphs, headings, links, emphasis, lists)
that's reasonable to hand to a mobile renderer. The excerpt is stripped all
the way down to plain text, since the app displays it as a plain string.

**Layering.** `main.py` (HTTP/routing) → `service.py` (caching +
orchestration) → `wp_client.py` (talks to WordPress, knows its quirks) →
`transform.py` (WordPress JSON → our Pydantic models) → `models.py` (the
public response shape). Each layer only knows about the one below it, so a
change to WordPress's data shape never has to touch route code, and a change
to our API's response shape never has to touch the WordPress client.

**CORS: wide open, deliberately.** `app/main.py` allows requests from any
origin. Every endpoint here is public, read-only GET data with no
cookies/auth and no per-user state — there's nothing a restrictive origin
allowlist would be protecting, and it's what lets the static preview be
hosted on a completely different domain (see deployment, below) from the
API it calls.

---

## 5. Testing

`pytest` runs the whole suite with **zero real network calls**. Instead of
mocking individual functions, the tests replace the shared `httpx.AsyncClient`
with one built on `httpx.MockTransport` — a fake transport that returns
canned `httpx.Response` objects for requests matching DTH's real URL shapes
(see `tests/conftest.py`'s `FakeWordPress`). FastAPI's
`app.dependency_overrides` swaps this fake client in for the route handlers,
so the actual route/service/transform code runs completely unmodified.

- `tests/test_transform.py` — unit tests for the trickiest logic in
  isolation: recovering the author from the `staff_name` taxonomy, skipping
  `weight-*` categories (including when one happens to be listed first),
  and cleaning article HTML.
- `tests/test_articles.py`, `test_sections.py`, `test_search.py` — route-level
  tests for each endpoint's shape, pagination, and filtering.
- `tests/test_errors_and_caching.py` — upstream timeouts/connection failures
  become `503`s, and two identical requests only hit the fake WordPress once
  (proving the cache actually works).

---

## 6. The frontend preview

`static/index.html` + `style.css` + `app.js` — plain HTML/CSS/JS, no build
step, no framework. It's served at `/` directly by FastAPI (see `app/main.py`).
It's deliberately simple and kept separate from the backend logic: its only
job is to call the four endpoints above and render the result, as a rough
stand-in for what the real iOS (SwiftUI) app will do. It is **not** meant to
be production frontend code.

It renders inside a fixed ~390px-wide "phone frame" so it visually reads as a
mobile app rather than a website, with:
- a scrolling home feed with "load more" pagination,
- section tabs loaded from `/sections`,
- a search bar wired to `/search`,
- an article screen (with a back button) wired to `/articles/{id}`,
- loading and friendly error states for all of the above.

---

## 7. Deploying

This repo is set up to deploy as **two separate pieces**, which is the right
split given the backend's design: the API needs a persistent process (for
the in-memory cache described in section 4) and the static preview doesn't.

```
Vercel (static, global CDN)              Render (persistent process)
  static/index.html / style.css / app.js --> FastAPI + in-memory TTL cache
                      |                              |
                      '------ fetch(`${API_BASE_URL}/articles`) --------'
```

An all-in-one deploy (both pieces on the same host) also works — see
"Alternative: single-host deploy" below — but loses some of the caching
benefit on a serverless host like Vercel, since a serverless function
doesn't stay warm as one long-lived process the way Render's does.

### Backend: Render

1. Push this repo to GitHub.
2. On [render.com](https://render.com), **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Instance type: Free. Deploy.
6. Note the resulting URL (e.g. `https://dth-api-preview.onrender.com`) — the
   frontend needs it in the next step.

*(Railway works the same way via its included `Procfile`, if you'd rather
use that instead of Render.)*

### Frontend: Vercel

The static preview is just the `static/` folder — Vercel can deploy it
directly, with no build step.

1. Edit `static/index.html`'s inline `window.API_BASE_URL = "";` line to
   point at your deployed Render URL from the step above, e.g.
   `window.API_BASE_URL = "https://dth-api-preview.onrender.com";`, and
   commit that change.
2. From the repo root: `vercel --cwd static --prod` (first run will ask you
   to log in and link a project — accept the defaults). Or, via the Vercel
   dashboard: **New Project → Import** this repo, and set **Root Directory**
   to `static`.
3. Vercel gives you a URL like `https://dth-api-preview.vercel.app` — that's
   the live preview link.

**Note on free tiers:** Render's free tier spins the service down after a
period of inactivity and cold-starts it on the next request, which can take
several seconds — normal for a demo/prototype, not something this project
tries to work around.

### Alternative: single-host deploy

Both pieces can also be deployed together as one FastAPI app (simpler, one
URL, one host) — follow the Render *or* Railway steps above but skip the
Vercel step and leave `API_BASE_URL` empty; the FastAPI app serves the
preview page itself at `/` and calls its own `/articles`, `/sections`, etc.
on the same origin, exactly as it does locally.
