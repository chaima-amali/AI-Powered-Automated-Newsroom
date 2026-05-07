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
    article_selectors : CSS selectors for BeautifulSoup fallback extractor

FIXES applied:
  - FIX 1: Renamed "El Watan" -> "El Watan FR" and "ElWatan News (AR)" -> "El Watan AR".
  - FIX 2: ElKhabar RSS URL corrected from /rss -> /feed.
  - FIX 3: ElBilad RSS URL corrected from /rss.xml -> /feed/.
  - FIX 4: Liberte Algerie REMOVED — newspaper permanently closed April 2022.
  - FIX 5: TSA Algerie updated to new domain tsa-algerie.dz.
  - FIX 6: Al Akhbar — fixed space bug in Google News URL (space -> %20).
  - FIX 7: Sawt El Ahrar — Google News 0 results -> switched to direct RSS.
  - FIX 8: El Watan FR — Google News 0 results -> switched to direct RSS.
  - FIX 9: Reporters Algerie — Google News 0 results -> switched to direct RSS.
  - FIX 10: L'Expression — broken /feed/ -> corrected to /rss/.
  - FIX 11: Maghreb Emergent — broken /feed/ -> corrected to /feed/rss/.
"""

SOURCES: list[dict] = [

    # Arabic sources
    {
        "name": "Ennahar Online",
        "rss_url": "https://www.ennaharonline.com/feed/",
        "base_url": "https://www.ennaharonline.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "div.entry-content", "article"],
    },
    {
        # FIX 2: corrected /rss -> /feed
        "name": "ElKhabar",
        "rss_url": "https://www.elkhabar.com/feed",
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
        # FIX 3: corrected /rss.xml -> /feed/
        "name": "ElBilad",
        "rss_url": "https://www.elbilad.net/feed/",
        "base_url": "https://www.elbilad.net",
        "language": "ar",
        "article_selectors": ["div.article-details", "div.content-area", "article"],
    },
    {
        # FIX 1: Renamed from "ElWatan News (AR)" -> "El Watan AR"
        "name": "El Watan AR",
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
        # FIX 6: space in URL encoded as %20 to fix "can't contain control characters" error
        "name": "Al Akhbar Algeria",
        "rss_url": "https://news.google.com/rss/search?q=site:al-akhbar.com%20algerie&hl=ar&gl=DZ&ceid=DZ:ar",
        "base_url": "https://www.al-akhbar.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "article"],
    },
    {
        # FIX 7: Google News returned 0 results. Switched to direct RSS.
        # Also corrected domain: original config used sawtelhiwar.com (wrong).
        "name": "Sawt El Ahrar",
        "rss_url": "https://www.sawt-el-ahrar.net/feed/",
        "base_url": "https://www.sawt-el-ahrar.net",
        "language": "ar",
        "article_selectors": ["div.td-post-content", "div.entry-content", "article"],
    },

    # French sources
    {
        # FIX 1: Renamed from "El Watan" -> "El Watan FR"
        # FIX 8: Google News 0 results -> switched back to direct RSS
        "name": "El Watan FR",
        "rss_url": "https://www.elwatan.com/feed/",
        "base_url": "https://www.elwatan.com",
        "language": "fr",
        "article_selectors": ["div.article-body", "div.field-items", "article"],
    },
    # FIX 4: Liberte Algerie REMOVED — closed permanently April 2022
    {
        # Google News working — keep as-is
        "name": "Le Soir d'Algerie",
        "rss_url": "https://news.google.com/rss/search?q=site:lesoirdalgerie.com&hl=fr&gl=DZ&ceid=DZ:fr",
        "base_url": "https://www.lesoirdalgerie.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
    },
    {
        # FIX 5: new domain tsa-algerie.dz
        "name": "TSA Algerie",
        "rss_url": "https://www.tsa-algerie.dz/feed/",
        "base_url": "https://www.tsa-algerie.dz",
        "language": "fr",
        "article_selectors": ["div.entry-content", "div.article-content", "article"],
    },
    {
        "name": "Algerie360",
        "rss_url": "https://www.algerie360.com/feed/",
        "base_url": "https://www.algerie360.com",
        "language": "fr",
        "article_selectors": ["div.td-post-content", "div.entry-content", "article"],
    },
    {
        # FIX 10: broken /feed/ -> corrected to /rss/
        "name": "L'Expression",
        "rss_url": "https://www.lexpressiondz.com/rss/",
        "base_url": "https://www.lexpressiondz.com",
        "language": "fr",
        "article_selectors": ["div.article-detail", "div.content", "article"],
    },
    {
        # FIX 9: Google News 0 results -> switched back to direct RSS
        "name": "Reporters Algerie",
        "rss_url": "https://www.reporters.dz/feed/",
        "base_url": "https://www.reporters.dz",
        "language": "fr",
        "article_selectors": ["div.entry-content", "article"],
    },
    {
        # Google News working — keep as-is
        "name": "Algerie Patriotique",
        "rss_url": "https://news.google.com/rss/search?q=site:algeriepatriotique.com&hl=fr&gl=DZ&ceid=DZ:fr",
        "base_url": "https://www.algeriepatriotique.com",
        "language": "fr",
        "article_selectors": ["div.td-post-content", "article"],
    },
    {
        # FIX 11: broken /feed/ -> corrected to /feed/rss/
        "name": "Maghreb Emergent",
        "rss_url": "https://maghrebemergent.info/feed/rss/",
        "base_url": "https://maghrebemergent.info",
        "language": "fr",
        "article_selectors": ["div.entry-content", "div.article-content", "article"],
    },
]