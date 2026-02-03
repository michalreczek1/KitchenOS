import type { RecipeCategory } from '@/lib/api'

export const GENERIC_RECIPE_IMAGE_URL = 'https://cdn-icons-png.flaticon.com/512/3081/3081557.png'

const PLACEHOLDER_MAP: Record<RecipeCategory, string> = {
  obiady: '/recipe-placeholders/soup.svg',
  sniadania: '/recipe-placeholders/bread.svg',
  lunchbox: '/recipe-placeholders/default.svg',
  salatki: '/recipe-placeholders/salad.svg',
  pieczywo: '/recipe-placeholders/bread.svg',
  desery: '/recipe-placeholders/dessert.svg',
  inne: '/recipe-placeholders/default.svg',
}

const CATEGORY_HINTS: Array<{ category: RecipeCategory; pattern: RegExp }> = [
  {
    category: 'desery',
    pattern: /(deser|ciasto|tort|babeczka|muffin|pudding|krem|szarlotka|sernik|brownie)/i,
  },
  {
    category: 'lunchbox',
    pattern: /(lunch|lunchbox|bento|do pracy|na wynos|box)/i,
  },
  {
    category: 'salatki',
    pattern: /(sa\u0142at|salat|salad|rukola)/i,
  },
  {
    category: 'sniadania',
    pattern: /(sniad|\u015bniad|breakfast|owsianka|omlet|jajecznic|kanapk)/i,
  },
  {
    category: 'pieczywo',
    pattern: /(chleb|bu\u0142k|bagiet|pizza|dro\u017cd\u017c|bu\u0142ecz)/i,
  },
  {
    category: 'obiady',
    pattern: /(zupa|roso\u0142|ramen|gulasz|curry|stew|zapiek|makaron|risotto|kaszotto|kurczak|ryba)/i,
  },
]

const inferCategoryFromTitle = (title?: string): RecipeCategory | undefined => {
  if (!title) return undefined
  const trimmed = title.trim()
  if (!trimmed) return undefined
  const match = CATEGORY_HINTS.find((entry) => entry.pattern.test(trimmed))
  return match?.category
}

export const getCustomRecipePlaceholder = (category?: RecipeCategory, title?: string) => {
  const resolvedCategory = category ?? inferCategoryFromTitle(title) ?? 'inne'
  return PLACEHOLDER_MAP[resolvedCategory]
}
