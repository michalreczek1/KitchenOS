'use client'

import { Search, Filter } from 'lucide-react'
import { useMemo, useState } from 'react'
import { RECIPE_CATEGORIES, type Recipe, type RecipeCategory } from '@/lib/api'
import { allCategoryStyles, categoryStyles } from '@/lib/recipe-category-styles'
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
  onRateRecipe: (id: number, rating: number) => void
}

export function RecipesView({
  recipes,
  isLoading,
  plannerRecipeIds,
  onAddToPlanner,
  onDeleteRecipe,
  onRateRecipe,
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

  const allStyles = allCategoryStyles

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground">Twoje przepisy</h1>
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
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
            activeCategory === null ? allStyles.active : allStyles.base
          }`}
        >
          Wszystkie
        </button>
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
              showRating
              onRate={onRateRecipe}
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
