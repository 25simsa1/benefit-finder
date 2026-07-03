// Thin wrapper around the FastAPI backend. Same-origin, no auth.

async function detail(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

export async function getMeta() {
  const res = await fetch("/api/meta");
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function screen(profile) {
  const res = await fetch("/api/screen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function report(profile) {
  const res = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error(await detail(res));
  return res.text();
}
