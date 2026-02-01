'use client'

import { useMemo } from 'react'
import { Minus, Plus, Trash2, ShoppingCart, Users, CalendarDays, UtensilsCrossed, PlusCircle } from 'lucide-react'
import { RECIPE_CATEGORIES, type PlannerRecipe, type RecipeCategory } from '@/lib/api'
import { getNextAvailableDay } from '@/lib/planner-utils'
import { EmptyState } from '@/components/empty-state'

interface PlannerViewProps {
  plannerRecipes: PlannerRecipe[]
  onUpdatePortions: (id: number, portions: number) => void
  onRemoveFromPlanner: (id: number, day?: string) => void
  onGenerateShoppingList: () => void
  isGenerating: boolean
  onAssignDay: (recipeId: number, day: string) => void
}

interface DayInfo {
  name: string
  shortName: string
  date: Date
  dateString: string
  isToday: boolean
  isTomorrow: boolean
}

const CATEGORY_LABELS = new Map(RECIPE_CATEGORIES.map((category) => [category.value, category.label]))

const CATEGORY_STYLES: Record<RecipeCategory, string> = {
  obiady: 'border-amber-200 bg-amber-100/70 text-amber-700',
  salatki: 'border-emerald-200 bg-emerald-100/70 text-emerald-700',
  pieczywo: 'border-yellow-200 bg-yellow-100/70 text-yellow-800',
  desery: 'border-rose-200 bg-rose-100/70 text-rose-700',
  inne: 'border-slate-200 bg-slate-100/70 text-slate-700',
}

const getAssignedDays = (recipe: PlannerRecipe) => {
  if (Array.isArray(recipe.assignedDays) && recipe.assignedDays.length > 0) {
    return Array.from(new Set(recipe.assignedDays))
  }
  if (recipe.assignedDay) {
    return [recipe.assignedDay]
  }
  return []
}

function getWeekDays(): DayInfo[] {
  const today = new Date()
  const currentDayOfWeek = today.getDay() // 0 = Sunday, 1 = Monday, etc.
  
  const dayNames = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
  const shortNames = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd']
  
  const days: DayInfo[] = []
  
  for (let i = 0; i < 7; i++) {
    // i = 0 is Monday (dayOfWeek = 1), i = 5 is Saturday (dayOfWeek = 6), i = 6 is Sunday (dayOfWeek = 0)
    const targetDayOfWeek = i < 6 ? i + 1 : 0 // Monday = 1, ..., Saturday = 6, Sunday = 0
    
    let daysToAdd: number
    if (currentDayOfWeek === 0) {
      // Today is Sunday
      daysToAdd = targetDayOfWeek === 0 ? 0 : targetDayOfWeek
    } else if (targetDayOfWeek === 0) {
      // Target is Sunday
      daysToAdd = 7 - currentDayOfWeek
    } else if (targetDayOfWeek >= currentDayOfWeek) {
      // Day is today or later this week
      daysToAdd = targetDayOfWeek - currentDayOfWeek
    } else {
      // Day has passed, go to next week
      daysToAdd = 7 - currentDayOfWeek + targetDayOfWeek
    }
    
    const date = new Date(today)
    date.setDate(today.getDate() + daysToAdd)
    
    const isToday = daysToAdd === 0
    const isTomorrow = daysToAdd === 1
    
    days.push({
      name: dayNames[i],
      shortName: shortNames[i],
      date,
      dateString: date.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' }),
      isToday,
      isTomorrow,
    })
  }
  
  return days
}

