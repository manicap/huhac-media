import { describe, expect, it } from "vitest";

import { defineModuleRegistry } from "./moduleContract";
import { studioModuleRegistry } from "./moduleRegistry";

describe("static module registry", () => {
  it("registers the two prototype modules in navigation order", () => {
    expect(studioModuleRegistry.map((module) => module.id)).toEqual([
      "projects",
      "media-library",
    ]);
    expect(studioModuleRegistry.every((module) => module.component && module.icon)).toBe(true);
  });

  it("sorts definitions and rejects duplicate ids", () => {
    const [projects, library] = studioModuleRegistry;
    expect(defineModuleRegistry([library, projects])).toEqual([projects, library]);
    expect(() => defineModuleRegistry([projects, projects])).toThrow(/Duplicate/);
  });

  it("keeps module source trees isolated from each other", () => {
    const sources = import.meta.glob("../modules/**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const projectsSources = Object.entries(sources)
      .filter(([path]) => path.includes("/projects/"))
      .map(([, source]) => source)
      .join("\n");
    const librarySources = Object.entries(sources)
      .filter(([path]) => path.includes("/media-library/"))
      .map(([, source]) => source)
      .join("\n");

    expect(projectsSources).not.toMatch(/media-library/);
    expect(librarySources).not.toMatch(/modules\/projects/);
  });
});
