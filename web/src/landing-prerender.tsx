import { renderToString } from "react-dom/server";
import { LandingContent } from "./features/landing/LandingContent";
import { landingPrimaryAction } from "./features/landing/landingConfig";

export function renderLandingHtml(logoSrc: string) {
  return renderToString(
    <LandingContent logoSrc={logoSrc} primaryAction={landingPrimaryAction} />,
  );
}
