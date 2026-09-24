import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { startAuthentication } from "./auth";
import { queryClient } from "./query-client";
import "@fontsource/roboto/latin-400.css";
import "@fontsource/roboto/latin-500.css";
import "@fontsource/roboto/latin-600.css";
import "@fontsource/roboto/latin-700.css";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

startAuthentication()
  .then(() => root.render(<BrowserRouter><QueryClientProvider client={queryClient}><App /></QueryClientProvider></BrowserRouter>))
  .catch(() => root.render(<p className="fatal-error">No fue posible iniciar sesión con Keycloak.</p>));
