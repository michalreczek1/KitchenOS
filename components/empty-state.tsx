'use client'

import { UtensilsCrossed, Calendar, ShoppingCart, Sparkles } from 'lucide-react'

interface EmptyStateProps {
  type: 'recipes' | 'planner' | 'shopping'
  title: string
  description: string
}

export function EmptyState({ type, title, description }: EmptyStateProps) {
  const getIcon = () => {
    switch (type) {
      case 'recipes':
        return <UtensilsCrossed className="h-16 w-16 icon-peach" />
      case 'planner':
        return <Calendar className="h-16 w-16 icon-sky" />
      case 'shopping':
        return <ShoppingCart className="h-16 w-16 icon-rose" />
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-6 flex h-28 w-28 items-center justify-center rounded-3xl border border-border bg-card shadow-sm">
        {getIcon()}
      </div>
      <h3 className="mb-2 text-xl font-semibold text-foreground">{title}</h3>
      <p className="max-w-sm text-muted-foreground">{description}</p>
      <div className="mt-4 flex items-center gap-2 text-sm text-primary">
        <Sparkles className="h-4 w-4" />
        <span>Dodaj przepis, aby rozpocząć</span>
      </div>
    </div>
  )
}
