'use client'

import { Search, Filter } from 'lucide-react'
import { useState } from 'react'
import type { Recipe } from '@/lib/api'
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
  const [selectedRecipeId, setSelectedRecipeId] = useState<number | null>(null)

  const filteredRecipes = recipes.filter((recipe) =>
    recipe.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

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
