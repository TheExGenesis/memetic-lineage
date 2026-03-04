import { Suspense } from 'react'
import { notFound } from 'next/navigation'
import { StrandDetailPage } from './StrandDetailPage'
import { loadStrandBySeed } from '../loadStrands'

interface PageProps {
  params: Promise<{ seed: string }>
}

export default async function StrandByIdPage({ params }: PageProps) {
  const { seed } = await params
  const strand = await loadStrandBySeed(seed)

  if (!strand) {
    notFound()
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strand...</div>}>
      <StrandDetailPage strand={strand} />
    </Suspense>
  )
}
