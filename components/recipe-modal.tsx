'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { X, Clock, Users, ExternalLink, UtensilsCrossed, Loader2, PenLine, Info, Plus, Trash2 } from 'lucide-react'
import {
  fetchRecipeDetails,
  recalculateRecipeNutrition,
  updateRecipeIngredients,
  RECIPE_CATEGORIES,
  type Recipe,
  type RecipeCategory,
  type RecipeDetails,
} from '@/lib/api'
import {
  createEditableIngredient,
  normalizeEditableIngredients,
  parseIngredientLine,
  type EditableIngredient,
} from '@/lib/recipe-ingredients'
import { categoryStyles } from '@/lib/recipe-category-styles'
import { getCustomRecipeCategoryMap, saveCustomRecipeCategory } from '@/lib/custom-recipe-categories'
import { useToast } from '@/components/toast-provider'

interface RecipeModalProps {
  recipeId: number | null
  onClose: () => void
  onRecipeUpdated?: (recipe: Recipe) => void
}

const normalizeToList = (value: string[] | string | null | undefined) => {
  if (!value) return []
  if (Array.isArray(value)) return value
  return value.split(/\r?\n+/).map((entry) => entry.trim()).filter(Boolean)
}

const normalizeInstructionSteps = (value: string[] | string | null | undefined) => {
  const raw = normalizeToList(value)
  const noisePattern =
    /^(czas przygotowania|czas pieczenia|czas gotowania|liczba porcji|porcje|dla osob|w\s*100\s*g|wartosc energetyczna|wartosc odzywcza|weglowodany|bialko|tluszcz\w*|blonnik|dieta)\b/i
  const cleaned: string[] = []
  for (const entry of raw) {
    let line = entry.replace(/^(?:krok\s*\d+[:.)-]*\s*|\d+[.)-]\s*|[-*\u2022]\s*)/i, '').replace(/\s+/g, ' ').trim()
    if (!line || noisePattern.test(line)) continue
    if (cleaned.length === 0) {
      cleaned.push(line)
      continue
    }
    const prev = cleaned[cleaned.length - 1]
    const prevWords = prev.split(/\s+/).length
    const lineWords = line.split(/\s+/).length
    const prevEndsSentence = /[.!?]$/.test(prev)
    const lineStartsSentence = /^[A-ZĄĆĘŁŃÓŚŹŻ]/.test(line)
    const shouldMerge = (lineWords <= 4 || line.length < 24 || prevWords <= 2 || prev.length < 18) && !(prevEndsSentence && lineStartsSentence)
    if (shouldMerge) cleaned[cleaned.length - 1] = `${prev} ${line}`.replace(/\s+/g, ' ').trim()
    else cleaned.push(line)
  }
  return cleaned
}

const getPolishPluralForm = (count: number, singular: string, few: string, many: string) => {
  const absCount = Math.abs(count)
  const mod10 = absCount % 10
  const mod100 = absCount % 100
  if (absCount === 1) return singular
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

const formatPortionsLabel = (count: number, unit: 'servings' | 'people') =>
  `${count} ${
    unit === 'people'
      ? getPolishPluralForm(count, 'osoba', 'osoby', 'osób')
      : getPolishPluralForm(count, 'porcja', 'porcje', 'porcji')
  }`

const formatNutritionValue = (value?: number | null, suffix = 'g') => {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  return suffix ? `${value.toFixed(1)} ${suffix}` : value.toFixed(1)
}

const formatWeightLabel = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  const rounded = Math.round(value * 10) / 10
  return Math.abs(rounded - Math.round(rounded)) < 0.001 ? `${Math.round(rounded)} g` : `${rounded.toFixed(1)} g`
}

