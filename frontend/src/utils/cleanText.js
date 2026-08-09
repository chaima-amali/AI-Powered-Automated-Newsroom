/**
 * utils/cleanText.js
 * ------------------
 * Frontend-only text sanitiser applied before displaying article content.
 * No pipeline/backend changes needed.
 */

// Section headers that mark trailing non-editorial content to strip
const SECTION_HEADERS = [
  'resources', 'resource',
  'references', 'reference',
  'sources', 'source',
  'source article details',
  'liens utiles', 'liens sources',
  'bibliography', 'bibliographie',
  'références', 'voir aussi',
  'see also', 'external links', 'extern links',
];

// Inline cut markers — if the phrase appears ANYWHERE in the text, cut from there
const INLINE_CUT_MARKERS = [
  'source article details',
];

// Phrases that indicate a line is pipeline/cluster metadata
const CLUSTER_MARKERS = [
  'cluster summary',
  'cluster_summary',
  'topic cluster',
  'news cluster',
  'article cluster',
  'summary of cluster',
  'résumé du cluster',
  'generated summary',
  'auto-generated',
  'pipeline output',
  'groupe de news',
];

/**
 * Clean a summary/excerpt/body string before rendering.
 *
 * Rules (applied in order):
 * 1. Strip everything from the first "Resources / Sources / References / …"
 *    section header to the end of the text.
 * 2. Remove individual lines that contain cluster-metadata phrases.
 * 3. Collapse consecutive blank lines.
 *
 * @param {string} text
 * @returns {string}
 */
export function cleanText(text) {
  if (!text || typeof text !== 'string') return text;

  // ── Rule 0: hard inline cut — remove from marker to end of string ────────
  for (const marker of INLINE_CUT_MARKERS) {
    const idx = text.toLowerCase().indexOf(marker);
    if (idx !== -1) {
      text = text.slice(0, idx);
    }
  }

  // ── Rule 1: cut at first resource/reference section header ──────────────
  const lines = text.split('\n');
  let cutAt = lines.length;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim().toLowerCase().replace(/:?\s*$/, ''); // strip trailing colon
    if (SECTION_HEADERS.includes(trimmed)) {
      cutAt = i;
      break;
    }
  }

  const trimmedLines = lines.slice(0, cutAt);

  // ── Rule 2: remove lines containing cluster-metadata markers ────────────
  const cleanedLines = trimmedLines.filter(line => {
    const lower = line.toLowerCase();
    return !CLUSTER_MARKERS.some(marker => lower.includes(marker));
  });

  // ── Rule 3: collapse consecutive blank lines ─────────────────────────────
  const result = [];
  let prevBlank = false;
  for (const line of cleanedLines) {
    const isBlank = !line.trim();
    if (isBlank && prevBlank) continue;
    result.push(line);
    prevBlank = isBlank;
  }

  return result.join('\n').trim();
}
