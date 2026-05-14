export default function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden animate-pulse">
      <div className="aspect-square bg-gray-100" />
      <div className="p-4 flex flex-col gap-3">
        <div className="h-3 w-16 bg-gray-100 rounded" />
        <div className="h-4 w-3/4 bg-gray-100 rounded" />
        <div className="h-4 w-1/2 bg-gray-100 rounded" />
        <div className="flex justify-between items-center pt-1">
          <div className="h-6 w-20 bg-gray-100 rounded" />
          <div className="h-5 w-14 bg-gray-100 rounded-full" />
        </div>
      </div>
    </div>
  );
}
