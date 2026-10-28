import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LibraryIcon } from "./moduleIcons";
import { defineModuleRegistry } from "./moduleContract";
import { studioModuleRegistry } from "./moduleRegistry";
import { renderStudio } from "../test/renderStudio";

function BrokenModule(): never {
  throw new Error("render failed");
}

describe("Studio shell", () => {
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
