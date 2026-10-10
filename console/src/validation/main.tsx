import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./validation.css";
import { EspaceValidation } from "./EspaceValidation";

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <EspaceValidation />
  </StrictMode>
);
