import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { startAuthentication } from "./auth";
import { queryClient } from "./query-client";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

startAuthentication()
  .then(() => root.render(<BrowserRouter><QueryClientProvider client={queryClient}><App /></QueryClientProvider></BrowserRouter>))
  .catch(() => root.render(<p className="fatal-error">No fue posible iniciar sesión con Keycloak.</p>));
