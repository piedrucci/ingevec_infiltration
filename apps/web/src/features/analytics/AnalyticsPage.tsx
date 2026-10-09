import { useState } from "react";

import { hasAnalyticsAccess } from "../../auth";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { EmbeddedDashboard } from "./EmbeddedDashboard";
import { useAnalyticsDashboard } from "./queries";

function errorStatus(error: Error): number | undefined {
  return (error as Error & { status?: number }).status;
}

export function AnalyticsPage() {
  const query = useAnalyticsDashboard();
  const [retryKey, setRetryKey] = useState(0);

  if (!hasAnalyticsAccess()) {
    return <Alert variant="destructive"><AlertTitle>Acceso restringido</AlertTitle><AlertDescription>Tu cuenta no tiene un rol de analítica asignado.</AlertDescription></Alert>;
  }

  return <Card className="gap-0 overflow-hidden p-0">
    <CardContent className="p-0">
      {query.isPending && <p role="status" className="py-12 text-center text-muted-foreground">Cargando panel…</p>}
      {query.isError && <Alert variant="destructive"><AlertTitle>{errorStatus(query.error) === 403 ? "Acceso restringido" : "No se pudo cargar el panel"}</AlertTitle><AlertDescription className="flex flex-wrap items-center justify-between gap-3"><span>{errorStatus(query.error) === 403 ? "Solicita acceso al equipo administrador." : "Comprueba tu conexión e inténtalo nuevamente."}</span><Button variant="outline" onClick={() => void query.refetch()}>Reintentar</Button></AlertDescription></Alert>}
      {query.data && !query.data.enabled && <Alert><AlertTitle>Panel no disponible</AlertTitle><AlertDescription>La integración de analítica aún no está habilitada en este entorno.</AlertDescription></Alert>}
      {query.data?.enabled && <EmbeddedDashboard key={retryKey} dashboard={query.data} retryKey={retryKey} onRetry={() => setRetryKey((value) => value + 1)} />}
    </CardContent>
  </Card>;
}
