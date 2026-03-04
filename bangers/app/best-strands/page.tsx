import { Suspense } from 'react';
import { BestStrandsClient } from './BestStrandsClient';
import { loadAllStrands } from './loadStrands';

export default async function BestStrandsPage() {
  const strands = await loadAllStrands();

  if (strands.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No strands found. Run `python strands.py --export-only` to generate data.</p>
      </div>
    );
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strands...</div>}>
      <BestStrandsClient strands={strands} />
    </Suspense>
  );
}
