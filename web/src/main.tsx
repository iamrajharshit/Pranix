// SPDX-License-Identifier: AGPL-3.0-only
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/cormorant-garamond/600.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "./styles.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
