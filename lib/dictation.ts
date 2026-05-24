export type DictationInsertResult = {
  value: string
  cursor: number
}

type InsertDictationTextOptions = {
  value: string
  transcript: string
  selectionStart?: number | null
  selectionEnd?: number | null
}

const normalizeTranscript = (transcript: string) => transcript.trim().replace(/\s+/g, ' ')

const clampOffset = (offset: number | null | undefined, value: string) => {
  if (typeof offset !== 'number' || Number.isNaN(offset)) return value.length
  return Math.max(0, Math.min(value.length, offset))
}

const needsSpaceBetween = (left: string, right: string) => {
  if (!left || !right) return false
  if (/\s$/.test(left) || /^\s/.test(right)) return false
  return !/^[,.;:!?)]/.test(right)
}

export function insertDictationText({
  value,
  transcript,
  selectionStart,
  selectionEnd,
}: InsertDictationTextOptions): DictationInsertResult {
  const spokenText = normalizeTranscript(transcript)
  if (!spokenText) {
    return {
      value,
      cursor: clampOffset(selectionEnd ?? selectionStart, value),
    }
  }

  const start = clampOffset(selectionStart, value)
  const end = clampOffset(selectionEnd, value)
  const rangeStart = Math.min(start, end)
  const rangeEnd = Math.max(start, end)
  const before = value.slice(0, rangeStart)
  const after = value.slice(rangeEnd)
  const hasSelection = rangeEnd > rangeStart

  if (!value) {
    return {
      value: spokenText,
      cursor: spokenText.length,
    }
  }

  if (hasSelection) {
    const nextValue = `${before}${spokenText}${after}`
    return {
      value: nextValue,
      cursor: before.length + spokenText.length,
    }
  }

  const prefix = needsSpaceBetween(before, spokenText) ? ' ' : ''
  const suffix = rangeStart < value.length && needsSpaceBetween(spokenText, after) ? ' ' : ''
  const nextValue = `${before}${prefix}${spokenText}${suffix}${after}`

  return {
    value: nextValue,
    cursor: before.length + prefix.length + spokenText.length,
  }
}
