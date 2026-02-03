import type { RecipeCategory } from '@/lib/api'

export const categoryStyles: Record<RecipeCategory, { base: string; active: string }> = {
  obiady: {
    base: 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100',
    active: 'border-amber-300 bg-amber-200 text-amber-900 shadow-[0_8px_18px_rgba(245,158,11,0.25)]',
  },
  sniadania: {
    base: 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
    active: 'border-sky-300 bg-sky-200 text-sky-900 shadow-[0_8px_18px_rgba(56,189,248,0.25)]',
  },
  lunchbox: {
    base: 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100',
    active: 'border-violet-300 bg-violet-200 text-violet-900 shadow-[0_8px_18px_rgba(139,92,246,0.25)]',
  },
  salatki: {
    base: 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
    active: 'border-emerald-300 bg-emerald-200 text-emerald-900 shadow-[0_8px_18px_rgba(16,185,129,0.25)]',
  },
  pieczywo: {
    base: 'border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100',
    active: 'border-orange-300 bg-orange-200 text-orange-900 shadow-[0_8px_18px_rgba(249,115,22,0.25)]',
  },
  desery: {
    base: 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100',
    active: 'border-rose-300 bg-rose-200 text-rose-900 shadow-[0_8px_18px_rgba(244,63,94,0.25)]',
  },
  inne: {
    base: 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100',
    active: 'border-slate-300 bg-slate-200 text-slate-900 shadow-[0_8px_18px_rgba(148,163,184,0.25)]',
  },
}

export const allCategoryStyles = {
  base: 'border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100',
  active: 'border-indigo-300 bg-indigo-200 text-indigo-900 shadow-[0_8px_18px_rgba(99,102,241,0.25)]',
}
