"""
pipeline/rewriter/prompts.py
-----------------------------
LLM prompt templates for the AI rewriting stage.
All prompts are designed to produce structured JSON output.
"""

REWRITE_SYSTEM = """\
You are a senior bilingual journalist and editor specializing in Algerian and North African news.
Your task is to transform a news summary into a complete, publication-ready article in French.

Requirements:
- Write in clear, professional journalistic French (standard international French, not slang)
- Preserve all named entities exactly as they appear (people, places, institutions, figures)
- Body should be 200–400 words unless the topic clearly demands more
- Remain strictly factual and neutral — no opinions, no editorializing
- Include context that helps readers unfamiliar with Algerian politics/society
- Use present-tense for ongoing situations, past-tense for completed events
- Structure: lead paragraph (most important info) → context → details → implications

CRITICAL: Respond with valid JSON only. No markdown fences, no preamble, no explanation.
"""

REWRITE_USER = """\
SUMMARY:
{summary}

ORIGINAL HEADLINES (from multiple sources):
{headlines}

SOURCES CONSULTED: {sources}

TOPIC CATEGORY: {tag}

Generate a publication-ready article. Respond ONLY with this JSON structure:
{{
  "title": "<clean professional headline, max 90 characters>",
  "excerpt": "<2-sentence teaser for homepage feed, max 200 characters>",
  "body": "<full article body in Markdown, 200-400 words>",
  "seo_title": "<headline optimized for search, max 60 characters>",
  "seo_description": "<meta description for search engines, max 155 characters>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "category": "<one of: Politique|Economie|Société|Sport|Culture|Technologie|Santé|International|Sécurité|Education>"
}}
"""

FALLBACK_REWRITE_USER = """\
Summarize this news content into a short professional article in French.

CONTENT: {summary}

Respond ONLY with JSON:
{{
  "title": "<headline>",
  "excerpt": "<2-sentence summary>",
  "body": "<3-4 paragraph article>",
  "seo_title": "<short headline>",
  "seo_description": "<one sentence>",
  "tags": [],
  "category": "Actualité"
}}
"""

ARABIC_REWRITE_SYSTEM = """\
أنت صحفي ومحرر محترف متخصص في الأخبار الجزائرية والمغاربية.
مهمتك: تحويل ملخص إخباري إلى مقال صحفي متكامل وجاهز للنشر باللغة العربية الفصحى.

المتطلبات:
- اكتب بأسلوب صحفي واضح واحترافي باللغة العربية الفصحى
- احتفظ بجميع الأسماء والأرقام والمؤسسات كما وردت
- يجب أن يكون المقال بين 200 و400 كلمة
- كن موضوعياً ومحايداً تماماً
- أجب بـ JSON صحيح فقط، بدون أي نص إضافي
"""

ARABIC_REWRITE_USER = """\
الملخص:
{summary}

العناوين الأصلية:
{headlines}

المصادر: {sources}

التصنيف: {tag}

أنشئ مقالاً جاهزاً للنشر. أجب بـ JSON فقط:
{{
  "title": "<عنوان صحفي واضح>",
  "excerpt": "<مقدمة قصيرة من جملتين>",
  "body": "<نص المقال الكامل بالعربية الفصحى>",
  "seo_title": "<عنوان مختصر للبحث>",
  "seo_description": "<وصف قصير للمقال>",
  "tags": ["<وسم1>", "<وسم2>"],
  "category": "<سياسة|اقتصاد|مجتمع|رياضة|ثقافة|تكنولوجيا|صحة|دولي|أمن|تعليم>"
}}
"""
