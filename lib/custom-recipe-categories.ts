import type { RecipeCategory } from '@/lib/api'

const STORAGE_KEY = 'kitchenOS_custom_recipe_categories'

type CategoryMap = Record<number, RecipeCategory>

const readCategoryMap = (): CategoryMap => {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as CategoryMap
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

const writeCategoryMap = (map: CategoryMap) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
}

export const saveCustomRecipeCategory = (id: number, category: RecipeCategory) => {
  const map = readCategoryMap()
  map[id] = category
  writeCategoryMap(map)
}

export const removeCustomRecipeCategory = (id: number) => {
  const map = readCategoryMap()
  if (!(id in map)) return
  delete map[id]
  writeCategoryMap(map)
}

export const getCustomRecipeCategoryMap = () => readCategoryMap()
