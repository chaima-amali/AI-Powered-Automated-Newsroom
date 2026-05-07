"""
config/sources.py
------------------
Centralised registry of all Algerian newspapers / news journals.
Add new sources here — no code changes required elsewhere.

Each entry:
    name        : human-readable identifier (used as source_name in DB)
    rss_url     : RSS/Atom feed URL  (None if no feed available)
    base_url    : homepage — used for scraping fallback
    language    : 'ar' | 'fr' | 'en'
    section_map : maps URL path fragments → section labels (optional)
    parser      : custom parser key if generic parser won't work (optional)
"""

SOURCES: list[dict] = [

    # ── Arabic ────────────────────────────────────────────────────────────────
    {
        "name": "Ennahar Online",
        "rss_url": "https://www.ennaharonline.com/feed/",
        "base_url": "https://www.ennaharonline.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "div.entry-content", "article"],
    },
    {
        "name": "ElKhabar",
        "rss_url": "https://www.elkhabar.com/rss",
        "base_url": "https://www.elkhabar.com",
        "language": "ar",
        "article_selectors": ["div.article-content", "div.news-content", "article"],
    },
    {
        "name": "Echorouk Online",
        "rss_url": "https://www.echoroukonline.com/feed",
        "base_url": "https://www.echoroukonline.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "div.td-post-content", "article"],
    },
    {
        "name": "ElBilad",
        "rss_url": "https://www.elbilad.net/rss.xml",
        "base_url": "https://www.elbilad.net",
        "language": "ar",
        "article_selectors": ["div.article-details", "div.content-area", "article"],
    },
    {
        "name": "ElWatan News (AR)",
        "rss_url": "https://elwatan-dz.com/feed",
        "base_url": "https://elwatan-dz.com",
        "language": "ar",
        "article_selectors": ["div.article-content", "div.entry-content"],
    },
    {
        "name": "Dzair Today",
        "rss_url": "https://www.dzairtoday.com/feed/",
        "base_url": "https://www.dzairtoday.com",
        "language": "ar",
        "article_selectors": ["div.entry-content", "article"],
    },
    {
        "name": "Al Akhbar Algeria",
        "rss_url": "https://www.al-akhbar.com/rss",
        "base_url": "https://www.al-akhbar.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "article"],
    },
    {
        "name": "Sawt El Ahrar",
        "rss_url": "https://www.sawtelhiwar.com/feed/",
        "base_url": "https://www.sawtelhiwar.com",
        "language": "ar",
        "article_selectors": ["div.td-post-content", "article"],
    },

    # ── French ────────────────────────────────────────────────────────────────
    {
        "name": "El Watan",
        "rss_url": "https://www.elwatan.com/feed/",
        "base_url": "https://www.elwatan.com",
        "language": "fr",
        "article_selectors": ["div.article-body", "div.field-items", "article"],
    },
    {
        "name": "Liberté Algérie",
        "rss_url": "https://www.liberte-algerie.com/rss.xml",
        "base_url": "https://www.liberte-algerie.com",
        "language": "fr",
        "article_selectors": ["div.article-text", "div.content", "article"],
    },
    {
        "name": "Le Soir d'Algérie",
        "rss_url": "https://www.lesoirdalgerie.com/feed/",
        "base_url": "https://www.lesoirdalgerie.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
    },
    {
        "name": "TSA Algérie",
        "rss_url": "https://www.tsa-algerie.com/feed/",
        "base_url": "https://www.tsa-algerie.com",
        "language": "fr",
        "article_selectors": ["div.entry-content", "div.article-content", "article"],
    },
    {
        "name": "Algérie360",
        "rss_url": "https://www.algerie360.com/feed/",
        "base_url": "https://www.algerie360.com",
        "language": "fr",
        "article_selectors": ["div.td-post-content", "div.entry-content", "article"],
    },
    {
        "name": "L'Expression",
        "rss_url": "https://www.lexpressiondz.com/feed/",
        "base_url": "https://www.lexpressiondz.com",
        "language": "fr",
        "article_selectors": ["div.article-detail", "div.content", "article"],
    },
    {
        "name": "Reporters Algérie",
        "rss_url": "https://www.reporters.dz/feed/",
        "base_url": "https://www.reporters.dz",
        "language": "fr",
        "article_selectors": ["div.entry-content", "article"],
    },
    {
        "name": "Algérie Patriotique",
        "rss_url": "https://www.algeriepatriotique.com/feed/",
        "base_url": "https://www.algeriepatriotique.com",
        "language": "fr",
        "article_selectors": ["div.td-post-content", "article"],
    },
    {
        "name": "Maghreb Emergent",
        "rss_url": "https://maghrebemergent.info/feed/",
        "base_url": "https://maghrebemergent.info",
        "language": "fr",
        "article_selectors": ["div.entry-content", "div.article-content", "article"],
    },
]
