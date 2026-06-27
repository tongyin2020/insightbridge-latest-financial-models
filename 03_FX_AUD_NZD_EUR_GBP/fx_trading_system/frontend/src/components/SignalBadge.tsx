import React from 'react';

interface SignalBadgeProps {
  direction: string;
  confidence: number;
  size?: 'sm' | 'md' | 'lg';
}

export default function SignalBadge({ direction, confidence, size = 'md' }: SignalBadgeProps) {
  const dir = direction?.toUpperCase() || 'WAIT';
  const badgeClass =
    dir === 'BUY' ? 'badge-buy' : dir === 'SELL' ? 'badge-sell' : 'badge-wait';

  const barColor =
    dir === 'BUY' ? 'bg-emerald-500' : dir === 'SELL' ? 'bg-red-500' : 'bg-amber-500';

  const sizeClass = size === 'lg' ? 'text-base px-4 py-1' : size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-0.5';

  const label = dir === 'BUY' ? 'BUY /' : dir === 'SELL' ? 'SELL /' : 'WAIT /';
  const labelCn = dir === 'BUY' ? ' 做多' : dir === 'SELL' ? ' 做空' : ' 观望';

  return (
    <div className="flex flex-col gap-1.5">
      <span className={`${badgeClass} ${sizeClass} inline-flex items-center gap-1 w-fit`}>
        {label}{labelCn}
      </span>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-300`}
            style={{ width: `${Math.min(100, Math.max(0, confidence))}%` }}
          />
        </div>
        <span className="text-xs text-slate-400 font-mono w-10 text-right">
          {confidence.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}
