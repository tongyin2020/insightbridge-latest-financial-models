import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  Bot, Lock, Unlock, ZapOff, Globe, Database, Cpu,
  LineChart as LineChartIcon, Terminal, Shield, Zap,
  TrendingUp, TrendingDown, Activity, AlertTriangle,
  LogOut, History, Bell, RefreshCcw, Play, Pause,
  ArrowUpRight, ArrowDownRight, ChevronRight,
  Settings, Wallet, BarChart3, PlayCircle, Store, Users,
  FileText, ShieldAlert
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, ComposedChart, Bar
} from 'recharts';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { Badge } from '../components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '../components/ui/dropdown-menu';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const Dashboard = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const wsRef = useRef(null);
  
  // System state
  const [systemState, setSystemState] = useState({
    status: 'SAFE',
    lifecycle: 'PRE-LIVE',
    mode: 'NORMAL',
    is_locked: true,
    black_swan_probability: 0.012
  });
  
  // Market data
  const [marketData, setMarketData] = useState([]);
  const [currentMarket, setCurrentMarket] = useState({
    wti_price: 75.00,
    bond_yield: 4.250,
    ispread: 15.00,
    risk_score: 25.0
  });
  
  // Signals and logs
  const [signals, setSignals] = useState([]);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  
  // Bond analytics
  const [bondAnalytics, setBondAnalytics] = useState(null);
  
  // AI Brief
  const [aiBrief, setAiBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(false);

  const connectWebSocket = useCallback(() => {
    const wsUrl = API_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    const ws = new WebSocket(`${wsUrl}/ws`);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
      toast.success('Connected to trading server');
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'MARKET_UPDATE') {
        setCurrentMarket(data.data);
        setMarketData(prev => {
          const newData = [...prev, {
            time: prev.length,
            wti_price: data.data.wti_price,
            bond_yield: data.data.bond_yield,
            ispread: data.data.ispread,
            risk_score: data.data.risk_score
          }];
          return newData.slice(-50);
        });
        setSystemState(prev => ({
          ...prev,
          ...data.system_state
        }));
      } else if (data.type === 'NEW_SIGNAL') {
        setSignals(prev => [data.signal, ...prev].slice(0, 20));
        toast.info(`New ${data.signal.signal_type} signal generated`);
      } else if (data.type === 'SIGNAL_EXECUTED') {
        setSignals(prev => prev.map(s => 
          s.id === data.signal.id ? data.signal : s
        ));
        setExecutionLogs(prev => [data.log, ...prev].slice(0, 30));
        toast.success('Signal executed successfully');
      } else if (data.type === 'KILL_SWITCH') {
        setSystemState(prev => ({
          ...prev,
          status: data.status,
          mode: data.mode
        }));
        setExecutionLogs(prev => [data.log, ...prev].slice(0, 30));
        toast.error('KILL SWITCH ACTIVATED', { duration: 5000 });
      } else if (data.type === 'BOND_ANALYTICS') {
        setBondAnalytics(data.data);
      } else if (data.type === 'RISK_ALERT') {
        const count = data.alerts?.length || 0;
        if (count > 0) {
          const first = data.alerts[0];
          toast.warning(
            `Risk Alert: ${first.alert_type?.replace(/_/g, ' ')} - ${first.message?.slice(0, 80)}`,
            { duration: 8000 }
          );
        }
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    wsRef.current = ws;
  }, []);
  
  // Initial data fetch
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [marketRes, stateRes, signalsRes, logsRes, alertsRes] = await Promise.all([
          axios.get(`${API_URL}/api/market/history?count=50`, { withCredentials: true }),
          axios.get(`${API_URL}/api/system/state`, { withCredentials: true }),
          axios.get(`${API_URL}/api/signals`, { withCredentials: true }),
          axios.get(`${API_URL}/api/execution-logs`, { withCredentials: true }),
          axios.get(`${API_URL}/api/alerts`, { withCredentials: true })
        ]);
        
        setMarketData(marketRes.data);
        setSystemState(stateRes.data);
        setSignals(signalsRes.data);
        setExecutionLogs(logsRes.data);
        setAlerts(alertsRes.data);
        setUnreadAlerts(alertsRes.data.filter(a => !a.is_read).length);
      } catch (error) {
        console.error('Error fetching initial data:', error);
      }
    };
    
    fetchInitialData();
    connectWebSocket();
    
    // Fetch bond analytics
    const fetchBondAnalytics = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/market/bond-analytics`, { withCredentials: true });
        setBondAnalytics(res.data);
      } catch (error) {
        console.error('Bond analytics fetch error:', error);
      }
    };
    fetchBondAnalytics();
    const bondInterval = setInterval(fetchBondAnalytics, 120000);
    
    // Fetch AI Brief
    const fetchAiBrief = async () => {
      setBriefLoading(true);
      try {
        const res = await axios.get(`${API_URL}/api/ai-brief`, { withCredentials: true });
        setAiBrief(res.data);
      } catch (error) {
        console.error('AI brief fetch error:', error);
      } finally {
        setBriefLoading(false);
      }
    };
    fetchAiBrief();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      clearInterval(bondInterval);
    };
  }, [connectWebSocket]);
  
  // Actions
  const toggleLock = async () => {
    try {
      const res = await axios.post(`${API_URL}/api/system/toggle-lock`, {}, { withCredentials: true });
      setSystemState(prev => ({ ...prev, is_locked: res.data.is_locked }));
      toast.info(res.data.is_locked ? 'System locked' : 'System unlocked');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to toggle lock');
    }
  };
  
  const toggleLifecycle = async () => {
    try {
      const res = await axios.post(`${API_URL}/api/system/toggle-lifecycle`, {}, { withCredentials: true });
      setSystemState(prev => ({ ...prev, lifecycle: res.data.lifecycle }));
      toast.success(`Switched to ${res.data.lifecycle}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to toggle lifecycle');
    }
  };
  
  const activateKillSwitch = async () => {
    try {
      await axios.post(`${API_URL}/api/system/kill-switch`, {}, { withCredentials: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to activate kill switch');
    }
  };
  
  const clearAlert = async () => {
    try {
      const res = await axios.post(`${API_URL}/api/system/clear-alert`, {}, { withCredentials: true });
      setSystemState(prev => ({ ...prev, status: res.data.status, mode: res.data.mode }));
      toast.success('Alert cleared');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to clear alert');
    }
  };
  
  const setReduceMode = async () => {
    try {
      const res = await axios.post(`${API_URL}/api/system/set-mode?mode=REDUCE`, {}, { withCredentials: true });
      setSystemState(prev => ({ ...prev, mode: res.data.mode }));
      toast.warning('Reduce mode activated');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to set mode');
    }
  };
  
  const executeSignal = async (signalId) => {
    try {
      await axios.post(`${API_URL}/api/signals/${signalId}/execute`, {}, { withCredentials: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to execute signal');
    }
  };
  
  const handleLogout = async () => {
    await logout();
    navigate('/auth');
  };
  
  // Status configuration
  const statusConfig = {
    SAFE: { color: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-500/30', glow: 'shadow-emerald-500/20' },
    WARNING: { color: 'bg-amber-500', text: 'text-amber-400', border: 'border-amber-500/30', glow: 'shadow-amber-500/20' },
    EXIT_ONLY: { color: 'bg-orange-600', text: 'text-orange-400', border: 'border-orange-500/30', glow: 'shadow-orange-500/20' },
    HALT: { color: 'bg-red-600', text: 'text-red-500', border: 'border-red-500/30', glow: 'shadow-red-500/20' }
  };
  
  const currentStatus = statusConfig[systemState.status] || statusConfig.SAFE;

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-300 font-body overflow-hidden">
      <Toaster position="bottom-right" theme="dark" />
      
      {/* Top Navigation */}
      <nav className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-sm flex items-center justify-center">
            <Bot size={18} className="text-white" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-xs font-black tracking-[0.15em] text-white uppercase font-heading">
              Trading Command Center
            </h1>
            <div className="flex gap-3 text-[9px] text-zinc-500">
              <span className="flex items-center gap-1"><Database size={10} /> FEED: LIVE</span>
              <span className="flex items-center gap-1"><Cpu size={10} /> AI: GPT-5.2</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 sm:gap-4">
          {/* Status indicators */}
          <div className="hidden sm:flex gap-1">
            {Object.keys(statusConfig).map(s => (
              <div 
                key={s} 
                className={`w-1.5 h-1.5 rounded-full ${systemState.status === s ? statusConfig[s].color : 'bg-zinc-800'}`} 
              />
            ))}
          </div>
          
          {/* Lifecycle badge */}
          <div 
            data-testid="lifecycle-badge"
            className={`px-2 sm:px-3 py-1 rounded-sm text-[10px] font-bold border transition-all ${
              systemState.lifecycle === 'GO-LIVE' 
                ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400' 
                : 'bg-zinc-900 border-zinc-700 text-zinc-500'
            }`}
          >
            {systemState.lifecycle}
          </div>
          
          {/* Lock button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleLock}
            data-testid="lock-btn"
            className={`p-1.5 rounded-sm hover:bg-zinc-800 ${!systemState.is_locked ? 'text-amber-500' : 'text-zinc-400'}`}
          >
            {systemState.is_locked ? <Lock size={16} /> : <Unlock size={16} />}
          </Button>
          
          {/* Alerts dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="relative p-1.5" data-testid="alerts-btn">
                <Bell size={16} />
                {unreadAlerts > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-[10px] flex items-center justify-center">
                    {unreadAlerts}
                  </span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-72 bg-zinc-900 border-zinc-800">
              <div className="p-2 border-b border-zinc-800">
                <span className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">Notifications</span>
              </div>
              <ScrollArea className="h-64">
                {alerts.length === 0 ? (
                  <div className="p-4 text-center text-zinc-500 text-sm">No alerts</div>
                ) : (
                  alerts.map((alert, i) => (
                    <div key={i} className="p-2 border-b border-zinc-800/50 hover:bg-zinc-800/50">
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={14} className={
                          alert.severity === 'CRITICAL' ? 'text-red-500' : 
                          alert.severity === 'WARNING' ? 'text-amber-500' : 'text-blue-500'
                        } />
                        <div className="flex-1">
                          <p className="text-xs font-semibold text-zinc-200">{alert.title}</p>
                          <p className="text-[10px] text-zinc-500">{alert.message}</p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </ScrollArea>
            </DropdownMenuContent>
          </DropdownMenu>
          
          {/* Kill Switch */}
          <Button
            disabled={systemState.is_locked}
            onClick={activateKillSwitch}
            data-testid="kill-switch-btn"
            className={`flex items-center gap-1 sm:gap-2 px-2 sm:px-4 py-1.5 rounded-sm text-[10px] font-bold transition-all ${
              systemState.status === 'HALT' 
                ? 'bg-red-600 text-white' 
                : 'bg-red-950/20 text-red-500 border border-red-900/50 hover:bg-red-600 hover:text-white animate-pulse-glow'
            }`}
          >
            <ZapOff size={14} /> 
            <span className="hidden sm:inline">KILL SWITCH</span>
          </Button>
          
          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="flex items-center gap-2" data-testid="user-menu-btn">
                <div className="w-7 h-7 bg-blue-600 rounded-sm flex items-center justify-center text-white text-xs font-bold">
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <span className="hidden sm:inline text-xs text-zinc-400">{user?.name}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="bg-zinc-900 border-zinc-800">
              <DropdownMenuItem onClick={() => navigate('/history')} className="cursor-pointer">
                <History size={14} className="mr-2" /> Trade History
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/portfolio')} className="cursor-pointer">
                <Wallet size={14} className="mr-2" /> Portfolio
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/paper-trading')} className="cursor-pointer">
                <PlayCircle size={14} className="mr-2" /> Paper Trading
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/backtest')} className="cursor-pointer">
                <BarChart3 size={14} className="mr-2" /> Backtesting
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/marketplace')} className="cursor-pointer">
                <Store size={14} className="mr-2" /> Strategy Marketplace
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/social')} className="cursor-pointer" data-testid="social-nav">
                <Users size={14} className="mr-2" /> Trading Community
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/yield-curve')} className="cursor-pointer" data-testid="yield-curve-nav">
                <Activity size={14} className="mr-2" /> Yield Curve
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/risk-analytics')} className="cursor-pointer" data-testid="risk-analytics-nav">
                <ShieldAlert size={14} className="mr-2" /> Risk Analytics
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/portfolio-optimizer')} className="cursor-pointer" data-testid="portfolio-optimizer-nav">
                <BarChart3 size={14} className="mr-2" /> Portfolio Optimizer
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/settings')} className="cursor-pointer">
                <Settings size={14} className="mr-2" /> Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-zinc-800" />
              <DropdownMenuItem onClick={handleLogout} className="cursor-pointer text-red-400">
                <LogOut size={14} className="mr-2" /> Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden p-2 sm:p-4 grid grid-cols-12 gap-2 sm:gap-4">
        {/* Left Panel - Charts and Logs */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-2 sm:gap-4 overflow-hidden">
          {/* Status Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4">
            {/* Global Status */}
            <div 
              data-testid="status-card"
              className={`p-3 sm:p-4 rounded-sm border ${currentStatus.border} bg-zinc-900/50 flex flex-col justify-between`}
            >
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Global Status</span>
              <span className={`text-lg sm:text-xl font-black font-heading ${currentStatus.text}`}>
                {systemState.status}
              </span>
            </div>
            
            {/* Mode */}
            <div className="p-3 sm:p-4 rounded-sm border border-zinc-800 bg-zinc-900/50 flex flex-col justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Mode</span>
              <span className="text-lg sm:text-xl font-black font-heading text-white">{systemState.mode}</span>
            </div>
            
            {/* WTI Spot */}
            <div className="p-3 sm:p-4 rounded-sm border border-zinc-800 bg-zinc-900/50 flex flex-col justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">WTI Spot</span>
              <span className="text-lg sm:text-xl font-black font-heading text-cyan-400 font-mono">
                ${currentMarket.wti_price?.toFixed(2)}
              </span>
            </div>
            
            {/* 10Y Yield */}
            <div className="p-3 sm:p-4 rounded-sm border border-zinc-800 bg-zinc-900/50 flex flex-col justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">10Y Yield</span>
              <span className="text-lg sm:text-xl font-black font-heading text-emerald-400 font-mono">
                {currentMarket.bond_yield?.toFixed(3)}%
              </span>
            </div>
          </div>

          {/* Ispread Chart */}
          <div className="flex-1 bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-6 relative min-h-[280px] sm:min-h-[350px]">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center mb-4 sm:mb-6 gap-2">
              <h2 className="text-xs font-bold flex items-center gap-2 tracking-widest text-zinc-400 uppercase">
                <LineChartIcon size={14} className="text-blue-500" /> ISPREAD ANALYSIS (WTI VS BOND)
              </h2>
              <div className="flex gap-4 text-[10px]">
                <span className="flex items-center gap-1"><div className="w-2 h-2 bg-cyan-500 rounded-full" /> WTI PRICE</span>
                <span className="flex items-center gap-1"><div className="w-2 h-2 bg-emerald-500 rounded-full" /> BOND RATE</span>
              </div>
            </div>
            <div className="h-48 sm:h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={marketData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis dataKey="time" hide />
                  <YAxis yAxisId="left" hide domain={['auto', 'auto']} />
                  <YAxis yAxisId="right" orientation="right" hide domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '10px', fontFamily: 'JetBrains Mono' }}
                    labelStyle={{ color: '#71717a' }}
                  />
                  <Area yAxisId="left" type="monotone" dataKey="wti_price" fill="#06b6d4" fillOpacity={0.1} stroke="#06b6d4" strokeWidth={2} isAnimationActive={false} />
                  <Line yAxisId="right" type="monotone" dataKey="bond_yield" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Bar yAxisId="left" dataKey="ispread" fill="#3b82f6" opacity={0.2} barSize={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Bond Analytics Panel */}
          {bondAnalytics && (
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-4" data-testid="bond-analytics-panel">
              <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase flex items-center gap-2 font-heading tracking-widest">
                <Database size={12} className="text-purple-500" /> Bond Analytics
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {/* Yield Curve Slope */}
                <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-sm p-2">
                  <span className="text-[9px] text-zinc-600 uppercase">Curve Slope</span>
                  <div className={`font-mono font-bold text-sm ${bondAnalytics.yield_curve?.slope_10y_3m >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {bondAnalytics.yield_curve?.slope_10y_3m?.toFixed(3)}%
                  </div>
                  <span className={`text-[8px] ${bondAnalytics.yield_curve?.is_inverted ? 'text-red-400' : 'text-zinc-600'}`}>
                    {bondAnalytics.yield_curve?.is_inverted ? 'INVERTED' : '10Y-3M'}
                  </span>
                </div>
                {/* VIX */}
                <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-sm p-2">
                  <span className="text-[9px] text-zinc-600 uppercase">VIX</span>
                  <div className={`font-mono font-bold text-sm ${
                    bondAnalytics.risk_metrics?.vix > 25 ? 'text-red-400' : 
                    bondAnalytics.risk_metrics?.vix > 18 ? 'text-amber-400' : 'text-emerald-400'
                  }`}>
                    {bondAnalytics.risk_metrics?.vix?.toFixed(1)}
                  </div>
                  <span className={`text-[8px] ${
                    bondAnalytics.risk_metrics?.vix_change > 0 ? 'text-red-400' : 'text-emerald-400'
                  }`}>
                    {bondAnalytics.risk_metrics?.vix_change > 0 ? '+' : ''}{bondAnalytics.risk_metrics?.vix_change?.toFixed(2)}
                  </span>
                </div>
                {/* Dollar Index */}
                <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-sm p-2">
                  <span className="text-[9px] text-zinc-600 uppercase">DXY</span>
                  <div className="font-mono font-bold text-sm text-blue-400">
                    {bondAnalytics.risk_metrics?.dollar_index?.toFixed(1)}
                  </div>
                  <span className={`text-[8px] ${
                    bondAnalytics.risk_metrics?.dollar_change > 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {bondAnalytics.risk_metrics?.dollar_change > 0 ? '+' : ''}{bondAnalytics.risk_metrics?.dollar_change?.toFixed(2)}
                  </span>
                </div>
                {/* Real Yield */}
                <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-sm p-2">
                  <span className="text-[9px] text-zinc-600 uppercase">Real Yield</span>
                  <div className="font-mono font-bold text-sm text-purple-400">
                    {bondAnalytics.inflation?.real_yield?.toFixed(3)}%
                  </div>
                  <span className="text-[8px] text-zinc-600">
                    BEI: {bondAnalytics.inflation?.breakeven_inflation?.toFixed(2)}%
                  </span>
                </div>
              </div>
              {/* Signal Badges */}
              <div className="flex flex-wrap gap-1.5 mt-2">
                {bondAnalytics.signals && Object.entries(bondAnalytics.signals).map(([key, value]) => (
                  <span key={key} className={`text-[8px] px-1.5 py-0.5 rounded-sm font-mono font-bold ${
                    value === 'NORMAL' || value === 'LOW' || value === 'LOW_RISK' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                    value === 'ELEVATED' || value === 'NEUTRAL' || value === 'MODERATE' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                    'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {key.replace(/_/g, ' ')}: {value}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* AI Market Brief Card */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-4" data-testid="ai-brief-card">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-[10px] font-bold text-zinc-500 uppercase flex items-center gap-2 font-heading tracking-widest">
                <FileText size={12} className="text-blue-500" /> AI Market Brief
              </h3>
              {aiBrief?.ai_generated && (
                <Badge className="text-[7px] bg-blue-500/10 text-blue-400 border border-blue-500/20">GPT-5.2</Badge>
              )}
            </div>
            {briefLoading && !aiBrief ? (
              <div className="py-4 text-center text-[10px] text-zinc-600 animate-pulse">Generating AI brief...</div>
            ) : aiBrief ? (
              <div>
                <p className="text-xs font-bold text-white mb-2">{aiBrief.headline}</p>
                <div className="text-[10px] text-zinc-400 leading-relaxed whitespace-pre-line line-clamp-4 mb-2">{aiBrief.body}</div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {aiBrief.market_snapshot?.y10 !== undefined && (
                    <span className="text-[8px] px-1.5 py-0.5 bg-zinc-800 rounded-sm text-zinc-400 font-mono">10Y: {Number(aiBrief.market_snapshot.y10).toFixed(3)}%</span>
                  )}
                  {aiBrief.market_snapshot?.slope !== undefined && (
                    <span className="text-[8px] px-1.5 py-0.5 bg-zinc-800 rounded-sm text-zinc-400 font-mono">Slope: {Number(aiBrief.market_snapshot.slope).toFixed(3)}%</span>
                  )}
                  {aiBrief.market_snapshot?.vix !== undefined && (
                    <span className="text-[8px] px-1.5 py-0.5 bg-zinc-800 rounded-sm text-zinc-400 font-mono">VIX: {Number(aiBrief.market_snapshot.vix).toFixed(1)}</span>
                  )}
                  {aiBrief.market_snapshot?.curve_signal && (
                    <span className={`text-[8px] px-1.5 py-0.5 rounded-sm font-mono font-bold ${
                      aiBrief.market_snapshot.curve_signal === 'NORMAL' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                      'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}>{aiBrief.market_snapshot.curve_signal}</span>
                  )}
                </div>
                <div className="text-[8px] text-zinc-600 mt-2">{aiBrief.date}</div>
              </div>
            ) : (
              <div className="py-3 text-center text-[10px] text-zinc-600">No brief available</div>
            )}
          </div>

          {/* Execution Logs Terminal */}
          <div 
            data-testid="execution-logs"
            className="h-36 sm:h-48 bg-black border border-zinc-800 rounded-sm p-3 sm:p-4 overflow-hidden flex flex-col"
          >
            <h3 className="text-[10px] font-bold text-zinc-500 mb-2 uppercase flex items-center gap-2 font-heading">
              <Terminal size={12} className="text-green-500" /> Execution Analytics & Logs
            </h3>
            <ScrollArea className="flex-1">
              <div className="space-y-1 pr-2">
                {executionLogs.map((log, i) => (
                  <div key={i} className="text-[10px] sm:text-xs text-green-400 border-l border-zinc-800 pl-3 leading-relaxed font-mono">
                    <span className="text-blue-500 mr-2">▶</span> {log}
                  </div>
                ))}
                {executionLogs.length === 0 && (
                  <div className="text-[10px] text-zinc-600 italic font-mono cursor-blink">
                    Awaiting automated execution events...
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        {/* Right Panel - Controls and Signals */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-2 sm:gap-4 overflow-hidden">
          {/* Lifecycle Control */}
          <div className="bg-blue-500/5 border border-blue-500/20 rounded-sm p-3 sm:p-4">
            <div className="flex justify-between items-center mb-3">
              <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest font-heading">System Lifecycle</span>
              <Button
                disabled={systemState.is_locked}
                onClick={toggleLifecycle}
                data-testid="lifecycle-toggle-btn"
                size="sm"
                className={`px-2 py-1 rounded-sm text-[9px] font-bold uppercase transition-all ${
                  systemState.lifecycle === 'GO-LIVE' 
                    ? 'bg-emerald-600 text-white hover:bg-emerald-500' 
                    : 'bg-zinc-800 text-zinc-500 hover:bg-zinc-700'
                }`}
              >
                {systemState.lifecycle === 'GO-LIVE' ? <Pause size={12} className="mr-1" /> : <Play size={12} className="mr-1" />}
                Switch Phase
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className={`h-1.5 rounded-full ${systemState.lifecycle === 'PRE-LIVE' ? 'bg-blue-500 shadow-[0_0_8px_#3b82f6]' : 'bg-zinc-800'}`} />
              <div className={`h-1.5 rounded-full ${systemState.lifecycle === 'GO-LIVE' ? 'bg-emerald-500 shadow-[0_0_8px_#10b981]' : 'bg-zinc-800'}`} />
            </div>
          </div>

          {/* AI Signal Queue */}
          <div 
            data-testid="signal-queue"
            className="flex-1 bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-4 flex flex-col overflow-hidden"
          >
            <h3 className="text-[10px] font-bold text-zinc-500 mb-3 sm:mb-4 flex items-center gap-2 uppercase font-heading">
              <Zap size={14} className="text-amber-500" /> AI Decision Queue
            </h3>
            <ScrollArea className="flex-1">
              <div className="space-y-2 pr-1">
                {signals.map(signal => (
                  <div 
                    key={signal.id} 
                    data-testid={`signal-${signal.id}`}
                    className="p-2 sm:p-3 bg-zinc-950/50 border border-zinc-800 rounded-sm hover:border-zinc-700 transition-all group"
                  >
                    <div className="flex justify-between items-center mb-2">
                      <Badge 
                        className={`text-[9px] px-1.5 py-0.5 font-black rounded-sm ${
                          signal.signal_type?.includes('BUY') || signal.signal_type?.includes('LONG')
                            ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' 
                            : 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                        }`}
                      >
                        {signal.signal_type}
                      </Badge>
                      <span className="text-[9px] text-zinc-600 font-mono">
                        {new Date(signal.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="flex justify-between items-end">
                      <div>
                        <div className="text-[8px] text-zinc-500 uppercase">AI Confidence</div>
                        <div className="text-sm font-bold text-white font-mono tracking-tighter">
                          {(signal.confidence * 100).toFixed(2)}%
                        </div>
                      </div>
                      <div className="text-right">
                        {signal.status === 'PENDING' ? (
                          <Button
                            size="sm"
                            onClick={() => executeSignal(signal.id)}
                            disabled={systemState.is_locked}
                            className="text-[8px] px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-sm"
                          >
                            Execute
                          </Button>
                        ) : (
                          <span className={`text-[8px] font-bold uppercase ${
                            signal.status === 'EXECUTED' ? 'text-emerald-400' : 'text-amber-500'
                          }`}>
                            {signal.status}
                          </span>
                        )}
                      </div>
                    </div>
                    {signal.ai_reasoning && (
                      <p className="mt-2 text-[9px] text-zinc-500 line-clamp-2">{signal.ai_reasoning}</p>
                    )}
                  </div>
                ))}
                {signals.length === 0 && (
                  <div className="h-full flex flex-col items-center justify-center py-8 text-zinc-600">
                    <Globe size={30} className="mb-2 opacity-30" />
                    <span className="text-[10px] italic">Waiting for AI Signals...</span>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Risk Guard Engine */}
          <div 
            data-testid="risk-guard"
            className="bg-red-500/5 border border-red-500/20 rounded-sm p-3 sm:p-4"
          >
            <h3 className="text-[10px] font-bold text-red-500 mb-3 sm:mb-4 flex items-center gap-2 uppercase tracking-widest font-heading">
              <Shield size={14} /> Risk Guard Engine
            </h3>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-[9px] mb-1.5">
                  <span className="text-zinc-500 uppercase">Black Swan Probability</span>
                  <span className="text-white font-bold font-mono">
                    {(systemState.black_swan_probability * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-red-600 to-red-400 transition-all duration-500"
                    style={{ width: `${Math.min(systemState.black_swan_probability * 100, 100)}%` }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  disabled={systemState.is_locked}
                  onClick={setReduceMode}
                  data-testid="reduce-mode-btn"
                  variant="outline"
                  size="sm"
                  className="py-2 bg-orange-950/20 border-orange-900/40 text-orange-500 text-[9px] font-bold rounded-sm uppercase tracking-tighter hover:bg-orange-900/30"
                >
                  Reduce Mode
                </Button>
                <Button
                  disabled={systemState.is_locked}
                  onClick={clearAlert}
                  data-testid="clear-alert-btn"
                  variant="outline"
                  size="sm"
                  className="py-2 bg-emerald-950/20 border-emerald-900/40 text-emerald-500 text-[9px] font-bold rounded-sm uppercase tracking-tighter hover:bg-emerald-900/30"
                >
                  Clear Alert
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer Status Bar */}
      <footer className="h-6 bg-black border-t border-zinc-800 flex items-center px-4 justify-between shrink-0">
        <div className="flex gap-4">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${currentStatus.color} status-indicator`} />
            <span className="text-[9px] font-bold text-zinc-500 uppercase">System Integrity: {systemState.status}</span>
          </div>
          <div className="hidden sm:block text-[9px] text-zinc-600 truncate max-w-md font-mono">
            CORE: Processing WTI-BOND spread parity ... Ispread: {currentMarket.ispread?.toFixed(2)} ... Latency: 14ms
          </div>
        </div>
        <div className="text-[9px] text-zinc-500 flex items-center gap-2 font-mono">
          {new Date().toISOString()}
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;
