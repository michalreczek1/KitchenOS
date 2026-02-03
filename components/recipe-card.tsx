'use client'

import {
  Plus,
  Trash2,
  ExternalLink,
  UtensilsCrossed,
  Eye,
  Soup,
  Salad,
  Wheat,
  CakeSlice,
  Utensils,
} from 'lucide-react'
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid'
import { StarIcon as StarOutlineIcon } from '@heroicons/react/24/outline'
import type { Recipe, RecipeCategory } from '@/lib/api'
import { GENERIC_RECIPE_IMAGE_URL, getCustomRecipePlaceholder } from '@/lib/recipe-placeholders'

interface RecipeCardProps {
  recipe: Recipe
  onAddToPlanner: (recipe: Recipe) => void
  onDelete: (id: number) => void
  isInPlanner?: boolean
  onOpenPreview?: (id: number) => void
  showRating?: boolean
  onRate?: (id: number, rating: number) => void
}

export function RecipeCard({
  recipe,
  onAddToPlanner,
  onDelete,
  isInPlanner,
  onOpenPreview,
  showRating = false,
  onRate,
}: RecipeCardProps) {
  const CATEGORY_ICON_MAP: Record<RecipeCategory, { Icon: typeof UtensilsCrossed; className: string }> = {
    obiady: { Icon: Soup, className: 'text-amber-400' },
    salatki: { Icon: Salad, className: 'text-emerald-400' },
    pieczywo: { Icon: Wheat, className: 'text-yellow-500' },
    desery: { Icon: CakeSlice, className: 'text-rose-400' },
    inne: { Icon: Utensils, className: 'text-slate-400' },
  }

  const sourceUrl =
    (recipe as Recipe & { source_url?: string; url?: string }).source_url ??
    (recipe as Recipe & { url?: string }).url
  const isHttpUrl = (value?: string) => typeof value === 'string' && /^https?:\/\//i.test(value)
  const isCustom = !isHttpUrl(sourceUrl)
  const isGenericImage = recipe.image_url === GENERIC_RECIPE_IMAGE_URL
  const placeholderImage = isCustom ? getCustomRecipePlaceholder(recipe.category, recipe.title) : undefined
  const displayImage = recipe.image_url && !isGenericImage ? recipe.image_url : placeholderImage
  const categoryIcon = recipe.category ? CATEGORY_ICON_MAP[recipe.category] : null
  const FallbackIcon = categoryIcon?.Icon ?? UtensilsCrossed
  const fallbackIconClass = categoryIcon?.className ?? 'text-muted-foreground/30'
  const ratingValue = recipe.rating ?? 0

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all duration-300 hover:shadow-md">
      <div className="relative aspect-video w-full overflow-hidden bg-muted">
        {displayImage ? (
          <img
            src={displayImage}
            alt={recipe.title}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <FallbackIcon className={`h-12 w-12 ${fallbackIconClass}`} />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />
      </div>
      
      <div className="p-4">
        {showRating && (
          <div className="mb-2 flex items-center gap-1.5">
            {Array.from({ length: 5 }).map((_, index) => {
              const value = index + 1
              const isActive = value <= ratingValue
              return (
                <button
                  key={value}
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    onRate?.(recipe.id, value)
                  }}
                  className="group/star rounded-full p-1 transition-all hover:-translate-y-0.5 hover:bg-amber-50/80"
                  aria-label={`Oceń na ${value} gwiazdek`}
                >
                  {isActive ? (
                    <StarSolidIcon className="h-4 w-4 text-amber-500 drop-shadow-[0_2px_6px_rgba(245,158,11,0.35)] transition-all" />
                  ) : (
                    <StarOutlineIcon className="h-4 w-4 text-muted-foreground/40 transition-all group-hover/star:text-amber-400/70" />
                  )}
                </button>
              )
            })}
          </div>
        )}
        <h3 className="mb-1 line-clamp-2 text-base font-semibold text-foreground">
          {recipe.title}
        </h3>
        {isHttpUrl(sourceUrl) && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-primary"
          >
            <ExternalLink className="h-3 w-3" />
            <span className="truncate">{new URL(sourceUrl).hostname}</span>
          </a>
        )}
      </div>

      <div className="absolute top-3 right-3 flex gap-2 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
        {onOpenPreview && (
          <button
            onClick={(event) => {
              event.stopPropagation()
              onOpenPreview(recipe.id)
            }}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card shadow-sm text-muted-foreground transition-all hover:scale-105 hover:border-primary/40 hover:text-primary"
            title="PodglÄ…d przepisu"
          >
            <Eye className="h-4 w-4" />
          </button>
        )}
        <button
          onClick={(event) => {
            event.stopPropagation()
            onAddToPlanner(recipe)
          }}
          disabled={isInPlanner}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card shadow-sm icon-mint transition-all hover:scale-105 hover:bg-primary hover:text-primary-foreground disabled:opacity-50 disabled:hover:scale-100 disabled:hover:bg-card"
          title={isInPlanner ? 'Już w planerze' : 'Dodaj do planera'}
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          onClick={(event) => {
            event.stopPropagation()
            onDelete(recipe.id)
          }}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card shadow-sm icon-rose transition-all hover:scale-105 hover:bg-destructive hover:text-destructive-foreground"
          title="Usuń przepis"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
