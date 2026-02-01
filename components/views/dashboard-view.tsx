'use client'

import { useState } from 'react'
import { UtensilsCrossed, Calendar, ShoppingCart, TrendingUp, Clock, Sparkles, Link2, PenLine, Wand2, Loader2 } from 'lucide-react'
import { parseRecipe, addManualRecipe, RECIPE_CATEGORIES, type Stats, type Recipe, type RecipeCategory } from '@/lib/api'
import { StatCardSkeleton, RecipeCardSkeleton } from '@/components/skeletons'
import { RecipeCard } from '@/components/recipe-card'
import { RecipeModal } from '@/components/recipe-modal'
import { useToast } from '@/components/toast-provider'
import { saveCustomRecipeCategory } from '@/lib/custom-recipe-categories'

interface DashboardViewProps {
  stats: Stats | null
  recentRecipes: Recipe[]
  isLoading: boolean
  onViewRecipes: () => void
  onRecipeAdded: (recipe: Recipe) => void
  onAddToPlanner: (recipe: Recipe) => void
  onDeleteRecipe: (id: number) => void
  plannerRecipeIds: number[]
}

export function DashboardView({
  stats,
  recentRecipes,
  isLoading,
  onViewRecipes,
  onRecipeAdded,
  onAddToPlanner,
  onDeleteRecipe,
  plannerRecipeIds,
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<'link' | 'manual'>('link')
  const [linkValue, setLinkValue] = useState('')
  const [manualText, setManualText] = useState('')
  const [manualCategory, setManualCategory] = useState<RecipeCategory>('obiady')
  const [isImporting, setIsImporting] = useState(false)
  const [isSavingManual, setIsSavingManual] = useState(false)
  const [selectedRecipeId, setSelectedRecipeId] = useState<number | null>(null)
  const { showToast } = useToast()

  const statItems = [
    {
      label: 'Przepisy',
      value: stats?.total_recipes ?? 0,
      icon: UtensilsCrossed,
      color: 'icon-mint',
      bgColor: 'bg-[oklch(0.85_0.1_165/0.2)]',
    },
    {
      label: 'Zaplanowane',
      value: stats?.planned_meals ?? 0,
      icon: Calendar,
      color: 'icon-peach',
      bgColor: 'bg-[oklch(0.88_0.08_45/0.2)]',
    },
    {
      label: 'Produkty',
      value: stats?.shopping_items ?? 0,
      icon: ShoppingCart,
      color: 'icon-sky',
      bgColor: 'bg-[oklch(0.88_0.08_230/0.2)]',
    },
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-primary">
          <Sparkles className="h-5 w-5" />
          <span className="text-sm font-medium">Witaj w KitchenOS</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground">Twój Pulpit</h1>
        <p className="text-muted-foreground">Zarządzaj przepisami i planuj posiłki z pomocą AI</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-3">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => <StatCardSkeleton key={i} />)
          : statItems.map((item) => {
              const Icon = item.icon
              return (
                <div
                  key={item.label}
                  className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 p-6 backdrop-blur-xl transition-all hover:border-primary/30"
                >
                  <div className={`mb-4 inline-flex rounded-xl p-3 ${item.bgColor}`}>
                    <Icon className={`h-5 w-5 ${item.color}`} />
                  </div>
                  <p className="text-sm text-muted-foreground">{item.label}</p>
                  <p className="text-3xl font-bold text-foreground">{item.value}</p>
                  <div className="absolute -right-4 -bottom-4 opacity-5">
                    <Icon className="h-28 w-28" />
                  </div>
                </div>
              )
            })}
      </div>

      {/* Quick Actions */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-border/50 bg-card/60 p-6 backdrop-blur-xl">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-xl bg-[oklch(0.85_0.08_290/0.2)] p-3">
              <TrendingUp className="h-5 w-5 icon-lavender" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">Szybki Start</h3>
              <p className="text-sm text-muted-foreground">Dodaj przepis z URL</p>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Wklej link do przepisu, a AI automatycznie pobierze składniki i instrukcje.
          </p>
        </div>

        <div className="rounded-2xl border border-border/50 bg-card/60 p-6 backdrop-blur-xl">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-xl bg-[oklch(0.88_0.08_350/0.2)] p-3">
              <Clock className="h-5 w-5 icon-rose" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">Oszczędność Czasu</h3>
              <p className="text-sm text-muted-foreground">Automatyczna lista zakupów</p>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Wybierz przepisy do planera, a system wygeneruje optymalną listę zakupów.
          </p>
        </div>
      </div>

      {/* Quick Add Menu */}
      <div className="overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl">
        <div className="flex border-b border-border/50">
          <button
            onClick={() => setActiveTab('link')}
            className={`flex flex-1 items-center justify-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
              activeTab === 'link'
                ? 'border-b-2 border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Link2 className="h-4 w-4" />
            Z linku
          </button>
          <button
            onClick={() => setActiveTab('manual')}
            className={`flex flex-1 items-center justify-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
              activeTab === 'manual'
                ? 'border-b-2 border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <PenLine className="h-4 w-4" />
            Wlasny przepis
          </button>
        </div>

        <div className="p-5">
          {activeTab === 'link' ? (
            <form
              onSubmit={async (event) => {
                event.preventDefault()
                if (!linkValue.trim()) {
                  showToast('Wklej link do przepisu', 'error')
                  return
                }
                setIsImporting(true)
                try {
                  const recipe = await parseRecipe(linkValue.trim())
                  onRecipeAdded(recipe)
                  showToast('Przepis dodany pomyslnie!', 'success')
                  setLinkValue('')
                  onViewRecipes()
                } catch {
                  showToast('Nie udalo sie zaimportowac przepisu', 'error')
                } finally {
                  setIsImporting(false)
                }
              }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                <Wand2 className="h-4 w-4 icon-lavender" />
                Import z AI
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="relative flex-1">
                  <Link2 className="absolute top-1/2 left-4 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="url"
                    placeholder="Wklej link do przepisu"
                    value={linkValue}
                    onChange={(event) => setLinkValue(event.target.value)}
                    className="w-full rounded-xl border border-border/50 bg-background/80 py-2.5 pr-4 pl-11 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isImporting}
                  className="flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-60"
                >
                  {isImporting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Importuje...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Importuj
                    </>
                  )}
                </button>
              </div>
            </form>
          ) : (
            <form
              onSubmit={async (event) => {
                event.preventDefault()
                if (!manualText.trim()) {
                  showToast('Wklej tekst przepisu', 'error')
                  return
                }
                setIsSavingManual(true)
                try {
                  const recipe = await addManualRecipe({ content: manualText.trim() })
                  saveCustomRecipeCategory(recipe.id, manualCategory)
                  onRecipeAdded(recipe)
                  showToast('Przepis dodany pomyslnie!', 'success')
                  setManualText('')
                  onViewRecipes()
                } catch {
                  showToast('Nie udalo sie dodac przepisu', 'error')
                } finally {
                  setIsSavingManual(false)
                }
              }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                <PenLine className="h-4 w-4 icon-rose" />
                Wlasny przepis
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Kategoria</span>
                <select
                  value={manualCategory}
                  onChange={(event) => setManualCategory(event.target.value as RecipeCategory)}
                  className="w-full rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 sm:max-w-[220px]"
                >
                  {RECIPE_CATEGORIES.map((category) => (
                    <option key={category.value} value={category.value}>
                      {category.label}
                    </option>
                  ))}
                </select>
              </div>
              <textarea
                value={manualText}
                onChange={(event) => setManualText(event.target.value)}
                placeholder="Wklej caly przepis (tytul, skladniki, instrukcje)"
                rows={4}
                className="w-full rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isSavingManual}
                  className="flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-60"
                >
                  {isSavingManual ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Dodaje...
                    </>
                  ) : (
                    <>
                      <PenLine className="h-4 w-4" />
                      Dodaj przepis
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* Recent Recipes */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-foreground">Ostatnio Dodane</h2>
          <button
            onClick={onViewRecipes}
            className="text-sm font-medium text-primary transition-colors hover:text-primary/80"
          >
            Zobacz wszystkie
          </button>
        </div>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <RecipeCardSkeleton key={i} />
            ))}
          </div>
        ) : recentRecipes.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recentRecipes.slice(0, 3).map((recipe) => (
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
        ) : (
          <div className="rounded-2xl border border-dashed border-border/50 bg-card/30 p-8 text-center">
            <UtensilsCrossed className="mx-auto mb-4 h-12 w-12 text-muted-foreground/50" />
            <p className="text-muted-foreground">Brak przepisów. Dodaj pierwszy!</p>
          </div>
        )}
      </div>

      <RecipeModal recipeId={selectedRecipeId} onClose={() => setSelectedRecipeId(null)} />
    </div>
  )
}
