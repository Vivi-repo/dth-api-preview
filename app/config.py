"""
All the tunable knobs for this service live here, in one place, so the
reasoning behind each one can be explained without hunting through the code.
"""


class Settings:
    # The Daily Tar Heel's public WordPress REST API. No API key needed --
    # it's the same public data their own website uses to render pages.
    WP_API_BASE = "https://www.dailytarheel.com/wp-json/wp/v2"

    # WordPress sites (and the CDNs in front of them) like to know who is
    # calling and how to reach the operator if traffic looks abusive. A
    # descriptive UA is the polite, standard way to identify a bot/service.
    USER_AGENT = (
        "DTHAppPreviewBackend/1.0 "
        "(educational/portfolio project; contact: vesre557@gmail.com)"
    )

    # How long we wait for DTH's server before giving up and telling the
    # caller "upstream is slow" instead of hanging forever.
    HTTP_TIMEOUT_SECONDS = 10.0

    # --- Cache lifetimes -----------------------------------------------
    # Articles (lists and single posts) are cached briefly. The Daily Tar
    # Heel publishes maybe a handful of stories a day, so a few minutes of
    # staleness is invisible to readers, but it means a burst of app users
    # opening the feed at the same time results in at most one upstream
    # request per unique query every few minutes, not one per user.
    ARTICLES_CACHE_TTL_SECONDS = 180  # 3 minutes

    # Sections (categories) almost never change -- DTH doesn't add a new
    # news section every day -- and fetching the full list costs several
    # upstream requests (WordPress paginates at 100 per page and there are
    # 300+ categories). A long TTL avoids repeating that work often.
    SECTIONS_CACHE_TTL_SECONDS = 1800  # 30 minutes

    # Upper bound on per_page so a single request can't ask us to fetch and
    # cache an unreasonably large page from WordPress.
    MAX_PER_PAGE = 50
    DEFAULT_PER_PAGE = 10


settings = Settings()
