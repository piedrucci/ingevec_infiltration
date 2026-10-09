import { embedDashboard, type EmbeddedDashboard as EmbeddedDashboardHandle } from "@superset-ui/embedded-sdk";
import { useEffect, useRef, useState } from "react";

import { Button } from "../../components/ui/button";
import type { EmbeddedDashboardMetadata } from "../../types";
import { useAnalyticsGuestToken } from "./queries";

type Props = { dashboard: EmbeddedDashboardMetadata; retryKey: number; onRetry: () => void };

export function EmbeddedDashboard({ dashboard, retryKey, onRetry }: Props) {
  const mountPoint = useRef<HTMLDivElement>(null);
  const handle = useRef<EmbeddedDashboardHandle | null>(null);
  const tokenMutation = useAnalyticsGuestToken();
  const resetToken = tokenMutation.reset;
  const issueToken = tokenMutation.mutateAsync;
  const [error, setError] = useState(false);
  const [mounting, setMounting] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    setMounting(true);
    resetToken();
    if (!mountPoint.current || !dashboard.dashboard_uuid || !dashboard.superset_url) return;
    const point = mountPoint.current;

    void embedDashboard({
      id: dashboard.dashboard_uuid,
      supersetDomain: dashboard.superset_url,
      mountPoint: point,
      iframeTitle: dashboard.title ?? "Panel de analítica",
      referrerPolicy: "strict-origin-when-cross-origin",
      dashboardUiConfig: { hideTitle: true, hideTab: true, hideChartControls: true, filters: { visible: true, expanded: true } },
      fetchGuestToken: async () => {
        if (cancelled) throw new Error("La sesión de analítica terminó.");
        try {
          return (await issueToken()).token;
        } catch (cause) {
          if (!cancelled) {
            setError(true);
            handle.current?.unmount();
            handle.current = null;
          }
          throw cause;
        }
      },
    }).then((embedded) => {
      if (cancelled) embedded.unmount();
      else {
        handle.current = embedded;
        setMounting(false);
      }
    }).catch(() => {
      if (!cancelled) {
        point.replaceChildren();
        setError(true);
        setMounting(false);
      }
    });

    return () => {
      cancelled = true;
      handle.current?.unmount();
      handle.current = null;
      resetToken();
      point.replaceChildren();
    };
  }, [dashboard, retryKey, issueToken, resetToken]);

  return (
    <div className="relative h-[calc(100vh-15rem)] min-h-[560px] w-full min-w-0 overflow-hidden rounded-md [&_iframe]:h-full [&_iframe]:w-full [&_iframe]:border-0" aria-busy={mounting}>
      <div ref={mountPoint} className="h-full w-full min-w-0" />
      {mounting && !error && <div className="absolute inset-0 grid place-items-center bg-background/80 text-sm text-muted-foreground">Cargando panel de analítica…</div>}
      {error && <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-background text-center text-sm text-destructive"><p>La sesión de analítica expiró o no fue posible conectar. Vuelve a intentarlo.</p><Button variant="outline" onClick={onRetry}>Volver a conectar</Button></div>}
    </div>
  );
}
