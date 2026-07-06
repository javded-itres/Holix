/** Markdown → sanitized HTML for Holix Studio (editor preview + chat). */

import { marked } from "https://cdn.jsdelivr.net/npm/marked@15.0.7/+esm";
import DOMPurify from "https://cdn.jsdelivr.net/npm/dompurify@3.2.4/+esm";

marked.use({
  gfm: true,
  breaks: true,
});

const PURIFY_CONFIG = {
  USE_PROFILES: { html: true },
  ADD_ATTR: ["target", "rel"],
};

export function renderMarkdown(text) {
  const src = String(text ?? "");
  if (!src.trim()) return "";
  const html = marked.parse(src, { async: false });
  const safe = DOMPurify.sanitize(html, PURIFY_CONFIG);
  const doc = new DOMParser().parseFromString(safe, "text/html");
  doc.querySelectorAll("a[href]").forEach((a) => {
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer");
  });
  return doc.body.innerHTML;
}