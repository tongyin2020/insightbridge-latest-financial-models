import React, { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { Power, AlertOctagon, SlidersHorizontal, Eye, TrendingDown, DoorOpen } from 'lucide-react';
import { useData } from '../context/DataContext';
import { apiGet } from '../hooks/useApi';

const OVERRIDE_MODES = [
  { value: 'normal', label: '正常交易', icon: SlidersHorizontal, color: 'text-emerald-400 border-emerald-500 bg-emerald-500/10' },
  { value: 'observe', label: '只观察', icon: Eye, color: 'text-blue-400 border-blue-500 bg-blue-500/10' },
  { value: 'reduce', label: '只减仓', icon: TrendingDown, color: 'text-amber-400 border-amber-500 bg-amber-500/10' },
  { value: 'close_all', label: '全部平仓', icon: DoorOpen, color: 'text-red-400 border-red-500 bg-red-500/10' },
];

const DIRECTION_OPTIONS = [
  { value: 'long_only', label: '只做多' },
  { value: 'short_only', label: '只做空' },
  { value: 'paused', label: '暂停' },
];

interface SliderParam {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}

const SLIDERS: SliderParam[] = [
  { key: 'sma_period', label: 'SMA周期', min: 5, max: 100, step: 1, unit: '' },
  { key: 'adx_threshold', label: 'ADX阈值', min: 10, max: 50, step: 1, unit: '' },
  { key: 'atr_multiplier', label: 'ATR乘数', min: 0.5, max: 5, step: 0.1, unit: 'x' },
  { key: 'max_hold_minutes', label: '最大持仓时间', min: 5, max: 480, step: 5, unit: '分钟' },
  { key: 'stop_loss_pips', label: '止损点数', min: 5, max: 100, step: 1, unit: 'pips' },
  { key: 'take_profit_pips', label: '止盈点数', min: 5, max: 200, step: 1, unit: 'pips' },
];

export default function ModelSettings() {
  const { settings, updateSetting } = useData();
  const [driverWeights, setDriverWeights] = useState<any>(null);
  const [regime, setRegime] = useState<any>(null);

  useEffect(() => {
    apiGet('/model/drivers').then(setDriverWeights).catch(() => {});
    apiGet('/model/regime').then(setRegime).catch(() => {});
  }, []);

  const killSwitch = settings.kill_switch === 'true' || settings.kill_switch === true;
  const overrideMode = (settings.override_mode || 'NORMAL').toString().toUpperCase();
  const audDirection = (settings.aud_usd_direction || 'LONG_ONLY').toString().toUpperCase();
  const nzdDirection = (settings.nzd_usd_direction || 'LONG_ONLY').toString().toUpperCase();

  const renderDriverChart = (pair: string, weights: any) => {
    if (!weights) return null;
    // Handle both array [{factor, weight}] and object {name: value} formats
    const data = Array.isArray(weights)
      ? weights.map((w: any) => ({ name: w.factor || w.name, value: w.weight || w.value }))
      : Object.entries(weights).map(([name, value]) => ({ name, value: value as number }));
    return (
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis type="number" stroke="#64748b" tick={{ fontSize: 10 }} domain={[-1, 1]} />
            <YAxis type="category" dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} width={80} />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.value >= 0 ? '#10b981' : '#ef4444'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Kill switch + Override mode */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Kill Switch */}
        <div className={`card border-2 ${killSwitch ? 'border-red-500 bg-red-500/5' : 'border-slate-700'}`}>
          <h3 className="card-header flex items-center gap-2">
            <AlertOctagon className="w-4 h-4 text-red-400" /> 紧急停止开关
          </h3>
          <p className="text-xs text-slate-400 mb-4">启用后立即停止所有新开仓操作</p>
          <button
            onClick={() => updateSetting('kill_switch', !killSwitch)}
            className={`w-full py-4 rounded-xl text-lg font-bold flex items-center justify-center gap-3 transition-all ${
              killSwitch
                ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/25'
                : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
            }`}
          >
            <Power className="w-6 h-6" />
            {killSwitch ? '紧急停止已启用 - 点击关闭' : '点击启用紧急停止'}
          </button>
        </div>

        {/* Override mode */}
        <div className="card">
          <h3 className="card-header flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4" /> 覆盖模式
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {OVERRIDE_MODES.map((mode) => {
              const Icon = mode.icon;
              const isActive = overrideMode === mode.value;
              return (
                <button
                  key={mode.value}
                  onClick={() => updateSetting('override_mode', mode.value)}
                  className={`p-3 rounded-lg border text-left transition-colors ${
                    isActive ? mode.color : 'border-slate-700 bg-slate-900/50 text-slate-400'
                  }`}
                >
                  <Icon className="w-5 h-5 mb-1" />
                  <div className="text-sm font-medium">{mode.label}</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Direction control for each pair */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[
          { pair: 'AUD/USD', key: 'aud_usd_direction', value: audDirection },
          { pair: 'NZD/USD', key: 'nzd_usd_direction', value: nzdDirection },
        ].map(({ pair, key, value }) => (
          <div key={key} className="card">
            <h3 className="card-header">{pair} 方向控制</h3>
            <div className="flex gap-2">
              {DIRECTION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => updateSetting(key, opt.value)}
                  className={`flex-1 py-3 rounded-lg text-sm font-medium transition-colors ${
                    value === opt.value
                      ? opt.value === 'long_only'
                        ? 'bg-emerald-600 text-white'
                        : opt.value === 'short_only'
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Parameter sliders */}
      <div className="card">
        <h3 className="card-header flex items-center gap-2">
          <SlidersHorizontal className="w-4 h-4" /> 模型参数
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {SLIDERS.map((s) => {
            const val = settings[s.key] ?? s.min;
            return (
              <div key={s.key}>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-slate-300">{s.label}</label>
                  <span className="text-sm font-mono text-blue-400">
                    {typeof val === 'number' ? (Number.isInteger(s.step) ? val : val.toFixed(1)) : val}
                    {s.unit && <span className="text-slate-500 ml-1">{s.unit}</span>}
                  </span>
                </div>
                <input
                  type="range"
                  min={s.min}
                  max={s.max}
                  step={s.step}
                  value={val}
                  onChange={(e) => updateSetting(s.key, parseFloat(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                  <span>{s.min}{s.unit}</span>
                  <span>{s.max}{s.unit}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Driver weights + Regime */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="card-header">AUD/USD 驱动因子权重</h3>
          {(driverWeights?.['AUD/USD'] || driverWeights?.aud_usd) ? renderDriverChart('aud_usd', driverWeights['AUD/USD'] || driverWeights.aud_usd) : (
            <div className="h-40 flex items-center justify-center text-slate-500">暂无数据</div>
          )}
        </div>
        <div className="card">
          <h3 className="card-header">NZD/USD 驱动因子权重</h3>
          {(driverWeights?.['NZD/USD'] || driverWeights?.nzd_usd) ? renderDriverChart('nzd_usd', driverWeights['NZD/USD'] || driverWeights.nzd_usd) : (
            <div className="h-40 flex items-center justify-center text-slate-500">暂无数据</div>
          )}
        </div>
        <div className="card">
          <h3 className="card-header">市场状态检测</h3>
          {regime ? (
            <div className="space-y-3">
              <div className="p-3 rounded-lg bg-slate-900/50">
                <div className="text-xs text-slate-400 mb-1">当前状态</div>
                <div className={`text-xl font-bold ${
                  regime.current === 'trending' ? 'text-blue-400' :
                  regime.current === 'ranging' ? 'text-amber-400' :
                  regime.current === 'volatile' ? 'text-red-400' : 'text-slate-300'
                }`}>
                  {regime.current === 'trending' ? '趋势' :
                   regime.current === 'ranging' ? '震荡' :
                   regime.current === 'volatile' ? '高波动' : regime.current}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2 rounded bg-slate-900/50">
                  <div className="text-slate-400">ADX</div>
                  <div className="text-white font-mono">{regime.adx?.toFixed(1) ?? '-'}</div>
                </div>
                <div className="p-2 rounded bg-slate-900/50">
                  <div className="text-slate-400">ATR</div>
                  <div className="text-white font-mono">{regime.atr?.toFixed(5) ?? '-'}</div>
                </div>
                <div className="p-2 rounded bg-slate-900/50">
                  <div className="text-slate-400">波动率分位</div>
                  <div className="text-white font-mono">{regime.vol_percentile?.toFixed(0) ?? '-'}%</div>
                </div>
                <div className="p-2 rounded bg-slate-900/50">
                  <div className="text-slate-400">趋势强度</div>
                  <div className="text-white font-mono">{regime.trend_strength?.toFixed(2) ?? '-'}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-500">暂无数据</div>
          )}
        </div>
      </div>
    </div>
  );
}