const formatPortionProfileLabel = (
  profile?: 'soup' | 'main' | 'dessert_baked' | 'dessert_dense' | 'breakfast_sweet' | 'default' | null
) => {
  switch (profile) {
    case 'soup':
      return 'zupa'
    case 'main':
      return 'danie główne'
    case 'breakfast_sweet':
      return 'śniadanie na słodko'
    case 'dessert_baked':
      return 'deser pieczony'
    case 'dessert_dense':
      return 'deser gęsty'
    default:
      return 'profil ogólny'
  }
}

const formatProcessClassLabel = (processClass?: 'batter' | 'hydrate' | 'roast' | 'reduce' | 'unknown' | null) => {
  switch (processClass) {
    case 'batter':
      return 'BATTER'
    case 'hydrate':
      return 'HYDRATE'
    case 'roast':
      return 'ROAST'
    case 'reduce':
      return 'REDUCE'
    case 'unknown':
      return 'UNKNOWN'
    default:
      return null
  }
}

const formatWeightSourceLabel = (value?: 'deterministic' | 'ai' | 'mixed' | null) =>
  value === 'deterministic' ? 'deterministycznie' : value === 'ai' ? 'AI fallback' : value === 'mixed' ? 'mieszane' : null

const normalizeKeywordText = (value?: string | null) =>
  (value ?? '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')

