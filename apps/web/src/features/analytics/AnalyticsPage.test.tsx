// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EmbedDashboardParams } from "@superset-ui/embedded-sdk";
import { AnalyticsPage } from "./AnalyticsPage";

const { embedDashboard, getDashboard, getGuestToken, unmount } = vi.hoisted(() => ({
  embedDashboard: vi.fn(),
  getDashboard: vi.fn(),
  getGuestToken: vi.fn(),
  unmount: vi.fn(),
}));

vi.mock("@superset-ui/embedded-sdk", () => ({ embedDashboard }));
vi.mock("../../api", () => ({ getAnalyticsDashboard: getDashboard, getAnalyticsGuestToken: getGuestToken }));
vi.mock("../../auth", () => ({ hasAnalyticsAccess: () => true, analyticsSessionKey: () => "user-1:superset_viewer" }));

describe("AnalyticsPage embedding lifecycle", () => {
  beforeEach(() => {
    embedDashboard.mockReset().mockResolvedValue({ unmount });
    getDashboard.mockReset().mockResolvedValue({
      enabled: true,
      dashboard_uuid: "embed-uuid",
      superset_url: "http://localhost:8088",
      title: "Analítica",
    });
    getGuestToken.mockReset()
      .mockResolvedValueOnce({ token: "fresh-token-1", expires_in: 300 })
      .mockResolvedValueOnce({ token: "fresh-token-2", expires_in: 300 });
    unmount.mockReset();
  });

  afterEach(() => vi.clearAllMocks());

  it("requests a fresh token through the shared API callback and unmounts on route exit", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider>);

    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    const params = embedDashboard.mock.calls[0][0] as EmbedDashboardParams;
    expect(params.id).toBe("embed-uuid");
    expect(await params.fetchGuestToken()).toBe("fresh-token-1");
    expect(await params.fetchGuestToken()).toBe("fresh-token-2");
    expect(getGuestToken).toHaveBeenCalledTimes(2);

    view.unmount();
    expect(unmount).toHaveBeenCalledTimes(1);
  });

  it("stops an async SDK mount that resolves after the component was removed", async () => {
    let finishMount: ((value: { unmount: typeof unmount }) => void) | undefined;
    embedDashboard.mockImplementation(() => new Promise((resolve) => { finishMount = resolve; }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider>);

    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    view.unmount();
    finishMount?.({ unmount });
    await waitFor(() => expect(unmount).toHaveBeenCalledTimes(1));
  });

  it("cleans up the first mount during React StrictMode replay", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<StrictMode><QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider></StrictMode>);

    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(unmount).toHaveBeenCalledTimes(1));
    view.unmount();
    expect(unmount).toHaveBeenCalledTimes(2);
  });

  it("unmounts the iframe and shows recovery guidance when token refresh fails", async () => {
    getGuestToken.mockReset().mockRejectedValue(new Error("temporary API error"));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider>);

    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    const params = embedDashboard.mock.calls[0][0] as EmbedDashboardParams;
    await expect(params.fetchGuestToken()).rejects.toThrow("temporary API error");
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(unmount).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("toggles fullscreen on the dashboard container and follows the browser state", async () => {
    let current: Element | null = null;
    Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: true });
    Object.defineProperty(document, "fullscreenElement", { configurable: true, get: () => current });
    const change = (element: Element | null) => { current = element; document.dispatchEvent(new Event("fullscreenchange")); };
    const requestFullscreen = vi.fn(function (this: HTMLElement) { change(this); return Promise.resolve(); });
    HTMLElement.prototype.requestFullscreen = requestFullscreen;
    document.exitFullscreen = vi.fn(() => { change(null); return Promise.resolve(); });
    try {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const view = render(<QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider>);

      fireEvent.click(await screen.findByRole("button", { name: "Pantalla completa" }));
      await waitFor(() => expect(requestFullscreen).toHaveBeenCalledTimes(1));
      const container = requestFullscreen.mock.contexts[0] as HTMLElement;
      expect(container.contains(embedDashboard.mock.calls[0][0].mountPoint)).toBe(true);
      expect(screen.getByRole("button", { name: "Salir de pantalla completa" }).getAttribute("aria-pressed")).toBe("true");

      act(() => change(null));  // Esc exits through the browser
      expect(await screen.findByRole("button", { name: "Pantalla completa" })).toBeTruthy();
      view.unmount();
    } finally {
      delete (document as { fullscreenEnabled?: boolean }).fullscreenEnabled;
      delete (document as { fullscreenElement?: Element | null }).fullscreenElement;
    }
  });

  it("hides the fullscreen button where the browser does not support it", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><AnalyticsPage /></QueryClientProvider>);
    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("button", { name: "Pantalla completa" })).toBeNull();
    view.unmount();
  });
});
