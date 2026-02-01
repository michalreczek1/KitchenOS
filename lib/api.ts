import { getCustomRecipeCategoryMap } from '@/lib/custom-recipe-categories'

// Use environment variable, or fallback to same host as the frontend (for LAN access)
const getApiBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }
  // In browser, use the same hostname as frontend but port 8000
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`
  }
  // Server-side fallback
  return 'http://127.0.0.1:8000'
}

const API_BASE_URL = getApiBaseUrl()
const isHttpUrl = (value?: string) => typeof value === 'string' && /^https?:\/\//i.test(value)
const AUTH_TOKEN_KEY = 'kitchenOS_token'

export const getAuthToken = () => {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(AUTH_TOKEN_KEY)
}

export const setAuthToken = (token: string | null) => {
  if (typeof window === 'undefined') return
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY)
  }
}

const emitLogoutEvent = () => {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('kitchenos:logout'))
}

const apiFetch = async (path: string, options: RequestInit = {}) => {
  const headers = new Headers(options.headers ?? {})
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAuthToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })
  if (response.status === 401) {
    setAuthToken(null)
    emitLogoutEvent()
  }
  return response
}

export type RecipeCategory = 'obiady' | 'salatki' | 'pieczywo' | 'desery' | 'inne'

export const RECIPE_CATEGORIES: { value: RecipeCategory; label: string }[] = [
  { value: 'obiady', label: 'Obiady' },
  { value: 'salatki', label: 'Sałatki' },
  { value: 'pieczywo', label: 'Pieczywo' },
  { value: 'desery', label: 'Desery' },
  { value: 'inne', label: 'Inne' },
]

export interface Recipe {
  id: number
  title: string
  image_url: string
  source_url: string
  category?: RecipeCategory
  created_at?: string
}

export interface RecipeDetails extends Recipe {
  ingredients: string[]
  instructions: string[]
  servings: number
  prep_time?: string
  cook_time?: string
}

export interface Stats {
  total_recipes: number
  planned_meals: number
  shopping_items: number
}

export interface AuthUser {
  id: number
  email: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  last_login_at?: string | null
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  expires_in_days: number
}

export interface AdminUserCreateResponse {
  user: AuthUser
  temporary_password?: string | null
}

export interface ParseLogEntry {
  id: number
  owner_id: number
  url: string
  domain?: string | null
  status: string
  error_message?: string | null
  created_at: string
}

export interface DomainStat {
  domain: string
  count: number
}

export interface AdminStatsResponse {
  total_users: number
  active_users_dau: number
  active_users_mau: number
  total_recipes: number
  recipes_with_images: number
  top_domains: DomainStat[]
}

export interface ShoppingItem {
  name: string
  amount: string
  checked?: boolean
}

export interface ShoppingList {
  [category: string]: ShoppingItem[]
}

export interface ShoppingCategory {
  category: string
  items: string[]
}

export interface ShoppingListResponse {
  shopping_list: ShoppingCategory[]
  total_recipes: number
  generated_at: string
}

const parseShoppingItem = (item: string): ShoppingItem => {
  const trimmed = item.trim()
  const match = trimmed.match(/^(.*)\(([^)]+)\)\s*$/)
  if (match) {
    return { name: match[1].trim(), amount: match[2].trim() }
  }
  return { name: trimmed, amount: '' }
}

const normalizeShoppingList = (response: ShoppingListResponse): ShoppingList => {
  const list: ShoppingList = {}
  for (const category of response.shopping_list ?? []) {
    if (!category || !category.category) continue
    list[category.category] = (category.items ?? []).map(parseShoppingItem)
  }
  return list
}

export interface PlannerRecipe extends Recipe {
  portions: number
  assignedDays?: string[]
  assignedDay?: string
}

export async function fetchRecipes(): Promise<Recipe[]> {
  const response = await apiFetch('/api/recipes/available')
  if (!response.ok) {
    throw new Error('Failed to fetch recipes')
  }
  const data = (await response.json()) as Recipe[]
  if (typeof window === 'undefined') return data

  const categoryMap = getCustomRecipeCategoryMap()
  if (!categoryMap || Object.keys(categoryMap).length === 0) return data

  return data.map((recipe) => {
    if (recipe.category) return recipe
    const sourceUrl =
      (recipe as Recipe & { source_url?: string; url?: string }).source_url ??
      (recipe as Recipe & { url?: string }).url
    const isCustom = !isHttpUrl(sourceUrl)
    if (!isCustom) return recipe
    const storedCategory = categoryMap[recipe.id]
    return storedCategory ? { ...recipe, category: storedCategory } : recipe
  })
}

export async function fetchRecipeDetails(id: number): Promise<RecipeDetails> {
  const response = await apiFetch(`/api/recipes/${id}`)
  if (!response.ok) {
    throw new Error('Failed to fetch recipe details')
  }
  return response.json()
}

export async function fetchStats(): Promise<Stats> {
  const response = await apiFetch('/api/stats')
  if (!response.ok) {
    throw new Error('Failed to fetch stats')
  }
  return response.json()
}

export async function parseRecipe(url: string): Promise<Recipe> {
  const response = await apiFetch('/api/parse-recipe', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
  if (!response.ok) {
    throw new Error('Failed to parse recipe')
  }
  return response.json()
}

export async function generateShoppingList(
  recipeIds: number[],
  servings: Record<number, number>
): Promise<ShoppingList> {
  const response = await apiFetch('/api/planner/generate', {
    method: 'POST',
    body: JSON.stringify({
      selections: recipeIds.map((id) => ({
        id,
        portions: servings[id] ?? 1,
      })),
    }),
  })
  if (!response.ok) {
    throw new Error('Failed to generate shopping list')
  }
  const data = (await response.json()) as ShoppingListResponse
  return normalizeShoppingList(data)
}

export async function deleteRecipe(id: number): Promise<void> {
  const response = await apiFetch(`/api/recipes/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete recipe')
  }
}

