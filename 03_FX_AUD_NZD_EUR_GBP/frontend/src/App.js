import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, BarChart, Bar, Cell
} from 'recharts';
import {
  TrendUp, TrendDown, Lightning, Clock,
  ChartLine, Gear, CaretUp, CaretDown, Circle,
  ArrowsClockwise, Power, Database, WifiHigh, WifiSlash,
  CalendarBlank, ListBullets, ChartBar, Gauge, ShieldCheck,
  Brain, Crosshair, Pulse, Warning, Shield, Heart, FirstAid,
  Prohibit, Play, SkipForward, ArrowCounterClockwise,
  PaperPlaneTilt, Bell, CheckCircle, XCircle
} from '@phosphor-icons/react';
import { format } from 'date-fns';
import './App.css';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

// ─── Auth Helper ──────────────────────────────────────────────────────────────

const authApi = {
  login: async (email, password) => {
    const response = await fetch(`${API_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const detail = data.detail;
      if (typeof detail === 'string') throw new Error(detail);
      if (Array.isArray(detail)) throw new Error(detail.map(e => e.msg || JSON.stringify(e)).join(' '));
      throw new Error('登录失败，请检查邮箱和密码');
    }
    return response.json();
  },
  me: () => fetch(`${API_URL}/api/auth/me`, { credentials: 'include' }).then(r => {
    if (!r.ok) throw new Error('Not authenticated');
    return r.json();
  }),
  meWithToken: (token) => fetch(`${API_URL}/api/auth/me`, {
    headers: { 'Authorization': `Bearer ${token}` },
    credentials: 'include',
  }).then(r => {
    if (!r.ok) throw new Error('Not authenticated');
    return r.json();
  }),
  logout: () => fetch(`${API_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' }),
};

// ─── API Functions ────────────────────────────────────────────────────────────

const api = {
  health: () => fetch(`${API_URL}/api/health`).then(r => r.json()),
  prices: (pair) => fetch(`${API_URL}/api/prices/${pair.replace('/', '_')}`).then(r => r.json()),
  priceHistory: (pair) => fetch(`${API_URL}/api/prices/${pair.replace('/', '_')}/history?limit=100`).then(r => r.json()),
  signals: () => fetch(`${API_URL}/api/signals/current`).then(r => r.json()),
  events: () => fetch(`${API_URL}/api/events`).then(r => r.json()),
  eventState: () => fetch(`${API_URL}/api/events/state`).then(r => r.json()),
  triggerEvent: (level, title) => fetch(`${API_URL}/api/event/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level, title })
  }).then(r => r.json()),
  resetEvent: () => fetch(`${API_URL}/api/event/reset`, { method: 'POST' }).then(r => r.json()),
  settings: () => fetch(`${API_URL}/api/settings`).then(r => r.json()),
  updateSetting: (key, value) => fetch(`${API_URL}/api/settings/${key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value })
  }).then(r => r.json()),
  trades: () => fetch(`${API_URL}/api/trades/stats`).then(r => r.json()),
  brokerStatus: () => fetch(`${API_URL}/api/broker/status`).then(r => r.json()),
  dataSources: () => fetch(`${API_URL}/api/broker/datasources`).then(r => r.json()),
  drivers: () => fetch(`${API_URL}/api/model/drivers`).then(r => r.json()),
  aiAnalyze: (pair) => fetch(`${API_URL}/api/ai/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pair })
  }).then(r => r.json()),
  aiHistory: () => fetch(`${API_URL}/api/ai/history`).then(r => r.json()),
  backtestStats: () => fetch(`${API_URL}/api/backtest/stats`).then(r => r.json()),
  backtestResults: (pair) => fetch(`${API_URL}/api/backtest/results${pair ? `?pair=${pair.replace('/', '_')}` : ''}`).then(r => r.json()),
  backtestChartData: (pair) => fetch(`${API_URL}/api/backtest/chart-data${pair ? `?pair=${pair.replace('/', '_')}` : ''}`).then(r => r.json()),
  monteCarloSim: (numSim = 1000, tradesPerSim = 100) => fetch(`${API_URL}/api/backtest/monte-carlo?num_simulations=${numSim}&trades_per_sim=${tradesPerSim}`).then(r => r.json()),
  gridSearch: () => fetch(`${API_URL}/api/backtest/grid-search/quick`).then(r => r.json()),
  // Risk Control APIs
  riskStatus: () => fetch(`${API_URL}/api/risk/status`).then(r => r.json()),
  riskCapitalProtection: () => fetch(`${API_URL}/api/risk/capital-protection`).then(r => r.json()),
  riskConfig: () => fetch(`${API_URL}/api/risk/config`).then(r => r.json()),
  riskEvents: () => fetch(`${API_URL}/api/risk/events`).then(r => r.json()),
  triggerEmergency: (reason) => fetch(`${API_URL}/api/risk/trigger-emergency?reason=${encodeURIComponent(reason)}`, { method: 'POST' }).then(r => r.json()),
  triggerWarning: (reason) => fetch(`${API_URL}/api/risk/trigger-warning?reason=${encodeURIComponent(reason)}`, { method: 'POST' }).then(r => r.json()),
  endCooldown: () => fetch(`${API_URL}/api/risk/end-cooldown`, { method: 'POST' }).then(r => r.json()),
  advanceRestart: () => fetch(`${API_URL}/api/risk/advance-restart`, { method: 'POST' }).then(r => r.json()),
  resetRisk: () => fetch(`${API_URL}/api/risk/reset`, { method: 'POST' }).then(r => r.json()),
  updateStopLossLevels: (levels) => fetch(`${API_URL}/api/risk/stop-loss-levels`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(levels)
  }).then(r => r.json()),
  updateDailyLimits: (limits) => fetch(`${API_URL}/api/risk/daily-limits`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(limits)
  }).then(r => r.json()),
  // Telegram APIs
  telegramStatus: () => fetch(`${API_URL}/api/telegram/status`).then(r => r.json()),
  telegramTest: (message) => fetch(`${API_URL}/api/telegram/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  }).then(r => r.json()),
  telegramHistory: () => fetch(`${API_URL}/api/telegram/history`).then(r => r.json()),
  sendDailySummary: () => fetch(`${API_URL}/api/telegram/send-daily-summary`, { method: 'POST' }).then(r => r.json()),
  telegramConfig: (botToken, chatId) => fetch(`${API_URL}/api/telegram/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bot_token: botToken, chat_id: chatId })
  }).then(r => r.json()),
  // Event Response Engine
  eventResponseStatus: () => fetch(`${API_URL}/api/event-response/status`).then(r => r.json()),
  eventResponseTrigger: (level, title) => fetch(`${API_URL}/api/event-response/trigger?event_level=${level}&title=${encodeURIComponent(title)}`, { method: 'POST' }).then(r => r.json()),
  eventResponseReset: () => fetch(`${API_URL}/api/event-response/reset`, { method: 'POST' }).then(r => r.json()),
  // Execution Gate
  executionGateStatus: () => fetch(`${API_URL}/api/execution-gate/status`).then(r => r.json()),
  executionGateEvaluate: (pair) => fetch(`${API_URL}/api/execution-gate/evaluate?pair=${encodeURIComponent(pair)}`, { method: 'POST' }).then(r => r.json()),
  // Strategy Monitor
  strategyHealth: () => fetch(`${API_URL}/api/strategy-monitor/health`).then(r => r.json()),
  strategyRecordTrade: (pair, pnl) => fetch(`${API_URL}/api/strategy-monitor/record-trade?pair=${encodeURIComponent(pair)}&pnl_pips=${pnl}`, { method: 'POST' }).then(r => r.json()),
  strategyUnfreeze: (pair) => fetch(`${API_URL}/api/strategy-monitor/unfreeze?pair=${encodeURIComponent(pair)}`, { method: 'POST' }).then(r => r.json()),
  // Features
  features: (pair) => fetch(`${API_URL}/api/features/${pair.replace('/', '_')}`).then(r => r.json()),
};

// ─── Components ───────────────────────────────────────────────────────────────

function Panel({ title, icon: Icon, children, className = '' }) {
  return (
    <div className={`panel h-full flex flex-col ${className}`} data-testid={`panel-${title?.toLowerCase().replace(/\s+/g, '-')}`}>
      {title && (
        <div className="panel-header flex items-center gap-2">
          {Icon && <Icon size={14} weight="bold" />}
          <span>{title}</span>
        </div>
      )}
      <div className="flex-1 p-3 overflow-auto">
        {children}
      </div>
    </div>
  );
}

function PriceDisplay({ pair, price, indicators, prevPrice }) {
  const isUp = price?.mid > (prevPrice || price?.mid);
  const isDown = price?.mid < (prevPrice || price?.mid);

  return (
    <div className="space-y-3" data-testid={`price-display-${pair.replace('/', '-')}`}>
      <div className="flex items-center justify-between">
        <span className="font-heading text-lg font-bold uppercase tracking-tight">{pair}</span>
        <span className={`badge ${indicators?.regime === 'TREND' ? 'badge-trend' : 'badge-range'}`}>
          {indicators?.regime || 'RANGE'}
        </span>
      </div>
      
      <div className="flex items-baseline gap-2">
        <span className={`text-4xl font-medium tabular-nums ${isUp ? 'text-green-500' : isDown ? 'text-red-500' : ''}`}>
          {price?.mid?.toFixed(5) || '---'}
        </span>
        <span className="text-xs text-zinc-500">
          Spread: {price?.spread_pips?.toFixed(1) || '-'} pips
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-zinc-500">Bid</span>
          <span className="tabular-nums text-red-400">{price?.bid?.toFixed(5) || '-'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Ask</span>
          <span className="tabular-nums text-green-400">{price?.ask?.toFixed(5) || '-'}</span>
        </div>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-2">
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <div className="text-zinc-500">SMA20</div>
            <div className="tabular-nums">{indicators?.sma20?.toFixed(5) || '-'}</div>
          </div>
          <div>
            <div className="text-zinc-500">SMA50</div>
            <div className="tabular-nums">{indicators?.sma50?.toFixed(5) || '-'}</div>
          </div>
          <div>
            <div className="text-zinc-500">ADX</div>
            <div className="tabular-nums">{indicators?.adx?.toFixed(1) || '-'}</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <div className="text-zinc-500">RSI</div>
            <div className={`tabular-nums ${
              indicators?.rsi > 70 ? 'text-red-400' : 
              indicators?.rsi < 30 ? 'text-green-400' : ''
            }`}>{indicators?.rsi?.toFixed(1) || '-'}</div>
          </div>
          <div>
            <div className="text-zinc-500">ATR</div>
            <div className="tabular-nums">{indicators?.atr?.toFixed(5) || '-'}</div>
          </div>
          <div>
            <div className="text-zinc-500">BB Width</div>
            <div className="tabular-nums">
              {indicators?.bb_upper && indicators?.bb_lower 
                ? ((indicators.bb_upper - indicators.bb_lower) * 10000).toFixed(1) 
                : '-'} pips
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SignalCard({ signal }) {
  const getIcon = (direction) => {
    switch (direction) {
      case 'BUY': return <TrendUp size={20} weight="bold" className="text-green-500" />;
      case 'SELL': return <TrendDown size={20} weight="bold" className="text-red-500" />;
      default: return <Circle size={20} weight="bold" className="text-zinc-500" />;
    }
  };

  const getBadgeClass = (direction) => {
    switch (direction) {
      case 'BUY': return 'badge-buy';
      case 'SELL': return 'badge-sell';
      default: return 'badge-wait';
    }
  };

  return (
    <div className="border border-white/10 rounded-sm p-3 space-y-2" data-testid={`signal-card-${signal?.pair?.replace('/', '-')}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getIcon(signal?.direction)}
          <span className="font-heading text-sm font-bold uppercase">{signal?.pair}</span>
        </div>
        <span className={`badge ${getBadgeClass(signal?.direction)}`}>
          {signal?.direction || 'WAIT'}
        </span>
      </div>
      
      {signal?.direction !== 'WAIT' && (
        <>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div 
                className={`h-full ${signal?.direction === 'BUY' ? 'bg-green-500' : 'bg-red-500'}`}
                style={{ width: `${signal?.confidence || 0}%` }}
              />
            </div>
            <span className="text-xs tabular-nums">{signal?.confidence?.toFixed(0)}%</span>
          </div>
          <p className="text-xs text-zinc-500 line-clamp-2">{signal?.reason}</p>
        </>
      )}
    </div>
  );
}

