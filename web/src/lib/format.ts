// Small display helpers.

export function formatPages(first: number | null | undefined, last?: number | null): string {
  if (!first) return "";
  return last && last !== first ? `pages ${first}–${last}` : `page ${first}`;
}

export function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024 * 1024) return `${Math.max(bytes / 1024, 0.1).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const units: [number, string][] = [[60, "minute"], [3600, "hour"], [86400, "day"], [604800, "week"]];
  for (let i = units.length - 1; i >= 0; i--) {
    const [size, name] = units[i];
    if (seconds >= size) {
      const count = Math.floor(seconds / size);
      if (name === "week" && count > 8) break;
      return `${count} ${name}${count === 1 ? "" : "s"} ago`;
    }
  }
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function initials(name: string, email = ""): string {
  // For an email, only the part before @ is a name ("juma@example.org" -> "JU").
  const source = name.trim() || email.trim().split("@")[0] || "?";
  const words = source.split(/[\s._-]+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : source.slice(0, 2)).toUpperCase();
}

/** Turn [S1] and [S1, S2] into markdown links the answer renderer shows as citation chips. */
export function linkCitations(text: string): string {
  return text.replace(/\[(S\d+(?:\s*,\s*S\d+)*)\]/g, (_, group: string) =>
    group
      .split(",")
      .map((label) => `[${label.trim()}](#cite-${label.trim()})`)
      .join(" "),
  );
}

export function shortModelName(id: string | null | undefined): string {
  return (id ?? "").split("/").pop() ?? "";
}
