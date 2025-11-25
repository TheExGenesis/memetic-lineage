'use client';

interface VerticalSpineProps {
  label: string;
  onClick: () => void;
  isActive?: boolean;
}

export const VerticalSpine = ({ label, onClick, isActive = false }: VerticalSpineProps) => {
  return (
    <div 
      onClick={onClick}
      className={`
        h-full flex-shrink-0 w-12 border-r border-black bg-white 
        cursor-pointer hover:bg-gray-50 transition-colors
        flex flex-col items-center py-8 select-none
      `}
    >
      <div 
        className="writing-vertical-rl rotate-180 text-lg font-bold tracking-tight whitespace-nowrap overflow-hidden text-ellipsis max-h-full"
        style={{ writingMode: 'vertical-rl' }}
      >
        {label}
      </div>
    </div>
  );
};

