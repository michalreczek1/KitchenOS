'use client'

import { Search, Filter } from 'lucide-react'
import { useMemo, useState } from 'react'
import { RECIPE_CATEGORIES, type Recipe, type RecipeCategory } from '@/lib/api'
import { RecipeCard } from '@/components/recipe-card'
import { RecipeCardSkeleton } from '@/components/skeletons'
import { EmptyState } from '@/components/empty-state'
import { RecipeModal } from '@/components/recipe-modal'

interface RecipesViewProps {
  recipes: Recipe[]
  isLoading: boolean
  plannerRecipeIds: number[]
  onAddToPlanner: (recipe: Recipe) => void
  onDeleteRecipe: (id: number) => void
}

export function RecipesView({
  recipes,
  isLoading,
  plannerRecipeIds,
  onAddToPlanner,
  onDeleteRecipe,
}: RecipesViewProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<RecipeCategory | null>(null)
  const [selectedRecipeId, setSelectedRecipeId] = useState<number | null>(null)

  const filteredRecipes = useMemo(() => {
    const normalizedQuery = searchQuery.toLowerCase()
    return recipes.filter((recipe) => {
      const matchesQuery = recipe.title.toLowerCase().includes(normalizedQuery)
      if (!matchesQuery) return false
      if (!activeCategory) return true
      const recipeCategory = recipe.category ?? 'inne'
      return recipeCategory === activeCategory
    })
  }, [recipes, searchQuery, activeCategory])

  const categoryStyles: Record<RecipeCategory, { base: string; active: string }> = {
    obiady: {
      base: 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100',
      active: 'border-amber-300 bg-amber-200 text-amber-900 shadow-[0_8px_18px_rgba(245,158,11,0.25)]',
    },
    salatki: {
      base: 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
      active: 'border-emerald-300 bg-emerald-200 text-emerald-900 shadow-[0_8px_18px_rgba(16,185,129,0.25)]',
    },
    pieczywo: {
      base: 'border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100',
      active: 'border-orange-300 bg-orange-200 text-orange-900 shadow-[0_8px_18px_rgba(249,115,22,0.25)]',
    },
    desery: {
      base: 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100',
      active: 'border-rose-300 bg-rose-200 text-rose-900 shadow-[0_8px_18px_rgba(244,63,94,0.25)]',
    },
    inne: {
      base: 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100',
      active: 'border-slate-300 bg-slate-200 text-slate-900 shadow-[0_8px_18px_rgba(148,163,184,0.25)]',
    },
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground">Eksplorator Przepisów</h1>
        <p className="text-muted-foreground">Przeglądaj i zarządzaj swoją kolekcją przepisów</p>
      </div>

      {/* Search Bar */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Szukaj przepisów..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-border/50 bg-card/60 py-3 pr-4 pl-12 text-foreground placeholder:text-muted-foreground backdrop-blur-xl transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
        <button className="flex h-12 w-12 items-center justify-center rounded-xl border border-border/50 bg-card/60 text-muted-foreground backdrop-blur-xl transition-all hover:border-primary/50 hover:text-primary">
          <Filter className="h-5 w-5" />
        </button>
      </div>

      {/* Category Tags */}
      <div className="flex flex-wrap gap-2">
        {RECIPE_CATEGORIES.map((category) => {
          const isActive = activeCategory === category.value
          return (
            <button
              key={category.value}
              type="button"
              onClick={() =>
                setActiveCategory((prev) => (prev === category.value ? null : category.value))
              }
              className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
                isActive ? categoryStyles[category.value].active : categoryStyles[category.value].base
              }`}
            >
              {category.label}
            </button>
          )
        })}
      </div>

      {/* Recipes Grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <RecipeCardSkeleton key={i} />
          ))}
        </div>
      ) : filteredRecipes.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredRecipes.map((recipe) => (
            <RecipeCard
              key={recipe.id}
              recipe={recipe}
              onAddToPlanner={onAddToPlanner}
              onDelete={onDeleteRecipe}
              isInPlanner={plannerRecipeIds.includes(recipe.id)}
              onOpenPreview={setSelectedRecipeId}
            />
          ))}
        </div>
      ) : recipes.length === 0 ? (
        <EmptyState
          type="recipes"
          title="Brak przepisów"
          description="Twoja kolekcja przepisów jest pusta. Dodaj pierwszy przepis używając URL lub ręcznie."
        />
      ) : (
        <div className="py-12 text-center">
          <p className="text-muted-foreground">Brak wyników dla &quot;{searchQuery}&quot;</p>
        </div>
      )}

      <RecipeModal recipeId={selectedRecipeId} onClose={() => setSelectedRecipeId(null)} />
    </div>
  )
}
