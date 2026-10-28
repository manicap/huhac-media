import { describe, expect, it } from "vitest";

import { createStudioStore } from "./studioStore";

describe("shared Studio context", () => {
  it("keeps selection across module changes and clears it on project change", () => {
    const store = createStudioStore();
    store.getState().setProject("project-tour");
    store.getState().toggleMedia("media-stage-wide");
    store.getState().setActiveModule("media-library");
    store.getState().setActiveModule("projects");

    expect(store.getState().selectedMediaIds).toEqual(["media-stage-wide"]);

    store.getState().setProject("project-campaign");
    expect(store.getState().projectId).toBe("project-campaign");
    expect(store.getState().selectedMediaIds).toEqual([]);
  });

  it("clears the active project and selection when workspace changes", () => {
    const store = createStudioStore({ projectId: "project-tour" });
    store.getState().toggleMedia("media-stage-wide");

    store.getState().setWorkspace("workspace-archive");

    expect(store.getState().workspaceId).toBe("workspace-archive");
    expect(store.getState().projectId).toBeNull();
    expect(store.getState().selectedMediaIds).toEqual([]);
  });

  it("does not clear selection when the same project is selected again", () => {
    const store = createStudioStore({ projectId: "project-tour" });
    store.getState().toggleMedia("media-stage-wide");
    store.getState().setProject("project-tour");
    expect(store.getState().selectedMediaIds).toEqual(["media-stage-wide"]);
  });
});
