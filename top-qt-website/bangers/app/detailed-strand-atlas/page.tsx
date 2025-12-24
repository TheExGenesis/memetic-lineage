import { Suspense } from 'react';
import { AtlasClient } from './AtlasClient';

export const metadata = {
  title: 'Detailed Strand Atlas',
  robots: 'noindex', // Not linked from menu
};

export default function DetailedStrandAtlasPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading atlas data...</p>
        </div>
      </div>
    }>
      <AtlasClient />
    </Suspense>
  );
}
