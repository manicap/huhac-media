import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
