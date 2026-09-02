import { createRoot } from "react-dom/client";

import { App } from "./App";
import { startAuthentication } from "./auth";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

startAuthentication()
  .then(() => root.render(<App />))
  .catch(() => root.render(<p className="fatal-error">No fue posible iniciar sesión con Keycloak.</p>));
