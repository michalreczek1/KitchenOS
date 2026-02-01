'use client'

export function RecipeCardSkeleton() {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl">
      <div className="aspect-video w-full animate-pulse bg-secondary/50" />
      <div className="p-4">
        <div className="mb-2 h-5 w-3/4 animate-pulse rounded-lg bg-secondary/50" />
        <div className="h-4 w-1/2 animate-pulse rounded-lg bg-secondary/50" />
      </div>
      <div className="absolute top-3 right-3 flex gap-2">
        <div className="h-9 w-9 animate-pulse rounded-xl bg-secondary/50" />
        <div className="h-9 w-9 animate-pulse rounded-xl bg-secondary/50" />
      </div>
    </div>
  )
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/60 p-6 backdrop-blur-xl">
      <div className="mb-2 h-4 w-20 animate-pulse rounded-lg bg-secondary/50" />
      <div className="h-8 w-16 animate-pulse rounded-lg bg-secondary/50" />
    </div>
  )
}

export function PlannerItemSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border/50 bg-card/60 p-4 backdrop-blur-xl">
      <div className="h-16 w-16 animate-pulse rounded-xl bg-secondary/50" />
      <div className="flex-1">
        <div className="mb-2 h-5 w-2/3 animate-pulse rounded-lg bg-secondary/50" />
        <div className="h-4 w-1/3 animate-pulse rounded-lg bg-secondary/50" />
      </div>
      <div className="h-10 w-24 animate-pulse rounded-xl bg-secondary/50" />
    </div>
  )
}
