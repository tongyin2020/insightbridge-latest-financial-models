import React, { useState, useEffect, useCallback } from 'react';
import { Clock, CheckCircle2, XCircle, AlertTriangle, Play, ThumbsUp } from 'lucide-react';
import { useData } from '../context/DataContext';
import { apiGet } from '../hooks/useApi';

const LEVELS: { id: string; label: string; cooldown: number; color: string }[] = [
  { id: 'A', label: 'A级 (利率/GDP)', cooldown: 30, color: 'text-red-400 border-red-500 bg-red-500/10' },
  { id: 'B', label: 'B级 (就业/CPI)', cooldown: 20, color: 'text-amber-400 border-amber-500 bg-amber-500/10' },
  { id: 'C', label: 'C级 (PMI/零售)', cooldown: 10, color: 'text-blue-400 border-blue-500 bg-blue-500/10' },
];

export default function Confirmation() {
  const { eventState, triggerEvent, confirmEvent } = useData();
  const [selectedLevel, setSelectedLevel] = useState('A');
  const [historyEvents, setHistoryEvents] = useState<any[]>([]);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    apiGet('/events/history').then(setHistoryEvents).catch(() => setHistoryEvents([]));
  }, []);

  const handleTrigger = useCallback(async () => {
    setTriggering(true);
    await triggerEvent(selectedLevel);
    setTriggering(false);
  }, [selectedLevel, triggerEvent]);

  const handleConfirm = useCallback(async () => {
    await confirmEvent();
  }, [confirmEvent]);

  const countdown = eventState?.countdown ?? 0;
  const isActive = eventState?.active ?? false;
  const maxCountdown = LEVELS.find((l) => l.id === (eventState?.level || selectedLevel))?.cooldown || 30;
  const progress = isActive ? countdown / maxCountdown : 0;

  // SVG circle params
  const radius = 80;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - progress);

  const priceConfirmed = eventState?.price_confirmed ?? false;
  const spreadConfirmed = eventState?.spread_confirmed ?? false;
  const structureConfirmed = eventState?.structure_confirmed ?? false;
  const decision = eventState?.decision ?? '';

  const priceChange = eventState ? (eventState.current_price - eventState.pre_event_price) : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Level selector + trigger */}
        <div className="card">
          <h3 className="card-header flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> 事件级别选择
          </h3>
          <div className="space-y-2 mb-4">
            {LEVELS.map((level) => (
              <button
                key={level.id}
                onClick={() => setSelectedLevel(level.id)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  selectedLevel === level.id ? level.color : 'border-slate-700 bg-slate-900/50 text-slate-400'
                }`}
              >
                <div className="font-medium">{level.label}</div>
                <div className="text-xs mt-1 opacity-70">冷却时间: {level.cooldown}秒</div>
              </button>
            ))}
          </div>
          <button
            onClick={handleTrigger}
            disabled={isActive || triggering}
            className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            {triggering ? '触发中...' : '触发事件'}
          </button>
        </div>

        {/* Countdown timer */}
        <div className="card flex flex-col items-center justify-center">
          <h3 className="card-header self-start">倒计时</h3>
          <div className="relative w-48 h-48 my-4">
            <svg className="w-48 h-48 transform -rotate-90" viewBox="0 0 200 200">
              {/* Background circle */}
              <circle cx="100" cy="100" r={radius} fill="none" stroke="#334155" strokeWidth="8" />
              {/* Progress circle */}
              <circle
                cx="100" cy="100" r={radius}
                fill="none"
                stroke={isActive ? (countdown > 10 ? '#3b82f6' : countdown > 5 ? '#f59e0b' : '#ef4444') : '#475569'}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-4xl font-mono font-bold ${isActive ? 'text-white' : 'text-slate-500'}`}>
                {countdown}
              </span>
              <span className="text-xs text-slate-400 mt-1">秒</span>
            </div>
          </div>
          {isActive && (
            <div className="text-xs text-slate-400">
              事件级别: <span className="text-white font-medium">{eventState?.level}</span>
            </div>
          )}
        </div>

        {/* Confirmation indicators */}
        <div className="card">
          <h3 className="card-header flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" /> 确认指标
          </h3>
          <div className="space-y-4">
            {/* Price Direction */}
            <div className={`p-3 rounded-lg border ${priceConfirmed ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-slate-700 bg-slate-900/50'}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">价格方向</span>
                {priceConfirmed ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-slate-500" />
                )}
              </div>
              <div className={`text-lg font-mono mt-1 ${priceChange >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {priceChange >= 0 ? '+' : ''}{(priceChange * 10000).toFixed(1)} pips
              </div>
              <div className="text-xs text-slate-500 mt-1">
                事件前: {eventState?.pre_event_price?.toFixed(5) ?? '-'} | 当前: {eventState?.current_price?.toFixed(5) ?? '-'}
              </div>
            </div>

            {/* Spread Recovery */}
            <div className={`p-3 rounded-lg border ${spreadConfirmed ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-slate-700 bg-slate-900/50'}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">点差恢复</span>
                {spreadConfirmed ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-slate-500" />
                )}
              </div>
              <div className="text-lg font-mono mt-1 text-white">
                {eventState?.current_spread?.toFixed(1) ?? '-'} pips
              </div>
              <div className="text-xs text-slate-500 mt-1">
                阈值: {eventState?.spread_threshold?.toFixed(1) ?? '-'} pips
              </div>
            </div>

            {/* Structure Confirmation */}
            <div className={`p-3 rounded-lg border ${structureConfirmed ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-slate-700 bg-slate-900/50'}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">结构确认</span>
                {structureConfirmed ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-slate-500" />
                )}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                事件前区间: {eventState?.pre_event_range_low?.toFixed(5) ?? '-'} ~ {eventState?.pre_event_range_high?.toFixed(5) ?? '-'}
              </div>
              <div className="text-xs text-slate-500 mt-1">突破事件前高/低点</div>
            </div>
          </div>

          {/* Confirm button */}
          <button
            onClick={handleConfirm}
            disabled={!isActive}
            className="w-full mt-4 btn-success flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ThumbsUp className="w-4 h-4" />
            确认方向
          </button>

          {/* Decision output */}
          {decision && (
            <div className={`mt-3 p-3 rounded-lg text-center text-lg font-bold ${
              decision === 'allow' || decision === '允许开仓'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
            }`}>
              {decision === 'allow' || decision === '允许开仓' ? '允许开仓' : '继续观望'}
            </div>
          )}
        </div>
      </div>

      {/* Historical event replay */}
      <div className="card">
        <h3 className="card-header flex items-center gap-2">
          <Clock className="w-4 h-4" /> 历史事件回放
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-2">时间</th>
                <th className="text-left py-2 px-2">事件</th>
                <th className="text-center py-2 px-2">级别</th>
                <th className="text-center py-2 px-2">价格确认</th>
                <th className="text-center py-2 px-2">点差确认</th>
                <th className="text-center py-2 px-2">结构确认</th>
                <th className="text-left py-2 px-2">决策</th>
                <th className="text-right py-2 px-2">结果(pips)</th>
              </tr>
            </thead>
            <tbody>
              {historyEvents.length > 0 ? historyEvents.map((evt, i) => (
                <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-1.5 px-2 text-slate-400">{evt.datetime || evt.time}</td>
                  <td className="py-1.5 px-2 text-white">{evt.event || evt.name}</td>
                  <td className="py-1.5 px-2 text-center">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      evt.level === 'A' ? 'bg-red-500/20 text-red-400' :
                      evt.level === 'B' ? 'bg-amber-500/20 text-amber-400' : 'bg-blue-500/20 text-blue-400'
                    }`}>{evt.level}</span>
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {evt.price_confirmed ? <CheckCircle2 className="w-4 h-4 text-emerald-400 inline" /> : <XCircle className="w-4 h-4 text-slate-500 inline" />}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {evt.spread_confirmed ? <CheckCircle2 className="w-4 h-4 text-emerald-400 inline" /> : <XCircle className="w-4 h-4 text-slate-500 inline" />}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {evt.structure_confirmed ? <CheckCircle2 className="w-4 h-4 text-emerald-400 inline" /> : <XCircle className="w-4 h-4 text-slate-500 inline" />}
                  </td>
                  <td className="py-1.5 px-2">
                    <span className={evt.decision === 'allow' ? 'text-emerald-400' : 'text-amber-400'}>
                      {evt.decision === 'allow' ? '允许开仓' : '继续观望'}
                    </span>
                  </td>
                  <td className={`py-1.5 px-2 text-right font-mono ${(evt.result_pips || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {(evt.result_pips || 0) >= 0 ? '+' : ''}{(evt.result_pips || 0).toFixed(1)}
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-slate-500">暂无历史事件数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
