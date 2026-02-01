'use client'

import React from 'react'
import { useState } from 'react'
import { Link2, Sparkles, Loader2, CheckCircle2, AlertCircle, Wand2, PenLine, Plus, Trash2 } from 'lucide-react'
import { parseRecipe, addManualRecipe, RECIPE_CATEGORIES, type Recipe, type RecipeCategory } from '@/lib/api'
import { saveCustomRecipeCategory } from '@/lib/custom-recipe-categories'
import { useToast } from '@/components/toast-provider'

interface AddRecipeViewProps {
  onRecipeAdded: (recipe: Recipe) => void
}

type AddMode = 'url' | 'manual'

export function AddRecipeView({ onRecipeAdded }: AddRecipeViewProps) {
  const [mode, setMode] = useState<AddMode>('url')
  const [url, setUrl] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<'idle' | 'parsing' | 'success' | 'error'>('idle')
  const { showToast } = useToast()

  // Manual form state
  const [title, setTitle] = useState('')
  const [ingredients, setIngredients] = useState<string[]>([''])
  const [instructions, setInstructions] = useState('')
  const [category, setCategory] = useState<RecipeCategory>('obiady')
  const [servings, setServings] = useState(4)

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return

    setIsLoading(true)
    setStatus('parsing')

    try {
      const recipe = await parseRecipe(url)
      setStatus('success')
      showToast('Przepis dodany pomyslnie!', 'success')
      onRecipeAdded(recipe)
      setTimeout(() => {
        setUrl('')
        setStatus('idle')
      }, 2000)
    } catch {
      setStatus('error')
      showToast('Nie udalo sie przetworzyc przepisu', 'error')
      setTimeout(() => setStatus('idle'), 3000)
    } finally {
      setIsLoading(false)
    }
  }

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || ingredients.filter(i => i.trim()).length === 0) {
      showToast('Wypelnij tytul i co najmniej jeden skladnik', 'error')
      return
    }

    setIsLoading(true)
    try {
      const trimmedIngredients = ingredients.map((item) => item.trim()).filter(Boolean)
      const categoryLabel = RECIPE_CATEGORIES.find((item) => item.value === category)?.label ?? category
      const contentParts = [
        title.trim(),
        `Porcje: ${servings}`,
        `Kategoria: ${categoryLabel}`,
        'Skladniki:',
        ...trimmedIngredients.map((item) => `- ${item}`),
        'Instrukcje:',
        instructions.trim() || 'Brak instrukcji',
      ]
      const content = contentParts.join('\n')
      const recipe = await addManualRecipe({
        content,
      })
      saveCustomRecipeCategory(recipe.id, category)
      showToast('Przepis dodany pomyslnie!', 'success')
      onRecipeAdded(recipe)
      // Reset form
      setTitle('')
      setIngredients([''])
      setInstructions('')
      setCategory('obiady')
      setServings(4)
    } catch {
      showToast('Nie udalo sie dodac przepisu', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const addIngredient = () => {
    setIngredients([...ingredients, ''])
  }

  const updateIngredient = (index: number, value: string) => {
    const newIngredients = [...ingredients]
    newIngredients[index] = value
    setIngredients(newIngredients)
  }

  const removeIngredient = (index: number) => {
    if (ingredients.length > 1) {
      setIngredients(ingredients.filter((_, i) => i !== index))
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {/* Header */}
      <div className="space-y-2 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[oklch(0.85_0.08_290/0.2)]">
          <Wand2 className="h-8 w-8 icon-lavender" />
        </div>
        <h1 className="text-3xl font-bold text-foreground">Dodaj Przepis</h1>
        <p className="text-muted-foreground">
          Dodaj przepis z URL lub wpisz recznie
        </p>
      </div>

      {/* Mode Tabs */}
      <div className="flex gap-2 rounded-xl border border-border bg-muted/50 p-1">
        <button
          onClick={() => setMode('url')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-all ${
            mode === 'url'
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <Link2 className="h-4 w-4" />
          Z linku
        </button>
        <button
          onClick={() => setMode('manual')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-all ${
            mode === 'manual'
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <PenLine className="h-4 w-4" />
          Recznie
        </button>
      </div>

      {mode === 'url' ? (
        <>
          {/* URL Input Form */}
          <form onSubmit={handleUrlSubmit} className="space-y-4">
            <div className="relative">
              <Link2 className="absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="url"
                placeholder="https://example.com/przepis..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={isLoading}
                className="w-full rounded-2xl border border-border bg-card py-4 pr-4 pl-12 text-foreground placeholder:text-muted-foreground transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || !url.trim()}
              className="flex w-full items-center justify-center gap-3 rounded-2xl bg-primary py-4 font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-50 disabled:hover:bg-primary"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Przetwarzanie przez AI...</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-5 w-5" />
                  <span>Dodaj Przepis</span>
                </>
              )}
            </button>
          </form>

          {/* Status Animation */}
          {status !== 'idle' && (
            <div className="overflow-hidden rounded-2xl border border-border bg-card">
              <div className="p-6">
                {status === 'parsing' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
                        <Sparkles className="absolute top-1/2 left-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 text-primary" />
                      </div>
                      <div>
                        <p className="font-medium text-foreground">AI przetwarza przepis...</p>
                        <p className="text-sm text-muted-foreground">Analizowanie skladnikow i instrukcji</p>
                      </div>
                    </div>
                  </div>
                )}

                {status === 'success' && (
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20">
                      <CheckCircle2 className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Sukces!</p>
                      <p className="text-sm text-muted-foreground">Przepis zostal dodany do Twojej kolekcji</p>
                    </div>
                  </div>
                )}

                {status === 'error' && (
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/20">
                      <AlertCircle className="h-6 w-6 text-destructive" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Blad przetwarzania</p>
                      <p className="text-sm text-muted-foreground">Sprawdz URL i sprobuj ponownie</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        /* Manual Form */
        <form onSubmit={handleManualSubmit} className="space-y-6">
          {/* Title */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Nazwa przepisu *</label>
            <input
              type="text"
              placeholder="np. Spaghetti Bolognese"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl border border-border bg-card px-4 py-3 text-foreground placeholder:text-muted-foreground transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          {/* Category */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Kategoria</label>
            <div className="flex flex-wrap gap-2">
              {RECIPE_CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  type="button"
                  onClick={() => setCategory(cat.value)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                    category === cat.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-card text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          {/* Servings */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Liczba porcji</label>
            <input
              type="number"
              min={1}
              max={20}
              value={servings}
              onChange={(e) => setServings(Number(e.target.value))}
              className="w-24 rounded-xl border border-border bg-card px-4 py-3 text-foreground transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          {/* Ingredients */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Skladniki *</label>
            <div className="space-y-2">
              {ingredients.map((ingredient, index) => (
                <div key={index} className="flex gap-2">
                  <input
                    type="text"
                    placeholder={`Skladnik ${index + 1}, np. 500g makaronu`}
                    value={ingredient}
                    onChange={(e) => updateIngredient(index, e.target.value)}
                    className="flex-1 rounded-xl border border-border bg-card px-4 py-3 text-foreground placeholder:text-muted-foreground transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  {ingredients.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeIngredient(index)}
                      className="flex h-12 w-12 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:border-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addIngredient}
              className="flex items-center gap-2 text-sm text-primary hover:underline"
            >
              <Plus className="h-4 w-4" />
              Dodaj skladnik
            </button>
          </div>

          {/* Instructions */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Instrukcje (opcjonalnie)</label>
            <textarea
              placeholder="Opisz sposob przygotowania..."
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={4}
              className="w-full rounded-xl border border-border bg-card px-4 py-3 text-foreground placeholder:text-muted-foreground transition-all focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !title.trim() || ingredients.filter(i => i.trim()).length === 0}
            className="flex w-full items-center justify-center gap-3 rounded-2xl bg-primary py-4 font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Dodawanie...</span>
              </>
            ) : (
              <>
                <Plus className="h-5 w-5" />
                <span>Dodaj Przepis</span>
              </>
            )}
          </button>
        </form>
      )}

      {/* Info Cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="mb-2 font-medium text-foreground">Obslugiwane strony</h3>
          <p className="text-sm text-muted-foreground">
            Wiekszosc popularnych stron z przepisami, blogi kulinarne i portale gastronomiczne.
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="mb-2 font-medium text-foreground">Co wyodrebniamy</h3>
          <p className="text-sm text-muted-foreground">
            Tytul, skladniki, instrukcje, czas przygotowania, zdjecie i liczbe porcji.
          </p>
        </div>
      </div>
    </div>
  )
}
