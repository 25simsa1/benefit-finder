// Report view: renders the markdown report with Download and Print.
import { el, clear } from "./dom.js";
import { renderMarkdown } from "./markdown.js";

export function renderReport(root, markdown) {
  clear(root);

  const download = () => {
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "report.md" });
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const toolbar = el("div", { class: "report-toolbar" }, [
    el("button", { class: "btn", type: "button", onclick: download }, "Download .md"),
    el("button", { class: "btn secondary", type: "button", onclick: () => window.print() }, "Print / Save as PDF"),
  ]);

  const doc = el("article", { class: "card report-doc", html: renderMarkdown(markdown) });
  root.append(toolbar, doc);
}
