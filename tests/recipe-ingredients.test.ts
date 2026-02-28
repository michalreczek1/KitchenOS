import { describe, expect, it } from 'vitest'
import {
  normalizeEditableIngredients,
  parseIngredientLine,
  serializeEditableIngredient,
} from '../lib/recipe-ingredients'

describe('recipe ingredient utils', () => {
  it('parses legacy ingredient lines with amount in parentheses', () => {
    const ingredient = parseIngredientLine('mleko (200 ml)')

    expect(ingredient.item).toBe('mleko')
    expect(ingredient.amount).toBe('200 ml')
  })

  it('parses canonical ingredient lines with amount prefix', () => {
    const ingredient = parseIngredientLine('200 g maka')

    expect(ingredient.item).toBe('maka')
    expect(ingredient.amount).toBe('200 g')
  })

  it('falls back to ingredient-only when no amount is detected', () => {
    const ingredient = parseIngredientLine('pieprz cytrynowy')

    expect(ingredient.item).toBe('pieprz cytrynowy')
    expect(ingredient.amount).toBe('')
  })

  it('serializes editable ingredients to canonical storage format', () => {
    expect(serializeEditableIngredient({ item: 'maka pszenna', amount: '200 g' })).toBe('200 g maka pszenna')
    expect(serializeEditableIngredient({ item: 'sol', amount: '' })).toBe('sol')
  })

  it('normalizes payloads by trimming and filtering empty rows', () => {
    const normalized = normalizeEditableIngredients([
      { item: ' maka ', amount: ' 200 g ' },
      { item: '  ', amount: '1 szt' },
      { item: 'jajka', amount: '' },
    ])

    expect(normalized).toEqual([
      { item: 'maka', amount: '200 g' },
      { item: 'jajka', amount: '' },
    ])
  })
})
