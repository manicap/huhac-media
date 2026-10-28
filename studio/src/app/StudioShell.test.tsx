import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LibraryIcon } from "./moduleIcons";
import { defineModuleRegistry } from "./moduleContract";
import { studioModuleRegistry } from "./moduleRegistry";
import { renderStudio } from "../test/renderStudio";
import { createStudioStore } from "../context/studioStore";
import { syntheticDataSource } from "../data/syntheticDataSource";

function BrokenModule(): never {
  throw new Error("render failed");
}

describe("Studio shell", () => {
  it("clears stale context and identifies an offline backend", async () => {
    const store = createStudioStore({
      workspaceId: "workspace-main",
      projectId: "project-tour",
      activeModuleId: "media-library",
    });
    store.getState().toggleMedia("media-stage-wide");
    const offlineDataSource = {
      ...syntheticDataSource,
      async getSession() {
        return {
          runtimeId: "runtime-offline",
          mode: "offline" as const,
          activeWorkspaceId: null,
          workspaces: [{ id: "workspace-main", title: "workspace-main", status: "offline" as const }],
        };
      },
    };

    renderStudio({
      route: "/modules/media-library",
      store,
      dataSource: offlineDataSource,
    });

    expect(await screen.findByText("Offline · bez aktivní knihovny")).toBeVisible();
    await waitFor(() => expect(store.getState().workspaceId).toBeNull());
    expect(store.getState().projectId).toBeNull();
    expect(store.getState().selectedMediaIds).toEqual([]);
    expect(screen.getByRole("status")).toHaveTextContent("Není připojený workspace");
  });

  it("fails closed when the backend session is unavailable", async () => {
    const store = createStudioStore({ workspaceId: "workspace-main", projectId: "project-tour" });
    store.getState().toggleMedia("media-stage-wide");

    renderStudio({
      store,
      dataSource: {
        ...syntheticDataSource,
        async getSession() {
          throw new Error("backend unavailable");
        },
      },
    });

    expect(await screen.findByText("Backend není dostupný")).toBeVisible();
    await waitFor(() => expect(store.getState().workspaceId).toBeNull());
    expect(store.getState().projectId).toBeNull();
    expect(store.getState().selectedMediaIds).toEqual([]);
  });

  it("switches navigation and updates active module", async () => {
    const { store, user } = renderStudio();
    await screen.findByRole("heading", { name: "Projekty" });
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));

    expect(screen.getByRole("heading", { name: "Mediální knihovna" })).toBeVisible();
    expect(store.getState().activeModuleId).toBe("media-library");
  });

  it("supports keyboard navigation", async () => {
    const { user } = renderStudio();
    const libraryLink = screen.getByRole("link", { name: "Mediální knihovna" });
    libraryLink.focus();
    expect(libraryLink).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: "Mediální knihovna" })).toBeVisible();
  });

  it("keeps the shell usable when one module throws", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const modules = defineModuleRegistry([
      ...studioModuleRegistry,
      {
        id: "broken",
        title: "Porouchaný",
        navigationOrder: 30,
        icon: LibraryIcon,
        component: BrokenModule,
      },
    ]);
    const { user } = renderStudio({ modules, route: "/modules/broken" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Modul Porouchaný selhal");
    await user.click(screen.getByRole("link", { name: "Projekty" }));
    expect(await screen.findByRole("heading", { name: "Projekty" })).toBeVisible();
    consoleSpy.mockRestore();
  });

  it("renders a safe state for missing and unavailable modules", async () => {
    const modules = defineModuleRegistry([
      ...studioModuleRegistry,
      {
        id: "future",
        title: "Budoucí modul",
        navigationOrder: 30,
        icon: LibraryIcon,
        component: () => <div>future</div>,
        requiredCapabilities: ["future-capability"],
        unavailableReason: "Není součástí prototypu",
      },
    ]);
    renderStudio({ modules, route: "/modules/future" });

    expect(screen.getByText("Budoucí modul").closest("[aria-disabled='true']")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Modul není dostupný");
  });
});
