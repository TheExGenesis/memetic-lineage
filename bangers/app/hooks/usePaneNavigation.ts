import { useRef, useEffect, useMemo } from 'react'

const SPINE_WIDTH_PX = 48

export function usePaneNavigation(selectedCount: number) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollContainerRef.current && selectedCount > 0) {
      setTimeout(() => {
        scrollContainerRef.current?.scrollTo({
          left: scrollContainerRef.current.scrollWidth,
          behavior: 'smooth'
        })
      }, 100)
    }
  }, [selectedCount])

  const isHomeCollapsed = selectedCount > 0
  const collapsedWidth = isHomeCollapsed ? (selectedCount * SPINE_WIDTH_PX) : 0

  const activePaneStyle = useMemo(() =>
    isHomeCollapsed
      ? { width: `calc(100vw - ${collapsedWidth}px)`, minWidth: '320px' }
      : { width: '500px' },
    [isHomeCollapsed, collapsedWidth]
  )

  return {
    scrollContainerRef,
    isHomeCollapsed,
    activePaneStyle,
  }
}











