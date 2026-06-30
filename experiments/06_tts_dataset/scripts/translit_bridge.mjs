// Bridge to the project's Crimean-Tatar transliterator.
// Reads a JSON array of strings from stdin, writes the transliterated JSON
// array to stdout. Direction is auto-detected per string by the service
// (Cyrillic -> Latin here).
import { transliterate } from "/Users/servin/1_dev/my/anayurt/ana-yurt-lugat-rn/services/StranslinService.js";

// The service uses an undeclared loop var `i` (legal under its app bundler, but
// ESM strict mode rejects assignment to an undeclared global). Pre-declaring it
// as a global property makes the assignment legal without editing the source.
globalThis.i = 0;

let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (buf += d));
process.stdin.on("end", () => {
  const arr = JSON.parse(buf);
  const out = arr.map((s) => transliterate(s));
  process.stdout.write(JSON.stringify(out));
});
