export default function Loading() {
  return (
    <div className="h-screen flex flex-col bg-white text-black">
      {/* Skeleton header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center gap-4">
          <div className="h-10 w-48 bg-gray-100 animate-pulse rounded" />
          <div className="flex gap-2 ml-auto">
            <div className="h-8 w-20 bg-gray-100 animate-pulse rounded" />
            <div className="h-8 w-20 bg-gray-100 animate-pulse rounded" />
          </div>
        </div>
      </div>

      {/* Skeleton columns */}
      <div className="flex-1 flex overflow-hidden p-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex-shrink-0 w-80">
            <div className="h-8 w-16 bg-gray-100 animate-pulse rounded mb-4" />
            <div className="space-y-4">
              {[1, 2, 3].map((j) => (
                <div key={j} className="border border-gray-200 p-4 rounded">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-8 h-8 bg-gray-100 animate-pulse rounded-full" />
                    <div className="h-4 w-24 bg-gray-100 animate-pulse rounded" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-4 w-full bg-gray-100 animate-pulse rounded" />
                    <div className="h-4 w-3/4 bg-gray-100 animate-pulse rounded" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
