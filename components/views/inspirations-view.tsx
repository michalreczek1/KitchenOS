'use client'

import { useMemo, useState } from 'react'
import { Sparkles, Clock, ChefHat, BookmarkPlus, RefreshCcw } from 'lucide-react'
import { inspireRecipe, saveInspiredRecipe, type InspireRecipe, type Recipe } from '@/lib/api'
import { useToast } from '@/components/toast-provider'
import { Button } from '@/components/ui/button'

interface InspirationsViewProps {
  onRecipeSaved: (recipe: Recipe) => void
}

const parseIngredients = (value: string) =>
  value
    .split(/[,\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)

const SkeletonCard = () => (
  <div className="rounded-2xl border border-border/50 bg-card/60 p-6 shadow-sm">
    <div className="space-y-4 animate-pulse">
      <div className="h-6 w-1/3 rounded-lg bg-secondary/60" />
      <div className="h-4 w-2/3 rounded-lg bg-secondary/60" />
      <div className="h-4 w-1/2 rounded-lg bg-secondary/60" />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <div className="h-4 w-32 rounded bg-secondary/60" />
          <div className="h-4 w-3/4 rounded bg-secondary/60" />
          <div className="h-4 w-2/3 rounded bg-secondary/60" />
          <div className="h-4 w-1/2 rounded bg-secondary/60" />
        </div>
        <div className="space-y-3">
          <div className="h-4 w-32 rounded bg-secondary/60" />
          <div className="h-4 w-full rounded bg-secondary/60" />
          <div className="h-4 w-5/6 rounded bg-secondary/60" />
          <div className="h-4 w-2/3 rounded bg-secondary/60" />
        </div>
      </div>
    </div>
  </div>
)

export function InspirationsView({ onRecipeSaved }: InspirationsViewProps) {
  const [ingredientsText, setIngredientsText] = useState('')
  const [result, setResult] = useState<InspireRecipe | null>(null)
  const [lastIngredients, setLastIngredients] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [shake, setShake] = useState(false)
  const { showToast } = useToast()

  const providedIngredients = useMemo(
    () => result?.ingredients.filter((item) => !item.is_extra) ?? [],
    [result]
  )
  const extraIngredients = useMemo(
    () => result?.ingredients.filter((item) => item.is_extra) ?? [],
    [result]
  )
  const formattedPrepTime = useMemo(() => {
    if (!result?.prep_time) return null
    const trimmed = result.prep_time.trim()
    return /min/i.test(trimmed) ? trimmed : `${trimmed} min`
  }, [result])

  const triggerShake = () => {
    setShake(true)
    window.setTimeout(() => setShake(false), 500)
  }

  const handleGenerate = async (useLast = false) => {
    const list = useLast && lastIngredients.length > 0 ? lastIngredients : parseIngredients(ingredientsText)
    if (list.length === 0) {
      triggerShake()
      showToast('Dodaj choć jeden składnik!', 'info')
      return
    }
    setIsLoading(true)
    setResult(null)
    setLastIngredients(list)
    try {
      const data = await inspireRecipe(list)
      setResult(data)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Nie udało się wygenerować przepisu', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    if (!result) return
    setIsSaving(true)
    try {
      const saved = await saveInspiredRecipe(result)
      onRecipeSaved(saved)
      showToast('Przepis zapisany w Twojej kolekcji', 'success')
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Nie udało się zapisać przepisu', 'error')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground">Inspiracje</h1>
        <p className="text-muted-foreground font-semibold">
          Wpisz składniki, które masz pod ręką — KitchenOS podpowie, co możesz z nich wyczarować.
        </p>
      </div>

      <div className="space-y-3">
        <textarea
          value={ingredientsText}
          onChange={(event) => setIngredientsText(event.target.value)}
          placeholder="np. jajka, pomidory, ser, szczypiorek"
          rows={4}
          className="w-full rounded-2xl border border-border/60 bg-white p-4 text-sm text-foreground shadow-sm transition focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() => handleGenerate(false)}
            disabled={isLoading}
            className={shake ? 'animate-shake' : undefined}
          >
            <Sparkles className="mr-2 h-4 w-4" />
            Czaruj przepis
          </Button>
        </div>
      </div>

      {isLoading && <SkeletonCard />}

      {result && !isLoading && (
        <div className="rounded-2xl border border-border/50 bg-card/80 p-6 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-semibold text-foreground">{result.title}</h2>
            <span className="inline-flex items-center gap-2 rounded-full bg-[oklch(0.9_0.05_250/0.6)] px-3 py-1 text-xs font-semibold text-foreground">
              <Sparkles className="h-3.5 w-3.5" />
              Inspiracja AI
            </span>
          </div>
          {result.description && (
            <p className="mt-3 text-sm text-muted-foreground">{result.description}</p>
          )}
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
            {formattedPrepTime && (
              <span className="flex items-center gap-2">
                <Clock className="h-4 w-4 icon-peach" />
                {formattedPrepTime}
              </span>
            )}
            {result.difficulty && (
              <span className="flex items-center gap-2">
                <ChefHat className="h-4 w-4 icon-sky" />
                Trudność: {result.difficulty}
              </span>
            )}
          </div>

          <div className="mt-6 grid gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <div>
                <h3 className="mb-2 text-sm font-semibold text-foreground">Składniki z lodówki</h3>
                <ul className="space-y-2">
                  {providedIngredients.length > 0 ? (
                    providedIngredients.map((ingredient, index) => (
                      <li key={`provided-${index}`} className="text-sm text-muted-foreground">
                        • {ingredient.item}{ingredient.amount ? ` (${ingredient.amount})` : ''}
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-muted-foreground">Brak podanych składników.</li>
                  )}
                </ul>
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-foreground">Z bazy (opcjonalne)</h3>
                <ul className="space-y-2">
                  {extraIngredients.length > 0 ? (
                    extraIngredients.map((ingredient, index) => (
                      <li key={`extra-${index}`} className="text-sm text-muted-foreground">
                        • {ingredient.item}{ingredient.amount ? ` (${ingredient.amount})` : ''}
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-muted-foreground">Brak dodatkowych składników.</li>
                  )}
                </ul>
              </div>
            </div>

            <div>
              <h3 className="mb-3 text-sm font-semibold text-foreground">Instrukcja</h3>
              <ol className="space-y-3">
                {result.instructions.map((step, index) => (
                  <li key={`step-${index}`} className="flex gap-3 text-sm text-muted-foreground">
                    <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {result.tips && (
            <div className="mt-6 rounded-xl border border-border/50 bg-secondary/40 p-4 text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Porada Szefa:</span> {result.tips}
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <Button onClick={handleSave} disabled={isSaving}>
              <BookmarkPlus className="mr-2 h-4 w-4" />
              Zapisz w moich przepisach
            </Button>
            <Button variant="outline" onClick={() => handleGenerate(true)} disabled={isLoading}>
              <RefreshCcw className="mr-2 h-4 w-4" />
              Spróbuj czegoś innego
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
