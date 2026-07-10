import { useNavigate } from "react-router-dom";
import xuanmuLogo from "../../assets/xuanmu-logo.svg";
import { useAuth } from "../../shared/auth/AuthProvider";
import { LandingContent } from "./LandingContent";

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const consolePath = isAuthenticated ? "/playground" : "/login";

  return <LandingContent logoSrc={xuanmuLogo} primaryAction={{ label: "Open workbench", onSelect: () => navigate(consolePath) }} />;
}
