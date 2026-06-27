import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Shield, AlertTriangle, RefreshCcw, BarChart3,
  Target, PieChart, Bell, BellRing, Save, Play, Check, X,
  TrendingUp, Mail, Send, Clock
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Cell,
  LineChart, Line, Legend
} from 'recharts';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Switch } from '../components/ui/switch';
import { Slider } from '../components/ui/slider';
import { Label } from '../components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-500/15 text-red-400 border-red-500/30',
  HIGH: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  MODERATE: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  LOW: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
};

const RiskAnalyticsPage = () => {
  const navigate = useNavigate();
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Alert config state
  const [alertConfig, setAlertConfig] = useState(null);
  const [alertHistory, setAlertHistory] = useState([]);
  const [checkingRisk, setCheckingRisk] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  // Editable config fields
  const [alertEnabled, setAlertEnabled] = useState(true);
  const [varThreshold, setVarThreshold] = useState(5000);
  const [volThreshold, setVolThreshold] = useState(30);
  const [ddThreshold, setDdThreshold] = useState(15);
  const [sharpeThreshold, setSharpeThreshold] = useState(0.5);
  const [stressTrigger, setStressTrigger] = useState('CRITICAL');
  const [telegramPush, setTelegramPush] = useState(true);
  const [browserPush, setBrowserPush] = useState(true);

  // Risk Trends state
  const [trendData, setTrendData] = useState([]);
  const [trendDays, setTrendDays] = useState(30);
  const [trendMetric, setTrendMetric] = useState('var_95');

  // Email Digest state
  const [emailPrefs, setEmailPrefs] = useState(null);
  const [digestEmail, setDigestEmail] = useState('');
  const [digestEnabled, setDigestEnabled] = useState(true);
  const [includeRisk, setIncludeRisk] = useState(true);
  const [includeAlerts, setIncludeAlerts] = useState(true);
  const [includeBrief, setIncludeBrief] = useState(true);
  const [includePortfolio, setIncludePortfolio] = useState(true);
  const [sendingDigest, setSendingDigest] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [digestHistory, setDigestHistory] = useState([]);

  const fetchRiskData = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/risk-analytics`, { withCredentials: true });
      setRiskData(res.data);
    } catch (err) {
      toast.error('Failed to load risk analytics');
    } finally {
      setLoading(false);
    }
  };

  const fetchAlertConfig = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/risk-alerts/config`, { withCredentials: true });
      const cfg = res.data;
      setAlertConfig(cfg);
      setAlertEnabled(cfg.enabled ?? true);
      setVarThreshold(cfg.var_threshold ?? 5000);
      setVolThreshold(cfg.volatility_threshold ?? 30);
      setDdThreshold(cfg.drawdown_threshold ?? 15);
      setSharpeThreshold(cfg.sharpe_threshold ?? 0.5);
      setStressTrigger(cfg.stress_severity_trigger ?? 'CRITICAL');
      setTelegramPush(cfg.telegram_push ?? true);
      setBrowserPush(cfg.browser_push ?? true);
    } catch (err) {
      console.error('Failed to load alert config:', err);
    }
  }, []);

  const fetchAlertHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/risk-alerts/history`, { withCredentials: true });
      setAlertHistory(res.data);
    } catch (err) {
      console.error('Failed to load alert history:', err);
    }
  }, []);

  const fetchTrendData = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/risk-trends?days=${trendDays}`, { withCredentials: true });
      setTrendData(res.data.map(s => ({
        ...s,
        time: new Date(s.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      })));
    } catch (err) {
      console.error('Failed to load trend data:', err);
    }
  }, [trendDays]);

  const fetchEmailPrefs = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/email-digest/preferences`, { withCredentials: true });
      const p = res.data;
      setEmailPrefs(p);
      setDigestEmail(p.digest_email || '');
      setDigestEnabled(p.digest_enabled ?? true);
      setIncludeRisk(p.include_risk_summary ?? true);
      setIncludeAlerts(p.include_alerts ?? true);
      setIncludeBrief(p.include_ai_brief ?? true);
      setIncludePortfolio(p.include_portfolio ?? true);
    } catch (err) {
      console.error('Failed to load email prefs:', err);
    }
  }, []);

  const fetchDigestHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/email-digest/history`, { withCredentials: true });
      setDigestHistory(res.data);
    } catch (err) {
      console.error('Failed to load digest history:', err);
    }
  }, []);

  useEffect(() => {
    fetchRiskData();
    fetchAlertConfig();
    fetchAlertHistory();
    fetchTrendData();
    fetchEmailPrefs();
    fetchDigestHistory();
  }, [fetchAlertConfig, fetchAlertHistory, fetchTrendData, fetchEmailPrefs, fetchDigestHistory]);

  const saveConfig = async () => {
    setSavingConfig(true);
    try {
      await axios.post(`${API_URL}/api/risk-alerts/config`, {
        enabled: alertEnabled,
        var_threshold: varThreshold,
        volatility_threshold: volThreshold,
        drawdown_threshold: ddThreshold,
        sharpe_threshold: sharpeThreshold,
        stress_severity_trigger: stressTrigger,
        telegram_push: telegramPush,
        browser_push: browserPush
      }, { withCredentials: true });
      toast.success('Risk alert settings saved');
    } catch (err) {
      toast.error('Failed to save settings');
    } finally {
      setSavingConfig(false);
    }
  };

  const triggerRiskCheck = async () => {
    setCheckingRisk(true);
    try {
      const res = await axios.post(`${API_URL}/api/risk-alerts/check`, {}, { withCredentials: true });
      const result = res.data;
      if (result.alerts_fired > 0) {
        toast.warning(`${result.alerts_fired} risk alert(s) triggered!`);
      } else {
        toast.success('All risk metrics within thresholds');
      }
      fetchAlertHistory();
      fetchTrendData();
    } catch (err) {
      toast.error('Risk check failed');
    } finally {
      setCheckingRisk(false);
    }
  };

  const saveEmailPrefs = async () => {
    setSavingEmail(true);
    try {
      await axios.post(`${API_URL}/api/email-digest/preferences`, {
        digest_enabled: digestEnabled,
        digest_email: digestEmail,
        include_risk_summary: includeRisk,
        include_alerts: includeAlerts,
        include_ai_brief: includeBrief,
        include_portfolio: includePortfolio,
      }, { withCredentials: true });
      toast.success('Email preferences saved');
    } catch (err) {
      toast.error('Failed to save email preferences');
    } finally {
      setSavingEmail(false);
    }
  };

  const sendDigestNow = async () => {
    setSendingDigest(true);
    try {
      const res = await axios.post(`${API_URL}/api/email-digest/send`, {}, { withCredentials: true });
      if (res.data.sent) {
        toast.success(`Digest sent to ${res.data.email}`);
      } else {
        toast.error(res.data.reason || 'Failed to send digest');
      }
      fetchDigestHistory();
    } catch (err) {
      toast.error('Failed to send digest email');
    } finally {
      setSendingDigest(false);
    }
  };

  const radarData = riskData?.risk_distribution
    ? Object.entries(riskData.risk_distribution).map(([key, val]) => ({
        subject: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        value: val
      }))
    : [];

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-300 overflow-hidden" data-testid="risk-analytics-page">
      <Toaster position="bottom-right" theme="dark" />

      {/* Header */}
      <nav className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6 shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')} className="p-1.5" data-testid="back-btn">
            <ArrowLeft size={18} />
          </Button>
          <div className="w-8 h-8 bg-red-600 rounded-sm flex items-center justify-center">
            <Shield size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-xs font-black tracking-[0.15em] text-white uppercase">Risk Analytics</h1>
            <p className="text-[9px] text-zinc-500">Portfolio VaR, Stress Testing & Risk Alerts</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={triggerRiskCheck} disabled={checkingRisk} className="text-[10px] border-amber-700/50 text-amber-400 hover:bg-amber-900/20 gap-1.5" data-testid="check-risk-btn">
            <BellRing size={12} className={checkingRisk ? 'animate-pulse' : ''} /> {checkingRisk ? 'Checking...' : 'Run Risk Check'}
          </Button>
          <Button variant="outline" size="sm" onClick={fetchRiskData} disabled={loading} className="text-[10px] border-zinc-700 gap-1.5" data-testid="refresh-btn">
            <RefreshCcw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </Button>
        </div>
      </nav>

      {loading && !riskData ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <RefreshCcw size={32} className="animate-spin text-zinc-600 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">Computing risk metrics...</p>
          </div>
        </div>
      ) : riskData ? (
        <ScrollArea className="flex-1">
          <div className="p-3 sm:p-6 space-y-4 sm:space-y-6">

            {/* VaR Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3" data-testid="var-cards">
              <MetricCard label="VaR 95% (Hist)" value={`$${riskData.var.historical_95.toLocaleString()}`} sub="1-Day" color="text-red-400" />
              <MetricCard label="VaR 99% (Hist)" value={`$${riskData.var.historical_99.toLocaleString()}`} sub="1-Day" color="text-red-500" />
              <MetricCard label="CVaR 95%" value={`$${riskData.var.cvar_95.toLocaleString()}`} sub="Expected Shortfall" color="text-orange-400" />
              <MetricCard label="VaR 95% (Param)" value={`$${riskData.var.parametric_95.toLocaleString()}`} sub="Normal Dist" color="text-amber-400" />
              <MetricCard label="VaR 99% (Param)" value={`$${riskData.var.parametric_99.toLocaleString()}`} sub="Normal Dist" color="text-amber-500" />
            </div>

            {/* Key Risk Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3" data-testid="risk-metrics">
              <MetricCard label="Sharpe Ratio" value={riskData.metrics.sharpe_ratio.toFixed(3)} color={riskData.metrics.sharpe_ratio > 1 ? 'text-emerald-400' : riskData.metrics.sharpe_ratio > 0 ? 'text-amber-400' : 'text-red-400'} />
              <MetricCard label="Sortino Ratio" value={riskData.metrics.sortino_ratio.toFixed(3)} color={riskData.metrics.sortino_ratio > 1 ? 'text-emerald-400' : 'text-amber-400'} />
              <MetricCard label="Max Drawdown" value={`${riskData.metrics.max_drawdown_pct.toFixed(2)}%`} color="text-red-400" />
              <MetricCard label="Annual Vol" value={`${riskData.metrics.annual_volatility.toFixed(2)}%`} color="text-cyan-400" />
              <MetricCard label="Beta" value={riskData.metrics.beta.toFixed(3)} color="text-blue-400" />
              <MetricCard label="Portfolio Value" value={`$${riskData.metrics.total_value.toLocaleString()}`} color="text-white" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
              {/* Stress Tests */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="stress-tests">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-4 uppercase flex items-center gap-2 tracking-widest">
                  <AlertTriangle size={14} className="text-orange-500" /> Stress Test Scenarios
                </h3>
                <div className="space-y-2">
                  {riskData.stress_tests.map((test, i) => (
                    <div key={i} className={`p-2.5 sm:p-3 rounded-sm border ${SEVERITY_STYLES[test.severity] || SEVERITY_STYLES.MODERATE}`} data-testid={`stress-test-${i}`}>
                      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
                        <div>
                          <span className="text-xs font-bold">{test.name}</span>
                          <p className="text-[9px] opacity-70 mt-0.5">{test.description}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge className={`text-[8px] border ${SEVERITY_STYLES[test.severity]}`}>{test.severity}</Badge>
                          <span className={`text-sm font-mono font-bold ${test.impact_pct < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                            {test.impact_pct > 0 ? '+' : ''}{test.impact_pct}%
                          </span>
                        </div>
                      </div>
                      <div className="flex justify-between mt-1.5 text-[8px] opacity-60">
                        <span>P&L Impact: {test.impact_value > 0 ? '+' : ''}${test.impact_value.toLocaleString()}</span>
                        <span>After: ${test.portfolio_after.toLocaleString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right Column: Risk Radar + Return Distribution */}
              <div className="space-y-4 sm:space-y-6">
                {/* Risk Distribution Radar */}
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="risk-radar">
                  <h3 className="text-[10px] font-bold text-zinc-500 mb-4 uppercase flex items-center gap-2 tracking-widest">
                    <PieChart size={14} className="text-purple-500" /> Risk Decomposition
                  </h3>
                  <div className="h-56 sm:h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={radarData}>
                        <PolarGrid stroke="#27272a" />
                        <PolarAngleAxis dataKey="subject" tick={{ fill: '#71717a', fontSize: 9 }} />
                        <PolarRadiusAxis tick={{ fill: '#52525b', fontSize: 8 }} domain={[0, 50]} />
                        <Radar name="Risk %" dataKey="value" stroke="#a855f7" fill="#a855f7" fillOpacity={0.2} strokeWidth={2} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {radarData.map((item, i) => (
                      <span key={i} className="text-[8px] px-1.5 py-0.5 bg-zinc-800 rounded-sm text-zinc-400 font-mono">
                        {item.subject}: {item.value}%
                      </span>
                    ))}
                  </div>
                </div>

                {/* Return Distribution Histogram */}
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="return-distribution">
                  <h3 className="text-[10px] font-bold text-zinc-500 mb-2 uppercase flex items-center gap-2 tracking-widest">
                    <BarChart3 size={14} className="text-cyan-500" /> Return Distribution
                  </h3>
                  <div className="flex flex-wrap gap-3 mb-3 text-[9px] text-zinc-500">
                    <span>Mean: <strong className="text-white">{riskData.return_distribution.mean.toFixed(4)}%</strong></span>
                    <span>Std: <strong className="text-white">{riskData.return_distribution.std.toFixed(4)}%</strong></span>
                    <span>Skew: <strong className={riskData.return_distribution.skew < 0 ? 'text-red-400' : 'text-emerald-400'}>{riskData.return_distribution.skew.toFixed(3)}</strong></span>
                    <span>Kurtosis: <strong className="text-amber-400">{riskData.return_distribution.kurtosis.toFixed(3)}</strong></span>
                  </div>
                  <div className="h-44 sm:h-52">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={riskData.return_distribution.histogram}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                        <XAxis dataKey="range" tick={{ fill: '#52525b', fontSize: 8 }} interval="preserveStartEnd" />
                        <YAxis tick={{ fill: '#52525b', fontSize: 9 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '10px' }}
                          labelFormatter={(v) => `Return: ${v}%`}
                          formatter={(v) => [v, 'Count']}
                        />
                        <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                          {riskData.return_distribution.histogram.map((entry, idx) => (
                            <Cell key={idx} fill={parseFloat(entry.range) < 0 ? '#ef4444' : '#06b6d4'} fillOpacity={0.7} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </div>

            {/* Concentration Analysis */}
            {riskData.concentration && riskData.concentration.positions?.length > 0 && (
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="concentration">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase flex items-center gap-2 tracking-widest">
                  <Target size={14} className="text-amber-500" /> Position Concentration
                </h3>
                <div className="flex flex-wrap gap-4 mb-3 text-[9px] text-zinc-500">
                  <span>HHI: <strong className="text-white">{riskData.concentration.hhi}</strong></span>
                  <span>Largest: <strong className="text-white">{riskData.concentration.largest_position_pct}%</strong></span>
                  <Badge className={`text-[8px] border ${
                    riskData.concentration.rating === 'HIGH' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                    riskData.concentration.rating === 'MODERATE' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                    'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                  }`}>{riskData.concentration.rating} Concentration</Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {riskData.concentration.positions.map((pos, i) => (
                    <div key={i} className="bg-zinc-950/50 border border-zinc-800/50 rounded-sm p-2">
                      <span className="text-[9px] text-zinc-600">{pos.asset}</span>
                      <div className="font-mono font-bold text-sm text-white">{pos.weight}%</div>
                      <span className="text-[8px] text-zinc-600">${pos.market_value.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Risk Alert Settings + History */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
              {/* Alert Configuration */}
              <div className="bg-zinc-900/50 border border-amber-900/30 rounded-sm p-3 sm:p-5" data-testid="risk-alert-config">
                <h3 className="text-[10px] font-bold text-amber-400 mb-4 uppercase flex items-center gap-2 tracking-widest">
                  <BellRing size={14} /> Risk Alert Configuration
                </h3>

                <div className="space-y-4">
                  {/* Master Toggle */}
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-zinc-400">Enable Risk Alerts</Label>
                    <Switch checked={alertEnabled} onCheckedChange={setAlertEnabled} data-testid="alert-enabled-toggle" />
                  </div>

                  {alertEnabled && (
                    <>
                      {/* VaR Threshold */}
                      <div>
                        <div className="flex justify-between text-[10px] mb-1.5">
                          <span className="text-zinc-500">VaR 95% Threshold</span>
                          <span className="text-red-400 font-mono font-bold">${varThreshold.toLocaleString()}</span>
                        </div>
                        <Slider value={[varThreshold]} onValueChange={([v]) => setVarThreshold(v)} min={1000} max={20000} step={500} data-testid="var-threshold-slider" />
                      </div>

                      {/* Volatility Threshold */}
                      <div>
                        <div className="flex justify-between text-[10px] mb-1.5">
                          <span className="text-zinc-500">Annual Volatility Threshold</span>
                          <span className="text-cyan-400 font-mono font-bold">{volThreshold}%</span>
                        </div>
                        <Slider value={[volThreshold]} onValueChange={([v]) => setVolThreshold(v)} min={10} max={80} step={5} data-testid="vol-threshold-slider" />
                      </div>

                      {/* Drawdown Threshold */}
                      <div>
                        <div className="flex justify-between text-[10px] mb-1.5">
                          <span className="text-zinc-500">Max Drawdown Threshold</span>
                          <span className="text-orange-400 font-mono font-bold">{ddThreshold}%</span>
                        </div>
                        <Slider value={[ddThreshold]} onValueChange={([v]) => setDdThreshold(v)} min={5} max={50} step={1} data-testid="dd-threshold-slider" />
                      </div>

                      {/* Sharpe Threshold */}
                      <div>
                        <div className="flex justify-between text-[10px] mb-1.5">
                          <span className="text-zinc-500">Min Sharpe Ratio</span>
                          <span className="text-emerald-400 font-mono font-bold">{sharpeThreshold.toFixed(1)}</span>
                        </div>
                        <Slider value={[sharpeThreshold * 10]} onValueChange={([v]) => setSharpeThreshold(v / 10)} min={0} max={30} step={1} data-testid="sharpe-threshold-slider" />
                      </div>

                      {/* Stress Severity Trigger */}
                      <div>
                        <Label className="text-[10px] text-zinc-500 mb-1.5 block">Stress Test Severity Trigger</Label>
                        <Select value={stressTrigger} onValueChange={setStressTrigger}>
                          <SelectTrigger className="bg-zinc-950 border-zinc-800 text-xs" data-testid="stress-trigger-select">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-zinc-900 border-zinc-800">
                            <SelectItem value="CRITICAL">CRITICAL only</SelectItem>
                            <SelectItem value="HIGH">HIGH and above</SelectItem>
                            <SelectItem value="MODERATE">MODERATE and above</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Push Toggles */}
                      <div className="flex items-center justify-between pt-2 border-t border-zinc-800/50">
                        <Label className="text-[10px] text-zinc-500">Telegram Push</Label>
                        <Switch checked={telegramPush} onCheckedChange={setTelegramPush} data-testid="telegram-push-toggle" />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label className="text-[10px] text-zinc-500">Browser Push</Label>
                        <Switch checked={browserPush} onCheckedChange={setBrowserPush} data-testid="browser-push-toggle" />
                      </div>
                    </>
                  )}

                  <Button onClick={saveConfig} disabled={savingConfig} className="w-full text-[10px] bg-amber-600 hover:bg-amber-500 text-white gap-1.5" data-testid="save-alert-config-btn">
                    <Save size={12} /> {savingConfig ? 'Saving...' : 'Save Alert Settings'}
                  </Button>
                </div>
              </div>

              {/* Alert History */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="alert-history">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-4 uppercase flex items-center gap-2 tracking-widest">
                  <Bell size={14} className="text-red-500" /> Recent Risk Alerts
                </h3>
                <ScrollArea className="h-80 sm:h-96">
                  {alertHistory.length === 0 ? (
                    <div className="text-center py-8 text-zinc-600">
                      <Bell size={28} className="mx-auto mb-2 opacity-30" />
                      <p className="text-[10px]">No risk alerts triggered yet</p>
                      <p className="text-[9px] mt-1 text-zinc-700">Click "Run Risk Check" to test</p>
                    </div>
                  ) : (
                    <div className="space-y-2 pr-2">
                      {alertHistory.map((alert, i) => (
                        <div key={i} className={`p-2.5 rounded-sm border ${SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.MODERATE}`} data-testid={`alert-history-${i}`}>
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge className={`text-[7px] border ${SEVERITY_STYLES[alert.severity]}`}>{alert.severity}</Badge>
                                <span className="text-[9px] font-bold">{alert.alert_type?.replace(/_/g, ' ')}</span>
                              </div>
                              <p className="text-[9px] opacity-80">{alert.message}</p>
                            </div>
                            {alert.acknowledged && <Check size={12} className="text-emerald-500 shrink-0 mt-1" />}
                          </div>
                          <div className="text-[8px] opacity-50 mt-1">
                            {new Date(alert.triggered_at).toLocaleString()}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </div>
            </div>

            {/* Risk Trend Charts */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="risk-trends">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
                <h3 className="text-[10px] font-bold text-zinc-500 uppercase flex items-center gap-2 tracking-widest">
                  <TrendingUp size={14} className="text-blue-500" /> Risk Metric Trends
                </h3>
                <div className="flex gap-2">
                  <Select value={trendMetric} onValueChange={setTrendMetric}>
                    <SelectTrigger className="bg-zinc-950 border-zinc-800 text-[10px] w-32 h-7" data-testid="trend-metric-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      <SelectItem value="var_95">VaR 95%</SelectItem>
                      <SelectItem value="annual_vol">Ann. Volatility</SelectItem>
                      <SelectItem value="sharpe">Sharpe Ratio</SelectItem>
                      <SelectItem value="max_drawdown">Max Drawdown</SelectItem>
                      <SelectItem value="total_value">Portfolio Value</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="flex gap-1">
                    {[7, 30, 90].map(d => (
                      <Button key={d} variant={trendDays === d ? 'default' : 'outline'} size="sm"
                        onClick={() => setTrendDays(d)}
                        className={`text-[9px] h-7 px-2 ${trendDays === d ? 'bg-blue-600' : 'border-zinc-800'}`}
                        data-testid={`trend-days-${d}`}>
                        {d}D
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
              {trendData.length < 2 ? (
                <div className="text-center py-8 text-zinc-600">
                  <TrendingUp size={28} className="mx-auto mb-2 opacity-30" />
                  <p className="text-[10px]">Not enough snapshots yet ({trendData.length}/2 minimum)</p>
                  <p className="text-[9px] mt-1 text-zinc-700">Run "Risk Check" to start building trend data</p>
                </div>
              ) : (
                <div className="h-56 sm:h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="time" tick={{ fill: '#52525b', fontSize: 8 }} interval="preserveStartEnd" />
                      <YAxis tick={{ fill: '#52525b', fontSize: 9 }} />
                      <Tooltip contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '10px' }} />
                      <Line type="monotone" dataKey={trendMetric} stroke={
                        trendMetric === 'var_95' ? '#ef4444' :
                        trendMetric === 'annual_vol' ? '#06b6d4' :
                        trendMetric === 'sharpe' ? '#22c55e' :
                        trendMetric === 'max_drawdown' ? '#f97316' : '#a855f7'
                      } strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* Email Digest Settings */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
              <div className="bg-zinc-900/50 border border-blue-900/30 rounded-sm p-3 sm:p-5" data-testid="email-digest-config">
                <h3 className="text-[10px] font-bold text-blue-400 mb-4 uppercase flex items-center gap-2 tracking-widest">
                  <Mail size={14} /> Email Digest Settings
                </h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-zinc-400">Enable Daily Digest</Label>
                    <Switch checked={digestEnabled} onCheckedChange={setDigestEnabled} data-testid="digest-enabled-toggle" />
                  </div>
                  {digestEnabled && (
                    <>
                      <div>
                        <Label className="text-[10px] text-zinc-500 mb-1 block">Recipient Email</Label>
                        <input type="email" value={digestEmail} onChange={e => setDigestEmail(e.target.value)}
                          placeholder="your@email.com"
                          className="w-full bg-zinc-950 border border-zinc-800 rounded-sm px-3 py-1.5 text-xs text-white placeholder:text-zinc-700 focus:border-blue-600 outline-none"
                          data-testid="digest-email-input" />
                      </div>
                      <div className="space-y-2 pt-2 border-t border-zinc-800/50">
                        <p className="text-[9px] text-zinc-600 uppercase tracking-wider">Include in digest:</p>
                        <div className="flex items-center justify-between">
                          <Label className="text-[10px] text-zinc-500">Risk Summary</Label>
                          <Switch checked={includeRisk} onCheckedChange={setIncludeRisk} data-testid="include-risk-toggle" />
                        </div>
                        <div className="flex items-center justify-between">
                          <Label className="text-[10px] text-zinc-500">Alert History</Label>
                          <Switch checked={includeAlerts} onCheckedChange={setIncludeAlerts} data-testid="include-alerts-toggle" />
                        </div>
                        <div className="flex items-center justify-between">
                          <Label className="text-[10px] text-zinc-500">AI Market Brief</Label>
                          <Switch checked={includeBrief} onCheckedChange={setIncludeBrief} data-testid="include-brief-toggle" />
                        </div>
                        <div className="flex items-center justify-between">
                          <Label className="text-[10px] text-zinc-500">Portfolio Snapshot</Label>
                          <Switch checked={includePortfolio} onCheckedChange={setIncludePortfolio} data-testid="include-portfolio-toggle" />
                        </div>
                      </div>
                    </>
                  )}
                  <div className="flex gap-2 pt-2">
                    <Button onClick={saveEmailPrefs} disabled={savingEmail} className="flex-1 text-[10px] bg-blue-600 hover:bg-blue-500 text-white gap-1.5" data-testid="save-email-prefs-btn">
                      <Save size={12} /> {savingEmail ? 'Saving...' : 'Save Settings'}
                    </Button>
                    <Button onClick={sendDigestNow} disabled={sendingDigest} variant="outline" className="text-[10px] border-blue-800 text-blue-400 hover:bg-blue-900/20 gap-1.5" data-testid="send-digest-btn">
                      <Send size={12} /> {sendingDigest ? 'Sending...' : 'Send Now'}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Digest History */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="digest-history">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-4 uppercase flex items-center gap-2 tracking-widest">
                  <Clock size={14} className="text-blue-500" /> Digest Send History
                </h3>
                {digestHistory.length === 0 ? (
                  <div className="text-center py-8 text-zinc-600">
                    <Mail size={28} className="mx-auto mb-2 opacity-30" />
                    <p className="text-[10px]">No digests sent yet</p>
                    <p className="text-[9px] mt-1 text-zinc-700">Configure email and click "Send Now"</p>
                  </div>
                ) : (
                  <ScrollArea className="h-60">
                    <div className="space-y-2 pr-2">
                      {digestHistory.map((log, i) => (
                        <div key={i} className="p-2 bg-zinc-950/50 border border-zinc-800/50 rounded-sm" data-testid={`digest-log-${i}`}>
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] text-zinc-400 font-mono">{log.email}</span>
                            <Badge className={`text-[7px] ${log.sent ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                              {log.sent ? 'SENT' : 'FAILED'}
                            </Badge>
                          </div>
                          <div className="text-[8px] text-zinc-600 mt-1">{new Date(log.sent_at).toLocaleString()}</div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </div>
            </div>

          </div>
        </ScrollArea>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-zinc-500">No risk data available</p>
        </div>
      )}
    </div>
  );
};

const MetricCard = ({ label, value, sub, color = 'text-white' }) => (
  <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-2.5 sm:p-3">
    <span className="text-[9px] text-zinc-600 uppercase tracking-wide block">{label}</span>
    <div className={`font-mono font-bold text-sm sm:text-base ${color}`}>{value}</div>
    {sub && <span className="text-[8px] text-zinc-600">{sub}</span>}
  </div>
);

export default RiskAnalyticsPage;
