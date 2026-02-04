'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import useSWR from 'swr'
import { Navigation } from '@/components/navigation'
import { ToastProvider, useToast } from '@/components/toast-provider'
import { AuthProvider, useAuth } from '@/components/auth-provider'
import { LoginScreen } from '@/components/login-screen'
import { DashboardView } from '@/components/views/dashboard-view'
import { RecipesView } from '@/components/views/recipes-view'
import { AddRecipeView } from '@/components/views/add-recipe-view'
import { PlannerView } from '@/components/views/planner-view'
import { ShoppingView } from '@/components/views/shopping-view'
import { AdminView } from '@/components/views/admin-view'
import { InspirationsView } from '@/components/views/inspirations-view'
import {
  fetchRecipes,
  fetchStats,
  generateShoppingList,
  deleteRecipe,
  setRecipeRating,
  type Recipe,
  type Stats,
  type PlannerRecipe,
  type ShoppingList,
  type AuthUser,
} from '@/lib/api'
import { removeCustomRecipeCategory } from '@/lib/custom-recipe-categories'

const SHOPPING_LIST_STORAGE_KEY = 'kitchenOS_shopping_list'
const SHOPPING_META_STORAGE_KEY = 'kitchenOS_shopping_meta'
const PLANNER_STORAGE_KEY = 'kitchenOS_planner'

type ShoppingListMeta = {
  signature: string
  generatedAt: string
  isStale: boolean
}

const normalizeAssignedDays = (recipe: PlannerRecipe) => {
  const days = Array.isArray(recipe.assignedDays)
    ? recipe.assignedDays
    : recipe.assignedDay
      ? [recipe.assignedDay]
      : []
  return Array.from(new Set(days)).sort()
}

const buildPlannerSignature = (recipes: PlannerRecipe[]) => {
  if (!recipes.length) return ''
  const payload = recipes
    .map((recipe) => ({
      id: recipe.id,
      portions: recipe.portions,
      days: normalizeAssignedDays(recipe),
    }))
    .sort((a, b) => a.id - b.id)
  return JSON.stringify(payload)
}

type View = 'dashboard' | 'recipes' | 'add' | 'planner' | 'shopping' | 'inspiracje' | 'admin'