export interface ManualRecipeData {
  content: string
}

export async function addManualRecipe(data: ManualRecipeData): Promise<Recipe> {
  const response = await apiFetch('/api/recipes/custom', {
    method: 'POST',
    body: JSON.stringify({ content: data.content }),
  })
  if (!response.ok) {
    throw new Error('Failed to add manual recipe')
  }
  return response.json()
}

export async function login(email: string, password: string): Promise<AuthTokenResponse> {
  const response = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) {
    throw new Error('Failed to login')
  }
  return response.json()
}

export async function fetchMe(): Promise<AuthUser> {
  const response = await apiFetch('/api/auth/me')
  if (!response.ok) {
    throw new Error('Failed to fetch user')
  }
  return response.json()
}

export async function bootstrapAdmin(email: string, password: string, token?: string): Promise<AuthUser> {
  const response = await apiFetch('/api/auth/bootstrap', {
    method: 'POST',
    body: JSON.stringify({ email, password, token }),
  })
  if (!response.ok) {
    throw new Error('Failed to bootstrap admin')
  }
  return response.json()
}

export async function fetchAdminUsers(): Promise<AuthUser[]> {
  const response = await apiFetch('/api/admin/users')
  if (!response.ok) {
    throw new Error('Failed to fetch users')
  }
  return response.json()
}

export async function createAdminUser(payload: {
  email: string
  password?: string
  is_admin?: boolean
}): Promise<AdminUserCreateResponse> {
  const response = await apiFetch('/api/admin/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error('Failed to create user')
  }
  return response.json()
}

export async function updateAdminUser(
  userId: number,
  payload: { is_active?: boolean; is_admin?: boolean }
): Promise<AuthUser> {
  const response = await apiFetch(`/api/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error('Failed to update user')
  }
  return response.json()
}

export async function resetAdminUserPassword(userId: number): Promise<{ user_id: number; temporary_password: string }> {
  const response = await apiFetch(`/api/admin/users/${userId}/reset-password`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('Failed to reset password')
  }
  return response.json()
}

export async function deleteAdminUser(userId: number): Promise<void> {
  const response = await apiFetch(`/api/admin/users/${userId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete user')
  }
}

export async function fetchAdminStats(): Promise<AdminStatsResponse> {
  const response = await apiFetch('/api/admin/stats')
  if (!response.ok) {
    throw new Error('Failed to fetch admin stats')
  }
  return response.json()
}

export async function fetchParseLogs(limit = 100): Promise<ParseLogEntry[]> {
  const response = await apiFetch(`/api/admin/parse-logs?limit=${limit}`)
  if (!response.ok) {
    throw new Error('Failed to fetch parse logs')
  }
  return response.json()
}
