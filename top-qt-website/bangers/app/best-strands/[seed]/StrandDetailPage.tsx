'use client'

import { useRouter } from 'next/navigation'
import { StrandWithTweet } from '@/lib/types'
import { StrandDetail } from '../StrandDetail'

export function StrandDetailPage({ strand }: { strand: StrandWithTweet }) {
  const router = useRouter()

  return (
    <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
      <StrandDetail
        strand={strand}
        onBack={() => router.push('/best-strands')}
      />
    </div>
  )
}
