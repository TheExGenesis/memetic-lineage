'use client';

import { Tweet } from '@/lib/types';

interface VerticalSpineProps {
  tweet?: Tweet;
  label?: string;
  onClick: () => void;
  isActive?: boolean;
}

export const VerticalSpine = ({ tweet, label, onClick, isActive = false }: VerticalSpineProps) => {
  // Format date as YYYY-MM-DD
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toISOString().split('T')[0];
  };

  return (
    <div 
      onClick={onClick}
      className={`
        h-full flex-shrink-0 w-12 border-r border-black bg-white 
        cursor-pointer hover:bg-gray-50 transition-colors
        flex items-center justify-center py-8 select-none overflow-hidden
      `}
    >
      {tweet ? (
        <div>
        <div 
        className="rotate-180 text-right"
        style={{ writingMode: 'vertical-rl' }}>
          {/* Date - thin font weight at top of screen */}
          <span className="text-sm font-light tracking-tight">
            {formatDate(tweet.created_at)}
          </span>
          </div>
        <div 
          className="rotate-180 overflow-hidden max-h-full text-center"
          style={{ writingMode: 'vertical-rl' }}
        >

          {/* Username - bold with @ */}
          <span className="text-base font-bold tracking-tight">
            @{tweet.username} &nbsp;&nbsp;
          </span>
          {/* Tweet text - normal weight, truncated */}
          <span className="text-base font-normal tracking-tight">
            {tweet.full_text.slice(0, 30)}...
          </span>
          
          <span className="mx-2"> </span>
        
          
          <span className="mx-2"> </span>
        
        </div>

          </div>
      ) : (
        // Fallback for label-based spines (like "Bangers Home")
        <div 
          className="rotate-180 text-lg font-bold tracking-tight overflow-hidden max-h-full"
          style={{ writingMode: 'vertical-rl' }}
        >
          {label}
        </div>
      )}
    </div>
  );
};

