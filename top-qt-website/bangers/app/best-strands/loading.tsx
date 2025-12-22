export default function Loading() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Skeleton header */}
        <header className="mb-8 border-b-4 border-black pb-4">
          <div className="flex items-center gap-4 mb-2">
            <div className="w-10 h-10 bg-gray-200 animate-pulse rounded" />
            <div>
              <div className="h-8 w-32 bg-gray-200 animate-pulse rounded mb-2" />
              <div className="h-4 w-96 bg-gray-100 animate-pulse rounded" />
            </div>
          </div>
        </header>

        {/* Skeleton strand cards */}
        <div className="flex flex-col gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white border-2 border-black shadow-[4px_4px_0_0_#000]"
            >
              <div className="flex items-stretch">
                {/* Tweet Card skeleton */}
                <div className="w-[35%] p-4 border-r-2 border-black">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-8 h-8 bg-gray-200 animate-pulse rounded-full" />
                    <div className="h-4 w-24 bg-gray-200 animate-pulse rounded" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-4 w-full bg-gray-100 animate-pulse rounded" />
                    <div className="h-4 w-3/4 bg-gray-100 animate-pulse rounded" />
                    <div className="h-4 w-1/2 bg-gray-100 animate-pulse rounded" />
                  </div>
                </div>

                {/* Summary Card skeleton */}
                <div className="w-[65%] p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-12 h-8 bg-gray-200 animate-pulse rounded" />
                    <div className="flex gap-2">
                      <div className="h-4 w-20 bg-gray-100 animate-pulse rounded" />
                      <div className="h-4 w-20 bg-gray-100 animate-pulse rounded" />
                      <div className="h-4 w-20 bg-gray-100 animate-pulse rounded" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="h-4 w-full bg-gray-100 animate-pulse rounded" />
                    <div className="h-4 w-full bg-gray-100 animate-pulse rounded" />
                    <div className="h-4 w-2/3 bg-gray-100 animate-pulse rounded" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
