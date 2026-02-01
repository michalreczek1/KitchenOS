import type { ShoppingItem, ShoppingList } from './api'

export type RemainingItemsByCategory = Record<string, ShoppingItem[]>

export const getRemainingItemsByCategory = (
  shoppingList: ShoppingList | null,
  checkedItems: Record<string, boolean>
): RemainingItemsByCategory => {
  if (!shoppingList) return {}
  const entries = Object.entries(shoppingList)
    .map(([category, items]) => {
      const remaining = items.filter((_, index) => !checkedItems[`${category}-${index}`])
      return [category, remaining] as const
    })
    .filter(([, items]) => items.length > 0)
  return Object.fromEntries(entries)
}

export const countRemainingItems = (remaining: RemainingItemsByCategory): number => {
  return Object.values(remaining).reduce((sum, items) => sum + items.length, 0)
}

export const buildShareText = (remaining: RemainingItemsByCategory): string => {
  const lines: string[] = ['Lista zakupów (do kupienia):']
  Object.entries(remaining).forEach(([category, items]) => {
    lines.push('')
    lines.push(category)
    items.forEach((item) => {
      const suffix = item.amount ? ` (${item.amount})` : ''
      lines.push(`- ${item.name}${suffix}`)
    })
  })
  return lines.join('\n').trim()
}

export interface PrintLayoutConfig {
  columns: 2 | 3
  fontSize: number
}

export const getPrintLayoutConfig = (remaining: RemainingItemsByCategory): PrintLayoutConfig => {
  const totalLines = Object.values(remaining).reduce((sum, items) => sum + items.length + 1, 0)
  const columns = totalLines > 40 ? 3 : 2
  const fontSize = totalLines > 60 ? 9 : totalLines > 45 ? 10 : totalLines > 30 ? 11 : 12
  return { columns, fontSize }
}
