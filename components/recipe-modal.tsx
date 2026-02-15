'use client'

import { useEffect, useMemo, useState } from 'react'
import { X, Clock, Users, ExternalLink, UtensilsCrossed, Loader2, PenLine, Info } from 'lucide-react'
import { fetchRecipeDetails, RECIPE_CATEGORIES, type RecipeCategory, type RecipeDetails } from '@/lib/api'
import { categoryStyles } from '@/lib/recipe-category-styles'
import { getCustomRecipeCategoryMap, saveCustomRecipeCategory } from '@/lib/custom-recipe-categories'

interface RecipeModalProps {
  recipeId: number | null
  onClose: () => void
}

const normalizeToList = (value: string[] | string | null | undefined) => {
  if (!value) return []
  if (Array.isArray(value)) return value
  return value.split(/\r?\n+/).map((entry) => entry.trim()).filter(Boolean)
}

const getPolishPluralForm = (count: number, singular: string, few: string, many: string) => {
  const absCount = Math.abs(count)
  const mod10 = absCount % 10
  const mod100 = absCount % 100
  if (absCount === 1) return singular
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

const formatPortionsLabel = (count: number, unit: 'servings' | 'people') => {
  const unitLabel =
    unit === 'people'
      ? getPolishPluralForm(count, 'osoba', 'osoby', 'osób')
      : getPolishPluralForm(count, 'porcja', 'porcje', 'porcji')
  return `${count} ${unitLabel}`
}

const formatNutritionValue = (value?: number | null, suffix = 'g') => {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  return suffix ? `${value.toFixed(1)} ${suffix}` : value.toFixed(1)
}

const formatWeightLabel = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  const rounded = Math.round(value * 10) / 10
  if (Math.abs(rounded - Math.round(rounded)) < 0.001) {
    return `${Math.round(rounded)} g`
  }
  return `${rounded.toFixed(1)} g`
}

