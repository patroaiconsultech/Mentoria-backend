import React from "react";

import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import Landing from "./routes/Landing";
import MentoriaLanding from "./routes/MentoriaLanding";
import MentoriaPortal from "./routes/MentoriaPortal";
import AppConsole from "./routes/AppConsole";
import AccessPortal from "./routes/AccessPortal";
import AdminAccessGate from "./routes/AdminAccessGate";
import InviteAccept from "./routes/InviteAccept";
import PlatformInviteAccept from "./routes/PlatformInviteAccept";
import TalentApplication from "./routes/TalentApplication";
import PwaUpdateBanner from "./components/PwaUpdateBanner";
import BillingPremiumPreview from "./features/billing/pages/BillingPremiumPreview";
import ArtifactPremiumPreview from "./features/artifacts/pages/ArtifactPremiumPreview";

import "./styles.css";

const AppEntry = AppConsole;

export default function App() {
  const source = new URLSearchParams(window.location.search).get("source") || "";
  const isPwaLaunch = source.startsWith("pwa");

  return (
    <BrowserRouter>
      <a className="skip-link" href="#main-content">
        Ir para o conteúdo
      </a>
      <PwaUpdateBanner />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/mentoria" element={<MentoriaLanding />} />
        <Route path="/mentoria/area" element={<MentoriaPortal />} />
        <Route path="/access" element={<AccessPortal />} />
        <Route path="/talentos/candidatura" element={<TalentApplication />} />
        <Route path="/app" element={<AppEntry />} />
        <Route path="/admin" element={<AdminAccessGate />} />
        <Route path="/app/billing" element={<BillingPremiumPreview />} />
        <Route path="/app/artifacts" element={<ArtifactPremiumPreview />} />
        <Route path="/invite/:token" element={<InviteAccept />} />
        <Route path="/activate" element={<PlatformInviteAccept />} />
        <Route path="*" element={<Navigate to={isPwaLaunch ? "/" : "/"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
