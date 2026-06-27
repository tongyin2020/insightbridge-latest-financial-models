import { useState, useEffect, useCallback, useRef, createContext, useContext } from "react";
import "@/App.css";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart as RLineChart, Line, Area, AreaChart, CartesianGrid, Legend, ReferenceLine } from "recharts";
import { 
  Activity, AlertTriangle, TrendingUp, TrendingDown, 
  Power, Pause, Play, RefreshCw, Calendar, BarChart3,
  Shield, Zap, Clock, DollarSign, Target, XCircle,
  ChevronRight, Gauge, Brain, Settings, User, LogOut,
  Lock, Mail, Layers, GitBranch, LineChart, PieChart,
  Bell, BellRing, Wifi, WifiOff, Sparkles, Check
} from "lucide-react";
import { ReplayTab } from "./components/tabs/ReplayTab";
import { DashboardTab } from "./components/tabs/DashboardTab";
import { OptionsTab } from "./components/tabs/OptionsTab";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Configure axios to send cookies
axios.defaults.withCredentials = true;

// Regime badge colors
const REGIME_COLORS = {
  normal: "bg-emerald-500/20 text-emerald-400 border-emerald-500/50",
  event: "bg-amber-500/20 text-amber-400 border-amber-500/50",
  trend: "bg-blue-500/20 text-blue-400 border-blue-500/50",
  blocked: "bg-red-500/20 text-red-400 border-red-500/50",
};

// Direction colors
const DIRECTION_COLORS = {
  long: "text-emerald-400",
  short: "text-red-400",
};

// Asset colors
const ASSET_COLORS = {
  CL: "text-blue-400",
  BZ: "text-purple-400",
  NG: "text-amber-400",
};

// Asset symbols for correlation matrix
const ASSET_SYMBOLS = ["CL", "BZ", "NG"];

// Auth Context
const AuthContext = createContext(null);

function useAuth() {
  return useContext(AuthContext);
}

function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

