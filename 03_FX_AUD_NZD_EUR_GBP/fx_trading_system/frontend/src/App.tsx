import React, { useState } from 'react';
import { DataProvider, useData } from './context/DataContext';
import Dashboard from './pages/Dashboard';
import Confirmation from './pages/Confirmation';
import EventCalendar from './pages/EventCalendar';
import RiskManagement from './pages/RiskManagement';
import ModelSettings from './pages/ModelSettings';
import BrokerConnection from './pages/BrokerConnection';
import {
  LayoutDashboard,
  Timer,
  CalendarDays,
  ShieldAlert,
  SlidersHorizontal,
  Plug,
  Wifi,
  WifiOff,
} from 'lucide-react';

const tabs = [
  { id: 'dashboard', label: '仪表盘', labelEn: 'Dashboard', icon: LayoutDashboard },
  { id: 'confirmation', label: '30秒确认', labelEn: '30s Confirm', icon: Timer },
  { id: 'calendar', label: '事件日历', labelEn: 'Calendar', icon: CalendarDays },
  { id: 'risk', label: '风控管理', labelEn: 'Risk', icon: ShieldAlert },
  { id: 'settings', label: '模型设置', labelEn: 'Settings', icon: SlidersHorizontal },
  { id: 'broker', label: '券商连接', labelEn: 'Broker', icon: Plug },
];

function AppContent() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const { isConnected } = useData();

  const renderPage = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'confirmation': return <Confirmation />;
      case 'calendar': return <EventCalendar />;
      case 'risk': return <RiskManagement />;
      case 'settings': return <ModelSettings />;
      case 'broker': return <BrokerConnection />;
      default: return <Dashboard />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">
            FX
          </div>
          <h1 className="text-lg font-bold text-white hidden sm:block">FX Trading Dashboard</h1>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {isConnected ? (
            <span className="flex items-center gap-1.5 text-emerald-400">
              <Wifi className="w-3.5 h-3.5" />
              已连接
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-red-400">
              <WifiOff className="w-3.5 h-3.5" />
              断开连接
            </span>
          )}
        </div>
      </header>

      {/* Tab navigation */}
      <nav className="bg-slate-800/50 border-b border-slate-700 px-2 shrink-0 overflow-x-auto">
        <div className="flex gap-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap ${
                  isActive
                    ? 'bg-slate-900 text-blue-400 border-b-2 border-blue-400'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{tab.label}</span>
                <span className="md:hidden">{tab.labelEn}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1 overflow-auto p-4">
        {renderPage()}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <DataProvider>
      <AppContent />
    </DataProvider>
  );
}
