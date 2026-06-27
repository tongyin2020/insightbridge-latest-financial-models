import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Settings, Zap, Target, Shield, Save,
  RefreshCcw, Bell, Send, CheckCircle, XCircle,
  ShieldCheck, ShieldOff, Copy, Eye, EyeOff, BellRing
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Slider } from '../components/ui/slider';
import { Switch } from '../components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/ui/tabs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SettingsPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  // Strategy Config
  const [strategyType, setStrategyType] = useState('AI_HYBRID');
  const [ispreadUpper, setIspreadUpper] = useState(15.0);
  const [ispreadLower, setIspreadLower] = useState(10.0);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.8);
  const [maxPositionSize, setMaxPositionSize] = useState(100);
  const [stopLossPct, setStopLossPct] = useState(0.05);
  const [takeProfitPct, setTakeProfitPct] = useState(0.10);
  const [useAI, setUseAI] = useState(true);
  const [momentumPeriod, setMomentumPeriod] = useState(14);
  const [meanReversionWindow, setMeanReversionWindow] = useState(20);
  
  // Alert Settings
  const [telegramEnabled, setTelegramEnabled] = useState(true);
  const [alertOnSignal, setAlertOnSignal] = useState(true);
  const [alertOnExecution, setAlertOnExecution] = useState(true);
  const [alertOnRisk, setAlertOnRisk] = useState(true);
  const [alertOnSystem, setAlertOnSystem] = useState(true);
  
  // 2FA State
  const [twoFAEnabled, setTwoFAEnabled] = useState(false);
  const [twoFASetupData, setTwoFASetupData] = useState(null);
  const [otpCode, setOtpCode] = useState('');
  const [disableOtpCode, setDisableOtpCode] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [backupCodesRemaining, setBackupCodesRemaining] = useState(0);
  const [loading2FA, setLoading2FA] = useState(false);

  // Push notification state
  const [pushEnabled, setPushEnabled] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [testingTelegram, setTestingTelegram] = useState(false);

  useEffect(() => {
    fetchSettings();
    fetch2FAStatus();
    fetchPushStatus();
  }, []);

  const fetchSettings = async () => {
    try {
      const [strategyRes, alertRes] = await Promise.all([
        axios.get(`${API_URL}/api/strategy/config`, { withCredentials: true }),
        axios.get(`${API_URL}/api/alerts/settings`, { withCredentials: true })
      ]);
      
      const strategy = strategyRes.data;
      setStrategyType(strategy.strategy_type);
      setIspreadUpper(strategy.ispread_upper);
      setIspreadLower(strategy.ispread_lower);
      setConfidenceThreshold(strategy.confidence_threshold);
      setMaxPositionSize(strategy.max_position_size);
      setStopLossPct(strategy.stop_loss_pct);
      setTakeProfitPct(strategy.take_profit_pct);
      setUseAI(strategy.use_ai);
      setMomentumPeriod(strategy.momentum_period);
      setMeanReversionWindow(strategy.mean_reversion_window);
      
      const alerts = alertRes.data;
      setTelegramEnabled(alerts.telegram_enabled);
      setAlertOnSignal(alerts.alert_on_signal);
      setAlertOnExecution(alerts.alert_on_execution);
      setAlertOnRisk(alerts.alert_on_risk);
      setAlertOnSystem(alerts.alert_on_system);
    } catch (error) {
      console.error('Error fetching settings:', error);
    }
  };

  const fetch2FAStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/auth/2fa/status`, { withCredentials: true });
      setTwoFAEnabled(res.data.enabled);
      setBackupCodesRemaining(res.data.backup_codes_remaining);
    } catch (error) {
      console.error('Error fetching 2FA status:', error);
    }
  };

  const fetchPushStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/notifications/status`, { withCredentials: true });
      setPushEnabled(res.data.enabled);
    } catch (error) {
      console.error('Error fetching push status:', error);
    }
  };

  const saveStrategyConfig = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_URL}/api/strategy/config`, {
        strategy_type: strategyType,
        ispread_upper: ispreadUpper,
        ispread_lower: ispreadLower,
        confidence_threshold: confidenceThreshold,
        max_position_size: maxPositionSize,
        stop_loss_pct: stopLossPct,
        take_profit_pct: takeProfitPct,
        use_ai: useAI,
        momentum_period: momentumPeriod,
        mean_reversion_window: meanReversionWindow
      }, { withCredentials: true });
      
      toast.success('Strategy configuration saved');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setLoading(false);
    }
  };

  const saveAlertSettings = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_URL}/api/alerts/settings`, {
        telegram_enabled: telegramEnabled,
        alert_on_signal: alertOnSignal,
        alert_on_execution: alertOnExecution,
        alert_on_risk: alertOnRisk,
        alert_on_system: alertOnSystem
      }, { withCredentials: true });
      
      toast.success('Alert settings saved');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save alert settings');
    } finally {
      setLoading(false);
    }
  };

  const testTelegram = async () => {
    setTestingTelegram(true);
    try {
      await axios.post(`${API_URL}/api/alerts/test-telegram`, {}, { withCredentials: true });
      toast.success('Test notification sent to Telegram');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send test notification');
    } finally {
      setTestingTelegram(false);
    }
  };

  // 2FA Functions
  const setup2FA = async () => {
    setLoading2FA(true);
    try {
      const res = await axios.post(`${API_URL}/api/auth/2fa/setup`, {}, { withCredentials: true });
      setTwoFASetupData(res.data);
      toast.info('Scan the QR code with your authenticator app');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to setup 2FA');
    } finally {
      setLoading2FA(false);
    }
  };

  const confirm2FA = async () => {
    if (!otpCode || otpCode.length < 6) {
      toast.error('Please enter a valid 6-digit code');
      return;
    }
    setLoading2FA(true);
    try {
      await axios.post(`${API_URL}/api/auth/2fa/confirm`, null, { 
        params: { code: otpCode },
        withCredentials: true 
      });
      toast.success('2FA enabled successfully!');
      setTwoFAEnabled(true);
      setTwoFASetupData(null);
      setOtpCode('');
      fetch2FAStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Invalid verification code');
    } finally {
      setLoading2FA(false);
    }
  };

  const disable2FA = async () => {
    if (!disableOtpCode || disableOtpCode.length < 6) {
      toast.error('Please enter your current 2FA code');
      return;
    }
    setLoading2FA(true);
    try {
      await axios.post(`${API_URL}/api/auth/2fa/disable`, null, { 
        params: { code: disableOtpCode },
        withCredentials: true 
      });
      toast.success('2FA disabled');
      setTwoFAEnabled(false);
      setDisableOtpCode('');
      fetch2FAStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Invalid code');
    } finally {
      setLoading2FA(false);
    }
  };

  const copySecret = () => {
    if (twoFASetupData?.secret) {
      navigator.clipboard.writeText(twoFASetupData.secret);
      toast.success('Secret copied to clipboard');
    }
  };

  const togglePushNotifications = async () => {
    try {
      if (pushEnabled) {
        await axios.delete(`${API_URL}/api/notifications/unsubscribe`, { withCredentials: true });
        setPushEnabled(false);
        toast.success('Push notifications disabled');
      } else {
        // Subscribe with a placeholder - in production this would use Web Push API
        await axios.post(`${API_URL}/api/notifications/subscribe`, {
          endpoint: window.location.origin,
          enabled: true
        }, { withCredentials: true });
        setPushEnabled(true);
        toast.success('Push notifications enabled');
      }
    } catch (error) {
      toast.error('Failed to update push notifications');
    }
  };

  const strategyTypes = [
    { value: 'MEAN_REVERSION', label: 'Mean Reversion' },
    { value: 'MOMENTUM', label: 'Momentum' },
    { value: 'SPREAD_ARBITRAGE', label: 'Spread Arbitrage' },
    { value: 'AI_HYBRID', label: 'AI Hybrid' }
  ];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <Toaster position="bottom-right" theme="dark" />
      
      {/* Header */}
      <header className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/dashboard')}
            data-testid="back-btn"
            className="text-zinc-400 hover:text-white"
          >
            <ArrowLeft size={18} className="mr-2" />
            Dashboard
          </Button>
          <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
            Settings
          </h1>
        </div>
      </header>

      <div className="p-4 sm:p-6 max-w-4xl mx-auto">
        <Tabs defaultValue="strategy" className="w-full">
          <TabsList className="bg-zinc-900 border border-zinc-800 mb-6">
            <TabsTrigger value="strategy" className="data-[state=active]:bg-zinc-800">
              <Settings size={14} className="mr-2" />
              Strategy
            </TabsTrigger>
            <TabsTrigger value="alerts" className="data-[state=active]:bg-zinc-800">
              <Bell size={14} className="mr-2" />
              Alerts
            </TabsTrigger>
            <TabsTrigger value="security" className="data-[state=active]:bg-zinc-800" data-testid="security-tab">
              <Shield size={14} className="mr-2" />
              Security
            </TabsTrigger>
          </TabsList>

          {/* Strategy Configuration */}
          <TabsContent value="strategy" className="space-y-6">
            {/* Strategy Type */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Target size={16} className="text-blue-500" />
                Strategy Selection
              </h3>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Strategy Type</Label>
                  <Select value={strategyType} onValueChange={setStrategyType}>
                    <SelectTrigger className="mt-1 bg-zinc-950 border-zinc-800" data-testid="strategy-type-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      {strategyTypes.map(st => (
                        <SelectItem key={st.value} value={st.value}>{st.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="flex items-center justify-between sm:justify-start sm:gap-4 p-4 bg-zinc-950/50 rounded-sm">
                  <div>
                    <Label className="text-xs text-zinc-500 uppercase">AI Analysis</Label>
                    <p className="text-[10px] text-zinc-600 mt-1">Use GPT-5.2 for signal generation</p>
                  </div>
                  <Switch
                    checked={useAI}
                    onCheckedChange={setUseAI}
                    data-testid="use-ai-switch"
                  />
                </div>
              </div>
            </div>

            {/* Threshold Parameters */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Zap size={16} className="text-amber-500" />
                Trading Thresholds
              </h3>
              
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Ispread Upper Threshold</span>
                    <span className="text-white font-mono">{ispreadUpper.toFixed(1)}</span>
                  </div>
                  <Slider
                    value={[ispreadUpper]}
                    onValueChange={([v]) => setIspreadUpper(v)}
                    min={12}
                    max={20}
                    step={0.5}
                    className="cursor-pointer"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">Sell signal when Ispread exceeds this value</p>
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Ispread Lower Threshold</span>
                    <span className="text-white font-mono">{ispreadLower.toFixed(1)}</span>
                  </div>
                  <Slider
                    value={[ispreadLower]}
                    onValueChange={([v]) => setIspreadLower(v)}
                    min={5}
                    max={12}
                    step={0.5}
                    className="cursor-pointer"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">Buy signal when Ispread falls below this value</p>
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">AI Confidence Threshold</span>
                    <span className="text-white font-mono">{(confidenceThreshold * 100).toFixed(0)}%</span>
                  </div>
                  <Slider
                    value={[confidenceThreshold * 100]}
                    onValueChange={([v]) => setConfidenceThreshold(v / 100)}
                    min={50}
                    max={95}
                    step={5}
                    className="cursor-pointer"
                  />
                  <p className="text-[10px] text-zinc-600 mt-1">Minimum AI confidence to generate a signal</p>
                </div>
              </div>
            </div>

            {/* Risk Management */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Shield size={16} className="text-red-500" />
                Risk Management
              </h3>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Stop Loss</span>
                    <span className="text-red-400 font-mono">{(stopLossPct * 100).toFixed(0)}%</span>
                  </div>
                  <Slider
                    value={[stopLossPct * 100]}
                    onValueChange={([v]) => setStopLossPct(v / 100)}
                    min={1}
                    max={20}
                    step={1}
                    className="cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Take Profit</span>
                    <span className="text-emerald-400 font-mono">{(takeProfitPct * 100).toFixed(0)}%</span>
                  </div>
                  <Slider
                    value={[takeProfitPct * 100]}
                    onValueChange={([v]) => setTakeProfitPct(v / 100)}
                    min={1}
                    max={30}
                    step={1}
                    className="cursor-pointer"
                  />
                </div>

                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Max Position Size</Label>
                  <Input
                    type="number"
                    value={maxPositionSize}
                    onChange={(e) => setMaxPositionSize(Number(e.target.value))}
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono"
                    data-testid="max-position-input"
                  />
                </div>

                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Mean Reversion Window</Label>
                  <Input
                    type="number"
                    value={meanReversionWindow}
                    onChange={(e) => setMeanReversionWindow(Number(e.target.value))}
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono"
                  />
                </div>
              </div>
            </div>

            <Button
              onClick={saveStrategyConfig}
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold"
              data-testid="save-strategy-btn"
            >
              {loading ? <RefreshCcw size={14} className="mr-2 animate-spin" /> : <Save size={14} className="mr-2" />}
              Save Strategy Configuration
            </Button>
          </TabsContent>

          {/* Alert Settings */}
          <TabsContent value="alerts" className="space-y-6">
            {/* Telegram Settings */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Send size={16} className="text-blue-500" />
                Telegram Notifications
              </h3>
              
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-zinc-950/50 rounded-sm">
                  <div>
                    <Label className="text-sm text-white">Enable Telegram</Label>
                    <p className="text-[10px] text-zinc-600 mt-1">Receive trading alerts via Telegram</p>
                  </div>
                  <Switch
                    checked={telegramEnabled}
                    onCheckedChange={setTelegramEnabled}
                    data-testid="telegram-switch"
                  />
                </div>

                <Button
                  onClick={testTelegram}
                  disabled={testingTelegram || !telegramEnabled}
                  variant="outline"
                  className="w-full border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  data-testid="test-telegram-btn"
                >
                  {testingTelegram ? (
                    <RefreshCcw size={14} className="mr-2 animate-spin" />
                  ) : (
                    <Send size={14} className="mr-2" />
                  )}
                  Send Test Notification
                </Button>
              </div>
            </div>

            {/* Push Notifications */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <BellRing size={16} className="text-purple-500" />
                Browser Push Notifications
              </h3>
              <div className="flex items-center justify-between p-4 bg-zinc-950/50 rounded-sm">
                <div>
                  <Label className="text-sm text-white">Enable Push Notifications</Label>
                  <p className="text-[10px] text-zinc-600 mt-1">Receive real-time alerts in your browser</p>
                </div>
                <Switch
                  checked={pushEnabled}
                  onCheckedChange={togglePushNotifications}
                  data-testid="push-switch"
                />
              </div>
            </div>

            {/* Alert Types */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Bell size={16} className="text-amber-500" />
                Alert Types
              </h3>
              
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <div className="flex items-center gap-3">
                    <Zap size={16} className="text-blue-500" />
                    <div>
                      <Label className="text-sm text-white">Signal Alerts</Label>
                      <p className="text-[10px] text-zinc-600">New trading signals generated</p>
                    </div>
                  </div>
                  <Switch checked={alertOnSignal} onCheckedChange={setAlertOnSignal} />
                </div>

                <div className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <div className="flex items-center gap-3">
                    <CheckCircle size={16} className="text-emerald-500" />
                    <div>
                      <Label className="text-sm text-white">Execution Alerts</Label>
                      <p className="text-[10px] text-zinc-600">Trade executions</p>
                    </div>
                  </div>
                  <Switch checked={alertOnExecution} onCheckedChange={setAlertOnExecution} />
                </div>

                <div className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <div className="flex items-center gap-3">
                    <Shield size={16} className="text-red-500" />
                    <div>
                      <Label className="text-sm text-white">Risk Alerts</Label>
                      <p className="text-[10px] text-zinc-600">Black swan events, high volatility</p>
                    </div>
                  </div>
                  <Switch checked={alertOnRisk} onCheckedChange={setAlertOnRisk} />
                </div>

                <div className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <div className="flex items-center gap-3">
                    <XCircle size={16} className="text-orange-500" />
                    <div>
                      <Label className="text-sm text-white">System Alerts</Label>
                      <p className="text-[10px] text-zinc-600">Kill switch, lifecycle changes</p>
                    </div>
                  </div>
                  <Switch checked={alertOnSystem} onCheckedChange={setAlertOnSystem} />
                </div>
              </div>
            </div>

            <Button
              onClick={saveAlertSettings}
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold"
              data-testid="save-alerts-btn"
            >
              {loading ? <RefreshCcw size={14} className="mr-2 animate-spin" /> : <Save size={14} className="mr-2" />}
              Save Alert Settings
            </Button>
          </TabsContent>

          {/* Security Tab - 2FA */}
          <TabsContent value="security" className="space-y-6">
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <ShieldCheck size={16} className="text-blue-500" />
                Two-Factor Authentication (2FA)
              </h3>

              {/* Status Banner */}
              <div className={`p-4 rounded-sm mb-6 flex items-center gap-3 ${
                twoFAEnabled 
                  ? 'bg-emerald-500/10 border border-emerald-500/30' 
                  : 'bg-amber-500/10 border border-amber-500/30'
              }`}>
                {twoFAEnabled ? (
                  <ShieldCheck size={20} className="text-emerald-400" />
                ) : (
                  <ShieldOff size={20} className="text-amber-400" />
                )}
                <div>
                  <p className={`text-sm font-semibold ${twoFAEnabled ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {twoFAEnabled ? '2FA is Active' : '2FA is Not Enabled'}
                  </p>
                  <p className="text-[10px] text-zinc-500">
                    {twoFAEnabled 
                      ? `Your account is secured with two-factor authentication. ${backupCodesRemaining} backup codes remaining.`
                      : 'Add an extra layer of security to your trading account.'}
                  </p>
                </div>
              </div>

              {!twoFAEnabled && !twoFASetupData && (
                <Button
                  onClick={setup2FA}
                  disabled={loading2FA}
                  data-testid="setup-2fa-btn"
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                >
                  {loading2FA ? (
                    <RefreshCcw size={14} className="mr-2 animate-spin" />
                  ) : (
                    <ShieldCheck size={14} className="mr-2" />
                  )}
                  Enable Two-Factor Authentication
                </Button>
              )}

              {/* 2FA Setup Flow */}
              {twoFASetupData && (
                <div className="space-y-4">
                  <div className="text-xs text-zinc-400 space-y-2">
                    <p className="font-semibold text-white">Step 1: Scan QR Code</p>
                    <p>Open your authenticator app (Google Authenticator, Authy, etc.) and scan this QR code:</p>
                  </div>

                  {/* QR Code */}
                  <div className="flex justify-center p-4 bg-white rounded-sm" data-testid="2fa-qr-code">
                    <img 
                      src={twoFASetupData.qr_code} 
                      alt="2FA QR Code" 
                      className="w-48 h-48"
                    />
                  </div>

                  {/* Manual Secret */}
                  <div className="space-y-1">
                    <p className="text-xs text-zinc-400">
                      <span className="font-semibold text-white">Step 2:</span> Or enter this secret manually:
                    </p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-zinc-950 border border-zinc-800 rounded-sm p-3 font-mono text-sm text-center">
                        {showSecret ? twoFASetupData.secret : '••••••••••••••••'}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowSecret(!showSecret)}
                        className="border-zinc-700"
                      >
                        {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={copySecret}
                        className="border-zinc-700"
                        data-testid="copy-secret-btn"
                      >
                        <Copy size={14} />
                      </Button>
                    </div>
                  </div>

                  {/* Backup Codes */}
                  <div className="space-y-2">
                    <p className="text-xs text-zinc-400">
                      <span className="font-semibold text-white">Backup Codes</span> - Save these in a safe place:
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="backup-codes">
                      {twoFASetupData.backup_codes?.map((code, i) => (
                        <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-sm p-2 text-center font-mono text-xs text-zinc-300">
                          {code}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Verification */}
                  <div className="space-y-2 pt-2 border-t border-zinc-800">
                    <p className="text-xs text-zinc-400">
                      <span className="font-semibold text-white">Step 3:</span> Enter the 6-digit code from your authenticator to verify:
                    </p>
                    <div className="flex gap-2">
                      <Input
                        type="text"
                        placeholder="000000"
                        value={otpCode}
                        onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                        data-testid="confirm-2fa-code"
                        className="bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-lg tracking-[0.3em] text-center"
                        maxLength={6}
                      />
                      <Button
                        onClick={confirm2FA}
                        disabled={loading2FA || otpCode.length < 6}
                        data-testid="confirm-2fa-btn"
                        className="bg-emerald-600 hover:bg-emerald-500 text-white px-6"
                      >
                        {loading2FA ? <RefreshCcw size={14} className="animate-spin" /> : 'Verify'}
                      </Button>
                    </div>
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setTwoFASetupData(null); setOtpCode(''); }}
                    className="text-zinc-500 hover:text-zinc-300"
                  >
                    Cancel Setup
                  </Button>
                </div>
              )}

              {/* Disable 2FA */}
              {twoFAEnabled && (
                <div className="space-y-3 pt-4 border-t border-zinc-800">
                  <p className="text-xs text-zinc-400">Enter your current 2FA code to disable:</p>
                  <div className="flex gap-2">
                    <Input
                      type="text"
                      placeholder="000000"
                      value={disableOtpCode}
                      onChange={(e) => setDisableOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      data-testid="disable-2fa-code"
                      className="bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-lg tracking-[0.3em] text-center"
                      maxLength={6}
                    />
                    <Button
                      onClick={disable2FA}
                      disabled={loading2FA || disableOtpCode.length < 6}
                      data-testid="disable-2fa-btn"
                      className="bg-red-600 hover:bg-red-500 text-white px-6"
                    >
                      {loading2FA ? <RefreshCcw size={14} className="animate-spin" /> : 'Disable 2FA'}
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Account Info */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                <Settings size={16} className="text-zinc-400" />
                Account Information
              </h3>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <span className="text-zinc-500">Email</span>
                  <span className="text-zinc-300 font-mono">{user?.email}</span>
                </div>
                <div className="flex justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <span className="text-zinc-500">Name</span>
                  <span className="text-zinc-300">{user?.name}</span>
                </div>
                <div className="flex justify-between p-3 bg-zinc-950/50 rounded-sm">
                  <span className="text-zinc-500">Role</span>
                  <span className="text-zinc-300 uppercase">{user?.role}</span>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default SettingsPage;