const normalizeKeywordText = (value?: string | null) =>
  (value ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')

export function RecipeModal({ recipeId, onClose }: RecipeModalProps) {
  const [recipe, setRecipe] = useState<RecipeDetails | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<RecipeCategory>('inne')

  const GENERIC_ICON_URL = 'https://cdn-icons-png.flaticon.com/512/3081/3081557.png'
  const sourceUrl =
    (recipe as (RecipeDetails & { source_url?: string; url?: string }) | null)?.source_url ??
    (recipe as (RecipeDetails & { url?: string }) | null)?.url
  const isHttpUrl = (value?: string) => typeof value === 'string' && /^https?:\/\//i.test(value)
  const shouldShowImage = !!recipe?.image_url && recipe.image_url !== GENERIC_ICON_URL

  const normalizedIngredients = normalizeToList(recipe?.ingredients)
  const normalizedInstructions = normalizeToList(recipe?.instructions)
  const basePortions = Math.max(1, recipe?.servings ?? recipe?.base_portions ?? 1)
  const servingsUnit = recipe?.servings_unit === 'people' ? 'people' : 'servings'
  const yieldDisplayLabel = recipe?.yield_display_label?.trim() || null
  const yieldAssumptionReason = recipe?.yield_assumption_reason?.trim() || null
  const totalWeightLabel = formatWeightLabel(recipe?.total_weight_g)
  const portionWeightLabel = formatWeightLabel(recipe?.portion_weight_g)
  const pieceWeightLabel = formatWeightLabel(recipe?.piece_weight_g)

  const proteinLabel = formatNutritionValue(recipe?.nutrition_protein_g)
  const carbsLabel = formatNutritionValue(recipe?.nutrition_carbs_g)
  const fatLabel = formatNutritionValue(recipe?.nutrition_fat_g)
  const fiberLabel = formatNutritionValue(recipe?.nutrition_fiber_g)
  const glycemicLoadLabel = formatNutritionValue(recipe?.nutrition_glycemic_load, '')
  const caloriesLabel = formatNutritionValue(recipe?.nutrition_calories_kcal, 'kcal')
  const confidenceLabel =
    typeof recipe?.nutrition_confidence_score === 'number' && !Number.isNaN(recipe.nutrition_confidence_score)
      ? `${Math.round(recipe.nutrition_confidence_score)}%`
      : null
  const sourceLabel =
    recipe?.nutrition_source === 'page_100g'
      ? 'dane strony (W 100 g)'
      : recipe?.nutrition_source === 'mixed'
        ? 'źródło mieszane'
        : recipe?.nutrition_source === 'ai'
          ? 'estymacja AI'
          : null
  const confidenceTooltipText =
    confidenceLabel || sourceLabel
      ? `${confidenceLabel ? `Pewność estymacji: ${confidenceLabel}.` : ''}${
          sourceLabel ? `${confidenceLabel ? ' ' : ''}Źródło: ${sourceLabel}.` : ''
        }`
      : null
  const nutritionRows = [
    { label: 'Kalorie', value: caloriesLabel },
    { label: 'Białko', value: proteinLabel },
    { label: 'Węglowodany', value: carbsLabel },
    { label: 'Tłuszcze', value: fatLabel },
    { label: 'Błonnik', value: fiberLabel },
    { label: 'Ładunek glikemiczny', value: glycemicLoadLabel },
  ]
  const hasAnyNutrition = nutritionRows.some((row) => !!row.value)
  const denseNutritionLayout = normalizedIngredients.length >= 8
  const hasAutoPortionAdjustment = /auto-correction|snack-like recipe/i.test(yieldAssumptionReason ?? '')
  const autoPortionMessage = hasAutoPortionAdjustment
    ? `Automatycznie dopasowano wielkość porcji do standardów dietetycznych${
        portionWeightLabel ? ` (${portionWeightLabel}).` : '.'
      }`
    : null

  const yieldContext = useMemo(() => {
    const hasPanSize =
      typeof recipe?.pan_diameter_min_cm === 'number' || typeof recipe?.pan_diameter_max_cm === 'number'
    if (hasPanSize) return 'pan'

    const normalizedYieldLabel = normalizeKeywordText(yieldDisplayLabel)
    const looksLikePieces =
      typeof recipe?.piece_weight_g === 'number' ||
      /\bszt|oponk|paczk|kawal|kawalek|kawalk/.test(normalizedYieldLabel)
    if (looksLikePieces) return 'pieces'

    if (typeof recipe?.total_weight_g === 'number') return 'weight'
    return 'default'
  }, [recipe?.pan_diameter_min_cm, recipe?.pan_diameter_max_cm, recipe?.piece_weight_g, recipe?.total_weight_g, yieldDisplayLabel])

  const planSentence = useMemo(() => {
    if (yieldContext === 'pan') {
      const min = recipe?.pan_diameter_min_cm
      const max = recipe?.pan_diameter_max_cm
      if (typeof min === 'number' && typeof max === 'number') {
        return `Przepis dla formy ${min.toFixed(0)}-${max.toFixed(0)} cm. Założono ${formatPortionsLabel(basePortions, 'servings')}.`
      }
      if (typeof min === 'number') {
        return `Przepis dla formy ${min.toFixed(0)} cm. Założono ${formatPortionsLabel(basePortions, 'servings')}.`
      }
      return `Założono ${formatPortionsLabel(basePortions, 'servings')}.`
    }

    if (yieldContext === 'pieces') {
      const piecesLabel = `${basePortions} ${getPolishPluralForm(basePortions, 'sztukę', 'sztuki', 'sztuk')}`
      if (yieldDisplayLabel) return `Przepis zaplanowano na ${piecesLabel} (${yieldDisplayLabel}).`
      return `Przepis zaplanowano na ${piecesLabel}.`
    }

    if (yieldContext === 'weight' && totalWeightLabel) {
      const base = `Przepis ma około ${totalWeightLabel} całości. Założono ${formatPortionsLabel(basePortions, servingsUnit)}`
      if (portionWeightLabel) return `${base} (~${portionWeightLabel}/porcję).`
      return `${base}.`
    }

    if (yieldDisplayLabel) {
      return `Przepis zaplanowano na podstawie: ${yieldDisplayLabel}.`
    }
    if (servingsUnit === 'people') {
      return `Przepis zaplanowano dla ${formatPortionsLabel(basePortions, servingsUnit)}.`
    }
    return `Przepis zaplanowano na ${formatPortionsLabel(basePortions, servingsUnit)}.`
  }, [yieldContext, recipe?.pan_diameter_min_cm, recipe?.pan_diameter_max_cm, basePortions, servingsUnit, yieldDisplayLabel, totalWeightLabel, portionWeightLabel])

  const nutritionBasisSentence = useMemo(() => {
    const basisLabel = servingsUnit === 'people' ? 'na 1 osobę' : 'na 1 porcję'
    if (portionWeightLabel) return `Wartości odżywcze wyliczono ${basisLabel} (~${portionWeightLabel}).`
    if (pieceWeightLabel && yieldContext === 'pieces') return `Wartości odżywcze wyliczono ${basisLabel} (~${pieceWeightLabel}).`
    return `Wartości odżywcze wyliczono ${basisLabel}.`
  }, [servingsUnit, portionWeightLabel, pieceWeightLabel, yieldContext])

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
    if (!recipe) return
    const stored = getCustomRecipeCategoryMap()[recipe.id]
    const fallback = recipe.category ?? 'inne'
    setActiveCategory(stored ?? fallback)
  }, [recipe])

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
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
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
            {shouldShowImage && (
              <div className="relative aspect-video w-full overflow-hidden">
                <img src={recipe.image_url || '/placeholder.svg'} alt={recipe.title} className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent" />
              </div>
            )}

            <div className="p-6 space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-foreground">{recipe.title}</h2>
                <div className="mt-4 flex flex-wrap gap-2">
                  {RECIPE_CATEGORIES.map((category) => {
                    const isActive = activeCategory === category.value
                    return (
                      <button
                        key={category.value}
                        type="button"
                        onClick={() => {
                          setActiveCategory(category.value)
                          saveCustomRecipeCategory(recipe.id, category.value)
                        }}
                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-all ${
                          isActive
                            ? categoryStyles[category.value].active
                            : 'border-border bg-white text-muted-foreground hover:bg-muted'
                        }`}
                      >
                        {category.label}
                      </button>
                    )
                  })}
                </div>
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
                  {basePortions > 0 && (
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Users className="h-4 w-4 icon-sky" />
                      <span>{formatPortionsLabel(basePortions, servingsUnit)}</span>
                    </div>
                  )}
                </div>
              </div>

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
                  <div className={`mt-4 rounded-xl border border-border bg-muted/30 text-sm ${denseNutritionLayout ? 'p-3' : 'p-4'}`}>
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-foreground">Wartości odżywcze</h4>
                      {confidenceTooltipText && (
                        <span
                          className="inline-flex h-5 min-w-5 cursor-help items-center justify-center rounded-full border border-border px-1 text-xs font-semibold leading-none text-muted-foreground"
                          title={confidenceTooltipText}
                          aria-label={confidenceTooltipText}
                        >
                          *
                        </span>
                      )}
                    </div>
                    {autoPortionMessage && (
                      <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
                        <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                        <span>{autoPortionMessage}</span>
                      </div>
                    )}
                    <p className="mt-2 text-muted-foreground">{planSentence}</p>
                    {!autoPortionMessage && <p className="mt-1 text-muted-foreground">{nutritionBasisSentence}</p>}
                    {hasAnyNutrition ? (
                      <ul className={`mt-3 text-muted-foreground ${denseNutritionLayout ? 'space-y-1.5' : 'space-y-2'}`}>
                        {nutritionRows.map((row) => (
                          <li key={row.label} className="flex items-start gap-2">
                            <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary" />
                            <span>
                              {row.label}: {row.value ?? 'brak danych'}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-muted-foreground">Wartości odżywcze niedostępne dla tego przepisu.</p>
                    )}
                  </div>
                </div>
              )}

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
                  Przepis własny - brak linku źródłowego
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