export function RecipeModal({ recipeId, onClose, onRecipeUpdated }: RecipeModalProps) {
  const { showToast } = useToast()
  const [recipe, setRecipe] = useState<RecipeDetails | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isRecalculatingNutrition, setIsRecalculatingNutrition] = useState(false)
  const [isSavingEdit, setIsSavingEdit] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<RecipeCategory>('inne')
  const [showNutritionInfo, setShowNutritionInfo] = useState(false)
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [editableIngredients, setEditableIngredients] = useState<EditableIngredient[]>([])
  const [initialEditSignature, setInitialEditSignature] = useState('[]')

  const GENERIC_ICON_URL = 'https://cdn-icons-png.flaticon.com/512/3081/3081557.png'
  const sourceUrl =
    (recipe as (RecipeDetails & { source_url?: string; url?: string }) | null)?.source_url ??
    (recipe as (RecipeDetails & { url?: string }) | null)?.url
  const isHttpUrl = (value?: string) => typeof value === 'string' && /^https?:\/\//i.test(value)
  const shouldShowImage = !!recipe?.image_url && recipe.image_url !== GENERIC_ICON_URL
  const normalizedIngredients = normalizeToList(recipe?.ingredients)
  const normalizedInstructions = normalizeInstructionSteps(recipe?.instructions)
  const normalizedEditIngredients = useMemo(() => normalizeEditableIngredients(editableIngredients), [editableIngredients])
  const hasUnsavedChanges = mode === 'edit' && JSON.stringify(normalizedEditIngredients) !== initialEditSignature
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
      : recipe?.nutrition_source === 'mixed_fallback'
        ? 'mieszane + fallback'
        : recipe?.nutrition_source === 'fallback'
          ? 'fallback deterministyczny'
          : recipe?.nutrition_source === 'mixed'
            ? 'źródło mieszane'
            : recipe?.nutrition_source === 'ai'
              ? 'estymacja AI'
              : null
  const processClassLabel = formatProcessClassLabel(recipe?.process_class ?? null)
  const weightSourceLabel = formatWeightSourceLabel(recipe?.final_weight_estimation_source ?? null)
  const finalWeightConfidenceLabel =
    typeof recipe?.final_weight_confidence === 'number' && !Number.isNaN(recipe.final_weight_confidence)
      ? `${Math.round(recipe.final_weight_confidence)}%`
      : null
  const tooltipParts = [
    confidenceLabel ? `Pewność estymacji nutrition: ${confidenceLabel}.` : null,
    sourceLabel ? `Źródło nutrition: ${sourceLabel}.` : null,
    processClassLabel ? `Klasa procesu: ${processClassLabel}.` : null,
    weightSourceLabel ? `Estymacja masy: ${weightSourceLabel}.` : null,
    finalWeightConfidenceLabel ? `Pewność estymacji masy: ${finalWeightConfidenceLabel}.` : null,
  ].filter(Boolean)
  const confidenceTooltipText = tooltipParts.length > 0 ? tooltipParts.join(' ') : null
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
  const hasStructuredAutoPortionAdjustment = recipe?.portion_adjusted_auto === true
  const hasLegacyAutoPortionAdjustment = !hasStructuredAutoPortionAdjustment && /auto-correction|snack-like recipe/i.test(yieldAssumptionReason ?? '')
  const hasAutoPortionAdjustment = hasStructuredAutoPortionAdjustment || hasLegacyAutoPortionAdjustment
  const autoPortionMessage = useMemo(() => {
    if (!hasAutoPortionAdjustment) return null
    if (hasStructuredAutoPortionAdjustment) {
      const previousPortions =
        typeof recipe?.original_base_portions === 'number' && Number.isFinite(recipe.original_base_portions)
          ? Math.max(1, Math.round(recipe.original_base_portions))
          : null
      const currentPortions = Math.max(1, recipe?.servings ?? recipe?.base_portions ?? 1)
      const profileLabel = formatPortionProfileLabel(recipe?.portion_profile ?? null)
      const targetWeightLabel = formatWeightLabel(recipe?.target_portion_weight_g)
      const profileDetails = `profil: ${profileLabel}${targetWeightLabel ? `, cel ~${targetWeightLabel}/porcje` : ''}`
      if (previousPortions && previousPortions !== currentPortions) {
        return `Automatycznie dopasowano porcje: ${previousPortions} -> ${currentPortions} (${profileDetails}).`
      }
      return `Automatycznie dopasowano wielkość porcji (${profileDetails}).`
    }
    return `Automatycznie dopasowano wielkość porcji do standardów dietetycznych${portionWeightLabel ? ` (${portionWeightLabel}).` : '.'}`
  }, [
    hasAutoPortionAdjustment,
    hasStructuredAutoPortionAdjustment,
    recipe?.original_base_portions,
    recipe?.servings,
    recipe?.base_portions,
    recipe?.portion_profile,
    recipe?.target_portion_weight_g,
    portionWeightLabel,
  ])

  const yieldContext = useMemo(() => {
    const hasPanSize = typeof recipe?.pan_diameter_min_cm === 'number' || typeof recipe?.pan_diameter_max_cm === 'number'
    if (hasPanSize) return 'pan'
    const normalizedYieldLabel = normalizeKeywordText(yieldDisplayLabel)
    const looksLikePieces =
      typeof recipe?.piece_weight_g === 'number' || /\bszt|oponk|paczk|kawal|kawalek|kawalk/.test(normalizedYieldLabel)
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
      return yieldDisplayLabel ? `Przepis zaplanowano na ${piecesLabel} (${yieldDisplayLabel}).` : `Przepis zaplanowano na ${piecesLabel}.`
    }
    if (yieldContext === 'weight' && totalWeightLabel) {
      const base = `Przepis ma około ${totalWeightLabel} całości. Założono ${formatPortionsLabel(basePortions, servingsUnit)}`
      return portionWeightLabel ? `${base} (~${portionWeightLabel}/porcję).` : `${base}.`
    }
    if (yieldDisplayLabel) return `Przepis zaplanowano na podstawie: ${yieldDisplayLabel}.`
    if (servingsUnit === 'people') return `Przepis zaplanowano dla ${formatPortionsLabel(basePortions, servingsUnit)}.`
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
      setMode('view')
      setEditableIngredients([])
      setInitialEditSignature('[]')
      return
    }
    setShowNutritionInfo(false)
    setMode('view')
    setEditableIngredients([])
    setInitialEditSignature('[]')
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

  const handleRequestClose = useCallback(() => {
    if (isSavingEdit) return
    if (hasUnsavedChanges && typeof window !== 'undefined') {
      const confirmed = window.confirm('Masz niezapisane zmiany składników. Odrzucić je?')
      if (!confirmed) return
    }
    setMode('view')
    setEditableIngredients([])
    setInitialEditSignature('[]')
    onClose()
  }, [hasUnsavedChanges, isSavingEdit, onClose])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleRequestClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [handleRequestClose])

  const handleStartEditing = () => {
    const drafts = normalizedIngredients.length > 0 ? normalizedIngredients.map(parseIngredientLine) : [createEditableIngredient()]
    setEditableIngredients(drafts)
    setInitialEditSignature(JSON.stringify(normalizeEditableIngredients(drafts)))
    setMode('edit')
  }

  const handleCancelEditing = () => {
    if (hasUnsavedChanges && typeof window !== 'undefined') {
      const confirmed = window.confirm('Masz niezapisane zmiany składników. Odrzucić je?')
      if (!confirmed) return
    }
    setEditableIngredients([])
    setInitialEditSignature('[]')
    setMode('view')
  }

  const handleEditableIngredientChange = (ingredientId: string, field: 'item' | 'amount', value: string) => {
    setEditableIngredients((prev) => prev.map((ingredient) => (ingredient.id === ingredientId ? { ...ingredient, [field]: value } : ingredient)))
  }

  const handleAddIngredient = () => {
    setEditableIngredients((prev) => [...prev, createEditableIngredient()])
  }

  const handleRemoveIngredient = (ingredientId: string) => {
    setEditableIngredients((prev) => {
      const next = prev.filter((ingredient) => ingredient.id !== ingredientId)
      return next.length > 0 ? next : [createEditableIngredient()]
    })
  }

  const handleSaveIngredients = async () => {
    if (!recipe?.id || isSavingEdit) return
    if (normalizedEditIngredients.length === 0) {
      showToast('Dodaj co najmniej jeden składnik', 'error')
      return
    }
    setIsSavingEdit(true)
    try {
      const updatedRecipe = await updateRecipeIngredients(recipe.id, normalizedEditIngredients)
      setRecipe(updatedRecipe)
      setEditableIngredients([])
      setInitialEditSignature('[]')
      setMode('view')
      onRecipeUpdated?.(updatedRecipe)
      showToast('Składniki zapisane, a wartości odżywcze przeliczone', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Nie udało się zapisać składników'
      showToast(message, 'error')
    } finally {
      setIsSavingEdit(false)
    }
  }

  const handleRecalculateNutrition = async () => {
    if (!recipe?.id || isRecalculatingNutrition) return
    setIsRecalculatingNutrition(true)
    try {
      const recalculated = await recalculateRecipeNutrition(recipe.id)
      setRecipe(recalculated)
      onRecipeUpdated?.(recalculated)
      showToast('Wartości odżywcze przeliczone', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Nie udało się przeliczyć wartości odżywczych'
      showToast(message, 'error')
    } finally {
      setIsRecalculatingNutrition(false)
    }
  }

  if (!recipeId) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={handleRequestClose} />
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
        <button
          onClick={handleRequestClose}
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
          <div className="max-h-[90vh] overflow-y-auto">
            {shouldShowImage && (
              <div className="relative aspect-video w-full overflow-hidden">
                <img src={recipe.image_url || '/placeholder.svg'} alt={recipe.title} className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent" />
              </div>
            )}

            <div className="space-y-6 p-6">
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
                          isActive ? categoryStyles[category.value].active : 'border-border bg-white text-muted-foreground hover:bg-muted'
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

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-foreground">Składniki</h3>
                  {mode === 'view' ? (
                    <button
                      type="button"
                      onClick={handleStartEditing}
                      className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                    >
                      <PenLine className="h-3.5 w-3.5" />
                      Edytuj składniki
                    </button>
                  ) : null}
                </div>

                {mode === 'edit' ? (
                  <div className="space-y-4">
                    <div className="space-y-3">
                      {editableIngredients.map((ingredient, index) => (
                        <div key={ingredient.id} className="grid gap-3 rounded-xl border border-border bg-muted/20 p-3 sm:grid-cols-[140px_minmax(0,1fr)_44px]">
                          <input
                            type="text"
                            value={ingredient.amount}
                            onChange={(event) => handleEditableIngredientChange(ingredient.id, 'amount', event.target.value)}
                            placeholder="np. 200 g"
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                            aria-label={`Ilość składnika ${index + 1}`}
                          />
                          <input
                            type="text"
                            value={ingredient.item}
                            onChange={(event) => handleEditableIngredientChange(ingredient.id, 'item', event.target.value)}
                            placeholder="Nazwa składnika"
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                            aria-label={`Nazwa składnika ${index + 1}`}
                          />
                          <button
                            type="button"
                            onClick={() => handleRemoveIngredient(ingredient.id)}
                            className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground transition-colors hover:border-destructive/40 hover:text-destructive"
                            aria-label={`Usuń składnik ${index + 1}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <button
                        type="button"
                        onClick={handleAddIngredient}
                        className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
                      >
                        <Plus className="h-4 w-4" />
                        Dodaj składnik
                      </button>
                      <span className="text-xs text-muted-foreground">Po zapisie wartości odżywcze zostaną przeliczone automatycznie.</span>
                    </div>

                    <div className="flex justify-end gap-2 border-t border-border pt-2">
                      <button
                        type="button"
                        onClick={handleCancelEditing}
                        className="rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
                      >
                        Anuluj
                      </button>
                      <button
                        type="button"
                        onClick={handleSaveIngredients}
                        disabled={isSavingEdit}
                        className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isSavingEdit ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        Zapisz i przelicz
                      </button>
                    </div>
                  </div>
                ) : normalizedIngredients.length > 0 ? (
                  <>
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
                        {confidenceTooltipText ? (
                          <button
                            type="button"
                            onClick={() => setShowNutritionInfo((prev) => !prev)}
                            className="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-border px-1 text-xs font-semibold leading-none text-muted-foreground hover:bg-muted"
                            aria-label={confidenceTooltipText}
                          >
                            i
                          </button>
                        ) : null}
                      </div>
                      {showNutritionInfo && confidenceTooltipText ? (
                        <div className="mt-2 break-words rounded-lg border border-border bg-card p-2 text-xs text-muted-foreground">{confidenceTooltipText}</div>
                      ) : null}
                      {autoPortionMessage ? (
                        <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
                          <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                          <span>{autoPortionMessage}</span>
                        </div>
                      ) : null}
                      <p className="mt-2 text-muted-foreground">{planSentence}</p>
                      {!autoPortionMessage && hasAnyNutrition ? <p className="mt-1 text-muted-foreground">{nutritionBasisSentence}</p> : null}
                      {hasAnyNutrition ? (
                        <ul className={`mt-3 text-muted-foreground ${denseNutritionLayout ? 'space-y-1.5' : 'space-y-2'}`}>
                          {nutritionRows.map((row) => (
                            <li key={row.label} className="flex items-start gap-2">
                              <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary" />
                              <span>{row.label}: {row.value ?? 'brak danych'}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div className="mt-2 space-y-2">
                          <p className="text-muted-foreground">Wartości odżywcze niedostępne dla tego przepisu.</p>
                          <button
                            type="button"
                            onClick={handleRecalculateNutrition}
                            disabled={isRecalculatingNutrition}
                            className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {isRecalculatingNutrition ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                            Przelicz wartości odżywcze
                          </button>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Brak składników do wyświetlenia.</p>
                )}
              </div>

              {normalizedInstructions.length > 0 ? (
                <div>
                  <h3 className="mb-3 font-semibold text-foreground">Instrukcje</h3>
                  <ol className="space-y-3">
                    {normalizedInstructions.map((step, index) => (
                      <li key={index} className="flex gap-3 text-sm">
                        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{index + 1}</span>
                        <span className="pt-0.5 text-muted-foreground">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}

              {isHttpUrl(sourceUrl) ? (
                <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-primary hover:underline">
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
