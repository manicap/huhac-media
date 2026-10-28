import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { syntheticDataSource, syntheticProjects } from "../../data/syntheticDataSource";
import { renderStudio } from "../../test/renderStudio";

describe("Media Library module", () => {
  it("reactively filters media by project", async () => {
    const { user } = renderStudio();
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));

    const firstLibrary = await screen.findByLabelText("Média aktivního projektu");
    expect(within(firstLibrary).getByText("Pódium – široký záběr")).toBeVisible();
    expect(within(firstLibrary).queryByText("Cover singlu – finále")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Projekty" }));
    await user.click(screen.getByRole("button", { name: /Kampaň k singlu/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));

    const secondLibrary = await screen.findByLabelText("Média aktivního projektu");
    expect(within(secondLibrary).getByText("Cover singlu – finále")).toBeVisible();
    expect(within(secondLibrary).queryByText("Pódium – široký záběr")).not.toBeInTheDocument();
  });

  it("keeps selected media across module navigation", async () => {
    const { store, user } = renderStudio();
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    const checkbox = await screen.findByRole("checkbox", {
      name: "Vybrat Pódium – široký záběr",
    });
    await user.click(checkbox);
    await user.click(screen.getByRole("link", { name: "Projekty" }));

    expect(store.getState().selectedMediaIds).toEqual(["media-stage-wide"]);
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    expect(screen.getByRole("checkbox", { name: "Vybrat Pódium – široký záběr" })).toBeChecked();
  });

  it("clears selection when project changes", async () => {
    const { store, user } = renderStudio();
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    await user.click(await screen.findByRole("checkbox", { name: "Vybrat Pódium – široký záběr" }));
    await user.click(screen.getByRole("link", { name: "Projekty" }));
    await user.click(screen.getByRole("button", { name: /Kampaň k singlu/ }));

    expect(store.getState().selectedMediaIds).toEqual([]);
  });

  it("shows an explicit empty state", async () => {
    const { user } = renderStudio();
    const projectList = await screen.findByLabelText("Dostupné projekty");
    await user.click(within(projectList).getByRole("button", { name: /Nový projekt/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    expect(await screen.findByText("Tento projekt zatím nemá žádná média")).toBeVisible();
  });

  it("contains loading failures inside the module", async () => {
    const failingDataSource = {
      ...syntheticDataSource,
      async listProjectMedia() {
        throw new Error("synthetic failure");
      },
    };
    const { user } = renderStudio({ dataSource: failingDataSource });
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Knihovnu se nepodařilo načíst");
  });

  it("resets project and selection when workspace changes", async () => {
    const { store, user } = renderStudio();
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    await user.click(await screen.findByRole("checkbox", { name: "Vybrat Pódium – široký záběr" }));
    await user.selectOptions(screen.getByLabelText("Aktivní workspace"), "workspace-archive");

    expect(store.getState().projectId).toBeNull();
    expect(store.getState().selectedMediaIds).toEqual([]);
    expect(await screen.findByText("Nejprve vyberte aktivní projekt")).toBeVisible();
    expect(within(screen.getByLabelText("Pracovní kontext")).getByText("Žádný projekt")).toBeVisible();
  });

  it("adds and removes links without losing the latest project revision", async () => {
    const addMediaLinks = vi.fn(async () => ({
      ...syntheticProjects[0],
      mediaCount: 5,
      revision: 2,
    }));
    const removeMediaLinks = vi.fn(async () => ({
      ...syntheticProjects[0],
      mediaCount: 4,
      revision: 3,
    }));
    const { user } = renderStudio({
      dataSource: { ...syntheticDataSource, addMediaLinks, removeMediaLinks },
    });

    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    await user.click(screen.getByRole("button", { name: "Všechna média" }));
    await user.click(await screen.findByRole("checkbox", { name: "Vybrat Cover singlu – finále" }));
    await user.click(screen.getByRole("button", { name: "Přidat do projektu" }));
    expect(await screen.findByText("Vybraná média byla přidána do projektu.")).toBeVisible();
    expect(addMediaLinks).toHaveBeenCalledWith("project-tour", 1, ["media-cover"]);

    await user.click(screen.getByRole("button", { name: "Média projektu" }));
    await user.click(await screen.findByRole("checkbox", { name: "Vybrat Pódium – široký záběr" }));
    await user.click(screen.getByRole("button", { name: "Odebrat z projektu" }));
    expect(await screen.findByText(/Původní soubory zůstaly beze změny/)).toBeVisible();
    expect(removeMediaLinks).toHaveBeenCalledWith("project-tour", 2, ["media-stage-wide"]);
  });
});
