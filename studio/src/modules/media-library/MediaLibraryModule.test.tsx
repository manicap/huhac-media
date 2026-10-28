import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { syntheticDataSource } from "../../data/syntheticDataSource";
import { renderStudio } from "../../test/renderStudio";

describe("Media Library module", () => {
  it("reactively filters media by project", async () => {
    const { user } = renderStudio();
    await user.click(await screen.findByRole("button", { name: /Podzimní turné/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));

    expect(await screen.findByText("Pódium – široký záběr")).toBeVisible();
    expect(screen.queryByText("Cover singlu – finále")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Projekty" }));
    await user.click(screen.getByRole("button", { name: /Kampaň k singlu/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));

    expect(await screen.findByText("Cover singlu – finále")).toBeVisible();
    expect(screen.queryByText("Pódium – široký záběr")).not.toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: /Nový projekt/ }));
    await user.click(screen.getByRole("link", { name: "Mediální knihovna" }));
    expect(await screen.findByText("Tento projekt zatím nemá žádná média")).toBeVisible();
  });

  it("contains loading failures inside the module", async () => {
    const failingDataSource = {
      ...syntheticDataSource,
      async listMedia() {
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
    expect(await screen.findByText("Nejprve vyberte projekt")).toBeVisible();
    expect(within(screen.getByLabelText("Pracovní kontext")).getByText("Žádný projekt")).toBeVisible();
  });
});
