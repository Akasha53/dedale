import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./finitions.css";
import { App } from "./App";
import { DataProvider } from "./api/store";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DataProvider>
      <App />
    </DataProvider>
  </StrictMode>
);
