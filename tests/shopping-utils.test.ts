import { describe, expect, it } from 'vitest'
import {
  buildShareText,
  countRemainingItems,
  getPrintLayoutConfig,
  getRemainingItemsByCategory,
} from '../lib/shopping-utils'

describe('shopping utils', () => {
  it('filters out checked items and empty categories', () => {
    const shoppingList = {
      Warzywa: [
        { name: 'Cebula', amount: '2 szt' },
        { name: 'Marchew', amount: '' },
      ],
      Nabial: [{ name: 'Mleko', amount: '1 l' }],
    }
    const checked = {
      'Warzywa-1': true,
    }

    const remaining = getRemainingItemsByCategory(shoppingList, checked)

    expect(remaining.Warzywa).toHaveLength(1)
    expect(remaining.Warzywa[0].name).toBe('Cebula')
    expect(remaining.Nabial).toHaveLength(1)
    expect(countRemainingItems(remaining)).toBe(2)
  })

  it('builds share text for remaining items', () => {
    const remaining = {
      Warzywa: [{ name: 'Cebula', amount: '2 szt' }],
      Nabial: [{ name: 'Mleko', amount: '1 l' }],
    }

    const text = buildShareText(remaining)

    expect(text).toContain('Lista zakup')
    expect(text).toContain('Warzywa')
    expect(text).toContain('- Cebula (2 szt)')
    expect(text).toContain('- Mleko (1 l)')
  })

  it('picks print layout based on item count', () => {
    const items = Array.from({ length: 50 }, (_, index) => ({
      name: `Item ${index + 1}`,
      amount: '',
    }))
    const remaining = {
      Produkty: items,
    }

    const config = getPrintLayoutConfig(remaining)

    expect(config.columns).toBe(3)
    expect(config.fontSize).toBe(10)
  })
})
