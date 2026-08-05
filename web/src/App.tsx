import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GlobalNav } from "./components/layout/GlobalNav";
import { HomePage } from "./pages/HomePage";
import { StockPage } from "./pages/StockPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { StrategyPage } from "./pages/StrategyPage";
import { MarketPage } from "./pages/MarketPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <GlobalNav />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/stocks/:code" element={<StockPage />} />
          <Route path="/portfolios" element={<PortfolioPage />} />
          <Route path="/strategies" element={<StrategyPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
