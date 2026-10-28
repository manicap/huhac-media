import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { StudioApp } from "./app/StudioApp";
import "./studio.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <StudioApp />
    </BrowserRouter>
  </StrictMode>,
);
