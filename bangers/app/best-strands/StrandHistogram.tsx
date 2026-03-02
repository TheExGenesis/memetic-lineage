'use client';

import { memo } from 'react';

interface MonthInfo {
  year: number;
  month: number;
  date: string;
}

interface StrandData {
  strand_id: string;
  total_tweets: number;
  date_range: {
    start: string;
    end: string;
  };
  histogram: number[];
}

export interface HistogramData {
  generated_at: string;
  months: MonthInfo[];
  strands: Record<string, StrandData>;
}

interface StrandHistogramProps {
  strandData: StrandData | null;
  months: MonthInfo[];
  className?: string;
  showHeader?: boolean;
}

export const StrandHistogram = memo(function StrandHistogram({
  strandData,
  months,
  className = '',
  showHeader = false
}: StrandHistogramProps) {
  if (!strandData) {
    return (
      <div className={`flex items-center justify-center h-12 ${className}`}>
        <div className="text-xs text-gray-500">No data for this strand</div>
      </div>
    );
  }

  const { histogram, total_tweets } = strandData;
  const maxCount = Math.max(...histogram);

  if (maxCount === 0) {
    return (
      <div className={`flex items-center justify-center h-12 ${className}`}>
        <div className="text-xs text-gray-500">No tweets found</div>
      </div>
    );
  }

  const containerHeight = 32;
  const bars = histogram.map((count, index) => {
    let height = 0;
    if (maxCount > 0 && count > 0) {
      const proportionalHeight = (count / maxCount) * containerHeight;
      height = Math.max(proportionalHeight, 3);
    }

    const monthInfo = months[index];

    return (
      <div
        key={index}
        className="flex-1 flex flex-col-reverse items-center group relative min-w-0"
        title={monthInfo ? `${monthInfo.date}: ${count} tweets` : `${count} tweets`}
      >
        <div
          className={`transition-opacity duration-200 group-hover:opacity-70 ${
            count > 0 ? 'bg-black opacity-40' : 'bg-transparent'
          }`}
          style={{
            height: `${height}px`,
            width: '100%',
            minHeight: count > 0 ? '2px' : '0px'
          }}
        />

        {count > 0 && monthInfo && (
          <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-1 px-2 py-1 bg-black text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
            {monthInfo.date}: {count} tweets
          </div>
        )}
      </div>
    );
  });

  return (
    <div className={className}>
      {showHeader && (
        <div className="mb-1">
          <div className="text-xs text-gray-500">
            Timeline ({total_tweets} tweets)
          </div>
        </div>
      )}

      <div className="h-8 relative">
        <div className="h-full flex items-end">
          {bars}
        </div>
      </div>

      <div className="relative mt-1">
        <div className="flex justify-between text-xs text-gray-400">
          <span>2015</span>
          <span>2018</span>
          <span>2021</span>
          <span>2025</span>
        </div>
      </div>
    </div>
  );
});
