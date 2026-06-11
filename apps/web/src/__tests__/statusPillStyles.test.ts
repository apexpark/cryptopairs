// @ts-nocheck
import { readFileSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const styles = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../styles.css"),
  "utf8"
);

describe("simple Trade Now status pill styles", () => {
  it("keeps status pills content-sized inside grid table cells", () => {
    expect(styles).toMatch(/\.simple-status-pill\s*\{[^}]*\bwidth:\s*fit-content;/s);
    expect(styles).toMatch(/\.simple-status-pill\s*\{[^}]*\bjustify-self:\s*start;/s);
    expect(styles).toMatch(/\.simple-status-pill\s*\{[^}]*\bmax-width:\s*100%;/s);
  });
});
