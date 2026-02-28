import type { RecipeIngredientPayload } from '@/lib/api'

export interface EditableIngredient {
  id: string
  item: string
  amount: string
}

let editableIngredientCounter = 0

const PREFIX_AMOUNT_PATTERN =
  /^\s*(\d+(?:[.,]\d+)?(?:\s*\/\s*\d+(?:[.,]\d+)?)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?\s*(kg|g|ml|l|szt(?:uk(?:i)?)?|lyzki?|łyżki?|lyzeczki?|łyżeczki?|szklanki?|opakowani(?:e|a)|zabki?|ząbki?|glowki?|główki?|puszki?|paczki?|plasterki?|kromki?)\b[\s,.-]*(.+)$/i

const createEditableIngredientId = () => {
  editableIngredientCounter += 1
  return `ingredient-${editableIngredientCounter}`
}

export const createEditableIngredient = (item = '', amount = ''): EditableIngredient => ({
  id: createEditableIngredientId(),
  item,
  amount,
})

export const parseIngredientLine = (line: string): EditableIngredient => {
  const trimmed = line.trim()
  if (!trimmed) return createEditableIngredient()

  const legacyMatch = trimmed.match(/^(.*)\(([^)]+)\)\s*$/)
  if (legacyMatch) {
    const item = legacyMatch[1]?.trim() ?? ''
    const amount = legacyMatch[2]?.trim() ?? ''
    if (item && amount) {
      return createEditableIngredient(item, amount)
    }
  }

  const prefixMatch = trimmed.match(PREFIX_AMOUNT_PATTERN)
  if (prefixMatch) {
    const quantity = prefixMatch[1]?.trim() ?? ''
    const rangeMax = prefixMatch[2]?.trim() ?? ''
    const unit = prefixMatch[3]?.trim() ?? ''
    const item = prefixMatch[4]?.trim() ?? ''
    if (item) {
      const amount = `${quantity}${rangeMax ? `-${rangeMax}` : ''} ${unit}`.trim()
      return createEditableIngredient(item, amount)
    }
  }

  return createEditableIngredient(trimmed, '')
}

export const serializeEditableIngredient = (draft: Pick<EditableIngredient, 'item' | 'amount'>): string => {
  const item = draft.item.trim()
  const amount = draft.amount.trim()
  if (!item) return ''
  return amount ? `${amount} ${item}`.trim() : item
}

export const normalizeEditableIngredients = (
  drafts: Array<Pick<EditableIngredient, 'item' | 'amount'>>
): RecipeIngredientPayload[] =>
  drafts
    .map((draft) => ({
      item: draft.item.trim(),
      amount: draft.amount.trim(),
    }))
    .filter((draft) => draft.item.length > 0)
