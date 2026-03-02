'use client';

import { useRouter } from 'next/navigation';

interface BackButtonProps {
  fallbackHref?: string;
  label?: string;
  className?: string;
}

export function BackButton({ fallbackHref = '/', label, className = '' }: BackButtonProps) {
  const router = useRouter();

  const handleClick = () => {
    // Always navigate to the explicit hierarchy parent, not browser back
    router.push(fallbackHref);
  };

  return (
    <button
      onClick={handleClick}
      className={`p-2 hover:bg-gray-100 transition-colors border border-transparent hover:border-black flex items-center gap-2 ${className}`}
      title="Go back"
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 12H5" />
        <path d="M12 19l-7-7 7-7" />
      </svg>
      {label && <span className="text-sm">{label}</span>}
    </button>
  );
}
