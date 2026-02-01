export const getNextAvailableDay = (
  assignedDays: string[],
  weekDays: string[],
  currentDay: string
): string | null => {
  if (weekDays.length === 0) return null
  const assignedSet = new Set(assignedDays)
  if (assignedSet.size >= weekDays.length) return null

  const startIndex = weekDays.indexOf(currentDay)
  if (startIndex === -1) return null

  for (let offset = 1; offset <= weekDays.length; offset += 1) {
    const candidate = weekDays[(startIndex + offset) % weekDays.length]
    if (!assignedSet.has(candidate)) {
      return candidate
    }
  }

  return null
}
