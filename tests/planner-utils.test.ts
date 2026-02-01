import { describe, expect, it } from 'vitest'
import { getNextAvailableDay } from '../lib/planner-utils'

describe('planner utils', () => {
  it('returns the next available day in order', () => {
    const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    expect(getNextAvailableDay(['Mon'], weekDays, 'Mon')).toBe('Tue')
    expect(getNextAvailableDay(['Fri', 'Sun'], weekDays, 'Fri')).toBe('Sat')
  })

  it('wraps to the start of the week', () => {
    const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    expect(getNextAvailableDay(['Sun'], weekDays, 'Sun')).toBe('Mon')
  })

  it('returns null when all days are assigned', () => {
    const weekDays = ['Mon', 'Tue', 'Wed']
    expect(getNextAvailableDay(['Mon', 'Tue', 'Wed'], weekDays, 'Mon')).toBeNull()
  })
})
