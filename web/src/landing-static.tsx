import React from "react";
import ReactDOM, { hydrateRoot } from "react-dom/client";
import "./app/styles/landing-static.css";
import { LandingContent } from "./features/landing/LandingContent";
import { landingPrimaryAction } from "./features/landing/landingConfig";
import xuanmuLogo from "./assets/xuanmu-logo.svg";

const rootElement = document.getElementById("root") as HTMLElement;
const landing = (
  <React.StrictMode>
    <LandingContent logoSrc={xuanmuLogo} primaryAction={landingPrimaryAction} />
  </React.StrictMode>
);

if (rootElement.hasChildNodes()) {
  hydrateRoot(rootElement, landing);
} else {
  ReactDOM.createRoot(rootElement).render(landing);
}
