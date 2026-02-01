'use client'

import { useEffect, useState } from 'react'
import { X, Clock, Users, ExternalLink, UtensilsCrossed, Loader2, PenLine } from 'lucide-react'
import { fetchRecipeDetails, type RecipeDetails } from '@/lib/api'

interface RecipeModalProps {
  recipeId: number | null
  onClose: () => void
}

const normalizeToList = (value: string[] | string | null | undefined) => {
  if (!value) return []
  if (Array.isArray(value)) return value
  return value.split(/\r?\n+/).map((entry) => entry.trim()).filter(Boolean)
}

export function RecipeModal({ recipeId, onClose }: RecipeModalProps) {
  const [recipe, setRecipe] = useState<RecipeDetails | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const GENERIC_ICON_URL = 'https://cdn-icons-png.flaticon.com/512/3081/3081557.png'
  const sourceUrl =
    (recipe as RecipeDetails & { source_url?: string; url?: string } | null)?.source_url ??
    (recipe as RecipeDetails & { url?: string } | null)?.url
  const isHttpUrl = (value?: string) => typeof value === 'string' && /^https?:\/\//i.test(value)
  const shouldShowImage = !!recipe?.image_url && recipe.image_url !== GENERIC_ICON_URL

  const normalizedIngredients = normalizeToList(recipe?.ingredients)
  const normalizedInstructions = normalizeToList(recipe?.instructions)

  useEffect(() => {
    if (!recipeId) {
      setRecipe(null)
      return
    }

    setIsLoading(true)
    setError(null)

    fetchRecipeDetails(recipeId)
      .then(setRecipe)
      .catch(() => setError('Nie udało się załadować szczegółów przepisu'))
      .finally(() => setIsLoading(false))
  }, [recipeId])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!recipeId) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-card/80 text-muted-foreground backdrop-blur-sm transition-colors hover:bg-card hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 p-6">
            <UtensilsCrossed className="h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">{error}</p>
          </div>
        ) : recipe ? (
          <div className="overflow-y-auto max-h-[90vh]">
            {/* Image */}
            {shouldShowImage && (
              <div className="relative aspect-video w-full overflow-hidden">
                <img
                  src={recipe.image_url || "/placeholder.svg"}
                  alt={recipe.title}
                  className="h-full w-full object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent" />
              </div>
            )}

            <div className="p-6 space-y-6">
              {/* Header */}
              <div>
                <h2 className="text-2xl font-bold text-foreground">{recipe.title}</h2>
                <div className="mt-3 flex flex-wrap gap-3">
                  {recipe.prep_time && (
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Clock className="h-4 w-4 icon-peach" />
                      <span>Przygotowanie: {recipe.prep_time}</span>
                    </div>
                  )}
                  {recipe.cook_time && (
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Clock className="h-4 w-4 icon-rose" />
                      <span>Gotowanie: {recipe.cook_time}</span>
                    </div>
                  )}
                  {recipe.servings && (
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Users className="h-4 w-4 icon-sky" />
                      <span>{recipe.servings} porcji</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Ingredients */}
              {normalizedIngredients.length > 0 && (
                <div>
                  <h3 className="mb-3 font-semibold text-foreground">Składniki</h3>
                  <ul className="space-y-2">
                    {normalizedIngredients.map((ingredient, index) => (
                      <li key={index} className="flex items-start gap-2 text-sm">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary" />
                        <span className="text-muted-foreground">{ingredient}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Instructions */}
              {normalizedInstructions.length > 0 && (
                <div>
                  <h3 className="mb-3 font-semibold text-foreground">Instrukcje</h3>
                  <ol className="space-y-3">
                    {normalizedInstructions.map((step, index) => (
                      <li key={index} className="flex gap-3 text-sm">
                        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                          {index + 1}
                        </span>
                        <span className="text-muted-foreground pt-0.5">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Source Link */}
              {isHttpUrl(sourceUrl) ? (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-primary hover:underline"
                >
                  <ExternalLink className="h-4 w-4" />
                  Zobacz oryginalny przepis
                </a>
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <PenLine className="h-4 w-4" />
                  Przepis własny — brak linku źródłowego
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
