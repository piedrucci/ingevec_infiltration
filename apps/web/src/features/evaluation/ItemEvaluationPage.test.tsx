// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ItemEvaluationPage } from "./ItemEvaluationPage";

const { replaceCauses } = vi.hoisted(() => ({ replaceCauses: vi.fn() }));

function LocationProbe() {
  const location = useLocation();
  return <p>{`${location.pathname}${location.search}`}</p>;
}

vi.mock("../../api", () => ({
  createFailureCause: vi.fn(),
  removePostventaItemDocument: vi.fn(),
  replacePostventaItemFailureCauses: replaceCauses,
}));

vi.mock("../../queries/postventa-items", () => ({
  postventaItemQueryKeys: { all: ["postventa-items"] },
  usePostventaItem: () => ({
    data: {
      id: 42,
      public_id: "item-123",
      project_id: "722",
      project_name: "AKI KB Matta",
      classification: "Terminación",
      notes: "Observación de prueba",
      request_date: null,
      handled_by: null,
      failure_causes: [],
      document: null,
      reconciliation_status: "PENDING",
      has_document: false,
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../documents/queries", () => ({
  useFailureCauses: () => ({
    data: [
      { code: "FILTRACION", display_name_es: "Filtración", category_name_es: "Humedad" },
      { code: "GRIETA", display_name_es: "Grieta", category_name_es: "Estructural" },
    ],
    error: null,
    isLoading: false,
  }),
  useFailureCauseCategories: () => ({ data: [], error: null }),
  documentQueryKeys: { failureCauses: () => ["documents", "failure-causes"] },
}));

describe("ItemEvaluationPage", () => {
  beforeEach(() => {
    replaceCauses.mockReset();
    replaceCauses.mockResolvedValue({
      public_id: "item-123",
      failure_causes: [
        { code: "FILTRACION", display_name_es: "Filtración", category_name_es: "Humedad" },
        { code: "GRIETA", display_name_es: "Grieta", category_name_es: "Estructural" },
      ],
    });
  });

  it("saves selected causes and returns to the returnTo URL including its search query", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/items/item-123/evaluation?returnTo=%2Fitems%2Fevaluation%3FpageNumber%3D2"]}>
          <Routes>
            <Route path="/items/:publicId/evaluation" element={<ItemEvaluationPage />} />
            <Route path="/items/evaluation" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const causeInput = screen.getByRole("combobox", { name: "Buscar causas…" });
    await user.click(causeInput);
    await user.click(await screen.findByRole("option", { name: /Humedad · Filtración/ }));
    await user.click(causeInput);
    await user.click(await screen.findByRole("option", { name: /Estructural · Grieta/ }));
    await user.keyboard("{Escape}");

    expect(screen.getByText("2 seleccionadas")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Guardar causas" }));

    await waitFor(() => {
      expect(replaceCauses).toHaveBeenCalledWith("item-123", ["FILTRACION", "GRIETA"]);
    });
    expect(await screen.findByText("/items/evaluation?pageNumber=2")).toBeTruthy();
  });
});
