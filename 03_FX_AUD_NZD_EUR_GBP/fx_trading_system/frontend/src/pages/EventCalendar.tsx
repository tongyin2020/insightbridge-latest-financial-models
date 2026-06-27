import React, { useState, useMemo } from 'react';
import { CalendarDays, Filter, Newspaper } from 'lucide-react';
import { useApi } from '../hooks/useApi';

const COUNTRIES = [
  { code: 'AU', flag: '🇦🇺', name: '澳大利亚' },
  { code: 'NZ', flag: '🇳🇿', name: '新西兰' },
  { code: 'US', flag: '🇺🇸', name: '美国' },
  { code: 'CN', flag: '🇨🇳', name: '中国' },
];

const IMPACT_LEVELS = ['A', 'B', 'C'];

export default function EventCalendar() {
  const { data: events, loading: eventsLoading } = useApi<any[]>('/events');
  const { data: news } = useApi<any[]>('/news');

  const [filterImpact, setFilterImpact] = useState<string[]>(['A', 'B', 'C']);
  const [filterCountry, setFilterCountry] = useState<string[]>(['AU', 'NZ', 'US', 'CN']);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const toggleFilter = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const eventsList = Array.isArray(events) ? events : (events as any)?.events ?? [];

  const filteredEvents = useMemo(() => {
    if (!eventsList || eventsList.length === 0) return [];
    return eventsList.filter((evt: any) => {
      if (!filterImpact.includes(evt.impact)) return false;
      if (!filterCountry.includes(evt.country)) return false;
      if (dateFrom && evt.datetime && evt.datetime < dateFrom) return false;
      if (dateTo && evt.datetime && evt.datetime > dateTo) return false;
      return true;
    });
  }, [eventsList, filterImpact, filterCountry, dateFrom, dateTo]);

  const getCountryFlag = (code: string) => {
    const c = COUNTRIES.find((x) => x.code === code);
    return c ? c.flag : code;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      {/* Main calendar area */}
      <div className="lg:col-span-3 space-y-4">
        {/* Filters */}
        <div className="card">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-slate-400" />
              <span className="text-sm text-slate-400">影响级别:</span>
              {IMPACT_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => toggleFilter(filterImpact, level, setFilterImpact)}
                  className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${
                    filterImpact.includes(level)
                      ? level === 'A' ? 'bg-red-500/30 text-red-400 border border-red-500/50'
                        : level === 'B' ? 'bg-amber-500/30 text-amber-400 border border-amber-500/50'
                        : 'bg-blue-500/30 text-blue-400 border border-blue-500/50'
                      : 'bg-slate-700 text-slate-500 border border-slate-600'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">国家:</span>
              {COUNTRIES.map((c) => (
                <button
                  key={c.code}
                  onClick={() => toggleFilter(filterCountry, c.code, setFilterCountry)}
                  className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                    filterCountry.includes(c.code)
                      ? 'bg-slate-600 text-white border border-slate-500'
                      : 'bg-slate-800 text-slate-500 border border-slate-700'
                  }`}
                >
                  {c.flag} {c.code}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">日期:</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-white"
              />
              <span className="text-slate-500">~</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-white"
              />
            </div>
          </div>
        </div>

        {/* Events table */}
        <div className="card">
          <h3 className="card-header flex items-center gap-2">
            <CalendarDays className="w-4 h-4" /> 经济日历
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700 text-xs">
                  <th className="text-left py-2 px-2">时间</th>
                  <th className="text-left py-2 px-2">国家</th>
                  <th className="text-left py-2 px-2">事件</th>
                  <th className="text-center py-2 px-2">影响</th>
                  <th className="text-right py-2 px-2">预测</th>
                  <th className="text-right py-2 px-2">前值</th>
                  <th className="text-right py-2 px-2">实际</th>
                </tr>
              </thead>
              <tbody>
                {eventsLoading ? (
                  <tr><td colSpan={7} className="py-8 text-center text-slate-500">加载中...</td></tr>
                ) : filteredEvents.length > 0 ? (
                  filteredEvents.map((evt, i) => (
                    <tr
                      key={i}
                      className={`border-b border-slate-700/50 hover:bg-slate-700/30 ${
                        evt.impact === 'A' ? 'border-l-2 border-l-red-500' : ''
                      }`}
                    >
                      <td className="py-2 px-2 text-slate-300 text-xs font-mono whitespace-nowrap">
                        {evt.time || (evt.datetime ? new Date(evt.datetime).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-')}
                      </td>
                      <td className="py-2 px-2">
                        <span className="text-base">{getCountryFlag(evt.country)}</span>
                        <span className="text-xs text-slate-400 ml-1">{evt.country}</span>
                      </td>
                      <td className="py-2 px-2 text-white">{evt.event || evt.name}</td>
                      <td className="py-2 px-2 text-center">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                          evt.impact === 'A' ? 'bg-red-500/20 text-red-400' :
                          evt.impact === 'B' ? 'bg-amber-500/20 text-amber-400' :
                          'bg-blue-500/20 text-blue-400'
                        }`}>
                          {evt.impact}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right font-mono text-slate-300">{evt.forecast ?? '-'}</td>
                      <td className="py-2 px-2 text-right font-mono text-slate-400">{evt.previous ?? '-'}</td>
                      <td className={`py-2 px-2 text-right font-mono font-medium ${
                        evt.actual != null && evt.forecast != null
                          ? evt.actual > evt.forecast ? 'text-emerald-400' : evt.actual < evt.forecast ? 'text-red-400' : 'text-white'
                          : 'text-slate-500'
                      }`}>
                        {evt.actual ?? '-'}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={7} className="py-8 text-center text-slate-500">暂无事件数据</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* News sidebar */}
      <div className="card h-fit">
        <h3 className="card-header flex items-center gap-2">
          <Newspaper className="w-4 h-4" /> 新闻动态
        </h3>
        <div className="space-y-3">
          {(Array.isArray(news) ? news : (news as any)?.news ?? []).length > 0 ? (
            (Array.isArray(news) ? news : (news as any)?.news ?? []).map((item: any, i: number) => (
              <div key={i} className="p-2 rounded-lg bg-slate-900/50 border border-slate-700/50">
                <div className="text-xs text-slate-500 mb-1">{item.time || item.datetime}</div>
                <div className="text-sm text-white leading-tight">{item.title || item.headline}</div>
                {item.summary && (
                  <div className="text-xs text-slate-400 mt-1 line-clamp-2">{item.summary}</div>
                )}
                {item.impact && (
                  <span className={`inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    item.impact === 'positive' ? 'bg-emerald-500/20 text-emerald-400' :
                    item.impact === 'negative' ? 'bg-red-500/20 text-red-400' :
                    'bg-slate-600/30 text-slate-400'
                  }`}>
                    {item.impact === 'positive' ? '利好' : item.impact === 'negative' ? '利空' : '中性'}
                  </span>
                )}
              </div>
            ))
          ) : (
            <div className="text-slate-500 text-sm">暂无新闻</div>
          )}
        </div>
      </div>
    </div>
  );
}
