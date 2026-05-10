"""
config/sources.py
------------------
Centralised registry of Algerian news sources.
Add new sources here — no code changes needed elsewhere.
"""

SOURCES: list[dict] = [

    # ── Arabic sources ─────────────────────────────────────────────────────────
    {
        "name": "Ennahar Online",
        "rss_url": "https://www.ennaharonline.com/feed/",
        "base_url": "https://www.ennaharonline.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "div.entry-content", "article"],
        "categories": ["اخبار", "سياسة", "اقتصاد", "مجتمع", "رياضة"],
    },
    {
        "name": "ElKhabar",
        "rss_url": "https://www.elkhabar.com/feed",
        "base_url": "https://www.elkhabar.com",
        "language": "ar",
        "article_selectors": ["div.article-content", "div.news-content", "article"],
        "categories": ["وطني", "سياسة", "اقتصاد", "مجتمع", "رياضة", "دولي"],
    },
    {
        "name": "Echorouk Online",
        "rss_url": "https://www.echoroukonline.com/feed",
        "base_url": "https://www.echoroukonline.com",
        "language": "ar",
        "article_selectors": ["div.article-body", "div.td-post-content", "article"],
        "categories": ["اخبار", "سياسة", "اقتصاد", "رياضة"],
    },
    {
        "name": "ElBilad",
        "rss_url": "https://www.elbilad.net/feed/",
        "base_url": "https://www.elbilad.net",
        "language": "ar",
        "article_selectors": ["div.article-details", "div.content-area", "article"],
        "categories": ["اخبار", "سياسة", "اقتصاد", "مجتمع"],
    },
    {
        "name": "El Fadjr",
        "rss_url": "https://www.el-fadjr.com/feed/",
        "base_url": "https://www.el-fadjr.com",
        "language": "ar",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
        "categories": ["اخبار", "سياسة", "اقتصاد"],
    },
    {
        "name": "Djazairess",
        "rss_url": "https://www.djazairess.com/rss",
        "base_url": "https://www.djazairess.com",
        "language": "ar",
        "article_selectors": ["div.article-content", "div.content", "article"],
        "categories": ["الجزائر", "سياسة", "اقتصاد"],
    },
    {
        "name": "Sawt El Ahrar",
        "rss_url": "https://www.sawt-elaahrar.net/feed/",
        "base_url": "https://www.sawt-elaahrar.net",
        "language": "ar",
        "article_selectors": ["div.entry-content", "article"],
        "categories": ["اخبار", "سياسة"],
    },

    # ── French sources ─────────────────────────────────────────────────────────
    {
        "name": "El Watan",
        "rss_url": "https://www.elwatan.com/feed/",
        "base_url": "https://www.elwatan.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
        "categories": ["actualite", "politique", "economie", "societe", "sport"],
    },
    {
        "name": "TSA Algerie",
        "rss_url": "https://www.tsa-algerie.com/feed/",
        "base_url": "https://www.tsa-algerie.com",
        "language": "fr",
        "article_selectors": ["div.article-body", "div.content-area", "article"],
        "categories": ["actualite", "politique", "economie", "societe"],
    },
    {
        "name": "Reporters Algerie",
        "rss_url": "https://www.reporters.dz/feed/",
        "base_url": "https://www.reporters.dz",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
        "categories": ["actualite", "politique", "economie"],
    },
    {
        "name": "Liberté Algérie",
        "rss_url": "https://www.liberte-algerie.com/feed",
        "base_url": "https://www.liberte-algerie.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
        "categories": ["actualite", "politique", "economie", "culture"],
    },
    {
        "name": "L'Expression",
        "rss_url": "https://www.lexpressiondz.com/rss/",
        "base_url": "https://www.lexpressiondz.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.contenu", "article"],
        "categories": ["actualite", "politique", "economie", "sport"],
    },
    {
        "name": "Maghreb Emergent",
        "rss_url": "https://maghrebemergent.net/feed/rss/",
        "base_url": "https://maghrebemergent.net",
        "language": "fr",
        "article_selectors": ["div.entry-content", "article"],
        "categories": ["actualite", "economie", "international"],
    },
    {
        "name": "Le Soir d'Algerie",
        "rss_url": "https://news.google.com/rss/search?q=Le+Soir+Algerie&hl=fr&gl=DZ&ceid=DZ:fr",
        "base_url": "https://www.lesoirdalgerie.com",
        "language": "fr",
        "article_selectors": ["div.article-content", "div.entry-content", "article"],
        "categories": ["actualite", "politique", "economie"],
    },
    {
        "name": "Interlignes",
        "rss_url": "https://www.interlignes.net/feed/",
        "base_url": "https://www.interlignes.net",
        "language": "fr",
        "article_selectors": ["div.entry-content", "article"],
        "categories": ["actualite", "politique"],
    },
]
