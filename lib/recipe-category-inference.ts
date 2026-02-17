import type { RecipeCategory } from '@/lib/api'

interface InferRecipeCategoryInput {
  title?: string
  ingredients?: string[]
  rawText?: string
}

const normalizeForMatch = (value: string) =>
  value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')

const containsAny = (blob: string, patterns: RegExp[]) => patterns.some((pattern) => pattern.test(blob))

const DESSERT_PATTERNS = [
  /\bdeser\w*\b/,
  /\bciast\w*\b/,
  /\btort\w*\b/,
  /\bsernik\w*\b/,
  /\bbrownie\b/,
  /\bmuffin\w*\b/,
  /\bbabeczk\w*\b/,
  /\bpaczk\w*\b/,
  /\boponk\w*\b/,
  /\blod\w*\b/,
  /\bkarmel\w*\b/,
  /\bczekolad\w*\b/,
  /\bciasteczk\w*\b/,
]

const SWEET_PATTERNS = [/\bcukier\w*\b/, /\bmiod\w*\b/, /\bsyrop\w*\b/, /\bwanili\w*\b/, /\bslod\w*\b/]
const SNACK_PATTERNS = [/\bmigdal\w*\b/, /\borzech\w*\b/, /\bprzekask\w*\b/, /\bcukierk\w*\b/]
const MEAL_PATTERNS = [/\bkurczak\w*\b/, /\bmieso\w*\b/, /\bziemniak\w*\b/, /\bryz\w*\b/, /\bmakaron\w*\b/]

const CATEGORY_HINTS: Array<{ category: RecipeCategory; patterns: RegExp[] }> = [
  { category: 'lunchbox', patterns: [/\blunch\b/, /\blunchbox\b/, /\bbento\b/, /\bna wynos\b/, /\bdo pracy\b/] },
  { category: 'salatki', patterns: [/\bsalat\w*\b/, /\bsalad\b/, /\brukol\w*\b/] },
  { category: 'sniadania', patterns: [/\bsniadan\w*\b/, /\bbreakfast\b/, /\bowsiank\w*\b/, /\bomlet\w*\b/, /\bjajecznic\w*\b/] },
  { category: 'pieczywo', patterns: [/\bchleb\w*\b/, /\bbulk\w*\b/, /\bbagiet\w*\b/, /\bpizza\b/, /\bdrozdz\w*\b/] },
  { category: 'obiady', patterns: [/\bzupa\w*\b/, /\brosol\w*\b/, /\bgulasz\w*\b/, /\bcurry\b/, /\bramen\b/, /\blasagn\w*\b/, /\brisotto\b/] },
]

export const inferRecipeCategory = (input: InferRecipeCategoryInput): RecipeCategory | null => {
  const blob = normalizeForMatch(
    [input.title ?? '', ...(input.ingredients ?? []), input.rawText ?? '']
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()
  )

  if (!blob) return null

  const looksLikeSweetSnack = containsAny(blob, SWEET_PATTERNS) && containsAny(blob, SNACK_PATTERNS) && !containsAny(blob, MEAL_PATTERNS)
  if (looksLikeSweetSnack || containsAny(blob, DESSERT_PATTERNS)) {
    return 'desery'
  }

  for (const hint of CATEGORY_HINTS) {
    if (containsAny(blob, hint.patterns)) {
      return hint.category
    }
  }

  return null
}
