import { Navigate, Route, Routes } from "react-router-dom";

import { MarketMatrixPage } from "@/features/market/pages/MarketMatrixPage";
import { OutOfScopePage } from "@/features/market/pages/OutOfScopePage";
import { RunsPage } from "@/features/market/pages/RunsPage";
import { ScreenPage } from "@/features/market/pages/ScreenPage";
import { TickerDetailPage } from "@/features/market/pages/TickerDetailPage";
import { UniversesPage } from "@/features/market/pages/UniversesPage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/market" replace />} />
      <Route path="/market" element={<MarketMatrixPage />} />
      <Route path="/market/:ticker" element={<TickerDetailPage />} />
      <Route path="/screen" element={<ScreenPage />} />
      <Route path="/universes" element={<UniversesPage />} />
      <Route path="/runs" element={<RunsPage />} />
      <Route path="*" element={<OutOfScopePage />} />
    </Routes>
  );
}
