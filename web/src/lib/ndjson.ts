// Newline-delimited JSON, as sent by /api/ask/stream.

/** Split `buffer + chunk` into complete lines and the unfinished rest. */
export function splitLines(buffer: string, chunk: string): { lines: string[]; rest: string } {
  const parts = (buffer + chunk).split("\n");
  const rest = parts.pop() ?? "";
  return { lines: parts.filter((line) => line.trim() !== ""), rest };
}

export async function* readLines(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const { lines, rest } = splitLines(buffer, decoder.decode(value, { stream: true }));
      buffer = rest;
      yield* lines;
    }
    if (buffer.trim()) yield buffer;
  } finally {
    reader.releaseLock();
  }
}
