import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createStudioStore } from "../../context/studioStore";
import { syntheticDataSource, syntheticProjects } from "../../data/syntheticDataSource";
import { createPlaybackPreferencesStore } from "../../playback/playbackPreferences";
import { renderStudio } from "../../test/renderStudio";

afterEach(() => vi.restoreAllMocks());

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
    store.getState().setWorkspace("workspace-archive");

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

  it("keeps selection in the compact layout and exposes contextual batch actions", async () => {
    const store = createStudioStore({ workspaceId: "workspace-main", activeModuleId: "media-library" });
    const { user } = renderStudio({ route: "/modules/media-library", store });

    expect(screen.queryByRole("region", { name: "Hromadné operace" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Všechna média" }));
    const checkbox = await screen.findByRole("checkbox", { name: "Vybrat Pódium – široký záběr" });
    await user.click(checkbox);

    const actions = screen.getByRole("region", { name: "Hromadné operace" });
    expect(within(actions).getByText("1 vybráno")).toBeVisible();
    expect(within(actions).getByText(/nejprve vyberte aktivní projekt/)).toBeVisible();
    expect(within(actions).getByRole("button", { name: "Přidat do projektu" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Kompaktní" }));
    const gallery = screen.getByLabelText("Všechna média");
    expect(gallery).toHaveClass("media-grid--compact");
    expect(within(gallery).getAllByRole("article").slice(0, 3).map((card) => card.querySelector("strong")?.textContent)).toEqual([
      "Pódium – široký záběr",
      "Backstage moment",
      "Publikum pod světly",
    ]);
    expect(checkbox).toBeChecked();
    expect(store.getState().selectedMediaIds).toEqual(["media-stage-wide"]);

    await user.click(within(actions).getByRole("button", { name: "Zrušit výběr" }));
    expect(store.getState().selectedMediaIds).toEqual([]);
    expect(screen.queryByRole("region", { name: "Hromadné operace" })).not.toBeInTheDocument();
  });

  it("stops the previous video, shares volume, and keeps playback separate from selection", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
    const store = createStudioStore({
      workspaceId: "workspace-main",
      projectId: "project-tour",
      activeModuleId: "media-library",
    });
    const playbackStore = createPlaybackPreferencesStore(null);
    const { user } = renderStudio({
      route: "/modules/media-library",
      store,
      playbackStore,
    });

    await user.click(await screen.findByRole("button", { name: "Všechna média" }));
    const selectableCheckboxes = (await screen.findAllByRole("checkbox")).filter(
      (checkbox) => !checkbox.hasAttribute("disabled"),
    );
    await user.click(selectableCheckboxes[0]);
    expect(store.getState().selectedMediaIds).toEqual(["media-cover"]);
    await user.click(await screen.findByRole("button", { name: "Přehrát Backstage moment" }));
    const first = await screen.findByLabelText<HTMLVideoElement>("Přehrávač Backstage moment");
    expect(play).toHaveBeenCalled();
    expect(store.getState().selectedMediaIds).toEqual(["media-cover"]);

    first.volume = 0.3;
    fireEvent.volumeChange(first);
    expect(playbackStore.getState().volume).toBe(0.3);

    await user.click(screen.getByRole("button", { name: "Přehrát Vertikální teaser" }));
    const second = await screen.findByLabelText<HTMLVideoElement>("Přehrávač Vertikální teaser");
    expect(pause).toHaveBeenCalled();
    expect(second.volume).toBe(0.3);
    expect(store.getState().selectedMediaIds).toEqual(["media-cover"]);

    await user.click(screen.getByRole("link", { name: "Projekty" }));
    expect(screen.queryByLabelText("Přehrávač Vertikální teaser")).not.toBeInTheDocument();
    expect(pause).toHaveBeenCalledTimes(2);
  });

  it("uses catalog aspect ratios for horizontal, square, and vertical media", async () => {
    const store = createStudioStore({ workspaceId: "workspace-main", activeModuleId: "media-library" });
    const { user } = renderStudio({ route: "/modules/media-library", store });
    await user.click(await screen.findByRole("button", { name: "Všechna média" }));

    const horizontal = screen.getByText("Pódium – široký záběr").closest("article");
    const square = screen.getByText("Cover singlu – finále").closest("article");
    const vertical = screen.getByText("Vertikální teaser").closest("article");

    expect(horizontal?.querySelector(".media-card__preview")).toHaveStyle({ aspectRatio: String(16 / 9) });
    expect(square?.querySelector(".media-card__preview")).toHaveStyle({ aspectRatio: "1" });
    expect(vertical?.querySelector(".media-card__preview")).toHaveStyle({ aspectRatio: String(9 / 16) });
  });
});
