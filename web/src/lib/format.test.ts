import { describe, expect, it } from "vitest";
import { formatPages, formatSize, formatTokens, formatUsd, initials, linkCitations, shortModelName, timeAgo } from "./format";
import { splitLines } from "./ndjson";

describe("linkCitations", () => {
  it("turns citation labels into links the answer renderer shows as chips", () => {
    expect(linkCitations("Monthly [S1].")).toBe("Monthly [S1](#cite-S1).");
    expect(linkCitations("Both [S1, S3]")).toBe("Both [S1](#cite-S1) [S3](#cite-S3)");
    expect(linkCitations("No [citation] here")).toBe("No [citation] here");
  });
});

describe("splitLines", () => {
  it("keeps an unfinished line for the next chunk", () => {
    expect(splitLines("", '{"a":1}\n{"b"')).toEqual({ lines: ['{"a":1}'], rest: '{"b"' });
    expect(splitLines('{"b"', ":2}\n\n")).toEqual({ lines: ['{"b":2}'], rest: "" });
  });
});

describe("formatting", () => {
  it("formats pages, sizes, names and times", () => {
    expect(formatPages(3, 3)).toBe("page 3");
    expect(formatPages(3, 5)).toBe("pages 3–5");
    expect(formatPages(null)).toBe("");
    expect(formatSize(2048)).toBe("2.0 KB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(initials("Amina Yusuf")).toBe("AY");
    expect(initials("", "juma@example.org")).toBe("JU");
    expect(shortModelName("intfloat/multilingual-e5-small")).toBe("multilingual-e5-small");
    const now = Date.parse("2026-10-19T12:00:00Z");
    expect(timeAgo("2026-10-19T11:59:30Z", now)).toBe("just now");
    expect(timeAgo("2026-10-19T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-10-18T12:00:00Z", now)).toBe("1 day ago");
  });
});

describe("formatTokens and formatUsd", () => {
  it("shortens token counts", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(1234)).toBe("1.2K");
    expect(formatTokens(48_000)).toBe("48K");
    expect(formatTokens(2_500_000)).toBe("2.5M");
  });
  it("shows dollars, keeping tiny amounts visible", () => {
    expect(formatUsd(null)).toBe("–");
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(12.5)).toBe("$12.50");
    expect(formatUsd(0.0008)).toBe("$0.0008");
  });
});
