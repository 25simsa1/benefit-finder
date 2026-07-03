// A focused Markdown-to-HTML renderer for the report format this app
// produces (headings, blockquotes, GFM tables, task-list checkboxes,
// bold, italics, autolinks, and paragraphs). It is deliberately scoped
// to the known output rather than being a general Markdown parser.

const SENT = "\uE000"; // private-use sentinel; never appears in report text

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Inline formatting: pull links out first (so their URLs are not mangled
// by HTML-escaping), escape the rest, then apply bold/italic, then
// restore the links. Placeholders use a non-printable sentinel so plain
// text like "for 3 kids" is never mistaken for a token.
function inline(text) {
  const tokens = [];
  const stash = (html) => {
    tokens.push(html);
    return SENT + (tokens.length - 1) + SENT;
  };
  let s = text;
  // [label](url)
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_, label, url) =>
    stash('<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(label) + "</a>")
  );
  // <https://...> autolink
  s = s.replace(/<(https?:\/\/[^>]+)>/g, (_, url) =>
    stash('<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(url) + "</a>")
  );
  s = escapeHtml(s);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[\s(])_([^_]+)_(?=[\s.,;:)]|$)/g, "$1<em>$2</em>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(new RegExp(SENT + "(\\d+)" + SENT, "g"), (_, idx) => tokens[Number(idx)]);
  return s;
}

function tableRow(line) {
  return line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

export function renderMarkdown(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  let para = [];

  const flushPara = () => {
    if (para.length) {
      out.push("<p>" + inline(para.join(" ")) + "</p>");
      para = [];
    }
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) { flushPara(); i++; continue; }

    const h = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara();
      const level = h[1].length;
      out.push("<h" + level + ">" + inline(h[2]) + "</h" + level + ">");
      i++;
      continue;
    }

    if (/^---+$/.test(trimmed)) { flushPara(); out.push("<hr>"); i++; continue; }

    if (trimmed.startsWith(">")) {
      flushPara();
      const buf = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        buf.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      const html = buf.map((b) => (b ? inline(b) : "")).join("<br>");
      out.push("<blockquote>" + html + "</blockquote>");
      continue;
    }

    // table: a pipe row followed by a |---|---| delimiter row
    if (
      trimmed.includes("|") &&
      i + 1 < lines.length &&
      /^\|?[\s:|-]+\|?$/.test(lines[i + 1].trim()) &&
      lines[i + 1].includes("-")
    ) {
      flushPara();
      const header = tableRow(trimmed);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim().includes("|") && lines[i].trim()) {
        rows.push(tableRow(lines[i].trim()));
        i++;
      }
      const thead = "<thead><tr>" + header.map((c) => "<th>" + inline(c) + "</th>").join("") + "</tr></thead>";
      const tbody =
        "<tbody>" +
        rows.map((r) => "<tr>" + r.map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") +
        "</tbody>";
      out.push('<div class="table-scroll"><table>' + thead + tbody + "</table></div>");
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushPara();
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        const item = lines[i].trim().replace(/^[-*]\s+/, "");
        const task = item.match(/^\[( |x|X)\]\s+(.*)$/);
        if (task) {
          const checked = task[1].toLowerCase() === "x" ? " checked" : "";
          items.push(
            '<li><label><input type="checkbox" disabled' + checked + "> " + inline(task[2]) + "</label></li>"
          );
        } else {
          items.push("<li>" + inline(item) + "</li>");
        }
        i++;
      }
      out.push("<ul>" + items.join("") + "</ul>");
      continue;
    }

    para.push(trimmed);
    i++;
  }
  flushPara();
  return out.join("\n");
}
