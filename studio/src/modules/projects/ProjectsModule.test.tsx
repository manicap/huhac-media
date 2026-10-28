import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { syntheticDataSource, syntheticProjects } from "../../data/syntheticDataSource";
import { renderStudio } from "../../test/renderStudio";

describe("Projects module", () => {
  it("selects a project and publishes it to the shared context", async () => {
    const { store, user } = renderStudio();

    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));

    expect(store.getState().projectId).toBe("project-tour");
    expect(screen.getByText("Podzimní turné", { selector: ".active-project strong" })).toBeVisible();
  });

  it("preserves its local filter while another module is active", async () => {
    const { user } = renderStudio();
    const filter = await screen.findByPlaceholderText("Filtrovat projekty");
    await user.type(filter, "turné");
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    await user.click(screen.getByRole("link", { name: "Projekty" }));

    expect(screen.getByPlaceholderText("Filtrovat projekty")).toHaveValue("turné");
  });

  it("creates, edits, archives and restores a project with current revisions", async () => {
    const created = {
      ...syntheticProjects[2],
      id: "project-created",
      title: "Denní projekt",
      description: "První popis",
      tags: ["deník"],
    };
    let createdAvailable = false;
    const createProject = vi.fn(async () => {
      createdAvailable = true;
      return created;
    });
    const updateProject = vi.fn(async (_id, _revision, input) => ({
      ...created,
      ...input,
      description: input.description ?? "",
      notes: input.notes ?? "",
      revision: 2,
    }));
    const archiveProject = vi.fn(async () => ({
      ...created,
      revision: 3,
      status: "archived" as const,
      archivedAt: "2026-10-28T08:00:00Z",
    }));
    const restoreProject = vi.fn(async () => ({ ...created, revision: 4 }));
    const { store, user } = renderStudio({
      dataSource: {
        ...syntheticDataSource,
        listProjects: async (workspaceId) => [
          ...syntheticProjects.filter((project) => project.workspaceId === workspaceId),
          ...(createdAvailable && workspaceId === created.workspaceId ? [created] : []),
        ],
        createProject,
        updateProject,
        archiveProject,
        restoreProject,
      },
    });

    await user.click(await screen.findByRole("button", { name: "Nový projekt" }));
    await user.type(screen.getByLabelText("Název"), "Denní projekt");
    await user.type(screen.getByLabelText("Popis"), "První popis");
    await user.type(screen.getByLabelText(/Štítky/), "deník");
    await user.click(screen.getByRole("button", { name: "Vytvořit projekt" }));
    expect(await screen.findByText("Projekt byl vytvořen.")).toBeVisible();
    expect(store.getState().projectId).toBe("project-created");
    expect(createProject).toHaveBeenCalledWith("workspace-main", {
      title: "Denní projekt",
      description: "První popis",
      notes: null,
      tags: ["deník"],
    });

    const title = screen.getByLabelText("Název");
    await user.clear(title);
    await user.type(title, "Denní projekt upravený");
    await user.click(screen.getByRole("button", { name: "Uložit změny" }));
    expect(await screen.findByText("Změny projektu byly uloženy.")).toBeVisible();
    expect(updateProject).toHaveBeenCalledWith(
      "project-created",
      1,
      expect.objectContaining({ title: "Denní projekt upravený" }),
    );

    await user.click(screen.getByRole("button", { name: "Archivovat" }));
    expect(await screen.findByText(/Projekt byl archivován/)).toBeVisible();
    expect(archiveProject).toHaveBeenCalledWith("project-created", 2);
    await user.click(screen.getByRole("button", { name: "Obnovit projekt" }));
    expect(await screen.findByText("Projekt byl obnoven.")).toBeVisible();
    expect(restoreProject).toHaveBeenCalledWith("project-created", 3);
  });
});