function EventStatePanel({ eventState, onTrigger, onReset }) {
  const [triggerLevel, setTriggerLevel] = useState('A');
  const state = eventState?.state || 'NORMAL';
  const remaining = eventState?.remaining_seconds || 0;

  const getStateColor = () => {
    switch (state) {
      case 'COOLDOWN': return 'text-red-500';
      case 'CONFIRMING': return 'text-yellow-500';
      case 'POST_EVENT': return 'text-green-500';
      default: return 'text-zinc-400';
    }
  };

  const getProgressColor = () => {
    if (remaining <= 5) return 'bg-red-500';
    if (remaining <= 10) return 'bg-yellow-500';
    return 'bg-blue-500';
  };

  return (
    <div className="space-y-4" data-testid="event-state-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Lightning size={16} weight="bold" className={getStateColor()} />
          <span className={`font-heading text-sm font-bold uppercase ${getStateColor()}`}>
            {state}
          </span>
        </div>
        {eventState?.event_level && (
          <span className="badge badge-event">Level {eventState.event_level}</span>
        )}
      </div>

      {eventState?.event_title && (
        <div className="text-xs text-zinc-400">
          {eventState.event_title}
        </div>
      )}

      {(state === 'COOLDOWN' || state === 'CONFIRMING') && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-500">
              {state === 'COOLDOWN' ? '冷却倒计时' : '30秒确认窗口'}
            </span>
            <span className="tabular-nums font-bold">{remaining.toFixed(0)}s</span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div 
              className={`h-full progress-bar ${getProgressColor()}`}
              style={{ width: `${(remaining / 30) * 100}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <select 
          value={triggerLevel} 
          onChange={(e) => setTriggerLevel(e.target.value)}
          className="flex-1"
          data-testid="event-level-select"
        >
          <option value="A">A级 (30s)</option>
          <option value="B">B级 (20s)</option>
        </select>
        <button 
          className="btn btn-primary"
          onClick={() => onTrigger(triggerLevel, 'Manual Trigger')}
          disabled={state !== 'NORMAL'}
          data-testid="trigger-event-btn"
        >
          触发
        </button>
        <button 
          className="btn"
          onClick={onReset}
          disabled={state === 'NORMAL'}
          data-testid="reset-event-btn"
        >
          重置
        </button>
      </div>

      {eventState?.confirmed_direction && Object.keys(eventState.confirmed_direction).length > 0 && (
        <div className="border-t border-white/10 pt-2">
          <div className="text-xs text-zinc-500 mb-1">确认方向</div>
          {Object.entries(eventState.confirmed_direction).map(([pair, dir]) => (
            <div key={pair} className="flex items-center justify-between text-xs">
              <span>{pair}</span>
              <span className={dir === 'BUY' ? 'text-green-500' : dir === 'SELL' ? 'text-red-500' : ''}>
                {dir}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PriceChart({ data, pair }) {
  const chartData = data?.map((d, i) => ({
    time: i,
    price: d.close,
    sma20: d.sma20,
  })) || [];

  return (
    <div className="h-48" data-testid={`price-chart-${pair.replace('/', '-')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#007AFF" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#007AFF" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <XAxis 
            dataKey="time" 
            tick={{ fontSize: 10, fill: '#71717A' }}
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
          />
          <YAxis 
            domain={['dataMin - 0.0005', 'dataMax + 0.0005']}
            tick={{ fontSize: 10, fill: '#71717A' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => v.toFixed(4)}
            width={60}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: '#141414', 
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '2px',
              fontSize: '11px'
            }}
            labelStyle={{ color: '#71717A' }}
            formatter={(value) => [value?.toFixed(5), 'Price']}
          />
          <Area 
            type="monotone" 
            dataKey="price" 
            stroke="#007AFF" 
            strokeWidth={1.5}
            fill="url(#priceGradient)" 
          />
          <Line 
            type="monotone" 
            dataKey="sma20" 
            stroke="#F59E0B" 
            strokeWidth={1}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function DriverWeights({ drivers, pair }) {
  const data = drivers?.[pair] || [];
  const colors = ['#007AFF', '#34C759', '#F59E0B', '#FF3B30', '#AF52DE'];

  return (
    <div className="space-y-2" data-testid={`driver-weights-${pair.replace('/', '-')}`}>
      <div className="font-heading text-xs font-bold uppercase text-zinc-400">{pair} 驱动因素</div>
      {data.map((d, i) => (
        <div key={d.factor} className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-400">{d.factor}</span>
            <span className="tabular-nums">{d.weight}%</span>
          </div>
          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div 
              className="h-full rounded-full"
              style={{ width: `${d.weight}%`, backgroundColor: colors[i % colors.length] }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function AdvancedRiskControlPanel({ riskStatus, capitalProtection, onTriggerEmergency, onEndCooldown, onAdvanceRestart, onReset, isLoading }) {
  const status = riskStatus?.status || 'NORMAL';
  const riskLevel = riskStatus?.risk_level || {};
  const dailyStats = riskStatus?.daily_stats || {};
  const stopLossLevels = riskStatus?.stop_loss_levels || {};
  const dailyLimits = riskStatus?.daily_limits || {};
  const safetyScore = capitalProtection?.capital_safety_score || {};
  const alerts = riskStatus?.recent_alerts || [];

  const getStatusColor = (s) => {
    switch (s) {
      case 'NORMAL': return 'text-green-500';
      case 'WARNING': return 'text-yellow-500';
      case 'REDUCING': return 'text-orange-500';
      case 'EMERGENCY': return 'text-red-500';
      case 'COOLDOWN': return 'text-blue-500';
      case 'GRADUATED_RESTART': return 'text-cyan-500';
      default: return 'text-zinc-500';
    }
  };

  const getStatusIcon = (s) => {
    switch (s) {
      case 'NORMAL': return <Shield size={18} weight="fill" className="text-green-500" />;
      case 'WARNING': return <Warning size={18} weight="fill" className="text-yellow-500" />;
      case 'REDUCING': return <CaretDown size={18} weight="bold" className="text-orange-500" />;
      case 'EMERGENCY': return <Prohibit size={18} weight="fill" className="text-red-500" />;
      case 'COOLDOWN': return <Clock size={18} weight="fill" className="text-blue-500" />;
      case 'GRADUATED_RESTART': return <Play size={18} weight="fill" className="text-cyan-500" />;
      default: return <Circle size={18} />;
    }
  };

  const statusLabels = {
    'NORMAL': '正常交易',
    'WARNING': '预警状态',
    'REDUCING': '减仓中',
    'EMERGENCY': '紧急平仓',
    'COOLDOWN': '冷却期',
    'GRADUATED_RESTART': '渐进重启',
  };

  return (
    <div className="space-y-4" data-testid="advanced-risk-control-panel">
      {/* Status & Safety Score */}
      <div className="grid grid-cols-2 gap-3">
        {/* Current Status */}
        <div className="p-3 bg-zinc-900/50 rounded-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500 uppercase">系统状态</span>
            {getStatusIcon(status)}
          </div>
          <div className={`text-lg font-bold ${getStatusColor(status)}`}>
            {statusLabels[status] || status}
          </div>
          {riskStatus?.remaining_cooldown_seconds > 0 && (
            <div className="text-xs text-zinc-400">
              剩余: {Math.floor(riskStatus.remaining_cooldown_seconds / 60)}分{Math.round(riskStatus.remaining_cooldown_seconds % 60)}秒
            </div>
          )}
          {status === 'GRADUATED_RESTART' && (
            <div className="text-xs text-cyan-400">
              杠杆比例: {riskStatus?.current_leverage_ratio}% | 第{riskStatus?.graduated_step + 1}步
            </div>
          )}
        </div>

        {/* Capital Safety Score */}
        <div className="p-3 bg-zinc-900/50 rounded-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500 uppercase">资金安全评分</span>
            <Heart size={18} weight="fill" style={{ color: safetyScore.color }} />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums" style={{ color: safetyScore.color }}>
              {safetyScore.score || 100}
            </span>
            <span className="text-sm" style={{ color: safetyScore.color }}>{safetyScore.level}</span>
          </div>
          {safetyScore.factors?.length > 0 && (
            <div className="text-xs text-zinc-500">{safetyScore.factors.join(', ')}</div>
          )}
        </div>
      </div>

      {/* Risk Level Gauge */}
      <div className="p-3 bg-zinc-900/50 rounded-sm">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-zinc-500 uppercase">风险等级</span>
          <span className="text-sm font-bold" style={{ color: riskLevel.color }}>
            {riskLevel.level} ({riskLevel.score || 0})
          </span>
        </div>
        <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div 
            className="h-full transition-all duration-500"
            style={{ 
              width: `${riskLevel.score || 0}%`,
              backgroundColor: riskLevel.color || '#007AFF'
            }}
          />
        </div>
        {riskLevel.factors?.length > 0 && (
          <div className="mt-2 text-xs text-zinc-500">
            {riskLevel.factors.map((f, i) => (
              <span key={i} className="mr-2">• {f}</span>
            ))}
          </div>
        )}
      </div>

      {/* Multi-Level Stop Loss Display */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">多层级止损防御</div>
        <div className="grid grid-cols-4 gap-2">
          <div className="p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-sm text-center">
            <div className="text-xs text-yellow-500">警告点</div>
            <div className="text-lg font-bold text-yellow-400">{stopLossLevels.warning_pips || 8}</div>
            <div className="text-xs text-zinc-500">pips</div>
          </div>
          <div className="p-2 bg-orange-500/10 border border-orange-500/30 rounded-sm text-center">
            <div className="text-xs text-orange-500">减仓点</div>
            <div className="text-lg font-bold text-orange-400">{stopLossLevels.reduction_pips || 12}</div>
            <div className="text-xs text-zinc-500">pips</div>
          </div>
          <div className="p-2 bg-red-500/10 border border-red-500/30 rounded-sm text-center">
            <div className="text-xs text-red-500">主止损</div>
            <div className="text-lg font-bold text-red-400">{stopLossLevels.primary_stop_pips || 15}</div>
            <div className="text-xs text-zinc-500">pips</div>
          </div>
          <div className="p-2 bg-red-700/20 border border-red-700/40 rounded-sm text-center">
            <div className="text-xs text-red-700">灾难保护</div>
            <div className="text-lg font-bold text-red-600">{stopLossLevels.disaster_stop_pips || 25}</div>
            <div className="text-xs text-zinc-500">pips</div>
          </div>
        </div>
      </div>

      {/* Daily Stats */}
      <div className="grid grid-cols-4 gap-2">
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-lg font-bold tabular-nums ${
            (capitalProtection?.daily_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'
          }`}>
            {capitalProtection?.daily_pnl >= 0 ? '+' : ''}{capitalProtection?.daily_pnl || 0}
          </div>
          <div className="text-xs text-zinc-500">日盈亏(pips)</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-lg font-bold tabular-nums ${
            (capitalProtection?.daily_loss_used_percent || 0) > 70 ? 'text-red-500' : 
            (capitalProtection?.daily_loss_used_percent || 0) > 40 ? 'text-yellow-500' : 'text-green-500'
          }`}>
            {capitalProtection?.daily_loss_used_percent || 0}%
          </div>
          <div className="text-xs text-zinc-500">限额已用</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className="text-lg font-bold tabular-nums">
            {capitalProtection?.daily_trades_used || '0/10'}
          </div>
          <div className="text-xs text-zinc-500">交易次数</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-lg font-bold tabular-nums ${
            (capitalProtection?.consecutive_losses || 0) >= 2 ? 'text-red-500' : ''
          }`}>
            {capitalProtection?.consecutive_losses || 0}/{capitalProtection?.max_consecutive_allowed || 3}
          </div>
          <div className="text-xs text-zinc-500">连续亏损</div>
        </div>
      </div>

      {/* Control Buttons */}
      <div className="flex gap-2 flex-wrap">
        {status === 'NORMAL' && (
          <button 
            className="btn flex items-center gap-1 text-yellow-500 border-yellow-500/50"
            onClick={() => onTriggerEmergency('Manual emergency trigger')}
            disabled={isLoading}
            data-testid="trigger-emergency-btn"
          >
            <Warning size={14} weight="bold" />
            紧急平仓
          </button>
        )}
        {status === 'COOLDOWN' && (
          <button 
            className="btn btn-primary flex items-center gap-1"
            onClick={onEndCooldown}
            disabled={isLoading || (riskStatus?.remaining_cooldown_seconds > 0)}
            data-testid="end-cooldown-btn"
          >
            <Play size={14} weight="bold" />
            结束冷却
          </button>
        )}
        {status === 'GRADUATED_RESTART' && (
          <button 
            className="btn btn-success flex items-center gap-1"
            onClick={onAdvanceRestart}
            disabled={isLoading}
            data-testid="advance-restart-btn"
          >
            <SkipForward size={14} weight="bold" />
            推进重启
          </button>
        )}
        {status !== 'NORMAL' && (
          <button 
            className="btn flex items-center gap-1"
            onClick={onReset}
            disabled={isLoading}
            data-testid="reset-risk-btn"
          >
            <ArrowCounterClockwise size={14} weight="bold" />
            强制重置
          </button>
        )}
      </div>

      {/* Recent Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">最近警报</div>
          <div className="max-h-20 overflow-auto space-y-1">
            {alerts.slice(-5).reverse().map((alert, i) => (
              <div key={i} className={`text-xs p-1.5 rounded-sm ${
                alert.type === 'EMERGENCY' ? 'bg-red-500/10 text-red-400' :
                alert.type === 'WARNING' ? 'bg-yellow-500/10 text-yellow-400' :
                'bg-zinc-900/50 text-zinc-400'
              }`}>
                <span className="font-bold">[{alert.type}]</span> {alert.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SettingsPanel({ settings, onUpdate }) {
  const [killSwitch, setKillSwitch] = useState(settings?.kill_switch === 'true');

  const handleKillSwitch = async () => {
    const newValue = !killSwitch;
    setKillSwitch(newValue);
    await onUpdate('kill_switch', newValue.toString());
  };

  const handleDirectionChange = async (pair, value) => {
    const key = pair === 'AUD/USD' ? 'aud_usd_direction' : 'nzd_usd_direction';
    await onUpdate(key, value);
  };

  return (
    <div className="space-y-4" data-testid="settings-panel">
      {/* Kill Switch */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">紧急停止</div>
        <button 
          className={`w-full py-3 text-sm font-bold uppercase tracking-wider rounded-sm transition-all ${
            killSwitch 
              ? 'bg-red-500 text-white kill-switch-armed' 
              : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
          }`}
          onClick={handleKillSwitch}
          data-testid="kill-switch-btn"
        >
          <div className="flex items-center justify-center gap-2">
            <Power size={18} weight="bold" />
            {killSwitch ? 'KILL SWITCH ON' : 'KILL SWITCH OFF'}
          </div>
        </button>
      </div>

      {/* Direction Settings */}
      <div className="space-y-3">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">方向权限</div>
        {['AUD/USD', 'NZD/USD'].map((pair) => {
          const key = pair === 'AUD/USD' ? 'aud_usd_direction' : 'nzd_usd_direction';
          return (
            <div key={pair} className="flex items-center justify-between">
              <span className="text-xs font-bold">{pair}</span>
              <select 
                value={settings?.[key] || 'LONG_ONLY'}
                onChange={(e) => handleDirectionChange(pair, e.target.value)}
                className="text-xs"
                data-testid={`direction-select-${pair.replace('/', '-')}`}
              >
                <option value="LONG_ONLY">只做多</option>
                <option value="SHORT_ONLY">只做空</option>
                <option value="BOTH">双向</option>
              </select>
            </div>
          );
        })}
      </div>

      {/* Risk Parameters */}
      <div className="space-y-3">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">风控参数</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex justify-between">
            <span className="text-zinc-400">止损</span>
            <span className="tabular-nums">{settings?.stop_loss_pips || 15} pips</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">止盈</span>
            <span className="tabular-nums">{settings?.take_profit_pips || 25} pips</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">最长持仓</span>
            <span className="tabular-nums">{settings?.max_hold_minutes || 30} 分钟</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">点差阈值</span>
            <span className="tabular-nums">{settings?.spread_threshold_pips || 3.0} pips</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function CalendarPanel({ events }) {
  const getImpactBadge = (impact) => {
    switch (impact) {
      case 'A': return <span className="badge badge-event">A级</span>;
      case 'B': return <span className="badge badge-range">B级</span>;
      default: return <span className="badge badge-wait">C级</span>;
    }
  };

  return (
    <div className="space-y-2 max-h-64 overflow-auto" data-testid="calendar-panel">
      {events?.slice(0, 8).map((ev, i) => (
        <div key={i} className="flex items-start gap-2 p-2 bg-zinc-900/50 rounded-sm text-xs">
          <div className="flex-shrink-0 w-12 text-zinc-500">
            {format(new Date(ev.datetime), 'HH:mm')}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-bold truncate">{ev.title}</span>
              {getImpactBadge(ev.impact)}
            </div>
            <div className="text-zinc-500">{ev.country} • {ev.pair_affected}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function BrokerStatusPanel({ status, dataSources }) {
  return (
    <div className="space-y-4" data-testid="broker-status-panel">
      {/* Brokers */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">券商连接</div>
        {status?.dukascopy && (
          <div className="flex items-center justify-between p-2 bg-zinc-900/50 rounded-sm">
            <div className="flex items-center gap-2">
              {status.dukascopy.connected ? 
                <WifiHigh size={14} className="text-green-500" /> : 
                <WifiSlash size={14} className="text-zinc-500" />
              }
              <span className="text-xs font-bold">{status.dukascopy.name}</span>
            </div>
            <span className={`text-xs ${status.dukascopy.connected ? 'text-green-500' : 'text-zinc-500'}`}>
              {status.dukascopy.connected ? '已连接' : '未连接'}
            </span>
          </div>
        )}
        {status?.interactive_brokers && (
          <div className="flex items-center justify-between p-2 bg-zinc-900/50 rounded-sm">
            <div className="flex items-center gap-2">
              {status.interactive_brokers.connected ? 
                <WifiHigh size={14} className="text-green-500" /> : 
                <WifiSlash size={14} className="text-zinc-500" />
              }
              <span className="text-xs font-bold">{status.interactive_brokers.name}</span>
            </div>
            <span className={`text-xs ${status.interactive_brokers.connected ? 'text-green-500' : 'text-zinc-500'}`}>
              {status.interactive_brokers.connected ? '已连接' : '未连接'}
            </span>
          </div>
        )}
      </div>

      {/* Data Sources */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">数据源</div>
        {dataSources?.map((ds, i) => (
          <div key={i} className="flex items-center justify-between text-xs">
            <span className="text-zinc-400">{ds.name}</span>
            <div className="flex items-center gap-2">
              <span className={ds.status === '运行中' ? 'text-green-500' : 'text-zinc-500'}>
                {ds.status}
              </span>
              <span className="text-zinc-600">[{ds.role}]</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AIAnalysisPanel({ onAnalyze, analyses, isLoading }) {
  const [selectedPair, setSelectedPair] = useState('AUD/USD');

  return (
    <div className="space-y-3" data-testid="ai-analysis-panel">
      <div className="flex gap-2">
        <select 
          value={selectedPair} 
          onChange={(e) => setSelectedPair(e.target.value)}
          className="flex-1"
          data-testid="ai-pair-select"
        >
          <option value="AUD/USD">AUD/USD</option>
          <option value="NZD/USD">NZD/USD</option>
        </select>
        <button 
          className="btn btn-primary flex items-center gap-1"
          onClick={() => onAnalyze(selectedPair)}
          disabled={isLoading}
          data-testid="ai-analyze-btn"
        >
          {isLoading ? (
            <ArrowsClockwise size={14} className="spinner" />
          ) : (
            <Brain size={14} />
          )}
          分析
        </button>
      </div>

      <div className="space-y-2 max-h-48 overflow-auto">
        {analyses?.slice(0, 3).map((a, i) => (
          <div key={i} className="p-2 bg-zinc-900/50 rounded-sm text-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold">{a.pair}</span>
              <span className="text-zinc-500">{format(new Date(a.timestamp), 'HH:mm')}</span>
            </div>
            <p className="text-zinc-400 whitespace-pre-wrap line-clamp-4">{a.analysis}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TradeStatsPanel({ stats }) {
  return (
    <div className="grid grid-cols-2 gap-3" data-testid="trade-stats-panel">
      <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
        <div className="text-2xl font-bold tabular-nums">{stats?.total_trades || 0}</div>
        <div className="text-xs text-zinc-500">总交易</div>
      </div>
      <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
        <div className={`text-2xl font-bold tabular-nums ${
          (stats?.win_rate || 0) >= 50 ? 'text-green-500' : 'text-red-500'
        }`}>{stats?.win_rate?.toFixed(1) || 0}%</div>
        <div className="text-xs text-zinc-500">胜率</div>
      </div>
      <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
        <div className={`text-2xl font-bold tabular-nums ${
          (stats?.total_pnl_pips || 0) >= 0 ? 'text-green-500' : 'text-red-500'
        }`}>{stats?.total_pnl_pips >= 0 ? '+' : ''}{stats?.total_pnl_pips?.toFixed(1) || 0}</div>
        <div className="text-xs text-zinc-500">总盈亏 (pips)</div>
      </div>
      <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
        <div className="text-2xl font-bold tabular-nums text-blue-500">{stats?.open_trades || 0}</div>
        <div className="text-xs text-zinc-500">持仓中</div>
      </div>
    </div>
  );
}

function BacktestPanel({ stats, chartData }) {
  const summary = stats?.summary || {};
  const byPair = stats?.by_pair || {};
  const bestEvents = stats?.best_performing_events || [];
  const windowAnalysis = stats?.confirmation_window_analysis || {};

  return (
    <div className="space-y-4" data-testid="backtest-panel">
      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-2">
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className="text-xl font-bold tabular-nums">{summary.total_trades || 0}</div>
          <div className="text-xs text-zinc-500">总回测</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-xl font-bold tabular-nums ${
            (summary.overall_success_rate || 0) >= 50 ? 'text-green-500' : 'text-red-500'
          }`}>{summary.overall_success_rate || 0}%</div>
          <div className="text-xs text-zinc-500">确认成功率</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-xl font-bold tabular-nums ${
            (summary.total_pnl_pips || 0) >= 0 ? 'text-green-500' : 'text-red-500'
          }`}>{summary.total_pnl_pips >= 0 ? '+' : ''}{summary.total_pnl_pips || 0}</div>
          <div className="text-xs text-zinc-500">总盈亏</div>
        </div>
        <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
          <div className={`text-xl font-bold tabular-nums ${
            (summary.avg_pnl_per_trade || 0) >= 0 ? 'text-green-500' : 'text-red-500'
          }`}>{summary.avg_pnl_per_trade >= 0 ? '+' : ''}{summary.avg_pnl_per_trade || 0}</div>
          <div className="text-xs text-zinc-500">平均盈亏</div>
        </div>
      </div>

      {/* Cumulative PnL Chart */}
      {chartData?.chart_data && chartData.chart_data.length > 0 && (
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData.chart_data}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#34C759" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#34C759" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="index" tick={false} axisLine={false} />
              <YAxis 
                tick={{ fontSize: 9, fill: '#71717A' }}
                axisLine={false}
                tickLine={false}
                width={40}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#141414', 
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '2px',
                  fontSize: '10px'
                }}
                formatter={(value) => [`${value} pips`, 'Cumulative PnL']}
              />
              <Area 
                type="monotone" 
                dataKey="cumulative_pnl" 
                stroke="#34C759" 
                strokeWidth={1.5}
                fill="url(#pnlGradient)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Event Level Success Rates */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">30秒确认窗口分析</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 bg-zinc-900/50 rounded-sm">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs font-bold">A级事件</span>
              <span className="badge badge-event">高影响</span>
            </div>
            <div className="text-lg font-bold text-green-500 tabular-nums">
              {windowAnalysis.a_level_success_rate || 0}%
            </div>
            <div className="text-xs text-zinc-500">确认成功率</div>
          </div>
          <div className="p-2 bg-zinc-900/50 rounded-sm">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs font-bold">B级事件</span>
              <span className="badge badge-range">中影响</span>
            </div>
            <div className="text-lg font-bold text-yellow-500 tabular-nums">
              {windowAnalysis.b_level_success_rate || 0}%
            </div>
            <div className="text-xs text-zinc-500">确认成功率</div>
          </div>
        </div>
      </div>

      {/* Best Performing Events */}
      {bestEvents.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">最佳事件类型</div>
          <div className="space-y-1 max-h-24 overflow-auto">
            {bestEvents.slice(0, 3).map((ev, i) => (
              <div key={i} className="flex items-center justify-between text-xs p-1.5 bg-zinc-900/30 rounded-sm">
                <span className="truncate flex-1">{ev.event}</span>
                <div className="flex items-center gap-2">
                  <span className={ev.avg_pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                    {ev.avg_pnl >= 0 ? '+' : ''}{ev.avg_pnl}
                  </span>
                  <span className="text-zinc-400">{ev.success_rate}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendation */}
      {windowAnalysis.recommendation && (
        <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-sm">
          <div className="text-xs text-blue-400">{windowAnalysis.recommendation}</div>
        </div>
      )}
    </div>
  );
}

function MonteCarloPanel({ onRunSimulation, simResult, isLoading }) {
  const [numSim, setNumSim] = useState(1000);
  const [tradesPerSim, setTradesPerSim] = useState(100);
  
  const robustness = simResult?.robustness_score || {};
  const pnlStats = simResult?.pnl_statistics || {};
  const riskMetrics = simResult?.risk_metrics || {};
  const probAnalysis = simResult?.probability_analysis || {};
  const positionSizing = simResult?.position_sizing || {};
  const histogram = simResult?.histogram || [];
  const samplePaths = simResult?.sample_paths || [];

  return (
    <div className="space-y-4" data-testid="monte-carlo-panel">
      {/* Controls */}
      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <div className="text-xs text-zinc-500 mb-1">模拟次数</div>
          <select 
            value={numSim} 
            onChange={(e) => setNumSim(Number(e.target.value))}
            className="w-full text-xs"
            data-testid="mc-sim-count"
          >
            <option value={500}>500次</option>
            <option value={1000}>1,000次</option>
            <option value={5000}>5,000次</option>
          </select>
        </div>
        <div className="flex-1">
          <div className="text-xs text-zinc-500 mb-1">每次交易数</div>
          <select 
            value={tradesPerSim} 
            onChange={(e) => setTradesPerSim(Number(e.target.value))}
            className="w-full text-xs"
            data-testid="mc-trades-count"
          >
            <option value={50}>50笔</option>
            <option value={100}>100笔</option>
            <option value={200}>200笔</option>
          </select>
        </div>
        <button 
          className="btn btn-primary flex items-center gap-1"
          onClick={() => onRunSimulation(numSim, tradesPerSim)}
          disabled={isLoading}
          data-testid="run-mc-btn"
        >
          {isLoading ? (
            <ArrowsClockwise size={14} className="spinner" />
          ) : (
            <Gauge size={14} />
          )}
          运行
        </button>
      </div>

      {simResult && !simResult.error && (
        <>
          {/* Robustness Score */}
          <div className="p-3 bg-zinc-900/50 rounded-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500 uppercase">策略稳健性评分</span>
              <span className={`text-2xl font-bold tabular-nums ${
                robustness.score >= 70 ? 'text-green-500' : 
                robustness.score >= 50 ? 'text-yellow-500' : 'text-red-500'
              }`}>{robustness.score || 0}</span>
            </div>
            <div className="text-sm font-bold">{robustness.rating}</div>
            <div className="text-xs text-zinc-400">{robustness.recommendation}</div>
            
            {/* Score Components */}
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-white/10">
              <div className="text-center">
                <div className="text-xs text-zinc-500">盈利概率</div>
                <div className="text-sm font-bold tabular-nums">{robustness.components?.profit_probability || 0}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-zinc-500">风险收益</div>
                <div className="text-sm font-bold tabular-nums">{robustness.components?.risk_adjusted_return || 0}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-zinc-500">回撤控制</div>
                <div className="text-sm font-bold tabular-nums">{robustness.components?.drawdown_control || 0}</div>
              </div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-4 gap-2">
            <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
              <div className={`text-lg font-bold tabular-nums ${probAnalysis.prob_profit >= 50 ? 'text-green-500' : 'text-red-500'}`}>
                {probAnalysis.prob_profit || 0}%
              </div>
              <div className="text-xs text-zinc-500">盈利概率</div>
            </div>
            <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
              <div className={`text-lg font-bold tabular-nums ${pnlStats.mean >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {pnlStats.mean >= 0 ? '+' : ''}{pnlStats.mean || 0}
              </div>
              <div className="text-xs text-zinc-500">期望盈亏</div>
            </div>
            <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
              <div className="text-lg font-bold tabular-nums text-blue-500">
                {riskMetrics.sharpe_ratio || 0}
              </div>
              <div className="text-xs text-zinc-500">夏普比率</div>
            </div>
            <div className="text-center p-2 bg-zinc-900/50 rounded-sm">
              <div className="text-lg font-bold tabular-nums text-red-500">
                -{riskMetrics.max_drawdown_mean || 0}
              </div>
              <div className="text-xs text-zinc-500">平均回撤</div>
            </div>
          </div>

          {/* Distribution Chart */}
          {histogram.length > 0 && (
            <div className="h-24">
              <div className="text-xs text-zinc-500 mb-1">盈亏分布 (PnL Distribution)</div>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogram}>
                  <XAxis dataKey="range_start" tick={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: '#71717A' }} axisLine={false} tickLine={false} width={30} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#141414', 
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: '2px',
                      fontSize: '10px'
                    }}
                    formatter={(value, name, props) => [
                      `${value} (${props.payload.percentage}%)`,
                      `${props.payload.range_start} to ${props.payload.range_end} pips`
                    ]}
                  />
                  <Bar dataKey="count">
                    {histogram.map((entry, index) => (
                      <Cell 
                        key={`cell-${index}`} 
                        fill={entry.range_start >= 0 ? '#34C759' : '#FF3B30'} 
                        fillOpacity={0.7}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Sample Paths */}
          {samplePaths.length > 0 && (
            <div className="h-24">
              <div className="text-xs text-zinc-500 mb-1">模拟路径 (Sample Equity Curves)</div>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <XAxis dataKey="index" tick={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: '#71717A' }} axisLine={false} tickLine={false} width={35} />
                  {samplePaths.slice(0, 5).map((path, idx) => (
                    <Line 
                      key={path.path_id}
                      data={path.values.map((v, i) => ({ index: i, value: v }))}
                      dataKey="value"
                      stroke={['#007AFF', '#34C759', '#F59E0B', '#FF3B30', '#AF52DE'][idx]}
                      strokeWidth={1}
                      dot={false}
                      strokeOpacity={0.6}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Risk Metrics */}
          <div className="space-y-2">
            <div className="text-xs text-zinc-500 uppercase tracking-wider">风险指标 (VaR)</div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="flex justify-between p-1.5 bg-zinc-900/30 rounded-sm">
                <span className="text-zinc-400">VaR 95%</span>
                <span className="text-red-400 tabular-nums">{riskMetrics.var_95 || 0}</span>
              </div>
              <div className="flex justify-between p-1.5 bg-zinc-900/30 rounded-sm">
                <span className="text-zinc-400">VaR 99%</span>
                <span className="text-red-400 tabular-nums">{riskMetrics.var_99 || 0}</span>
              </div>
              <div className="flex justify-between p-1.5 bg-zinc-900/30 rounded-sm">
                <span className="text-zinc-400">最大回撤</span>
                <span className="text-red-400 tabular-nums">-{riskMetrics.max_drawdown_worst || 0}</span>
              </div>
            </div>
          </div>

          {/* Position Sizing Recommendation */}
          <div className="p-2 bg-green-500/10 border border-green-500/30 rounded-sm">
            <div className="text-xs text-green-400 font-bold mb-1">仓位管理建议</div>
            <div className="text-xs text-zinc-300">
              凯利公式: <span className="text-green-400 font-bold">{positionSizing.kelly_fraction}%</span> | 
              半凯利(推荐): <span className="text-yellow-400 font-bold">{positionSizing.half_kelly}%</span>
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              保守: {positionSizing.recommended_risk_per_trade?.conservative}% | 
              中等: {positionSizing.recommended_risk_per_trade?.moderate}% | 
              激进: {positionSizing.recommended_risk_per_trade?.aggressive}%
            </div>
          </div>
        </>
      )}

      {simResult?.error && (
        <div className="p-2 bg-red-500/10 border border-red-500/30 rounded-sm text-xs text-red-400">
          {simResult.message || simResult.error}
        </div>
      )}
    </div>
  );
}

function GridSearchPanel({ onRunSearch, searchResult, isLoading }) {
  const best = searchResult?.best_parameters || {};
  const topResults = searchResult?.top_10_results || [];
  const sensitivity = searchResult?.parameter_sensitivity || {};
  const recommendations = searchResult?.recommendations || [];
  const searchInfo = searchResult?.search_info || {};

  return (
    <div className="space-y-4" data-testid="grid-search-panel">
      {/* Run Button */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-zinc-400">
          测试 {searchInfo.total_combinations || '3125+'} 种参数组合
        </div>
        <button 
          className="btn btn-primary flex items-center gap-1"
          onClick={onRunSearch}
          disabled={isLoading}
          data-testid="run-grid-search-btn"
        >
          {isLoading ? (
            <ArrowsClockwise size={14} className="spinner" />
          ) : (
            <Gear size={14} />
          )}
          开始优化
        </button>
      </div>

      {searchResult && !searchResult.error && (
        <>
          {/* Best Parameters */}
          <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-green-400 font-bold uppercase">最优参数组合</span>
              <span className="text-xl font-bold text-green-500 tabular-nums">
                {best.scores?.composite_score || 0}分
              </span>
            </div>
            
            <div className="grid grid-cols-5 gap-2 text-xs">
              <div className="text-center p-1.5 bg-zinc-900/50 rounded-sm">
                <div className="text-zinc-500">A级冷却</div>
                <div className="font-bold text-green-400">{best.params?.cooldown_a || 30}s</div>
              </div>
              <div className="text-center p-1.5 bg-zinc-900/50 rounded-sm">
                <div className="text-zinc-500">B级冷却</div>
                <div className="font-bold text-green-400">{best.params?.cooldown_b || 20}s</div>
              </div>
              <div className="text-center p-1.5 bg-zinc-900/50 rounded-sm">
                <div className="text-zinc-500">止损</div>
                <div className="font-bold text-red-400">{best.params?.stop_loss || 15}</div>
              </div>
              <div className="text-center p-1.5 bg-zinc-900/50 rounded-sm">
                <div className="text-zinc-500">止盈</div>
                <div className="font-bold text-green-400">{best.params?.take_profit || 25}</div>
              </div>
              <div className="text-center p-1.5 bg-zinc-900/50 rounded-sm">
                <div className="text-zinc-500">确认窗口</div>
                <div className="font-bold text-blue-400">{best.params?.confirmation_window || 30}s</div>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2 text-xs pt-2 border-t border-green-500/20">
              <div className="text-center">
                <div className="text-zinc-500">期望盈亏</div>
                <div className={`font-bold tabular-nums ${(best.metrics?.avg_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {best.metrics?.avg_pnl >= 0 ? '+' : ''}{best.metrics?.avg_pnl || 0}
                </div>
              </div>
              <div className="text-center">
                <div className="text-zinc-500">夏普比率</div>
                <div className="font-bold tabular-nums text-blue-400">{best.metrics?.sharpe_ratio || 0}</div>
              </div>
              <div className="text-center">
                <div className="text-zinc-500">胜率</div>
                <div className="font-bold tabular-nums">{best.metrics?.avg_win_rate || 0}%</div>
              </div>
              <div className="text-center">
                <div className="text-zinc-500">回撤</div>
                <div className="font-bold tabular-nums text-red-400">-{best.metrics?.avg_max_drawdown || 0}</div>
              </div>
            </div>
          </div>

          {/* Parameter Sensitivity */}
          {sensitivity.impact_ranking && (
            <div className="space-y-2">
              <div className="text-xs text-zinc-500 uppercase tracking-wider">参数敏感度排名</div>
              <div className="space-y-1">
                {sensitivity.impact_ranking.slice(0, 5).map((item, idx) => {
                  const paramNames = {
                    cooldown_a: 'A级冷却',
                    cooldown_b: 'B级冷却',
                    stop_loss: '止损',
                    take_profit: '止盈',
                    confirmation_window: '确认窗口',
                  };
                  return (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="w-4 text-xs text-zinc-500">{idx + 1}</span>
                      <span className="flex-1 text-xs">{paramNames[item.parameter] || item.parameter}</span>
                      <div className="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${Math.min(item.impact * 5, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-zinc-400 tabular-nums w-12">
                        影响 {item.impact}
                      </span>
                      <span className="text-xs text-green-400 tabular-nums">
                        最优: {item.best_value}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Top 5 Results Comparison */}
          <div className="space-y-2">
            <div className="text-xs text-zinc-500 uppercase tracking-wider">Top 5 参数组合对比</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-zinc-500 border-b border-white/10">
                    <th className="text-left p-1">#</th>
                    <th className="text-center p-1">A冷却</th>
                    <th className="text-center p-1">B冷却</th>
                    <th className="text-center p-1">止损</th>
                    <th className="text-center p-1">止盈</th>
                    <th className="text-center p-1">确认</th>
                    <th className="text-right p-1">得分</th>
                    <th className="text-right p-1">盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  {topResults.slice(0, 5).map((r, idx) => (
                    <tr key={idx} className={`border-b border-white/5 ${idx === 0 ? 'bg-green-500/10' : ''}`}>
                      <td className="p-1 text-zinc-500">{idx + 1}</td>
                      <td className="text-center p-1">{r.params.cooldown_a}s</td>
                      <td className="text-center p-1">{r.params.cooldown_b}s</td>
                      <td className="text-center p-1 text-red-400">{r.params.stop_loss}</td>
                      <td className="text-center p-1 text-green-400">{r.params.take_profit}</td>
                      <td className="text-center p-1">{r.params.confirmation_window}s</td>
                      <td className="text-right p-1 font-bold">{r.scores.composite_score}</td>
                      <td className={`text-right p-1 tabular-nums ${r.metrics.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {r.metrics.avg_pnl >= 0 ? '+' : ''}{r.metrics.avg_pnl}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-zinc-500 uppercase tracking-wider">优化建议</div>
              <div className="space-y-1">
                {recommendations.map((rec, idx) => (
                  <div key={idx} className={`p-2 rounded-sm text-xs ${
                    rec.priority === '高' ? 'bg-green-500/10 border border-green-500/30' :
                    'bg-zinc-900/50 border border-white/10'
                  }`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`badge ${rec.priority === '高' ? 'badge-buy' : 'badge-wait'}`}>
                        {rec.priority}
                      </span>
                      <span className="font-bold">{rec.title}</span>
                    </div>
                    <div className="text-zinc-400">{rec.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {searchResult?.error && (
        <div className="p-2 bg-red-500/10 border border-red-500/30 rounded-sm text-xs text-red-400">
          {searchResult.message || searchResult.error}
        </div>
      )}
    </div>
  );
}

// ─── Event Response Engine Panel ──────────────────────────────────────────────

const EVENT_STATE_COLORS = {
  IDLE: 'text-zinc-500',
  EVENT_DETECTED: 'text-yellow-400',
  IMPULSE_PHASE: 'text-orange-400',
  LIQUIDITY_REBUILD: 'text-blue-400',
  DIRECTION_CONFIRM: 'text-cyan-400',
  READY: 'text-green-400',
  INVALID: 'text-red-400',
};

const EVENT_STATE_LABELS = {
  IDLE: '待命',
  EVENT_DETECTED: '事件检测',
  IMPULSE_PHASE: '冲击阶段',
  LIQUIDITY_REBUILD: '流动性恢复',
  DIRECTION_CONFIRM: '方向确认',
  READY: '可交易',
  INVALID: '无效',
};

function EventResponsePanel({ onTrigger, onReset }) {
  const [engines, setEngines] = useState({});
  const [pairConfig, setPairConfig] = useState({});
  const [triggerLevel, setTriggerLevel] = useState('A');
  const [triggerTitle, setTriggerTitle] = useState('');
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    const poll = () => {
      api.eventResponseStatus().then(d => {
        setEngines(d?.engines || {});
        setPairConfig(d?.pair_config || {});
      }).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => clearInterval(iv);
  }, []);

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await onTrigger(triggerLevel, triggerTitle || '手动触发');
      setTriggerTitle('');
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="event-response-panel">
      {/* 引擎状态 */}
      {Object.entries(engines).map(([pair, eng]) => (
        <div key={pair} className="p-2 bg-zinc-900/50 rounded-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold">{pair}</span>
            <span className={`text-xs font-bold ${EVENT_STATE_COLORS[eng.state] || 'text-zinc-500'}`}>
              {EVENT_STATE_LABELS[eng.state] || eng.state}
            </span>
          </div>

          {/* 5阶段进度条 */}
          <div className="flex gap-0.5 mb-2">
            {['EVENT_DETECTED', 'IMPULSE_PHASE', 'LIQUIDITY_REBUILD', 'DIRECTION_CONFIRM', 'READY'].map((s, i) => {
              const states = ['IDLE', 'EVENT_DETECTED', 'IMPULSE_PHASE', 'LIQUIDITY_REBUILD', 'DIRECTION_CONFIRM', 'READY'];
              const currentIdx = states.indexOf(eng.state);
              const targetIdx = states.indexOf(s);
              const active = eng.state !== 'IDLE' && eng.state !== 'INVALID' && currentIdx >= targetIdx;
              return (
                <div key={s} className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                  active ? (eng.state === 'READY' ? 'bg-green-500' : 'bg-blue-500') : 'bg-zinc-800'
                }`} />
              );
            })}
          </div>

          {eng.state !== 'IDLE' && (
            <div className="space-y-1 text-xs">
              <div className="flex justify-between text-zinc-500">
                <span>经过: {eng.elapsed_seconds?.toFixed(0)}s / {eng.max_wait_seconds}s</span>
                {eng.confirmed_direction && (
                  <span className={eng.confirmed_direction === 'BUY' ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
                    {eng.confirmed_direction} ({eng.confidence?.toFixed(0)}%)
                  </span>
                )}
              </div>
              {eng.impulse_direction && (
                <div className="text-zinc-400">
                  冲击: {eng.impulse_direction} | H:{eng.impulse_high?.toFixed(5)} L:{eng.impulse_low?.toFixed(5)}
                </div>
              )}
              <div className="text-zinc-500 truncate">{eng.reason}</div>
            </div>
          )}
        </div>
      ))}

      {/* 触发控制 */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">触发事件</div>
        <div className="flex gap-2">
          <select
            value={triggerLevel}
            onChange={(e) => setTriggerLevel(e.target.value)}
            className="text-xs w-16"
            data-testid="event-level-select"
          >
            <option value="A">A级</option>
            <option value="B">B级</option>
          </select>
          <input
            type="text"
            value={triggerTitle}
            onChange={(e) => setTriggerTitle(e.target.value)}
            placeholder="事件名称 (如: RBA利率决议)"
            className="flex-1 text-xs"
            data-testid="event-title-input"
          />
          <button
            className="btn btn-primary flex items-center gap-1"
            onClick={handleTrigger}
            disabled={triggering}
            data-testid="trigger-event-btn"
          >
            <Lightning size={14} weight="fill" />
            触发
          </button>
          <button
            className="btn flex items-center gap-1"
            onClick={onReset}
            data-testid="reset-event-btn"
          >
            <ArrowCounterClockwise size={14} />
          </button>
        </div>
      </div>

      {/* 品种配置 */}
      <div className="space-y-1">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">品种等待配置</div>
        {Object.entries(pairConfig).map(([pair, cfg]) => (
          <div key={pair} className="flex items-center justify-between text-xs p-1.5 bg-zinc-900/30 rounded-sm">
            <span className="font-bold">{pair}</span>
            <div className="flex gap-3 text-zinc-400">
              <span>最长 {cfg.max_wait_seconds}s</span>
              <span>冲击阈值 {cfg.impulse_vol_threshold}x</span>
              <span>{cfg.require_second_push ? '需二次确认' : '单次确认'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Execution Gate Panel ─────────────────────────────────────────────────────

const GATE_ACTION_COLORS = {
  ALLOW: 'bg-green-500/20 text-green-400 border-green-500/30',
  ALLOW_REDUCED: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  BLOCK: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30',
  EXIT_NOW: 'bg-red-500/20 text-red-400 border-red-500/30',
  FREEZE: 'bg-red-500/30 text-red-300 border-red-500/50',
};

function ExecutionGatePanel() {
  const [gateStatus, setGateStatus] = useState(null);
  const [evaluations, setEvaluations] = useState({});
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    const poll = () => {
      api.executionGateStatus().then(setGateStatus).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  const handleEvaluate = async (pair) => {
    setEvaluating(true);
    try {
      const result = await api.executionGateEvaluate(pair);
      setEvaluations(prev => ({ ...prev, [pair]: result }));
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="execution-gate-panel">
      {/* Gate 总状态 */}
      <div className="flex items-center justify-between p-2 bg-zinc-900/50 rounded-sm">
        <div className="flex items-center gap-2">
          <Shield size={16} weight="fill" className={
            gateStatus?.gate_state === 'OPEN' ? 'text-green-400' :
            gateStatus?.gate_state === 'THROTTLED' ? 'text-yellow-400' : 'text-red-400'
          } />
          <span className="text-sm font-bold">闸门: {gateStatus?.gate_state || 'OPEN'}</span>
        </div>
      </div>

      {/* 品种风险配置 */}
      {gateStatus?.pair_risk_config && (
        <div className="space-y-1">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">品种风险预算</div>
          {Object.entries(gateStatus.pair_risk_config).map(([pair, cfg]) => (
            <div key={pair} className="flex items-center justify-between p-1.5 bg-zinc-900/30 rounded-sm text-xs">
              <span className="font-bold">{pair}</span>
              <div className="flex gap-3 text-zinc-400">
                <span>基础风险: {cfg.base_risk_percent}%</span>
                <span>乘数: {cfg.risk_multiplier}x</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 评估按钮和结果 */}
      <div className="space-y-1">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">实时裁决</div>
        {['AUD/USD', 'NZD/USD'].map(pair => {
          const ev = evaluations[pair];
          const dec = ev?.decision;
          return (
            <div key={pair} className="space-y-1">
              <div className="flex items-center gap-2">
                <button
                  className="btn text-xs flex-1 flex items-center justify-center gap-1"
                  onClick={() => handleEvaluate(pair)}
                  disabled={evaluating}
                  data-testid={`evaluate-gate-${pair.replace('/', '-')}`}
                >
                  <Crosshair size={12} />
                  评估 {pair}
                </button>
                {dec && (
                  <span className={`text-xs px-2 py-0.5 rounded-sm border ${GATE_ACTION_COLORS[dec.action] || ''}`}>
                    {dec.action}
                  </span>
                )}
              </div>
              {dec && (
                <div className="text-xs p-1.5 bg-zinc-900/30 rounded-sm space-y-0.5">
                  <div className="flex justify-between text-zinc-400">
                    <span>优先级: {dec.priority_level}</span>
                    <span>风险: {(dec.risk_percent * 100).toFixed(2)}%</span>
                    <span>仓位: {(dec.size_multiplier * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {dec.reason_codes?.map((r, i) => (
                      <span key={i} className="text-xs px-1 py-0.5 bg-zinc-800 rounded-sm text-zinc-500">{r}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Regime 乘数表 */}
      {gateStatus?.regime_multipliers && (
        <div className="space-y-1">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">Regime 风险乘数</div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(gateStatus.regime_multipliers).map(([r, m]) => (
              <span key={r} className={`text-xs px-1.5 py-0.5 rounded-sm ${
                m === 0 ? 'bg-red-500/20 text-red-400' :
                m < 1 ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'
              }`}>
                {r}: {(m * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Strategy Monitor Panel ───────────────────────────────────────────────────

function StrategyMonitorPanel() {
  const [health, setHealth] = useState({});

  useEffect(() => {
    const poll = () => {
      api.strategyHealth().then(setHealth).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  const handleUnfreeze = async (pair) => {
    const result = await api.strategyUnfreeze(pair);
    setHealth(result);
  };

  return (
    <div className="space-y-3" data-testid="strategy-monitor-panel">
      {Object.entries(health).map(([pair, h]) => (
        <div key={pair} className={`p-2 rounded-sm border ${
          h.frozen ? 'bg-red-500/10 border-red-500/30' :
          h.recovery_state !== 'GREEN' ? 'bg-yellow-500/10 border-yellow-500/20' :
          'bg-zinc-900/50 border-zinc-800'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold">{pair}</span>
            <div className="flex items-center gap-2">
              {h.frozen ? (
                <span className="text-xs text-red-400 font-bold">FROZEN</span>
              ) : (
                <span className={`text-xs font-bold ${
                  h.recovery_state === 'GREEN' ? 'text-green-400' : 'text-yellow-400'
                }`}>
                  {h.recovery_state}
                </span>
              )}
              <span className={`text-xs px-1.5 py-0.5 rounded-sm ${
                h.risk_multiplier >= 1 ? 'bg-green-500/20 text-green-400' :
                h.risk_multiplier > 0 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {(h.risk_multiplier * 100).toFixed(0)}% 风险
              </span>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 text-xs">
            <div>
              <div className="text-zinc-500">连亏</div>
              <div className={`font-bold ${h.consecutive_losses >= 3 ? 'text-red-400' : 'text-zinc-300'}`}>
                {h.consecutive_losses}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">连赢</div>
              <div className="font-bold text-zinc-300">{h.consecutive_wins}</div>
            </div>
            <div>
              <div className="text-zinc-500">胜率</div>
              <div className="font-bold text-zinc-300">{(h.rolling_win_rate * 100).toFixed(0)}%</div>
            </div>
            <div>
              <div className="text-zinc-500">日PnL</div>
              <div className={`font-bold ${h.daily_pnl_pips >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {h.daily_pnl_pips?.toFixed(1)}p
              </div>
            </div>
          </div>

          {h.daily_deterioration_count > 0 && (
            <div className="mt-1 text-xs text-orange-400">
              今日恶化触发: {h.daily_deterioration_count}次
            </div>
          )}

          {h.frozen && (
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-red-400">{h.frozen_reason}</span>
              <button
                className="btn text-xs"
                onClick={() => handleUnfreeze(pair)}
                data-testid={`unfreeze-${pair.replace('/', '-')}`}
              >
                解冻
              </button>
            </div>
          )}

          {/* 恢复进度条 */}
          {h.recovery_state !== 'GREEN' && !h.frozen && (
            <div className="mt-2">
              <div className="text-xs text-zinc-500 mb-1">恢复进度: 30% → 50% → 75% → 100%</div>
              <div className="flex gap-0.5">
                {['RECOVERY_30', 'RECOVERY_50', 'RECOVERY_75', 'GREEN'].map((step) => {
                  const steps = ['COOLDOWN', 'RECOVERY_30', 'RECOVERY_50', 'RECOVERY_75', 'GREEN'];
                  const currentIdx = steps.indexOf(h.recovery_state);
                  const targetIdx = steps.indexOf(step);
                  const active = currentIdx >= targetIdx;
                  return (
                    <div key={step} className={`h-1 flex-1 rounded-full ${active ? 'bg-blue-500' : 'bg-zinc-800'}`} />
                  );
                })}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function TelegramPanel({ onSaveConfig, onTestMessage, onFetchHistory }) {
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [testMsg, setTestMsg] = useState('');
  const [status, setStatus] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showToken, setShowToken] = useState(false);

  useEffect(() => {
    api.telegramStatus().then(setStatus).catch(() => {});
    api.telegramHistory().then(d => setAlerts(d?.alerts || [])).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await onSaveConfig(botToken, chatId);
      setStatus(result);
      if (botToken) setBotToken('');
      if (chatId) setChatId('');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await onTestMessage(testMsg || 'FX Trading System - Telegram连接测试');
      setTestMsg('');
      const hist = await api.telegramHistory();
      setAlerts(hist?.alerts || []);
      const st = await api.telegramStatus();
      setStatus(st);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="telegram-panel">
      {/* Status */}
      <div className="flex items-center justify-between p-3 bg-zinc-900/50 rounded-sm">
        <div className="flex items-center gap-2">
          <PaperPlaneTilt size={18} weight="fill" className={status?.configured ? 'text-blue-400' : 'text-zinc-500'} />
          <span className="text-sm font-bold">{status?.configured ? 'Telegram 已连接' : 'Telegram 未配置'}</span>
        </div>
        <div className="flex items-center gap-2">
          {status?.bot_token_set ? (
            <CheckCircle size={14} weight="fill" className="text-green-500" />
          ) : (
            <XCircle size={14} weight="fill" className="text-zinc-500" />
          )}
          <span className="text-xs text-zinc-500">Token</span>
          {status?.chat_id_set ? (
            <CheckCircle size={14} weight="fill" className="text-green-500" />
          ) : (
            <XCircle size={14} weight="fill" className="text-zinc-500" />
          )}
          <span className="text-xs text-zinc-500">Chat ID</span>
        </div>
      </div>

      {/* Config Inputs */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Telegram 配置</div>
        <div className="space-y-2">
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Bot Token</label>
            <div className="flex gap-2">
              <input
                type={showToken ? 'text' : 'password'}
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder={status?.bot_token_set ? '••••••••(已设置, 留空保持不变)' : '输入 Bot Token'}
                className="flex-1 text-xs"
                data-testid="telegram-bot-token-input"
              />
              <button
                className="btn text-xs"
                onClick={() => setShowToken(!showToken)}
                data-testid="toggle-token-visibility"
              >
                {showToken ? '隐藏' : '显示'}
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Chat ID</label>
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder={status?.chat_id_set ? '(已设置, 留空保持不变)' : '输入 Chat ID'}
              className="w-full text-xs"
              data-testid="telegram-chat-id-input"
            />
          </div>
          <button
            className="btn btn-primary w-full flex items-center justify-center gap-1"
            onClick={handleSave}
            disabled={saving || (!botToken && !chatId)}
            data-testid="save-telegram-config-btn"
          >
            {saving ? <ArrowsClockwise size={14} className="spinner" /> : <Gear size={14} />}
            保存配置
          </button>
        </div>
      </div>

      {/* Test Message */}
      <div className="space-y-2">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">发送测试消息</div>
        <div className="flex gap-2">
          <input
            type="text"
            value={testMsg}
            onChange={(e) => setTestMsg(e.target.value)}
            placeholder="输入测试消息..."
            className="flex-1 text-xs"
            data-testid="telegram-test-msg-input"
          />
          <button
            className="btn btn-primary flex items-center gap-1"
            onClick={handleTest}
            disabled={testing || !status?.configured}
            data-testid="send-test-msg-btn"
          >
            {testing ? <ArrowsClockwise size={14} className="spinner" /> : <PaperPlaneTilt size={14} />}
            发送
          </button>
        </div>
        {!status?.configured && (
          <div className="text-xs text-yellow-500">请先配置 Bot Token 和 Chat ID</div>
        )}
      </div>

      {/* Alert Stats */}
      {status?.daily_alerts_sent > 0 && (
        <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-sm">
          <div className="text-xs text-blue-400">今日已发送 {status.daily_alerts_sent} 条警报</div>
        </div>
      )}

      {/* Recent Alerts History */}
      {alerts.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">最近消息记录</div>
          <div className="max-h-32 overflow-auto space-y-1">
            {alerts.slice(0, 10).map((a, i) => (
              <div key={i} className={`text-xs p-1.5 rounded-sm ${
                a.success ? 'bg-green-500/5 text-zinc-400' : 'bg-red-500/10 text-red-400'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="font-bold text-zinc-500">[{a.type}]</span>
                  <span className="text-zinc-600">{a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : ''}</span>
                </div>
                <div className="truncate mt-0.5">{a.message}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Setup Instructions */}
      {!status?.configured && (
        <div className="p-2 bg-zinc-900/50 rounded-sm space-y-1">
          <div className="text-xs text-zinc-400 font-bold">配置步骤:</div>
          <div className="text-xs text-zinc-500 space-y-0.5">
            <div>1. Telegram 搜索 @BotFather，发送 /newbot</div>
            <div>2. 按提示创建后获取 Bot Token</div>
            <div>3. 给 Bot 发一条消息</div>
            <div>4. 访问 api.telegram.org/bot&lt;TOKEN&gt;/getUpdates 获取 Chat ID</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Login Page ───────────────────────────────────────────────────────────────

function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      if (data.token) {
        localStorage.setItem('fx_token', data.token);
      }
      onLogin(data);
    } catch (err) {
      setError(err.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4" data-testid="login-page">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-3">
            <ChartLine size={32} weight="bold" className="text-blue-500" />
            <h1 className="text-2xl font-black tracking-tight text-zinc-100">FX TRADING</h1>
          </div>
          <p className="text-sm text-zinc-500">AUD/USD & NZD/USD Event-Driven System</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form">
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@cryptoai.com"
              className="w-full text-sm"
              required
              autoFocus
              data-testid="login-email-input"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              className="w-full text-sm"
              required
              data-testid="login-password-input"
            />
          </div>

          {error && (
            <div className="p-2 bg-red-500/10 border border-red-500/30 rounded-sm text-xs text-red-400" data-testid="login-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-full flex items-center justify-center gap-2 py-2"
            disabled={loading}
            data-testid="login-submit-btn"
          >
            {loading ? (
              <ArrowsClockwise size={16} className="spinner" />
            ) : (
              <Shield size={16} weight="fill" />
            )}
            {loading ? '登录中...' : '登录系统'}
          </button>
        </form>

        <div className="mt-6 text-center text-xs text-zinc-600">
          Powered by AI Event-Driven Trading Engine
        </div>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = localStorage.getItem('fx_token');
        if (token) {
          const userData = await authApi.meWithToken(token);
          setUser(userData);
        }
      } catch {
        localStorage.removeItem('fx_token');
      } finally {
        setAuthChecked(true);
      }
    };
    checkAuth();
  }, []);

  const handleLogout = async () => {
    await authApi.logout();
    localStorage.removeItem('fx_token');
    setUser(null);
  };

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <ArrowsClockwise size={24} className="spinner text-blue-500" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return <Dashboard user={user} onLogout={handleLogout} />;
}

function Dashboard({ user, onLogout }) {
  const [health, setHealth] = useState(null);
  const [prices, setPrices] = useState({});
  const [prevPrices, setPrevPrices] = useState({});
  const [priceHistory, setPriceHistory] = useState({});
  const [signals, setSignals] = useState({});
  const [eventState, setEventState] = useState(null);
  const [events, setEvents] = useState([]);
  const [settings, setSettings] = useState({});
  const [tradeStats, setTradeStats] = useState(null);
  const [brokerStatus, setBrokerStatus] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [drivers, setDrivers] = useState({});
  const [aiAnalyses, setAiAnalyses] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [backtestStats, setBacktestStats] = useState(null);
  const [backtestChartData, setBacktestChartData] = useState(null);
  const [monteCarloResult, setMonteCarloResult] = useState(null);
  const [mcLoading, setMcLoading] = useState(false);
  const [gridSearchResult, setGridSearchResult] = useState(null);
  const [gsLoading, setGsLoading] = useState(false);
  const [riskStatus, setRiskStatus] = useState(null);
  const [capitalProtection, setCapitalProtection] = useState(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const wsRef = useRef(null);

  // Initial data fetch
  const fetchInitialData = useCallback(async () => {
    try {
      const [
        healthData,
        audPrice,
        nzdPrice,
        audHistory,
        nzdHistory,
        signalsData,
        eventsData,
        settingsData,
        statsData,
        brokerData,
        dsData,
        driversData,
        aiData,
        btStats,
        btChartData,
        riskStatusData,
        capitalProtectionData
      ] = await Promise.all([
        api.health(),
        api.prices('AUD/USD'),
        api.prices('NZD/USD'),
        api.priceHistory('AUD/USD'),
        api.priceHistory('NZD/USD'),
        api.signals(),
        api.events(),
        api.settings(),
        api.trades(),
        api.brokerStatus(),
        api.dataSources(),
        api.drivers(),
        api.aiHistory(),
        api.backtestStats(),
        api.backtestChartData(),
        api.riskStatus(),
        api.riskCapitalProtection()
      ]);

      setHealth(healthData);
      setPrices({
        'AUD/USD': audPrice?.price,
        'NZD/USD': nzdPrice?.price,
      });
      setPriceHistory({
        'AUD/USD': audHistory?.prices || [],
        'NZD/USD': nzdHistory?.prices || [],
      });
      setSignals(signalsData?.signals || {});
      setEventState(signalsData?.event_state);
      setEvents(eventsData?.events || []);
      setSettings(settingsData || {});
      setTradeStats(statsData);
      setBrokerStatus(brokerData);
      setDataSources(dsData || []);
      setDrivers(driversData || {});
      setAiAnalyses(aiData?.analyses || []);
      setBacktestStats(btStats);
      setBacktestChartData(btChartData);
      setRiskStatus(riskStatusData);
      setCapitalProtection(capitalProtectionData);
    } catch (err) {
      console.error('Failed to fetch initial data:', err);
    }
  }, []);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = API_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/ws';
    
    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          
          switch (msg.type) {
            case 'price_update':
              const pair = msg.data.pair;
              setPrevPrices(prev => ({ ...prev, [pair]: prices[pair]?.mid }));
              setPrices(prev => ({ ...prev, [pair]: msg.data }));
              setPriceHistory(prev => {
                const history = prev[pair] || [];
                const newBar = {
                  timestamp: msg.data.timestamp,
                  open: msg.data.mid,
                  high: msg.data.mid,
                  low: msg.data.mid,
                  close: msg.data.mid,
                  ...msg.data.indicators
                };
                return { ...prev, [pair]: [...history.slice(-99), newBar] };
              });
              break;
            case 'signal':
              if (msg.data.pair) {
                setSignals(prev => ({ ...prev, [msg.data.pair]: msg.data }));
              } else {
                setSignals(msg.data);
              }
              break;
            case 'event_state':
              setEventState(msg.data);
              break;
            case 'setting_update':
              setSettings(prev => ({ ...prev, [msg.data.key]: msg.data.value }));
              break;
            case 'risk_status':
              setRiskStatus(msg.data);
              break;
            default:
              break;
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(connect, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };
    };

    fetchInitialData();
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [fetchInitialData]);

  // Handlers
  const handleTriggerEvent = async (level, title) => {
    try {
      const result = await api.triggerEvent(level, title);
      setEventState(result);
    } catch (err) {
      console.error('Failed to trigger event:', err);
    }
  };

  const handleResetEvent = async () => {
    try {
      const result = await api.resetEvent();
      setEventState(result);
    } catch (err) {
      console.error('Failed to reset event:', err);
    }
  };

  const handleUpdateSetting = async (key, value) => {
    try {
      await api.updateSetting(key, value);
      setSettings(prev => ({ ...prev, [key]: value }));
    } catch (err) {
      console.error('Failed to update setting:', err);
    }
  };

  const handleAIAnalyze = async (pair) => {
    setAiLoading(true);
    try {
      const result = await api.aiAnalyze(pair);
      setAiAnalyses(prev => [result, ...prev.slice(0, 9)]);
    } catch (err) {
      console.error('Failed to analyze:', err);
    } finally {
      setAiLoading(false);
    }
  };

  const handleMonteCarloSim = async (numSim, tradesPerSim) => {
    setMcLoading(true);
    try {
      const result = await api.monteCarloSim(numSim, tradesPerSim);
      setMonteCarloResult(result);
    } catch (err) {
      console.error('Failed to run Monte Carlo:', err);
    } finally {
      setMcLoading(false);
    }
  };

  const handleGridSearch = async () => {
    setGsLoading(true);
    try {
      const result = await api.gridSearch();
      setGridSearchResult(result);
    } catch (err) {
      console.error('Failed to run Grid Search:', err);
    } finally {
      setGsLoading(false);
    }
  };

  // Risk Control Handlers
  const handleTriggerEmergency = async (reason) => {
    setRiskLoading(true);
    try {
      const result = await api.triggerEmergency(reason);
      setRiskStatus(result);
      const cp = await api.riskCapitalProtection();
      setCapitalProtection(cp);
    } catch (err) {
      console.error('Failed to trigger emergency:', err);
    } finally {
      setRiskLoading(false);
    }
  };

  const handleEndCooldown = async () => {
    setRiskLoading(true);
    try {
      const result = await api.endCooldown();
      setRiskStatus(result);
    } catch (err) {
      console.error('Failed to end cooldown:', err);
    } finally {
      setRiskLoading(false);
    }
  };

  const handleAdvanceRestart = async () => {
    setRiskLoading(true);
    try {
      const result = await api.advanceRestart();
      setRiskStatus(result);
    } catch (err) {
      console.error('Failed to advance restart:', err);
    } finally {
      setRiskLoading(false);
    }
  };

  const handleResetRisk = async () => {
    setRiskLoading(true);
    try {
      const result = await api.resetRisk();
      setRiskStatus(result);
      const cp = await api.riskCapitalProtection();
      setCapitalProtection(cp);
    } catch (err) {
      console.error('Failed to reset risk:', err);
    } finally {
      setRiskLoading(false);
    }
  };

  const handleTelegramConfig = async (botToken, chatId) => {
    const result = await api.telegramConfig(botToken, chatId);
    return result;
  };

  const handleTelegramTest = async (message) => {
    await api.telegramTest(message);
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] p-2 md:p-4" data-testid="fx-trading-dashboard">
      {/* Header */}
      <header className="flex items-center justify-between mb-4 px-2">
        <div className="flex items-center gap-3">
          <Crosshair size={24} weight="bold" className="text-blue-500" />
          <h1 className="font-heading text-xl md:text-2xl font-bold uppercase tracking-tight">
            FX Trading System
          </h1>
          <span className="text-xs text-zinc-500">AUD/USD • NZD/USD</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-xs">
            {wsConnected ? (
              <>
                <Circle size={8} weight="fill" className="text-green-500" />
                <span className="text-green-500">LIVE</span>
              </>
            ) : (
              <>
                <Circle size={8} weight="fill" className="text-red-500" />
                <span className="text-red-500">OFFLINE</span>
              </>
            )}
          </div>
          <div className="text-xs text-zinc-500">
            {health?.data_source === 'simulated' ? '模拟数据' : 'Twelve Data'}
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span data-testid="user-email">{user?.email}</span>
            <button
              onClick={onLogout}
              className="btn text-xs flex items-center gap-1 px-2 py-1"
              data-testid="logout-btn"
            >
              <Power size={12} />
              退出
            </button>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-2 md:gap-4">
        {/* Left Column - Prices & Charts */}
        <div className="md:col-span-4 space-y-2 md:space-y-4">
          <Panel title="AUD/USD" icon={ChartLine}>
            <PriceDisplay 
              pair="AUD/USD" 
              price={prices['AUD/USD']} 
              indicators={prices['AUD/USD']?.indicators}
              prevPrice={prevPrices['AUD/USD']}
            />
            <div className="mt-3">
              <PriceChart data={priceHistory['AUD/USD']} pair="AUD/USD" />
            </div>
          </Panel>

          <Panel title="NZD/USD" icon={ChartLine}>
            <PriceDisplay 
              pair="NZD/USD" 
              price={prices['NZD/USD']} 
              indicators={prices['NZD/USD']?.indicators}
              prevPrice={prevPrices['NZD/USD']}
            />
            <div className="mt-3">
              <PriceChart data={priceHistory['NZD/USD']} pair="NZD/USD" />
            </div>
          </Panel>
        </div>

        {/* Middle Column - Signals & Events */}
        <div className="md:col-span-4 space-y-2 md:space-y-4">
          <Panel title="交易信号" icon={Pulse}>
            <div className="space-y-2">
              <SignalCard signal={signals['AUD/USD']} />
              <SignalCard signal={signals['NZD/USD']} />
            </div>
          </Panel>

          <Panel title="事件引擎" icon={Lightning}>
            <EventStatePanel 
              eventState={eventState}
              onTrigger={handleTriggerEvent}
              onReset={handleResetEvent}
            />
          </Panel>

          <Panel title="经济日历" icon={CalendarBlank}>
            <CalendarPanel events={events} />
          </Panel>
        </div>

        {/* Right Column - Settings & Stats */}
        <div className="md:col-span-4 space-y-2 md:space-y-4">
          <Panel title="高级风险控制" icon={FirstAid}>
            <AdvancedRiskControlPanel 
              riskStatus={riskStatus}
              capitalProtection={capitalProtection}
              onTriggerEmergency={handleTriggerEmergency}
              onEndCooldown={handleEndCooldown}
              onAdvanceRestart={handleAdvanceRestart}
              onReset={handleResetRisk}
              isLoading={riskLoading}
            />
          </Panel>

          <Panel title="AI分析" icon={Brain}>
            <AIAnalysisPanel 
              onAnalyze={handleAIAnalyze}
              analyses={aiAnalyses}
              isLoading={aiLoading}
            />
          </Panel>

          <Panel title="交易统计" icon={ChartBar}>
            <TradeStatsPanel stats={tradeStats} />
          </Panel>

          <Panel title="系统状态" icon={Database}>
            <BrokerStatusPanel 
              status={brokerStatus}
              dataSources={dataSources}
            />
          </Panel>
        </div>
      </div>

      {/* Bottom Row - Driver Weights & Backtest */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-4 mt-2 md:mt-4">
        <Panel title="宏观驱动因素" icon={Gauge}>
          <div className="grid grid-cols-2 gap-4">
            <DriverWeights drivers={drivers} pair="AUD/USD" />
            <DriverWeights drivers={drivers} pair="NZD/USD" />
          </div>
        </Panel>

        <Panel title="历史回测分析" icon={Clock}>
          <BacktestPanel stats={backtestStats} chartData={backtestChartData} />
        </Panel>
      </div>

      {/* Monte Carlo Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-4 mt-2 md:mt-4">
        <Panel title="蒙特卡洛模拟 (Monte Carlo Simulation)" icon={ChartBar}>
          <MonteCarloPanel 
            onRunSimulation={handleMonteCarloSim}
            simResult={monteCarloResult}
            isLoading={mcLoading}
          />
        </Panel>

        <Panel title="参数网格搜索 (Grid Search Optimization)" icon={Gear}>
          <GridSearchPanel 
            onRunSearch={handleGridSearch}
            searchResult={gridSearchResult}
            isLoading={gsLoading}
          />
        </Panel>
      </div>

      {/* Event Response Engine + Execution Gate Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-4 mt-2 md:mt-4">
        <Panel title="事件响应引擎 (Event Response Engine)" icon={Lightning}>
          <EventResponsePanel
            onTrigger={async (level, title) => {
              await api.eventResponseTrigger(level, title);
            }}
            onReset={async () => {
              await api.eventResponseReset();
            }}
          />
        </Panel>

        <Panel title="执行闸门 (Execution Gate)" icon={Shield}>
          <ExecutionGatePanel />
        </Panel>
      </div>

      {/* Strategy Monitor + Telegram + Settings Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 md:gap-4 mt-2 md:mt-4">
        <Panel title="策略健康监控 (Strategy Monitor)" icon={Heart}>
          <StrategyMonitorPanel />
        </Panel>

        <Panel title="Telegram 风险警报" icon={Bell}>
          <TelegramPanel
            onSaveConfig={handleTelegramConfig}
            onTestMessage={handleTelegramTest}
          />
        </Panel>

        <Panel title="风控设置" icon={ShieldCheck}>
          <SettingsPanel settings={settings} onUpdate={handleUpdateSetting} />
        </Panel>
      </div>
    </div>
  );
}

export default App;
