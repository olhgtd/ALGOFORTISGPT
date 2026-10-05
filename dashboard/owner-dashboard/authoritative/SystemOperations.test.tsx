import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "systemOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "SystemOperations.tsx"), "utf8");

describe("Owner system operations", () => {
  it("is source-backed and explicitly unavailable when commands do not exist", () => {
    expect(client).toContain("/api/v1/product-ops/owner/health");
    expect(screen).toContain("UNAVAILABLE");
    expect(screen).toContain("No bounded command authority is attached");
  });

  it("has no executable terminal, shell, arbitrary filesystem, or process-control authority", () => {
    const combined = `${client}\n${screen}`.toLowerCase();
    for (const forbidden of [
      "powershell",
      "cmd.exe",
      "file://",
      "/terminal",
      "/shell",
      "/process/kill",
      "run shell",
      "edit path",
    ]) {
      expect(combined).not.toContain(forbidden);
    }
    expect(screen).toContain("No terminal, arbitrary file path, or process-control authority is exposed.");
  });
});