// Auth Provider Component
function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = not authenticated
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const { data } = await axios.get(`${API}/auth/me`);
      setUser(data);
    } catch (err) {
      setUser(false);
    }
    setLoading(false);
  };

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });
    setUser(data);
    return data;
  };

  const register = async (email, password, name) => {
    const { data } = await axios.post(`${API}/auth/register`, { email, password, name });
    setUser(data);
    return data;
  };

  const logout = async () => {
    await axios.post(`${API}/auth/logout`);
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

// Full-page Login Gate
function LoginPage() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center px-4" data-testid="login-page">
      <div className="w-full max-w-md">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
              <Zap className="w-6 h-6 text-blue-400" />
            </div>
            <h1 className="font-outfit text-3xl font-bold tracking-tight">Energy AI Trading</h1>
          </div>
          <p className="text-zinc-500 text-sm">AI-driven crude oil futures trading platform</p>
        </div>

        {/* Login Card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8" data-testid="login-card">
          <h2 className="font-outfit text-xl font-bold mb-6 text-center">
            {mode === "login" ? "Sign In" : "Create Account"}
          </h2>

          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400 text-sm" data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="block text-sm text-zinc-400 mb-1.5">Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-10 pr-3 py-2.5 text-white placeholder:text-zinc-600 focus:border-blue-500 transition-colors"
                    placeholder="Your name"
                    data-testid="register-name-input"
                    required
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-10 pr-3 py-2.5 text-white placeholder:text-zinc-600 focus:border-blue-500 transition-colors"
                  placeholder="you@example.com"
                  data-testid="auth-email-input"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-10 pr-3 py-2.5 text-white placeholder:text-zinc-600 focus:border-blue-500 transition-colors"
                  placeholder="••••••••"
                  data-testid="auth-password-input"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg font-semibold transition-colors text-white"
              data-testid="auth-submit-btn"
            >
              {loading ? "Please wait..." : (mode === "login" ? "Sign In" : "Create Account")}
            </button>
          </form>

          <div className="mt-5 text-center text-sm text-zinc-500">
            {mode === "login" ? (
              <>
                Don't have an account?{" "}
                <button onClick={() => { setMode("register"); setError(""); }} className="text-blue-400 hover:text-blue-300 font-medium" data-testid="switch-to-register">
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button onClick={() => { setMode("login"); setError(""); }} className="text-blue-400 hover:text-blue-300 font-medium" data-testid="switch-to-login">
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>

        <p className="text-center text-[11px] text-zinc-600 mt-6">Protected access. Authorized users only.</p>
      </div>
    </div>
  );
}

function App() {
  // State
  const [systemStatus, setSystemStatus] = useState(null);
  const [marketData, setMarketData] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [mlPrediction, setMlPrediction] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [backtestResult, setBacktestResult] = useState(null);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [assets, setAssets] = useState([]);
  const [currentSymbol, setCurrentSymbol] = useState("CL");
  const [allAssetPrices, setAllAssetPrices] = useState({});
  const [spreadOpportunity, setSpreadOpportunity] = useState(null);
  const [portfolioAnalysis, setPortfolioAnalysis] = useState(null);
  const [optionChain, setOptionChain] = useState(null);
  const [optionStrategies, setOptionStrategies] = useState([]);
  const [volatilityAnalysis, setVolatilityAnalysis] = useState(null);
  const [realtimePnl, setRealtimePnl] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [autoStrategy, setAutoStrategy] = useState(null);
  const [isLoadingStrategy, setIsLoadingStrategy] = useState(false);
  const [tradovateStatus, setTradovateStatus] = useState(null);
  const [fragility, setFragility] = useState(null);
  const [signalScore, setSignalScore] = useState(null);
  const [executionGate, setExecutionGate] = useState(null);
  const [riskControl, setRiskControl] = useState(null);
  const [eventCalendar, setEventCalendar] = useState(null);
  const [dailyPnl, setDailyPnl] = useState([]);
  const [exitTiers, setExitTiers] = useState(null);
  const [botStatus, setBotStatus] = useState(null);
  const [botOpportunities, setBotOpportunities] = useState([]);
  const [botHistory, setBotHistory] = useState([]);
  const [replayEvents, setReplayEvents] = useState([]);
  const [replayResult, setReplayResult] = useState(null);
  const [isReplaying, setIsReplaying] = useState(false);
  const [simResult, setSimResult] = useState(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simConfig, setSimConfig] = useState({ min_confidence: 55, atr_sl_mult: 1.5, atr_tp1_mult: 2.0, atr_tp2_mult: 3.5 });
  const [payoffData, setPayoffData] = useState(null);
  const [payoffStrategy, setPayoffStrategy] = useState("straddle");
  const [priceAlerts, setPriceAlerts] = useState([]);
  const [alertForm, setAlertForm] = useState({ symbol: "CL", target_price: "", condition: "above", note: "" });
  const [leaderboard, setLeaderboard] = useState([]);
  const [following, setFollowing] = useState([]);
  const [pvpResult, setPvpResult] = useState(null);
  const [isPvpRunning, setIsPvpRunning] = useState(false);
  const [pvpConfigA, setPvpConfigA] = useState({ min_confidence: 40, atr_sl_mult: 1.0, atr_tp1_mult: 1.5, atr_tp2_mult: 3.0 });
  const [pvpConfigB, setPvpConfigB] = useState({ min_confidence: 70, atr_sl_mult: 2.0, atr_tp1_mult: 2.5, atr_tp2_mult: 4.0 });
  const [templates, setTemplates] = useState([]);
  
  const wsRef = useRef(null);
  const { user, loading: authLoading, logout } = useAuth();

  // Fetch initial data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, marketRes, positionsRes, tradesRes, calendarRes, historyRes, assetsRes] = await Promise.all([
        axios.get(`${API}/system/status`),
        axios.get(`${API}/market/current`),
        axios.get(`${API}/positions`),
        axios.get(`${API}/trades?limit=20`),
        axios.get(`${API}/calendar/events?days=14`),
        axios.get(`${API}/market/history?bars=50`),
        axios.get(`${API}/assets`),
      ]);
      
      setSystemStatus(statusRes.data);
      setMarketData(marketRes.data);
      setPositions(positionsRes.data);
      setTrades(tradesRes.data);
      setCalendarEvents(calendarRes.data);
      setPriceHistory(historyRes.data);
      setAssets(assetsRes.data);
      setCurrentSymbol(statusRes.data.current_symbol || "CL");
    } catch (err) {
      console.error("Error fetching data:", err);
    }
  }, []);

  // Fetch portfolio analysis
  const fetchPortfolioAnalysis = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/portfolio/analysis`);
      setPortfolioAnalysis(res.data);
    } catch (err) {
      console.error("Error fetching portfolio analysis:", err);
    }
  }, []);

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/notifications?limit=20`);
      setNotifications(res.data.notifications || []);
      setUnreadCount(res.data.unread_count || 0);
    } catch (err) {
      console.error("Error fetching notifications:", err);
    }
  }, []);

  // Fetch auto strategy recommendation
  const fetchAutoStrategy = async () => {
    setIsLoadingStrategy(true);
    try {
      const res = await axios.get(`${API}/options/auto-strategy/${currentSymbol}`);
      setAutoStrategy(res.data);
    } catch (err) {
      console.error("Error fetching auto strategy:", err);
    }
    setIsLoadingStrategy(false);
  };

  // Fetch Tradovate status
  const fetchTradovateStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/tradovate/status`);
      setTradovateStatus(res.data);
    } catch (err) {
      console.error("Error fetching tradovate status:", err);
    }
  }, []);

  // Fetch advanced analytics (fragility, signals, risk, events)
  const fetchAdvancedAnalytics = useCallback(async () => {
    try {
      const [fragRes, sigRes, gateRes, riskRes, evtRes, pnlRes, botRes, oppRes] = await Promise.all([
        axios.get(`${API}/fragility`),
        axios.get(`${API}/signal-score/${currentSymbol}`),
        axios.get(`${API}/execution-gate/${currentSymbol}`),
        axios.get(`${API}/risk-control/status`),
        axios.get(`${API}/events/calendar?hours_ahead=48`),
        axios.get(`${API}/risk-control/daily-pnl`),
        axios.get(`${API}/bot/status`),
        axios.get(`${API}/bot/opportunities`),
      ]);
      setFragility(fragRes.data);
      setSignalScore(sigRes.data);
      setExecutionGate(gateRes.data);
      setRiskControl(riskRes.data);
      setEventCalendar(evtRes.data);
      setDailyPnl(pnlRes.data.history || []);
      setBotStatus(botRes.data);
      setBotOpportunities(oppRes.data.opportunities || []);
    } catch (err) {
      console.error("Error fetching advanced analytics:", err);
    }
  }, [currentSymbol]);

  // Bot actions
  const toggleBot = async () => {
    try {
      const res = await axios.post(`${API}/bot/toggle`);
      setBotStatus(prev => prev ? {...prev, enabled: res.data.enabled} : prev);
      fetchAdvancedAnalytics();
    } catch (err) {
      console.error("Error toggling bot:", err);
    }
  };

  const approveOpportunity = async (oppId) => {
    try {
      const res = await axios.post(`${API}/bot/approve/${oppId}`);
      fetchAdvancedAnalytics();
      fetchData();
    } catch (err) {
      console.error("Error approving opportunity:", err);
    }
  };

  const rejectOpportunity = async (oppId) => {
    try {
      await axios.post(`${API}/bot/reject/${oppId}`);
      fetchAdvancedAnalytics();
    } catch (err) {
      console.error("Error rejecting opportunity:", err);
    }
  };

  const fetchBotHistory = async () => {
    try {
      const res = await axios.get(`${API}/bot/history?limit=20`);
      setBotHistory(res.data.history || []);
    } catch (err) {
      console.error("Error fetching bot history:", err);
    }
  };

  // Fetch replay events list
  const fetchReplayEvents = async () => {
    try {
      const res = await axios.get(`${API}/replay/events`);
      setReplayEvents(res.data.events || []);
    } catch (err) {
      console.error("Error fetching replay events:", err);
    }
  };

  // Run event replay
  const runReplay = async (eventId) => {
    setIsReplaying(true);
    setSimResult(null);
    try {
      const res = await axios.get(`${API}/replay/${eventId}`);
      setReplayResult(res.data);
    } catch (err) {
      console.error("Error replaying:", err);
    }
    setIsReplaying(false);
  };

  // Run bot strategy simulation on replay event
  const runSimulation = async (eventId) => {
    setIsSimulating(true);
    try {
      const res = await axios.post(`${API}/replay/simulate`, {
        event_id: eventId,
        config: simConfig,
      });
      setSimResult(res.data);
    } catch (err) {
      console.error("Error simulating:", err);
    }
    setIsSimulating(false);
  };

  // Fetch payoff diagram
  const fetchPayoff = async (strategy) => {
    try {
      const res = await axios.get(`${API}/options/payoff/${strategy}?symbol=${currentSymbol}&expiry_days=30`);
      setPayoffData(res.data);
      setPayoffStrategy(strategy);
    } catch (err) {
      console.error("Error fetching payoff:", err);
    }
  };

  // Price Alerts
  const fetchAlerts = async () => {
    try {
      const res = await axios.get(`${API}/alerts`);
      setPriceAlerts(res.data.alerts || []);
    } catch (err) { console.error("Error fetching alerts:", err); }
  };

  const createAlert = async () => {
    if (!alertForm.target_price) return;
    try {
      await axios.post(`${API}/alerts`, alertForm);
      setAlertForm(p => ({ ...p, target_price: "", note: "" }));
      fetchAlerts();
    } catch (err) { console.error("Error creating alert:", err); }
  };

  const deleteAlert = async (alertId) => {
    try {
      await axios.delete(`${API}/alerts/${alertId}`);
      fetchAlerts();
    } catch (err) { console.error("Error deleting alert:", err); }
  };

  const exportTradesCSV = () => {
    window.open(`${API}/trades/export/csv`, '_blank');
  };

  // Social / Copy Trading
  const fetchLeaderboard = async () => {
    try {
      const res = await axios.get(`${API}/social/leaderboard`);
      setLeaderboard(res.data.strategies || []);
    } catch (err) { console.error("Leaderboard error:", err); }
  };

  const fetchFollowing = async () => {
    try {
      const res = await axios.get(`${API}/social/following`);
      setFollowing(res.data.following || []);
    } catch (err) { console.error("Following error:", err); }
  };

  const followStrategy = async (strategyId) => {
    try {
      const res = await axios.post(`${API}/social/follow/${strategyId}`);
      if (res.data.action === 'followed' && res.data.config) {
        setSimConfig(res.data.config);
      }
      fetchLeaderboard();
      fetchFollowing();
    } catch (err) { console.error("Follow error:", err); }
  };

  const shareStrategy = async (name, description, config, performance) => {
    try {
      await axios.post(`${API}/social/share`, { name, description, config, performance });
      fetchLeaderboard();
    } catch (err) { console.error("Share error:", err); }
  };

  const runPvpBattle = async () => {
    setIsPvpRunning(true);
    try {
      const res = await axios.post(`${API}/social/pvp`, {
        name_a: "Strategy A", name_b: "Strategy B",
        config_a: pvpConfigA, config_b: pvpConfigB,
      });
      setPvpResult(res.data);
    } catch (err) { console.error("PvP error:", err); }
    setIsPvpRunning(false);
  };

  const fetchTemplates = async () => {
    try {
      const res = await axios.get(`${API}/social/templates`);
      setTemplates(res.data.templates || []);
    } catch (err) { console.error("Templates error:", err); }
  };

  const importTemplateToReplay = async (strategyId, config) => {
    try {
      await axios.post(`${API}/social/templates/${strategyId}/import`);
    } catch (err) { /* ignore import tracking errors */ }
    setSimConfig(config);
    setActiveTab('replay');
  };

  const importTemplateToPvp = async (strategyId, config, slot) => {
    try {
      await axios.post(`${API}/social/templates/${strategyId}/import`);
    } catch (err) { /* ignore */ }
    if (slot === 'a') setPvpConfigA(config);
    else setPvpConfigB(config);
  };

  // WebSocket connection
  useEffect(() => {
    const connectWebSocket = () => {
      const wsUrl = BACKEND_URL.replace("https://", "wss://").replace("http://", "ws://");
      const ws = new WebSocket(`${wsUrl}/api/ws`);
      
      ws.onopen = () => {
        setIsConnected(true);
        console.log("WebSocket connected");
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "market_update") {
            setMarketData(prev => ({
              ...prev,
              symbol: data.current_symbol,
              price: data.tick.last,
              bid: data.tick.bid,
              ask: data.tick.ask,
              spread: data.tick.spread,
              indicators: data.indicators,
            }));
            setSystemStatus(prev => ({
              ...prev,
              current_regime: data.regime,
              equity: data.equity,
              daily_pnl: data.risk.daily_pnl,
              is_halted: data.risk.is_halted,
              kill_switch: data.risk.kill_switch,
              current_symbol: data.current_symbol,
            }));
            setPositions(data.positions);
            setAllAssetPrices(data.assets || {});
            if (data.ml_prediction) {
              setMlPrediction(data.ml_prediction);
            }
            if (data.spread_opportunity) {
              setSpreadOpportunity(data.spread_opportunity);
            }
            // Update price history
            setPriceHistory(prev => {
              const newPoint = {
                timestamp: data.timestamp,
                close: data.tick.last,
                high: data.tick.ask,
                low: data.tick.bid,
              };
              const updated = [...prev, newPoint];
              return updated.slice(-50);
            });
          }
        } catch (err) {
          console.error("WebSocket message error:", err);
        }
      };
      
      ws.onclose = () => {
        setIsConnected(false);
        console.log("WebSocket disconnected, reconnecting...");
        setTimeout(connectWebSocket, 3000);
      };
      
      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
      
      wsRef.current = ws;
    };
    
    fetchData();
    fetchPortfolioAnalysis();
    fetchNotifications();
    fetchTradovateStatus();
    fetchAdvancedAnalytics();
    connectWebSocket();
    
    const pollInterval = setInterval(fetchData, 10000);
    const portfolioInterval = setInterval(fetchPortfolioAnalysis, 30000);
    const notifInterval = setInterval(fetchNotifications, 15000);
    const advancedInterval = setInterval(fetchAdvancedAnalytics, 8000);
    
    return () => {
      clearInterval(pollInterval);
      clearInterval(portfolioInterval);
      clearInterval(notifInterval);
      clearInterval(advancedInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [fetchData, fetchPortfolioAnalysis, fetchNotifications, fetchTradovateStatus, fetchAdvancedAnalytics]);

  // Auto-fetch replay events when tab switches to replay
  useEffect(() => {
    if (activeTab === 'replay' && replayEvents.length === 0) {
      fetchReplayEvents();
    }
    if (activeTab === 'settings') {
      fetchAlerts();
    }
    if (activeTab === 'social') {
      fetchLeaderboard();
      fetchFollowing();
      fetchTemplates();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Control functions
  const startSystem = async () => {
    try {
      await axios.post(`${API}/system/start`);
      fetchData();
    } catch (err) {
      console.error("Error starting system:", err);
    }
  };

  const stopSystem = async () => {
    try {
      await axios.post(`${API}/system/stop`);
      fetchData();
    } catch (err) {
      console.error("Error stopping system:", err);
    }
  };

  const activateKillSwitch = async () => {
    if (window.confirm("⚠️ ACTIVATE KILL SWITCH?\n\nThis will close all positions and halt trading.")) {
      try {
        await axios.post(`${API}/risk/kill-switch`);
        fetchData();
      } catch (err) {
        console.error("Error activating kill switch:", err);
      }
    }
  };

  const setRegimeOverride = async (regime, reason) => {
    try {
      await axios.post(`${API}/regime/override`, {
        regime,
        reason,
        duration_hours: 4.0,
      });
      fetchData();
    } catch (err) {
      console.error("Error setting regime override:", err);
    }
  };

  const clearOverride = async () => {
    try {
      await axios.post(`${API}/regime/clear-override`);
      fetchData();
    } catch (err) {
      console.error("Error clearing override:", err);
    }
  };

  const closePosition = async (positionId) => {
    try {
      await axios.post(`${API}/positions/${positionId}/close`);
      fetchData();
    } catch (err) {
      console.error("Error closing position:", err);
    }
  };

  const triggerEvent = async (eventId) => {
    try {
      await axios.post(`${API}/calendar/trigger/${eventId}`);
      fetchData();
    } catch (err) {
      console.error("Error triggering event:", err);
    }
  };

  const switchSymbol = async (symbol) => {
    try {
      await axios.post(`${API}/system/symbol/${symbol}`);
      setCurrentSymbol(symbol);
      // Also send via WebSocket for immediate update
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "set_symbol", symbol }));
      }
      fetchData();
    } catch (err) {
      console.error("Error switching symbol:", err);
    }
  };

  const runBacktest = async () => {
    setIsBacktesting(true);
    try {
      const res = await axios.post(`${API}/backtest/run`, {
        start_date: "2024-01-01",
        end_date: "2024-06-30",
        initial_equity: 50000,
        slippage_ticks: 1.5,
        commission_per_rt: 4.0,
      });
      setBacktestResult(res.data);
    } catch (err) {
      console.error("Error running backtest:", err);
    }
    setIsBacktesting(false);
  };

  const getMlPrediction = async () => {
    try {
      const res = await axios.get(`${API}/ml/prediction`);
      setMlPrediction(res.data);
    } catch (err) {
      console.error("Error getting ML prediction:", err);
    }
  };

  // Render price chart
  const renderPriceChart = () => {
    if (priceHistory.length < 2) return null;
    
    const prices = priceHistory.map(p => p.close);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const range = maxPrice - minPrice || 1;
    
    const width = 800;
    const height = 200;
    const padding = 20;
    
    const points = prices.map((price, i) => {
      const x = padding + (i / (prices.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((price - minPrice) / range) * (height - 2 * padding);
      return `${x},${y}`;
    }).join(" ");
    
    const isUp = prices[prices.length - 1] >= prices[0];
    const lineColor = isUp ? "#10B981" : "#EF4444";
    
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-48">
        <defs>
          <linearGradient id="priceGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.3" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline
          fill="none"
          stroke={lineColor}
          strokeWidth="2"
          points={points}
        />
        <polygon
          fill="url(#priceGradient)"
          points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
        />
        <text x={padding} y={padding} fill="#A1A1AA" fontSize="10" fontFamily="JetBrains Mono">
          ${maxPrice.toFixed(2)}
        </text>
        <text x={padding} y={height - 5} fill="#A1A1AA" fontSize="10" fontFamily="JetBrains Mono">
          ${minPrice.toFixed(2)}
        </text>
      </svg>
    );
  };

  // Auth gate: show login page if not authenticated
  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#09090B] flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-zinc-500 text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <div className="min-h-screen bg-[#09090B] text-white">
      
      {/* Top Control Bar */}
      <header className="border-b border-zinc-800 bg-[#18181B] px-4 md:px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="font-outfit text-xl font-bold tracking-tight flex items-center gap-2">
              <Zap className="w-5 h-5 text-blue-500" />
              Energy AI Trading
            </h1>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-xs text-zinc-400 font-mono">
                {isConnected ? 'LIVE' : 'DISCONNECTED'}
              </span>
            </div>
            
            {/* Asset Selector */}
            <div className="flex items-center gap-1 bg-zinc-800 rounded-sm p-1">
              {assets.map(asset => (
                <button
                  key={asset.symbol}
                  data-testid={`asset-${asset.symbol}-btn`}
                  onClick={() => switchSymbol(asset.symbol)}
                  className={`px-3 py-1 text-xs font-mono rounded-sm transition-colors ${
                    currentSymbol === asset.symbol 
                      ? `bg-blue-600 text-white` 
                      : `text-zinc-400 hover:text-white ${ASSET_COLORS[asset.symbol]}`
                  }`}
                >
                  {asset.symbol}
                </button>
              ))}
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Regime Badge */}
            {systemStatus && (
              <div className={`px-3 py-1 rounded-sm border font-mono text-xs uppercase tracking-wider ${REGIME_COLORS[systemStatus.current_regime] || REGIME_COLORS.normal}`}
                   data-testid="regime-badge">
                {systemStatus.current_regime}
              </div>
            )}
            
            {/* Mode Toggle */}
            <div className="flex items-center gap-2 bg-zinc-800 rounded-sm p-1">
              <button
                data-testid="paper-mode-btn"
                className={`px-3 py-1 text-xs font-mono rounded-sm transition-colors ${
                  systemStatus?.mode === 'paper' ? 'bg-blue-600 text-white' : 'text-zinc-400 hover:text-white'
                }`}
                onClick={() => axios.post(`${API}/system/mode/paper`).then(fetchData)}
              >
                PAPER
              </button>
              <button
                data-testid="live-mode-btn"
                className={`px-3 py-1 text-xs font-mono rounded-sm transition-colors ${
                  systemStatus?.mode === 'live' ? 'bg-emerald-600 text-white' : 'text-zinc-400 hover:text-white'
                }`}
                onClick={() => axios.post(`${API}/system/mode/live`).then(fetchData)}
              >
                LIVE
              </button>
            </div>
            
            {/* System Controls */}
            <div className="flex items-center gap-2">
              <button
                data-testid="start-btn"
                onClick={startSystem}
                disabled={systemStatus?.is_running}
                className="p-2 rounded-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Play className="w-4 h-4" />
              </button>
              <button
                data-testid="stop-btn"
                onClick={stopSystem}
                disabled={!systemStatus?.is_running}
                className="p-2 rounded-sm bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Pause className="w-4 h-4" />
              </button>
            </div>
            
            {/* Kill Switch */}
            <button
              data-testid="kill-switch-btn"
              onClick={activateKillSwitch}
              className={`px-4 py-2 rounded-sm font-bold text-sm transition-all ${
                systemStatus?.kill_switch
                  ? 'bg-red-900 text-red-400 border-2 border-red-500 cursor-not-allowed'
                  : 'bg-red-600 hover:bg-red-500 text-white border-2 border-red-500/50 hover:border-red-400'
              }`}
              disabled={systemStatus?.kill_switch}
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                KILL
              </div>
            </button>
            
            {/* Tradovate Status */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-xs font-mono ${
              tradovateStatus?.connected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 text-zinc-500'
            }`} data-testid="tradovate-status">
              {tradovateStatus?.connected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
              {tradovateStatus?.connected ? 'BROKER' : tradovateStatus?.is_configured ? 'OFFLINE' : 'SIM'}
            </div>

            {/* Notification Bell */}
            <div className="relative">
              <button
                onClick={() => { setShowNotifications(!showNotifications); if (!showNotifications) fetchNotifications(); }}
                className="relative p-2 rounded-sm bg-zinc-800 hover:bg-zinc-700 transition-colors"
                data-testid="notification-bell"
              >
                {unreadCount > 0 ? <BellRing className="w-4 h-4 text-amber-400" /> : <Bell className="w-4 h-4 text-zinc-400" />}
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-[10px] flex items-center justify-center font-bold">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>

              {showNotifications && (
                <div className="absolute right-0 top-full mt-2 w-80 bg-zinc-900 border border-zinc-700 rounded-md shadow-xl z-50 max-h-96 overflow-y-auto"
                     data-testid="notification-dropdown">
                  <div className="flex items-center justify-between p-3 border-b border-zinc-800">
                    <span className="font-semibold text-sm">Notifications</span>
                    <div className="flex gap-2">
                      <button
                        onClick={async () => { await axios.post(`${API}/notifications/read-all`); fetchNotifications(); }}
                        className="text-xs text-blue-400 hover:underline"
                        data-testid="mark-all-read-btn"
                      >
                        Mark all read
                      </button>
                      <button
                        onClick={async () => { await axios.post(`${API}/notifications/test`); fetchNotifications(); }}
                        className="text-xs text-zinc-400 hover:text-white"
                        data-testid="test-notification-btn"
                      >
                        Test
                      </button>
                    </div>
                  </div>
                  {notifications.length === 0 ? (
                    <div className="p-6 text-center text-sm text-zinc-500">No notifications yet</div>
                  ) : (
                    notifications.map(n => (
                      <div
                        key={n.id}
                        className={`p-3 border-b border-zinc-800/50 hover:bg-zinc-800/50 transition-colors ${!n.read ? 'bg-blue-900/10' : ''}`}
                        onClick={async () => { if (!n.read) { await axios.post(`${API}/notifications/${n.id}/read`); fetchNotifications(); } }}
                      >
                        <div className="flex items-start gap-2">
                          <span className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${
                            n.severity === 'critical' ? 'bg-red-500' : n.severity === 'warning' ? 'bg-amber-500' : 'bg-blue-500'
                          }`} />
                          <div className="min-w-0">
                            <div className="text-sm font-medium truncate">{n.title}</div>
                            <div className="text-xs text-zinc-400 mt-0.5">{n.message}</div>
                            <div className="text-[10px] text-zinc-600 mt-1">{new Date(n.timestamp).toLocaleString()}</div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-400">{user.name || user.email}</span>
              <button
                onClick={logout}
                className="p-2 rounded-sm bg-zinc-800 hover:bg-zinc-700 transition-colors"
                data-testid="logout-btn"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="border-b border-zinc-800 bg-[#18181B] px-4 md:px-6">
        <div className="flex gap-1 overflow-x-auto mobile-tabs overscroll-contain">
          {[
            { id: 'dashboard', label: 'Dashboard', icon: Activity },
            { id: 'options', label: 'Options', icon: LineChart },
            { id: 'portfolio', label: 'Portfolio', icon: Layers },
            { id: 'backtest', label: 'Backtest', icon: BarChart3 },
            { id: 'replay', label: 'Replay', icon: RefreshCw },
            { id: 'social', label: 'Social', icon: GitBranch },
            { id: 'calendar', label: 'Calendar', icon: Calendar },
            { id: 'settings', label: 'Settings', icon: Settings },
          ].map(tab => (
            <button
              key={tab.id}
              data-testid={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0 ${
                activeTab === tab.id
                  ? 'text-blue-400 border-blue-500'
                  : 'text-zinc-400 border-transparent hover:text-white'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="p-3 md:p-6 overscroll-contain safe-area-bottom">
        {/* ──── TRADING BOT PANEL (Always visible) ──── */}
        <div className={`mb-6 bg-zinc-900 border rounded-md p-4 transition-all ${
          botStatus?.enabled ? 'border-amber-500/50' : 'border-zinc-800'
        }`} data-testid="trading-bot-panel">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className={`w-2.5 h-2.5 rounded-full ${botStatus?.enabled ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`} />
              <h3 className="font-outfit font-semibold flex items-center gap-2">
                <Brain className="w-5 h-5 text-amber-400" />
                Trading Bot
              </h3>
              <span className={`text-xs px-2 py-0.5 rounded font-mono ${
                botStatus?.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700 text-zinc-500'
              }`}>{botStatus?.enabled ? 'ACTIVE' : 'OFFLINE'}</span>
              {botStatus?.enabled && (
                <span className="text-xs text-zinc-500 font-mono">
                  Min confidence: {botStatus?.min_confidence}% | Scans: {botStatus?.scan_interval_sec}s | Today: {botStatus?.executed_today}/{botStatus?.max_daily_trades}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {botStatus?.enabled && (
                <button
                  data-testid="bot-history-btn"
                  onClick={fetchBotHistory}
                  className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-xs transition-colors"
                >
                  History
                </button>
              )}
              <button
                data-testid="bot-toggle-btn"
                onClick={toggleBot}
                className={`px-4 py-1.5 rounded text-sm font-medium transition-all ${
                  botStatus?.enabled 
                    ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/50' 
                    : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/50'
                }`}
              >
                {botStatus?.enabled ? 'Stop Bot' : 'Start Bot'}
              </button>
            </div>
          </div>

          {/* Pending Opportunities */}
          {botOpportunities.length > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-amber-400 font-mono uppercase tracking-wider flex items-center gap-1.5">
                <BellRing className="w-3.5 h-3.5" />
                {botOpportunities.length} Pending Approval
              </div>
              {botOpportunities.map(opp => (
                <div key={opp.id} className={`p-4 rounded-md border ${
                  opp.direction === 'long' ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-red-500/5 border-red-500/30'
                }`} data-testid={`opportunity-${opp.id}`}>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className={`text-lg font-bold font-mono ${
                          opp.direction === 'long' ? 'text-emerald-400' : 'text-red-400'
                        }`}>
                          {opp.direction === 'long' ? 'BUY' : 'SELL'} {opp.symbol}
                        </span>
                        <span className="text-xl font-mono font-bold">${opp.entry_price?.toFixed(2)}</span>
                        <span className={`text-sm px-2 py-0.5 rounded font-mono font-bold ${
                          opp.confidence >= 80 ? 'bg-emerald-500/20 text-emerald-400' :
                          opp.confidence >= 70 ? 'bg-green-500/20 text-green-400' :
                          'bg-amber-500/20 text-amber-400'
                        }`}>{opp.confidence?.toFixed(0)}%</span>
                        <span className="text-xs text-zinc-500 font-mono">{opp.size} contracts</span>
                      </div>
                      <div className="text-xs text-zinc-400 mb-2">{opp.reasoning}</div>
                      <div className="grid grid-cols-4 gap-3 text-xs">
                        <div>
                          <span className="text-zinc-500">Stop Loss</span>
                          <div className="font-mono text-red-400">${opp.stop_loss?.toFixed(2)}</div>
                        </div>
                        <div>
                          <span className="text-zinc-500">Target 1</span>
                          <div className="font-mono text-emerald-400">${opp.take_profit_1?.toFixed(2)}</div>
                        </div>
                        <div>
                          <span className="text-zinc-500">Target 2</span>
                          <div className="font-mono text-emerald-400">${opp.take_profit_2?.toFixed(2)}</div>
                        </div>
                        <div>
                          <span className="text-zinc-500">Gate</span>
                          <div className="font-mono text-zinc-300">{opp.gate_status}</div>
                        </div>
                      </div>
                      {/* Exit Tiers */}
                      <div className="flex gap-2 mt-2">
                        {(opp.exit_tiers || []).map((t, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 bg-zinc-800/80 rounded text-zinc-500 font-mono">
                            {t.tier} ${t.price}
                          </span>
                        ))}
                      </div>
                      <div className="text-[10px] text-zinc-600 mt-1">
                        Expires: {new Date(opp.expires_at).toLocaleTimeString()}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2 ml-4">
                      <button
                        data-testid={`approve-${opp.id}`}
                        onClick={() => approveOpportunity(opp.id)}
                        className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-sm transition-colors"
                      >
                        APPROVE
                      </button>
                      <button
                        data-testid={`reject-${opp.id}`}
                        onClick={() => rejectOpportunity(opp.id)}
                        className="px-5 py-2.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded text-sm transition-colors"
                      >
                        REJECT
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Bot History */}
          {botHistory.length > 0 && (
            <div className="mt-3 border-t border-zinc-800 pt-3">
              <div className="text-xs text-zinc-500 font-mono mb-2">Recent Bot History</div>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {botHistory.slice(-5).reverse().map(h => (
                  <div key={h.id} className="flex items-center justify-between text-xs py-1 px-2 bg-zinc-800/30 rounded">
                    <div className="flex items-center gap-2">
                      <span className={`font-mono font-bold ${h.direction === 'long' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {h.direction === 'long' ? 'BUY' : 'SELL'}
                      </span>
                      <span className="text-zinc-300">{h.symbol}</span>
                      <span className="font-mono text-zinc-500">${h.entry_price?.toFixed(2)}</span>
                      <span className="text-zinc-600">{h.confidence?.toFixed(0)}%</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                      h.status === 'executed' ? 'bg-emerald-500/20 text-emerald-400' :
                      h.status === 'rejected' ? 'bg-red-500/20 text-red-400' :
                      h.status === 'expired' ? 'bg-zinc-700 text-zinc-500' :
                      'bg-amber-500/20 text-amber-400'
                    }`}>{h.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {botStatus?.enabled && botOpportunities.length === 0 && botHistory.length === 0 && (
            <div className="text-center text-sm text-zinc-500 py-2">
              Scanning market for opportunities... (min confidence: {botStatus?.min_confidence}%)
            </div>
          )}
        </div>

        {activeTab === 'dashboard' && (
          <DashboardTab ctx={{
            assets, allAssetPrices, currentSymbol, switchSymbol, marketData,
            renderPriceChart, spreadOpportunity, positions, closePosition,
            trades, exportTradesCSV, systemStatus, portfolioAnalysis,
            mlPrediction, getMlPrediction, signalScore, executionGate,
            fragility, riskControl, eventCalendar, calendarEvents, dailyPnl,
            fetchAdvancedAnalytics, fetchData, setRegimeOverride, clearOverride,
            triggerEvent, ASSET_COLORS, DIRECTION_COLORS, REGIME_COLORS
          }} />
        )}

        {activeTab === 'options' && (
          <OptionsTab ctx={{
            currentSymbol, optionChain, setOptionChain, optionStrategies,
            setOptionStrategies, volatilityAnalysis, setVolatilityAnalysis,
            autoStrategy, backtestResult, setBacktestResult, payoffData,
            payoffStrategy, fetchPayoff, setActiveTab,
            fetchAutoStrategy, isLoadingStrategy
          }} />
        )}

        {activeTab === 'portfolio' && (
          <div className="max-w-6xl mx-auto space-y-6">
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="portfolio-page">
              <h2 className="font-outfit text-2xl font-bold mb-6">Portfolio Analysis</h2>
              
              {/* Asset Correlation Matrix */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold mb-4">Asset Correlations</h3>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-xs text-zinc-400 font-mono uppercase border-b border-zinc-800">
                        <th className="pb-2"></th>
                        {ASSET_SYMBOLS.map(s => (
                          <th key={s} className={`pb-2 text-center ${ASSET_COLORS[s]}`}>{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="font-mono text-sm">
                      {portfolioAnalysis?.correlations && Object.entries(portfolioAnalysis.correlations).map(([s1, row]) => (
                        <tr key={s1} className="border-b border-zinc-800/50">
                          <td className={`py-2 ${ASSET_COLORS[s1]}`}>{s1}</td>
                          {Object.entries(row).map(([s2, corr]) => (
                            <td 
                              key={s2} 
                              className={`py-2 text-center ${
                                corr >= 0.8 ? 'text-emerald-400' : 
                                corr >= 0.5 ? 'text-amber-400' : 
                                'text-zinc-400'
                              }`}
                            >
                              {corr.toFixed(2)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Risk Metrics */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-zinc-800 p-4 rounded">
                  <div className="text-xs text-zinc-400 font-mono uppercase">Total Position Value</div>
                  <div className="font-mono text-xl font-bold">
                    ${portfolioAnalysis?.total_value?.toFixed(2) || '0.00'}
                  </div>
                </div>
                <div className="bg-zinc-800 p-4 rounded">
                  <div className="text-xs text-zinc-400 font-mono uppercase">VaR 95% (1-Day)</div>
                  <div className="font-mono text-xl font-bold text-red-400">
                    ${portfolioAnalysis?.var_95_1d?.toFixed(2) || '0.00'}
                  </div>
                </div>
                <div className="bg-zinc-800 p-4 rounded">
                  <div className="text-xs text-zinc-400 font-mono uppercase">VaR 99% (1-Day)</div>
                  <div className="font-mono text-xl font-bold text-red-400">
                    ${portfolioAnalysis?.var_99_1d?.toFixed(2) || '0.00'}
                  </div>
                </div>
              </div>

              {/* Spread Opportunity */}
              {portfolioAnalysis?.spread_opportunity && (
                <div className="bg-purple-900/20 border border-purple-500/50 rounded-md p-4">
                  <h3 className="font-semibold text-purple-400 mb-3">Spread Trading Opportunity Detected</h3>
                  <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-zinc-400">Signal</div>
                      <div className="font-mono font-bold">{portfolioAnalysis.spread_opportunity.signal}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Current Spread</div>
                      <div className="font-mono">${portfolioAnalysis.spread_opportunity.spread}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Z-Score</div>
                      <div className="font-mono">{portfolioAnalysis.spread_opportunity.z_score}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Expected Convergence</div>
                      <div className="font-mono text-emerald-400">
                        ${portfolioAnalysis.spread_opportunity.expected_convergence}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'backtest' && (
          <div className="max-w-4xl mx-auto space-y-6">
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="backtest-panel">
              <h2 className="font-outfit text-2xl font-bold mb-6">Strategy Backtest</h2>
              
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <label className="block text-sm text-zinc-400 mb-1">Start Date</label>
                  <input 
                    type="date" 
                    defaultValue="2024-01-01"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-sm text-zinc-400 mb-1">End Date</label>
                  <input 
                    type="date" 
                    defaultValue="2024-06-30"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                  />
                </div>
              </div>
              
              <button
                data-testid="run-backtest-btn"
                onClick={runBacktest}
                disabled={isBacktesting}
                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded font-semibold transition-colors"
              >
                {isBacktesting ? 'Running Backtest...' : 'Run Backtest'}
              </button>
            </div>

            {backtestResult && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="backtest-results">
                <h3 className="font-outfit text-xl font-bold mb-4">Backtest Results</h3>
                
                <div className="grid grid-cols-4 gap-4 mb-6">
                  <div className="bg-zinc-800 p-4 rounded">
                    <div className="text-xs text-zinc-400 font-mono uppercase">Final Equity</div>
                    <div className="font-mono text-xl font-bold text-emerald-400">
                      ${backtestResult.final_equity?.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-zinc-800 p-4 rounded">
                    <div className="text-xs text-zinc-400 font-mono uppercase">Win Rate</div>
                    <div className="font-mono text-xl font-bold">
                      {backtestResult.win_rate}%
                    </div>
                  </div>
                  <div className="bg-zinc-800 p-4 rounded">
                    <div className="text-xs text-zinc-400 font-mono uppercase">Profit Factor</div>
                    <div className="font-mono text-xl font-bold">
                      {backtestResult.profit_factor}
                    </div>
                  </div>
                  <div className="bg-zinc-800 p-4 rounded">
                    <div className="text-xs text-zinc-400 font-mono uppercase">Max Drawdown</div>
                    <div className="font-mono text-xl font-bold text-red-400">
                      {backtestResult.max_drawdown}%
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-zinc-800 p-3 rounded">
                    <div className="text-xs text-zinc-400 font-mono">Total Trades</div>
                    <div className="font-mono text-lg">{backtestResult.total_trades}</div>
                  </div>
                  <div className="bg-zinc-800 p-3 rounded">
                    <div className="text-xs text-zinc-400 font-mono">Sharpe Ratio</div>
                    <div className="font-mono text-lg">{backtestResult.sharpe_ratio}</div>
                  </div>
                  <div className="bg-zinc-800 p-3 rounded">
                    <div className="text-xs text-zinc-400 font-mono">Return</div>
                    <div className={`font-mono text-lg ${backtestResult.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {backtestResult.return_pct >= 0 ? '+' : ''}{backtestResult.return_pct}%
                    </div>
                  </div>
                </div>

                {backtestResult.equity_curve?.length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-sm font-medium mb-2">Equity Curve</h4>
                    <svg viewBox="0 0 800 150" className="w-full h-32">
                      {(() => {
                        const data = backtestResult.equity_curve;
                        const values = data.map(d => d.equity);
                        const min = Math.min(...values);
                        const max = Math.max(...values);
                        const range = max - min || 1;
                        
                        const points = values.map((v, i) => {
                          const x = 20 + (i / (values.length - 1)) * 760;
                          const y = 140 - ((v - min) / range) * 120;
                          return `${x},${y}`;
                        }).join(" ");
                        
                        return (
                          <>
                            <polyline fill="none" stroke="#10B981" strokeWidth="2" points={points} />
                            <text x="20" y="15" fill="#A1A1AA" fontSize="10" fontFamily="JetBrains Mono">${max.toFixed(0)}</text>
                            <text x="20" y="145" fill="#A1A1AA" fontSize="10" fontFamily="JetBrains Mono">${min.toFixed(0)}</text>
                          </>
                        );
                      })()}
                    </svg>
                  </div>
                )}

                {backtestResult.trades?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">Sample Trades</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="text-left text-xs text-zinc-400 font-mono border-b border-zinc-800">
                            <th className="pb-2">Direction</th>
                            <th className="pb-2 text-right">Entry</th>
                            <th className="pb-2 text-right">Exit</th>
                            <th className="pb-2 text-right">P&L</th>
                          </tr>
                        </thead>
                        <tbody className="font-mono text-sm">
                          {backtestResult.trades.slice(0, 10).map((trade, i) => (
                            <tr key={i} className="border-b border-zinc-800/50">
                              <td className={`py-2 ${trade.direction === 'long' ? 'text-emerald-400' : 'text-red-400'}`}>
                                {trade.direction?.toUpperCase()}
                              </td>
                              <td className="py-2 text-right">${trade.entry_price?.toFixed(2)}</td>
                              <td className="py-2 text-right">${trade.exit_price?.toFixed(2)}</td>
                              <td className={`py-2 text-right ${trade.pnl_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {trade.pnl_usd >= 0 ? '+' : ''}${trade.pnl_usd?.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}


        {activeTab === 'replay' && (
          <ReplayTab
            replayEvents={replayEvents} replayResult={replayResult}
            isReplaying={isReplaying} simResult={simResult}
            isSimulating={isSimulating} simConfig={simConfig}
            setSimConfig={setSimConfig} runReplay={runReplay}
            runSimulation={runSimulation} fetchReplayEvents={fetchReplayEvents}
          />
        )}


        {activeTab === 'social' && (
          <div className="max-w-4xl mx-auto space-y-6" data-testid="social-page">
            {/* Leaderboard */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
              <h2 className="font-outfit text-2xl font-bold mb-2 flex items-center gap-2">
                <GitBranch className="w-6 h-6 text-violet-400" />
                Strategy Leaderboard
              </h2>
              <p className="text-xs text-zinc-500 mb-4">Top shared strategies by risk-adjusted score. Follow to copy the config to your bot.</p>

              {leaderboard.length === 0 ? (
                <div className="text-center py-8 text-zinc-500">
                  <p className="mb-3">No shared strategies yet. Be the first!</p>
                  <p className="text-xs">Go to Replay &gt; Strategy Optimizer &gt; Share your best config.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {leaderboard.map((strat, idx) => (
                    <div key={strat.id} className="flex items-center justify-between bg-zinc-800/50 rounded-md p-4 hover:bg-zinc-800 transition-colors" data-testid={`leaderboard-${idx}`}>
                      <div className="flex items-center gap-4">
                        <span className={`font-mono text-lg font-bold ${idx === 0 ? 'text-amber-400' : idx === 1 ? 'text-zinc-300' : idx === 2 ? 'text-amber-700' : 'text-zinc-500'}`}>#{idx + 1}</span>
                        <div>
                          <div className="font-semibold text-sm">{strat.name}</div>
                          <div className="text-xs text-zinc-500">by {strat.author} {strat.description && `- ${strat.description}`}</div>
                          <div className="flex gap-3 mt-1 text-xs">
                            <span className="font-mono">Conf: {strat.config?.min_confidence}%</span>
                            <span className="font-mono">SL: {strat.config?.atr_sl_mult}x</span>
                            <span className="font-mono">TP1: {strat.config?.atr_tp1_mult}x</span>
                            <span className="font-mono">TP2: {strat.config?.atr_tp2_mult}x</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <div className={`font-mono text-sm font-bold ${strat.performance?.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            ${strat.performance?.total_pnl?.toLocaleString() || '0'}
                          </div>
                          <div className="text-[10px] text-zinc-500">
                            {strat.followers || 0} followers | Score: {strat.score}
                          </div>
                        </div>
                        <button
                          onClick={() => followStrategy(strat.id)}
                          data-testid={`follow-${strat.id}`}
                          className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium rounded transition-colors"
                        >
                          Follow
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Strategy Template Market */}
            {templates.length > 0 && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="strategy-market">
                <h2 className="font-outfit text-xl font-bold mb-2 flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-cyan-400" />
                  Strategy Market
                </h2>
                <p className="text-xs text-zinc-500 mb-4">One-click import popular strategies into Replay Engine or PvP Battle</p>

                <div className="space-y-3">
                  {templates.slice(0, 10).map((tmpl, idx) => (
                    <div key={tmpl.id} className="bg-zinc-800/40 border border-zinc-700/50 rounded-lg p-4 hover:border-cyan-500/30 transition-colors" data-testid={`template-${idx}`}>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${idx === 0 ? 'bg-amber-500/20 text-amber-400' : idx < 3 ? 'bg-cyan-500/15 text-cyan-400' : 'bg-zinc-700 text-zinc-400'}`}>
                              #{idx + 1}
                            </span>
                            <span className="font-semibold text-sm truncate">{tmpl.name}</span>
                            <span className="text-[10px] text-zinc-500 shrink-0">by {tmpl.author}</span>
                          </div>
                          {tmpl.description && <p className="text-[11px] text-zinc-500 mb-2 truncate">{tmpl.description}</p>}
                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                            <span className="font-mono text-zinc-400">Conf: <span className="text-white">{tmpl.config?.min_confidence}%</span></span>
                            <span className="font-mono text-zinc-400">SL: <span className="text-white">{tmpl.config?.atr_sl_mult}x</span></span>
                            <span className="font-mono text-zinc-400">TP1: <span className="text-white">{tmpl.config?.atr_tp1_mult}x</span></span>
                            <span className="font-mono text-zinc-400">TP2: <span className="text-white">{tmpl.config?.atr_tp2_mult}x</span></span>
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-2 shrink-0">
                          <div className="text-right">
                            <div className={`font-mono text-sm font-bold ${tmpl.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              ${tmpl.total_pnl?.toLocaleString() || '0'}
                            </div>
                            <div className="text-[10px] text-zinc-500">{tmpl.win_rate}% win | {tmpl.imports || 0} imports</div>
                          </div>
                          <div className="flex gap-1.5">
                            <button
                              data-testid={`import-replay-${idx}`}
                              onClick={() => importTemplateToReplay(tmpl.id, tmpl.config)}
                              className="px-2.5 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] font-semibold rounded transition-colors"
                            >
                              Import & Test
                            </button>
                            <button
                              data-testid={`import-pvp-a-${idx}`}
                              onClick={() => importTemplateToPvp(tmpl.id, tmpl.config, 'a')}
                              className="px-2 py-1.5 bg-blue-600/60 hover:bg-blue-500 text-white text-[10px] font-semibold rounded transition-colors"
                              title="Load as PvP Strategy A"
                            >
                              PvP A
                            </button>
                            <button
                              data-testid={`import-pvp-b-${idx}`}
                              onClick={() => importTemplateToPvp(tmpl.id, tmpl.config, 'b')}
                              className="px-2 py-1.5 bg-red-600/60 hover:bg-red-500 text-white text-[10px] font-semibold rounded transition-colors"
                              title="Load as PvP Strategy B"
                            >
                              PvP B
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* PvP Battle Arena */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
              <h2 className="font-outfit text-xl font-bold mb-2 flex items-center gap-2">
                <Zap className="w-5 h-5 text-amber-400" />
                PvP Strategy Battle
              </h2>
              <p className="text-xs text-zinc-500 mb-4">Pit two strategies against each other across all historical events</p>

              <div className="grid grid-cols-2 gap-6 mb-4">
                {/* Config A */}
                <div className="space-y-2" data-testid="pvp-config-a">
                  <h4 className="text-sm font-bold text-blue-400">Strategy A</h4>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">Conf%</label>
                      <input type="number" value={pvpConfigA.min_confidence} onChange={e => setPvpConfigA(p => ({...p, min_confidence: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">SL</label>
                      <input type="number" step="0.5" value={pvpConfigA.atr_sl_mult} onChange={e => setPvpConfigA(p => ({...p, atr_sl_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">TP1</label>
                      <input type="number" step="0.5" value={pvpConfigA.atr_tp1_mult} onChange={e => setPvpConfigA(p => ({...p, atr_tp1_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">TP2</label>
                      <input type="number" step="0.5" value={pvpConfigA.atr_tp2_mult} onChange={e => setPvpConfigA(p => ({...p, atr_tp2_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                  </div>
                </div>
                {/* Config B */}
                <div className="space-y-2" data-testid="pvp-config-b">
                  <h4 className="text-sm font-bold text-red-400">Strategy B</h4>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">Conf%</label>
                      <input type="number" value={pvpConfigB.min_confidence} onChange={e => setPvpConfigB(p => ({...p, min_confidence: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">SL</label>
                      <input type="number" step="0.5" value={pvpConfigB.atr_sl_mult} onChange={e => setPvpConfigB(p => ({...p, atr_sl_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">TP1</label>
                      <input type="number" step="0.5" value={pvpConfigB.atr_tp1_mult} onChange={e => setPvpConfigB(p => ({...p, atr_tp1_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2">
                      <label className="text-[10px] text-zinc-500 block">TP2</label>
                      <input type="number" step="0.5" value={pvpConfigB.atr_tp2_mult} onChange={e => setPvpConfigB(p => ({...p, atr_tp2_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" />
                    </div>
                  </div>
                </div>
              </div>

              <button
                data-testid="run-pvp-btn"
                onClick={runPvpBattle}
                disabled={isPvpRunning}
                className="w-full py-3 bg-gradient-to-r from-blue-600 to-red-600 hover:from-blue-500 hover:to-red-500 disabled:from-zinc-700 disabled:to-zinc-700 text-white font-bold rounded-md transition-all text-sm"
              >
                {isPvpRunning ? 'Battle in progress...' : 'Start Battle'}
              </button>

              {isPvpRunning && <div className="text-center py-4 text-amber-400 animate-pulse mt-2">Simulating across all events...</div>}

              {/* PvP Results */}
              {pvpResult && !isPvpRunning && (
                <div className="mt-6 space-y-4" data-testid="pvp-results">
                  {/* Winner Banner */}
                  <div className={`text-center py-4 rounded-md font-bold text-lg ${
                    pvpResult.overall_winner === 'a' ? 'bg-blue-600/20 text-blue-400' :
                    pvpResult.overall_winner === 'b' ? 'bg-red-600/20 text-red-400' :
                    'bg-zinc-700/50 text-zinc-400'
                  }`} data-testid="pvp-winner">
                    {pvpResult.overall_winner === 'a' ? 'Strategy A Wins!' :
                     pvpResult.overall_winner === 'b' ? 'Strategy B Wins!' : 'Draw!'}
                  </div>

                  {/* Summary Comparison */}
                  <div className="grid grid-cols-3 gap-4">
                    {/* Strategy A stats */}
                    <div className="text-center space-y-2 bg-blue-500/5 rounded-md p-3 border border-blue-500/20">
                      <h4 className="text-xs font-bold text-blue-400">Strategy A</h4>
                      <div className="font-mono text-lg font-bold text-blue-400">${pvpResult.summary_a?.total_pnl?.toLocaleString()}</div>
                      <div className="text-xs text-zinc-500">{pvpResult.summary_a?.total_trades} trades | {pvpResult.summary_a?.win_rate}% win</div>
                      <div className="text-xs text-zinc-500">Events won: {pvpResult.summary_a?.events_won}</div>
                    </div>
                    {/* VS */}
                    <div className="flex items-center justify-center">
                      <div className="text-3xl font-black text-zinc-600">VS</div>
                    </div>
                    {/* Strategy B stats */}
                    <div className="text-center space-y-2 bg-red-500/5 rounded-md p-3 border border-red-500/20">
                      <h4 className="text-xs font-bold text-red-400">Strategy B</h4>
                      <div className="font-mono text-lg font-bold text-red-400">${pvpResult.summary_b?.total_pnl?.toLocaleString()}</div>
                      <div className="text-xs text-zinc-500">{pvpResult.summary_b?.total_trades} trades | {pvpResult.summary_b?.win_rate}% win</div>
                      <div className="text-xs text-zinc-500">Events won: {pvpResult.summary_b?.events_won}</div>
                    </div>
                  </div>

                  {/* Per-Event Results */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs" data-testid="pvp-events-table">
                      <thead>
                        <tr className="text-zinc-500 border-b border-zinc-800">
                          <th className="py-2 px-2 text-left">Event</th>
                          <th className="py-2 px-2 text-right text-blue-400">A PnL</th>
                          <th className="py-2 px-2 text-right text-blue-400">A Trades</th>
                          <th className="py-2 px-2 text-right text-red-400">B PnL</th>
                          <th className="py-2 px-2 text-right text-red-400">B Trades</th>
                          <th className="py-2 px-2 text-center">Winner</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pvpResult.per_event?.map((evt, idx) => (
                          <tr key={idx} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-1.5 px-2 truncate max-w-[140px]">{evt.event_name}</td>
                            <td className={`py-1.5 px-2 text-right font-mono ${evt.a_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              ${evt.a_pnl?.toLocaleString()}
                            </td>
                            <td className="py-1.5 px-2 text-right font-mono text-zinc-400">{evt.a_trades}</td>
                            <td className={`py-1.5 px-2 text-right font-mono ${evt.b_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              ${evt.b_pnl?.toLocaleString()}
                            </td>
                            <td className="py-1.5 px-2 text-right font-mono text-zinc-400">{evt.b_trades}</td>
                            <td className="py-1.5 px-2 text-center">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                evt.winner === 'a' ? 'bg-blue-500/20 text-blue-400' :
                                evt.winner === 'b' ? 'bg-red-500/20 text-red-400' :
                                'bg-zinc-700 text-zinc-400'
                              }`}>{evt.winner === 'a' ? 'A' : evt.winner === 'b' ? 'B' : 'TIE'}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Following */}
            {following.length > 0 && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
                <h3 className="font-outfit text-lg font-bold mb-4">Following ({following.length})</h3>
                <div className="space-y-2">
                  {following.map(strat => (
                    <div key={strat.id} className="flex items-center justify-between bg-zinc-800/50 rounded p-3" data-testid={`following-${strat.id}`}>
                      <div>
                        <span className="font-semibold text-sm">{strat.name}</span>
                        <span className="text-xs text-zinc-500 ml-2">by {strat.author}</span>
                      </div>
                      <button
                        onClick={() => followStrategy(strat.id)}
                        className="px-2 py-1 bg-zinc-700 hover:bg-red-600 text-xs rounded transition-colors"
                      >
                        Unfollow
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'calendar' && (
          <div className="max-w-4xl mx-auto">
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="calendar-page">
              <h2 className="font-outfit text-2xl font-bold mb-6">Economic Calendar</h2>
              
              <div className="space-y-3">
                {calendarEvents.map(event => (
                  <div 
                    key={event.id}
                    className="flex items-center justify-between p-4 bg-zinc-800/50 rounded-md hover:bg-zinc-800 transition-colors"
                    data-testid={`calendar-event-${event.id}`}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className={`w-2 h-2 rounded-full ${
                          event.importance === 'high' ? 'bg-red-500' :
                          event.importance === 'medium' ? 'bg-amber-500' : 'bg-zinc-500'
                        }`} />
                        <span className="font-medium">{event.event_name}</span>
                        <span className="text-xs px-2 py-0.5 bg-zinc-700 rounded text-zinc-400">
                          {event.event_type}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-sm text-zinc-400">
                        <span>{event.country}</span>
                        <span>{new Date(event.date).toLocaleString()}</span>
                        {event.forecast !== null && (
                          <span>Forecast: {event.forecast?.toFixed(2)}</span>
                        )}
                        {event.previous !== null && (
                          <span>Previous: {event.previous?.toFixed(2)}</span>
                        )}
                      </div>
                    </div>
                    <button
                      data-testid={`trigger-calendar-${event.id}`}
                      onClick={() => triggerEvent(event.id)}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
                    >
                      Simulate
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="max-w-2xl mx-auto space-y-6">
            {/* Price Alerts */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="price-alerts-panel">
              <h2 className="font-outfit text-2xl font-bold mb-4 flex items-center gap-2">
                <Bell className="w-6 h-6 text-amber-400" />
                Price Alerts
              </h2>

              {/* Create Alert Form */}
              <div className="grid grid-cols-5 gap-2 mb-4">
                <select
                  data-testid="alert-symbol"
                  value={alertForm.symbol}
                  onChange={e => setAlertForm(p => ({...p, symbol: e.target.value}))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-2 text-sm font-mono"
                >
                  <option value="CL">CL</option>
                  <option value="BZ">BZ</option>
                  <option value="NG">NG</option>
                </select>
                <select
                  data-testid="alert-condition"
                  value={alertForm.condition}
                  onChange={e => setAlertForm(p => ({...p, condition: e.target.value}))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-2 text-sm font-mono"
                >
                  <option value="above">Above</option>
                  <option value="below">Below</option>
                </select>
                <input
                  data-testid="alert-price"
                  type="number"
                  step="0.01"
                  placeholder="Target $"
                  value={alertForm.target_price}
                  onChange={e => setAlertForm(p => ({...p, target_price: e.target.value}))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-2 text-sm font-mono"
                />
                <input
                  data-testid="alert-note"
                  type="text"
                  placeholder="Note (optional)"
                  value={alertForm.note}
                  onChange={e => setAlertForm(p => ({...p, note: e.target.value}))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-2 text-sm"
                />
                <button
                  data-testid="create-alert-btn"
                  onClick={createAlert}
                  className="bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded transition-colors"
                >
                  Create
                </button>
              </div>

              {/* Active Alerts */}
              <div className="space-y-2" data-testid="alerts-list">
                {priceAlerts.length === 0 ? (
                  <div className="text-center py-4 text-zinc-500 text-sm">No active alerts. Create one above.</div>
                ) : (
                  priceAlerts.map(alert => (
                    <div key={alert.id} className="flex items-center justify-between bg-zinc-800/50 rounded p-3" data-testid={`alert-${alert.id}`}>
                      <div className="flex items-center gap-3">
                        <span className={`font-mono text-sm font-bold ${alert.symbol === 'CL' ? 'text-blue-400' : alert.symbol === 'BZ' ? 'text-purple-400' : 'text-emerald-400'}`}>{alert.symbol}</span>
                        <span className="text-xs text-zinc-400">{alert.condition === 'above' ? 'Above' : 'Below'}</span>
                        <span className="font-mono font-bold">${alert.target_price}</span>
                        {alert.note && <span className="text-xs text-zinc-500 ml-2">({alert.note})</span>}
                        {alert.triggered && <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">TRIGGERED</span>}
                      </div>
                      <button
                        onClick={() => deleteAlert(alert.id)}
                        className="p-1.5 rounded bg-zinc-700 hover:bg-red-600 transition-colors"
                        data-testid={`delete-alert-${alert.id}`}
                      >
                        <XCircle className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Trade Export */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="export-panel">
              <h2 className="font-outfit text-xl font-bold mb-4">Trade Export</h2>
              <button
                data-testid="export-csv-btn"
                onClick={exportTradesCSV}
                className="w-full py-3 bg-zinc-700 hover:bg-zinc-600 rounded font-semibold transition-colors flex items-center justify-center gap-2"
              >
                <DollarSign className="w-4 h-4" />
                Download Trades CSV
              </button>
            </div>

            {/* Settings */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="settings-page">
              <h2 className="font-outfit text-2xl font-bold mb-6">Settings</h2>
              
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold mb-3">Risk Parameters</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">Max Risk Per Trade (%)</label>
                      <input 
                        type="number" 
                        defaultValue="0.5"
                        step="0.1"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">Max Daily Loss (%)</label>
                      <input 
                        type="number" 
                        defaultValue="1.5"
                        step="0.1"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">Max Consecutive Losses</label>
                      <input 
                        type="number" 
                        defaultValue="3"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">Max Spread (ticks)</label>
                      <input 
                        type="number" 
                        defaultValue="6"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-3">Signal Parameters</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">ADX Threshold</label>
                      <input 
                        type="number" 
                        defaultValue="22"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-zinc-400 mb-1">Min Volume Ratio</label>
                      <input 
                        type="number" 
                        defaultValue="1.2"
                        step="0.1"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono"
                      />
                    </div>
                  </div>
                </div>

                <button className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded font-semibold transition-colors">
                  Save Settings
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// Wrap App with AuthProvider
function AppWithAuth() {
  return (
    <AuthProvider>
      <App />
    </AuthProvider>
  );
}

export default AppWithAuth;