function KitchenOSApp({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [currentView, setCurrentView] = useState<View>('dashboard')
  const [plannerRecipes, setPlannerRecipes] = useState<PlannerRecipe[]>([])
  const [shoppingList, setShoppingList] = useState<ShoppingList | null>(null)
  const [shoppingListMeta, setShoppingListMeta] = useState<ShoppingListMeta | null>(null)
  const [isGeneratingList, setIsGeneratingList] = useState(false)
  const lastAutoRequestSignature = useRef<string | null>(null)
  const { showToast } = useToast()
  const plannerStorageKey = `${PLANNER_STORAGE_KEY}_${user.id}`
  const shoppingListStorageKey = `${SHOPPING_LIST_STORAGE_KEY}_${user.id}`
  const shoppingMetaStorageKey = `${SHOPPING_META_STORAGE_KEY}_${user.id}`

  // Fetch recipes
  const {
    data: recipes = [],
    isLoading: isLoadingRecipes,
    mutate: mutateRecipes,
  } = useSWR(user ? 'recipes' : null, fetchRecipes, {
    onError: () => showToast('Nie udało się pobrać przepisów', 'error'),
    revalidateOnFocus: false,
  })

  useEffect(() => {
    const handleCategoriesUpdate = () => mutateRecipes()
    window.addEventListener('kitchenos:categories', handleCategoriesUpdate)
    return () => window.removeEventListener('kitchenos:categories', handleCategoriesUpdate)
  }, [mutateRecipes])

  // Fetch stats
  const {
    data: stats,
    isLoading: isLoadingStats,
    mutate: mutateStats,
  } = useSWR<Stats>(user ? 'stats' : null, fetchStats, {
    onError: () => console.log('[v0] Failed to fetch stats'),
    revalidateOnFocus: false,
  })

  // Load planner from localStorage on mount
  useEffect(() => {
    const savedPlanner = localStorage.getItem(plannerStorageKey)
    if (savedPlanner) {
      try {
        const parsed = JSON.parse(savedPlanner) as PlannerRecipe[]
        if (Array.isArray(parsed)) {
          const normalized = parsed.map((recipe) => {
            const assignedDays =
              Array.isArray(recipe.assignedDays) && recipe.assignedDays.length > 0
                ? recipe.assignedDays
                : recipe.assignedDay
                  ? [recipe.assignedDay]
                  : []
            return { ...recipe, assignedDays }
          })
          setPlannerRecipes(normalized)
        }
      } catch {
        console.log('[v0] Failed to load planner from localStorage')
      }
    }
  }, [plannerStorageKey])

  useEffect(() => {
    const savedList = localStorage.getItem(shoppingListStorageKey)
    const savedMeta = localStorage.getItem(shoppingMetaStorageKey)
    if (!savedList || !savedMeta) return
    try {
      const parsedList = JSON.parse(savedList) as ShoppingList
      const parsedMeta = JSON.parse(savedMeta) as { signature: string; generatedAt: string }
      if (parsedList && parsedMeta?.signature) {
        setShoppingList(parsedList)
        setShoppingListMeta({
          signature: parsedMeta.signature,
          generatedAt: parsedMeta.generatedAt,
          isStale: false,
        })
      }
    } catch {
      console.log('[v0] Failed to load shopping list from localStorage')
    }
  }, [shoppingListStorageKey, shoppingMetaStorageKey])

  // Save planner to localStorage when it changes
  useEffect(() => {
    localStorage.setItem(plannerStorageKey, JSON.stringify(plannerRecipes))
  }, [plannerRecipes, plannerStorageKey])

  useEffect(() => {
    if (shoppingList && shoppingListMeta) {
      localStorage.setItem(shoppingListStorageKey, JSON.stringify(shoppingList))
      localStorage.setItem(
        shoppingMetaStorageKey,
        JSON.stringify({
          signature: shoppingListMeta.signature,
          generatedAt: shoppingListMeta.generatedAt,
        })
      )
      return
    }
    localStorage.removeItem(shoppingListStorageKey)
    localStorage.removeItem(shoppingMetaStorageKey)
  }, [shoppingList, shoppingListMeta, shoppingListStorageKey, shoppingMetaStorageKey])

  // Add recipe to planner
  const handleAddToPlanner = useCallback((recipe: Recipe) => {
    setPlannerRecipes((prev) => {
      if (prev.find((r) => r.id === recipe.id)) {
        return prev
      }
      return [...prev, { ...recipe, portions: 2, assignedDays: [] }]
    })
    showToast('Dodano do planera!', 'success')
  }, [showToast])

  // Update portions
  const handleUpdatePortions = useCallback((id: number, portions: number) => {
    setPlannerRecipes((prev) =>
      prev.map((r) => (r.id === id ? { ...r, portions } : r))
    )
  }, [])

  // Remove from planner
  const handleRemoveFromPlanner = useCallback((id: number, day?: string) => {
    setPlannerRecipes((prev) =>
      prev.flatMap((recipe) => {
        if (recipe.id !== id) return [recipe]
        if (!day) {
          return []
        }
        const currentDays =
          Array.isArray(recipe.assignedDays) && recipe.assignedDays.length > 0
            ? recipe.assignedDays
            : recipe.assignedDay
              ? [recipe.assignedDay]
              : []
        const nextDays = currentDays.filter((value) => value !== day)
        if (nextDays.length === 0) {
          return []
        }
        return [{ ...recipe, assignedDays: nextDays }]
      })
    )
    showToast(day ? `Usunięto z dnia: ${day}` : 'Usunięto z planera', 'info')
  }, [showToast])

  // Assign recipe to a day
  const handleAssignDay = useCallback((recipeId: number, day: string) => {
    let action: 'add' | 'remove' = 'add'
    setPlannerRecipes((prev) =>
      prev.map((r) => {
        if (r.id !== recipeId) return r
        const currentDays =
          Array.isArray(r.assignedDays) && r.assignedDays.length > 0
            ? r.assignedDays
            : r.assignedDay
              ? [r.assignedDay]
              : []
        const exists = currentDays.includes(day)
        const nextDays = exists
          ? currentDays.filter((d) => d !== day)
          : [...currentDays, day]
        action = exists ? 'remove' : 'add'
        return { ...r, assignedDays: nextDays }
      })
    )
    showToast(
      action === 'add' ? `Dodano do dnia: ${day}` : `Usunięto z dnia: ${day}`,
      'success'
    )
  }, [showToast])

  // Delete recipe
  const handleDeleteRecipe = useCallback(async (id: number) => {
    try {
      await deleteRecipe(id)
      removeCustomRecipeCategory(id)
      mutateRecipes()
      mutateStats()
      setPlannerRecipes((prev) => prev.filter((r) => r.id !== id))
      showToast('Przepis usunięty', 'success')
    } catch {
      showToast('Nie udało się usunąć przepisu', 'error')
    }
  }, [mutateRecipes, mutateStats, showToast])

  // Handle recipe added
  const handleRecipeAdded = useCallback((recipe: Recipe) => {
    mutateRecipes(
      (prev) => {
        if (!prev) return [recipe]
        const withoutDuplicate = prev.filter((item) => item.id !== recipe.id)
        return [recipe, ...withoutDuplicate]
      },
      { revalidate: true }
    )
    mutateStats()
    console.log('[v0] Recipe added:', recipe.title)
  }, [mutateRecipes, mutateStats])

  const handleRateRecipe = useCallback(
    async (id: number, rating: number) => {
      try {
        await setRecipeRating(id, rating)
        mutateRecipes(
          (prev) => (prev ? prev.map((recipe) => (recipe.id === id ? { ...recipe, rating } : recipe)) : prev),
          { revalidate: false }
        )
        showToast('Ocena zapisana', 'success')
      } catch {
        showToast('Nie udało się zapisać oceny', 'error')
      }
    },
    [mutateRecipes, showToast]
  )

  const plannerSignature = useMemo(
    () => buildPlannerSignature(plannerRecipes),
    [plannerRecipes]
  )

  // Generate shopping list
  const handleGenerateShoppingList = useCallback(async (options?: { silent?: boolean }) => {
    if (plannerRecipes.length === 0) return

    setIsGeneratingList(true)
    try {
      const servings = plannerRecipes.reduce((acc, r) => {
        const dayCount = r.assignedDays && r.assignedDays.length > 0 ? r.assignedDays.length : 1
        acc[r.id] = (acc[r.id] ?? 0) + r.portions * dayCount
        return acc
      }, {} as Record<number, number>)
      const recipeIds = Object.keys(servings).map((id) => Number(id))

      const list = await generateShoppingList(recipeIds, servings)
      setShoppingList(list)
      const generatedAt = new Date().toISOString()
      const signature = buildPlannerSignature(plannerRecipes)
      setShoppingListMeta({ signature, generatedAt, isStale: false })
      if (!options?.silent) {
        setCurrentView('shopping')
        showToast('Lista zakupów wygenerowana!', 'success')
      }
    } catch {
      if (!options?.silent) {
        showToast('Nie udało się wygenerować listy', 'error')
      }
    } finally {
      setIsGeneratingList(false)
    }
  }, [plannerRecipes, showToast])

  useEffect(() => {
    if (plannerRecipes.length === 0) {
      if (shoppingList) {
        setShoppingList(null)
        setShoppingListMeta(null)
      }
      lastAutoRequestSignature.current = null
      return
    }

    if (!plannerSignature) return

    const isUpToDate =
      !!shoppingList &&
      shoppingListMeta?.signature === plannerSignature &&
      shoppingListMeta?.isStale === false

    if (isUpToDate) return

    if (shoppingList && shoppingListMeta?.signature !== plannerSignature && !shoppingListMeta?.isStale) {
      setShoppingListMeta((prev) =>
        prev ? { ...prev, isStale: true } : prev
      )
    }

    if (isGeneratingList) return

    if (lastAutoRequestSignature.current === plannerSignature) return
    lastAutoRequestSignature.current = plannerSignature

    const timeout = setTimeout(() => {
      handleGenerateShoppingList({ silent: true })
    }, 600)

    return () => clearTimeout(timeout)
  }, [
    plannerSignature,
    plannerRecipes.length,
    shoppingList,
    shoppingListMeta?.signature,
    shoppingListMeta?.isStale,
    isGeneratingList,
    handleGenerateShoppingList,
  ])

  useEffect(() => {
    if (
      shoppingListMeta?.isStale &&
      shoppingListMeta.signature === plannerSignature
    ) {
      setShoppingListMeta((prev) => (prev ? { ...prev, isStale: false } : prev))
    }
  }, [plannerSignature, shoppingListMeta?.isStale, shoppingListMeta?.signature])

  const plannerRecipeIds = plannerRecipes.map((r) => r.id)

  // Dashboard counters should update immediately based on current in-app state
  // (planner is localStorage-backed; shopping list is generated on demand / auto-refresh).
  const plannedMealsCount = useMemo(() => {
    return plannerRecipes.reduce((acc, recipe) => {
      const dayCount = recipe.assignedDays && recipe.assignedDays.length > 0 ? recipe.assignedDays.length : 1
      return acc + dayCount
    }, 0)
  }, [plannerRecipes])

  const shoppingItemsCount = useMemo(() => {
    if (!shoppingList) return 0
    return Object.values(shoppingList).reduce((acc, items) => {
      return acc + items.filter((item) => !item.checked).length
    }, 0)
  }, [shoppingList])

  const dashboardStats = useMemo<Stats>(() => {
    return {
      total_recipes: stats?.total_recipes ?? recipes.length,
      planned_meals: plannedMealsCount,
      shopping_items: shoppingItemsCount,
    }
  }, [plannedMealsCount, shoppingItemsCount, recipes.length, stats?.total_recipes])

  const recentRecipes = useMemo(() => {
    const sorted = [...recipes].sort((a, b) => {
      if (a.created_at && b.created_at) {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      }
      return (b.id ?? 0) - (a.id ?? 0)
    })
    return sorted.slice(0, 6)
  }, [recipes])

  useEffect(() => {
    if (currentView === 'admin' && !user.is_admin) {
      setCurrentView('dashboard')
    }
  }, [currentView, user.is_admin])

  return (
    <div className="min-h-screen bg-background">
      <Navigation
        currentView={currentView}
        onViewChange={setCurrentView}
        plannerCount={plannerRecipes.length}
        isAdmin={user.is_admin}
        userEmail={user.email}
        onLogout={onLogout}
      />

      <main className="pb-24 md:ml-64 md:pb-8">
        <div
          className={`mx-auto p-4 pt-6 md:p-8 ${
            currentView === 'planner' ? 'max-w-[1600px]' : 'max-w-6xl'
          }`}
        >
          {currentView === 'dashboard' && (
            <DashboardView
              stats={dashboardStats}
              recentRecipes={recentRecipes}
              isLoading={isLoadingStats || isLoadingRecipes}
              onViewRecipes={() => setCurrentView('recipes')}
              onRecipeAdded={handleRecipeAdded}
              onAddToPlanner={handleAddToPlanner}
              onDeleteRecipe={handleDeleteRecipe}
              plannerRecipeIds={plannerRecipeIds}
            />
          )}

          {currentView === 'recipes' && (
            <RecipesView
              recipes={recipes}
              isLoading={isLoadingRecipes}
              plannerRecipeIds={plannerRecipeIds}
              onAddToPlanner={handleAddToPlanner}
              onDeleteRecipe={handleDeleteRecipe}
              onRateRecipe={handleRateRecipe}
            />
          )}

          {currentView === 'add' && (
            <AddRecipeView onRecipeAdded={handleRecipeAdded} />
          )}

          {currentView === 'planner' && (
            <PlannerView
              plannerRecipes={plannerRecipes}
              onUpdatePortions={handleUpdatePortions}
              onRemoveFromPlanner={handleRemoveFromPlanner}
              onGenerateShoppingList={handleGenerateShoppingList}
              isGenerating={isGeneratingList}
              onAssignDay={handleAssignDay}
            />
          )}

          {currentView === 'shopping' && (
            <ShoppingView
              shoppingList={shoppingList}
              onRefresh={handleGenerateShoppingList}
              isLoading={isGeneratingList}
              listSignature={shoppingListMeta?.signature ?? null}
              isStale={shoppingListMeta?.isStale ?? false}
              userId={user.id}
            />
          )}

          {currentView === 'inspiracje' && (
            <InspirationsView onRecipeSaved={handleRecipeAdded} />
          )}

          {currentView === 'admin' && user.is_admin && <AdminView />}
        </div>
      </main>
    </div>
  )
}

function AppWithAuth() {
  const { user, isLoading, logout } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        Ladowanie...
      </div>
    )
  }

  if (!user) {
    return <LoginScreen />
  }

  return <KitchenOSApp key={user.id} user={user} onLogout={logout} />
}

export default function Home() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppWithAuth />
      </ToastProvider>
    </AuthProvider>
  )
}
