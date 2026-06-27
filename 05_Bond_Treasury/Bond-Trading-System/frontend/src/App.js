import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import HistoryPage from "./pages/HistoryPage";
import BacktestPage from "./pages/BacktestPage";
import PortfolioPage from "./pages/PortfolioPage";
import SettingsPage from "./pages/SettingsPage";
import PaperTradingPage from "./pages/PaperTradingPage";
import MarketplacePage from "./pages/MarketplacePage";
import SocialPage from "./pages/SocialPage";
import YieldCurvePage from "./pages/YieldCurvePage";
import RiskAnalyticsPage from "./pages/RiskAnalyticsPage";
import PortfolioOptimizerPage from "./pages/PortfolioOptimizerPage";

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route 
              path="/dashboard" 
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/history" 
              element={
                <ProtectedRoute>
                  <HistoryPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/backtest" 
              element={
                <ProtectedRoute>
                  <BacktestPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/portfolio" 
              element={
                <ProtectedRoute>
                  <PortfolioPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/settings" 
              element={
                <ProtectedRoute>
                  <SettingsPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/paper-trading" 
              element={
                <ProtectedRoute>
                  <PaperTradingPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/marketplace" 
              element={
                <ProtectedRoute>
                  <MarketplacePage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/social" 
              element={
                <ProtectedRoute>
                  <SocialPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/social/:userId" 
              element={
                <ProtectedRoute>
                  <SocialPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/yield-curve" 
              element={
                <ProtectedRoute>
                  <YieldCurvePage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/risk-analytics" 
              element={
                <ProtectedRoute>
                  <RiskAnalyticsPage />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/portfolio-optimizer" 
              element={
                <ProtectedRoute>
                  <PortfolioOptimizerPage />
                </ProtectedRoute>
              } 
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