export function PlannerView({
  plannerRecipes,
  onUpdatePortions,
  onRemoveFromPlanner,
  onGenerateShoppingList,
  isGenerating,
  onAssignDay,
}: PlannerViewProps) {
  const totalPortions = plannerRecipes.reduce((sum, r) => {
    const dayCount = getAssignedDays(r).length || 1
    return sum + r.portions * dayCount
  }, 0)
  const weekDays = useMemo(() => getWeekDays(), [])
  const weekDayNames = useMemo(() => weekDays.map((day) => day.name), [weekDays])
  const shortNameByDay = useMemo(
    () => new Map(weekDays.map((day) => [day.name, day.shortName])),
    [weekDays]
  )
  
  // Group recipes by assigned day
  const recipesByDay = useMemo(() => {
    const grouped: Record<string, PlannerRecipe[]> = {}
    weekDays.forEach(day => {
      grouped[day.name] = []
    })
    grouped['Nieprzypisane'] = []
    
    plannerRecipes.forEach(recipe => {
      const assignedDays = getAssignedDays(recipe)
      if (assignedDays.length === 0) {
        grouped['Nieprzypisane'].push(recipe)
        return
      }
      assignedDays.forEach((day) => {
        if (grouped[day]) {
          grouped[day].push(recipe)
        }
      })
    })
    
    return grouped
  }, [plannerRecipes, weekDays])

  return (
    <div className="space-y-6 overflow-x-hidden">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-foreground">Planer Tygodniowy</h1>
          <p className="text-muted-foreground">
            Przypisz przepisy do dni i ustaw liczbę porcji
          </p>
        </div>
        {plannerRecipes.length > 0 && (
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-2 shadow-sm">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              Łącznie: <span className="font-semibold text-foreground">{totalPortions} porcji</span>
            </span>
          </div>
        )}
      </div>

      {/* Week Days Grid */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-7 xl:gap-5">
        {weekDays.map((day) => (
          <div
            key={day.name}
            className={`min-w-0 rounded-2xl border bg-card p-5 shadow-sm transition-all md:p-6 lg:min-h-[320px] ${
              day.isToday ? 'border-primary ring-1 ring-primary/20' : 'border-border'
            }`}
          >
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{day.shortName}</span>
                  {day.isToday && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      Dziś
                    </span>
                  )}
                  {day.isTomorrow && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                      Jutro
                    </span>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">{day.dateString}</span>
              </div>
              <CalendarDays className="h-4 w-4 icon-sky" />
            </div>
            
            <div className="space-y-2">
              {recipesByDay[day.name].length > 0 ? (
                recipesByDay[day.name].map((recipe) => {
                  const assignedDays = getAssignedDays(recipe)
                  const categoryLabel = recipe.category
                    ? CATEGORY_LABELS.get(recipe.category) ?? recipe.category
                    : null
                  const categoryStyle = recipe.category
                    ? CATEGORY_STYLES[recipe.category] ?? 'border-border bg-muted text-muted-foreground'
                    : 'border-border bg-muted text-muted-foreground'
                  const nextDay = getNextAvailableDay(assignedDays, weekDayNames, day.name)
                  const nextDayLabel = nextDay ? shortNameByDay.get(nextDay) ?? nextDay : null

                  return (
                    <div
                      key={`${recipe.id}-${day.name}`}
                      className="rounded-xl border border-border bg-secondary/30 p-2"
                    >
                      <div className="mb-2 flex items-start gap-2">
                        <div className="relative h-10 w-10 flex-shrink-0 overflow-hidden rounded-lg bg-muted">
                          {recipe.image_url ? (
                            <img
                              src={recipe.image_url || "/placeholder.svg"}
                              alt={recipe.title}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center">
                              <UtensilsCrossed className="h-4 w-4 text-muted-foreground/50" />
                            </div>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          {categoryLabel && (
                            <span
                              className={`mb-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${categoryStyle}`}
                            >
                              {categoryLabel}
                            </span>
                          )}
                          <p className="truncate text-xs font-medium text-foreground">{recipe.title}</p>
                          <p className="text-xs text-muted-foreground">{recipe.portions} porcji</p>
                          {assignedDays.length > 0 && (
                            <p className="text-[11px] text-muted-foreground">
                              Dni: {assignedDays.map((value) => shortNameByDay.get(value) ?? value).join(', ')}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-0.5">
                          <button
                            onClick={() => onUpdatePortions(recipe.id, Math.max(1, recipe.portions - 1))}
                            className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                          >
                            <Minus className="h-3 w-3" />
                          </button>
                          <span className="w-5 text-center text-xs font-medium">{recipe.portions}</span>
                          <button
                            onClick={() => onUpdatePortions(recipe.id, recipe.portions + 1)}
                            className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                          >
                            <Plus className="h-3 w-3" />
                          </button>
                        </div>
                        <button
                          onClick={() => onRemoveFromPlanner(recipe.id, day.name)}
                          className="flex h-6 w-6 items-center justify-center rounded text-destructive/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                      {nextDay && (
                        <button
                          onClick={() => onAssignDay(recipe.id, nextDay)}
                          className="mt-2 flex w-full flex-wrap items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-card/60 px-2 py-1 text-[11px] font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
                        >
                          <PlusCircle className="h-3.5 w-3.5" />
                          <span className="whitespace-normal text-center leading-tight">
                            Dodaj na {nextDayLabel ?? 'kolejny dzień'}
                          </span>
                        </button>
                      )}
                    </div>
                  )
                })
              ) : (
                <div className="flex h-16 items-center justify-center rounded-xl border border-dashed border-border text-xs text-muted-foreground">
                  Brak posiłków
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Unassigned Recipes */}
      {recipesByDay['Nieprzypisane'].length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <h3 className="mb-4 font-semibold text-foreground">Nieprzypisane przepisy</h3>
          <div className="space-y-3">
            {recipesByDay['Nieprzypisane'].map((recipe) => {
              const assignedDays = getAssignedDays(recipe)
              const categoryLabel = recipe.category
                ? CATEGORY_LABELS.get(recipe.category) ?? recipe.category
                : null
              const categoryStyle = recipe.category
                ? CATEGORY_STYLES[recipe.category] ?? 'border-border bg-muted text-muted-foreground'
                : 'border-border bg-muted text-muted-foreground'
              return (
                <div
                  key={recipe.id}
                  className="min-w-0 flex flex-col gap-4 rounded-xl border border-border bg-secondary/30 p-3 sm:flex-row sm:items-center"
                >
                <div className="relative h-16 w-full overflow-hidden rounded-lg bg-muted sm:h-12 sm:w-20 sm:flex-shrink-0">
                  {recipe.image_url ? (
                    <img
                      src={recipe.image_url || "/placeholder.svg"}
                      alt={recipe.title}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <UtensilsCrossed className="h-6 w-6 text-muted-foreground/50" />
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  {categoryLabel && (
                    <span
                      className={`mb-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${categoryStyle}`}
                    >
                      {categoryLabel}
                    </span>
                  )}
                  <h4 className="truncate font-medium text-foreground">{recipe.title}</h4>
                  <p className="text-sm text-muted-foreground">
                    {recipe.portions} {recipe.portions === 1 ? 'porcja' : recipe.portions < 5 ? 'porcje' : 'porcji'}
                  </p>
                </div>

                {/* Day Selection */}
                <div className="flex flex-wrap gap-1.5 sm:min-w-0 sm:flex-1">
                  {weekDays.map((day) => {
                    const isAssigned = assignedDays.includes(day.name)
                    return (
                      <button
                        key={day.name}
                        onClick={() => onAssignDay(recipe.id, day.name)}
                        className={`rounded-lg border px-2 py-1 text-xs font-medium transition-colors ${
                          isAssigned
                            ? 'border-primary bg-primary/10 text-primary hover:bg-primary/20'
                            : 'border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground'
                        }`}
                      >
                        {day.shortName}
                      </button>
                    )
                  })}
                </div>

                <div className="flex items-center gap-2 sm:shrink-0">
                  <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-0.5">
                    <button
                      onClick={() => onUpdatePortions(recipe.id, Math.max(1, recipe.portions - 1))}
                      className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </button>
                    <span className="w-6 text-center text-sm font-medium">{recipe.portions}</span>
                    <button
                      onClick={() => onUpdatePortions(recipe.id, recipe.portions + 1)}
                      className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <button
                    onClick={() => onRemoveFromPlanner(recipe.id)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-destructive/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Empty State */}
      {plannerRecipes.length === 0 && (
        <EmptyState
          type="planner"
          title="Planer jest pusty"
          description="Dodaj przepisy z Eksploratora, aby zaplanować posiłki na tydzień."
        />
      )}

      {/* Generate Button */}
      {plannerRecipes.length > 0 && (
        <button
          onClick={onGenerateShoppingList}
          disabled={isGenerating}
          className="flex w-full items-center justify-center gap-3 rounded-2xl bg-primary py-4 font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          {isGenerating ? (
            <>
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-foreground/20 border-t-primary-foreground" />
              <span>Generowanie listy...</span>
            </>
          ) : (
            <>
              <ShoppingCart className="h-5 w-5" />
              <span>Generuj Listę Zakupów</span>
            </>
          )}
        </button>
      )}
    </div>
  )
}
