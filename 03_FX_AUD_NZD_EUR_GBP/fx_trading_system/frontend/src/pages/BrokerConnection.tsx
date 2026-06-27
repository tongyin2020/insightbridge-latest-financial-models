import React, { useEffect, useState } from 'react';
import { Plug, CheckCircle2, XCircle, RefreshCw, Server, Database, ArrowRight, Wifi } from 'lucide-react';
import { apiGet, apiPost } from '../hooks/useApi';

interface BrokerStatus {
  connected: boolean;
  name: string;
  latency?: number;
  last_heartbeat?: string;
}

interface DataSource {
  name: string;
  type: string;
  status: string;
  latency?: number;
  last_update?: string;
}

export default function BrokerConnection() {
  const [dukascopy, setDukascopy] = useState<BrokerStatus | null>(null);
  const [ib, setIb] = useState<BrokerStatus | null>(null);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [testing, setTesting] = useState<Record<string, boolean>>({});

  // Config fields
  const [dukConfig, setDukConfig] = useState({
    host: 'localhost',
    port: '10443',
    username: '',
    password: '',
    demo: true,
  });
  const [ibConfig, setIbConfig] = useState({
    host: '127.0.0.1',
    port: '7497',
    client_id: '1',
    gateway_mode: false,
  });

  useEffect(() => {
    apiGet('/broker/dukascopy/status').then(setDukascopy).catch(() => setDukascopy({ connected: false, name: 'Dukascopy' }));
    apiGet('/broker/ib/status').then(setIb).catch(() => setIb({ connected: false, name: 'Interactive Brokers' }));
    apiGet('/broker/datasources').then(setDataSources).catch(() => setDataSources([
      { name: 'Dukascopy SWFX', type: '价格数据', status: 'unknown' },
      { name: 'IB Econoday', type: '经济日历', status: 'unknown' },
      { name: 'IB Market Data', type: '备用价格', status: 'unknown' },
      { name: 'RBA Feed', type: '央行数据', status: 'unknown' },
      { name: 'RBNZ Feed', type: '央行数据', status: 'unknown' },
    ]));
  }, []);

  const testConnection = async (broker: string) => {
    setTesting((prev) => ({ ...prev, [broker]: true }));
    try {
      const config = broker === 'dukascopy' ? dukConfig : ibConfig;
      const result = await apiPost(`/broker/${broker}/test`, config);
      if (broker === 'dukascopy') setDukascopy(result);
      else setIb(result);
    } catch (err) {
      // Keep current state on error
    }
    setTesting((prev) => ({ ...prev, [broker]: false }));
  };

  const StatusDot = ({ connected }: { connected: boolean }) => (
    <span className={`inline-block w-3 h-3 rounded-full ${connected ? 'bg-emerald-400 shadow-lg shadow-emerald-400/50' : 'bg-red-400 shadow-lg shadow-red-400/50'}`} />
  );

  return (
    <div className="space-y-4">
      {/* Broker sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Dukascopy */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <Server className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Dukascopy</h3>
                <div className="flex items-center gap-2 text-xs">
                  <StatusDot connected={dukascopy?.connected ?? false} />
                  <span className={dukascopy?.connected ? 'text-emerald-400' : 'text-red-400'}>
                    {dukascopy?.connected ? '已连接' : '未连接'}
                  </span>
                  {dukascopy?.latency != null && (
                    <span className="text-slate-500">{dukascopy.latency}ms</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Host</label>
                <input
                  type="text"
                  value={dukConfig.host}
                  onChange={(e) => setDukConfig((p) => ({ ...p, host: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Port</label>
                <input
                  type="text"
                  value={dukConfig.port}
                  onChange={(e) => setDukConfig((p) => ({ ...p, port: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Username</label>
              <input
                type="text"
                value={dukConfig.username}
                onChange={(e) => setDukConfig((p) => ({ ...p, username: e.target.value }))}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                placeholder="JForex 用户名"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Password</label>
              <input
                type="password"
                value={dukConfig.password}
                onChange={(e) => setDukConfig((p) => ({ ...p, password: e.target.value }))}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                placeholder="JForex 密码"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={dukConfig.demo}
                onChange={(e) => setDukConfig((p) => ({ ...p, demo: e.target.checked }))}
                className="rounded border-slate-600"
              />
              模拟账户 (Demo)
            </label>
          </div>

          <div className="border-t border-slate-700 pt-3 mb-3">
            <div className="text-xs text-slate-400 mb-2">功能特性:</div>
            <div className="flex flex-wrap gap-1.5">
              {['SWFX 实时价格', 'ECN 执行', '低延迟', 'JForex API', '多货币对'].map((f) => (
                <span key={f} className="px-2 py-0.5 rounded bg-slate-700/50 text-[10px] text-slate-300">{f}</span>
              ))}
            </div>
          </div>

          <button
            onClick={() => testConnection('dukascopy')}
            disabled={testing.dukascopy}
            className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${testing.dukascopy ? 'animate-spin' : ''}`} />
            {testing.dukascopy ? '测试中...' : '测试连接'}
          </button>
        </div>

        {/* Interactive Brokers */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                <Server className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Interactive Brokers</h3>
                <div className="flex items-center gap-2 text-xs">
                  <StatusDot connected={ib?.connected ?? false} />
                  <span className={ib?.connected ? 'text-emerald-400' : 'text-red-400'}>
                    {ib?.connected ? '已连接' : '未连接'}
                  </span>
                  {ib?.latency != null && (
                    <span className="text-slate-500">{ib.latency}ms</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Host</label>
                <input
                  type="text"
                  value={ibConfig.host}
                  onChange={(e) => setIbConfig((p) => ({ ...p, host: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Port</label>
                <input
                  type="text"
                  value={ibConfig.port}
                  onChange={(e) => setIbConfig((p) => ({ ...p, port: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Client ID</label>
              <input
                type="text"
                value={ibConfig.client_id}
                onChange={(e) => setIbConfig((p) => ({ ...p, client_id: e.target.value }))}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={ibConfig.gateway_mode}
                onChange={(e) => setIbConfig((p) => ({ ...p, gateway_mode: e.target.checked }))}
                className="rounded border-slate-600"
              />
              IB Gateway 模式 (非 TWS)
            </label>
          </div>

          <div className="border-t border-slate-700 pt-3 mb-3">
            <div className="text-xs text-slate-400 mb-2">功能特性:</div>
            <div className="flex flex-wrap gap-1.5">
              {['Econoday 日历', '备用价格源', '账户管理', 'TWS/Gateway', '历史数据'].map((f) => (
                <span key={f} className="px-2 py-0.5 rounded bg-slate-700/50 text-[10px] text-slate-300">{f}</span>
              ))}
            </div>
          </div>

          <button
            onClick={() => testConnection('ib')}
            disabled={testing.ib}
            className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${testing.ib ? 'animate-spin' : ''}`} />
            {testing.ib ? '测试中...' : '测试连接'}
          </button>
        </div>
      </div>

      {/* Data flow architecture diagram */}
      <div className="card">
        <h3 className="card-header flex items-center gap-2">
          <Database className="w-4 h-4" /> 数据流架构
        </h3>
        <div className="flex flex-wrap items-center justify-center gap-3 py-6">
          {/* Data sources */}
          <div className="flex flex-col gap-2">
            <div className="px-4 py-2 rounded-lg border border-blue-500/50 bg-blue-500/10 text-blue-400 text-xs text-center">
              Dukascopy<br />SWFX
            </div>
            <div className="px-4 py-2 rounded-lg border border-purple-500/50 bg-purple-500/10 text-purple-400 text-xs text-center">
              IB TWS/<br />Gateway
            </div>
            <div className="px-4 py-2 rounded-lg border border-amber-500/50 bg-amber-500/10 text-amber-400 text-xs text-center">
              央行<br />数据源
            </div>
          </div>

          <ArrowRight className="w-6 h-6 text-slate-500" />

          {/* Processing */}
          <div className="px-6 py-4 rounded-xl border-2 border-slate-500 bg-slate-800 text-center">
            <div className="text-sm font-bold text-white mb-1">FX Engine</div>
            <div className="text-[10px] text-slate-400">FastAPI Backend</div>
            <div className="flex gap-1 mt-2 justify-center">
              <span className="px-1.5 py-0.5 rounded bg-slate-700 text-[9px] text-slate-300">信号生成</span>
              <span className="px-1.5 py-0.5 rounded bg-slate-700 text-[9px] text-slate-300">风控</span>
              <span className="px-1.5 py-0.5 rounded bg-slate-700 text-[9px] text-slate-300">执行</span>
            </div>
          </div>

          <ArrowRight className="w-6 h-6 text-slate-500" />

          {/* Frontend */}
          <div className="px-6 py-4 rounded-xl border-2 border-emerald-500/50 bg-emerald-500/10 text-center">
            <div className="text-sm font-bold text-emerald-400 mb-1">Dashboard</div>
            <div className="text-[10px] text-slate-400">React Frontend</div>
            <div className="flex gap-1 mt-2 justify-center">
              <span className="px-1.5 py-0.5 rounded bg-slate-700 text-[9px] text-slate-300">WebSocket</span>
              <span className="px-1.5 py-0.5 rounded bg-slate-700 text-[9px] text-slate-300">REST API</span>
            </div>
          </div>

          <ArrowRight className="w-6 h-6 text-slate-500" />

          {/* Output */}
          <div className="flex flex-col gap-2">
            <div className="px-4 py-2 rounded-lg border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 text-xs text-center">
              交易执行
            </div>
            <div className="px-4 py-2 rounded-lg border border-slate-500/50 bg-slate-500/10 text-slate-300 text-xs text-center">
              日志/监控
            </div>
          </div>
        </div>
      </div>

      {/* Data source status table */}
      <div className="card">
        <h3 className="card-header flex items-center gap-2">
          <Wifi className="w-4 h-4" /> 数据源状态
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700 text-xs">
                <th className="text-left py-2 px-3">数据源</th>
                <th className="text-left py-2 px-3">类型</th>
                <th className="text-center py-2 px-3">状态</th>
                <th className="text-right py-2 px-3">延迟</th>
                <th className="text-left py-2 px-3">最后更新</th>
              </tr>
            </thead>
            <tbody>
              {dataSources.map((ds, i) => (
                <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-2 px-3 text-white font-medium">{ds.name}</td>
                  <td className="py-2 px-3 text-slate-400">{ds.type}</td>
                  <td className="py-2 px-3 text-center">
                    {ds.status === 'connected' || ds.status === 'active' ? (
                      <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
                        <CheckCircle2 className="w-3.5 h-3.5" /> 正常
                      </span>
                    ) : ds.status === 'error' ? (
                      <span className="inline-flex items-center gap-1 text-red-400 text-xs">
                        <XCircle className="w-3.5 h-3.5" /> 错误
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-slate-500 text-xs">
                        <XCircle className="w-3.5 h-3.5" /> 未知
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-slate-300">
                    {ds.latency != null ? `${ds.latency}ms` : '-'}
                  </td>
                  <td className="py-2 px-3 text-slate-400 text-xs">
                    {ds.last_update ? new Date(ds.last_update).toLocaleString('zh-CN') : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
