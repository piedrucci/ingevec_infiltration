// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

const { keycloak } = vi.hoisted(() => ({
  keycloak: {
    subject: "user-1",
    realmAccess: { roles: ["superset_viewer"] },
    init: vi.fn().mockResolvedValue(true),
    updateToken: vi.fn().mockResolvedValue(true),
    logout: vi.fn().mockResolvedValue(undefined),
    onAuthRefreshSuccess: undefined as (() => void) | undefined,
    onAuthRefreshError: undefined as (() => void) | undefined,
    onAuthLogout: undefined as (() => void) | undefined,
  },
}));

vi.mock("keycloak-js", () => ({ default: vi.fn(function () { return keycloak; }) }));

import { queryClient } from "./query-client";
import { logout, startAuthentication } from "./auth";

describe("analytics auth cache isolation", () => {
  afterEach(() => queryClient.clear());

  it("clears metadata and guest-token mutation state when analytics identity changes or logs out", async () => {
    await startAuthentication();
    queryClient.setQueryData(["analytics", "user-1:superset_viewer", "dashboard"], { title: "private" });
    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationKey: ["analytics", "guest-token"],
      mutationFn: async () => "private-token",
    });

    keycloak.realmAccess = { roles: ["superset_admin"] };
    keycloak.onAuthRefreshSuccess?.();
    expect(queryClient.getQueryCache().findAll({ queryKey: ["analytics"] })).toHaveLength(0);
    expect(queryClient.getMutationCache().findAll({ mutationKey: ["analytics"] })).toHaveLength(0);

    queryClient.setQueryData(["analytics", "user-1:superset_admin", "dashboard"], { title: "private" });
    await logout();
    expect(queryClient.getQueryCache().findAll({ queryKey: ["analytics"] })).toHaveLength(0);
    expect(keycloak.logout).toHaveBeenCalledOnce();
    queryClient.getMutationCache().remove(mutation);
  });
});
