'use client'

import { useState, useEffect, useMemo, type CSSProperties } from 'react'
import { Check, ShoppingBag, RefreshCw, Package, Share2, FileDown } from 'lucide-react'
import type { ShoppingList } from '@/lib/api'
import { EmptyState } from '@/components/empty-state'
import { useToast } from '@/components/toast-provider'
import {
  buildShareText,
  countRemainingItems,
  getPrintLayoutConfig,
  getRemainingItemsByCategory,
} from '@/lib/shopping-utils'

interface ShoppingViewProps {
  shoppingList: ShoppingList | null
  onRefresh: () => void
  isLoading: boolean
  listSignature: string | null
  isStale?: boolean
  userId: number
}

interface CheckedItems {
  [key: string]: boolean
}

export function ShoppingView({ shoppingList, onRefresh, isLoading, listSignature, isStale, userId }: ShoppingViewProps) {
  const [checkedItems, setCheckedItems] = useState<CheckedItems>({})
  const { showToast } = useToast()

  const CHECKED_STORAGE_KEY = `kitchenOS_shopping_checked_${userId}`

  useEffect(() => {
    if (!listSignature) {
      setCheckedItems({})
      localStorage.removeItem(CHECKED_STORAGE_KEY)
      return
    }
    const saved = localStorage.getItem(CHECKED_STORAGE_KEY)
    if (!saved) {
      setCheckedItems({})
      return
    }
    try {
      const parsed = JSON.parse(saved) as { signature?: string; items?: CheckedItems }
      if (parsed.signature === listSignature && parsed.items) {
        setCheckedItems(parsed.items)
      } else {
        setCheckedItems({})
      }
    } catch {
      setCheckedItems({})
    }
  }, [listSignature])

  useEffect(() => {
    if (!listSignature) return
    localStorage.setItem(
      CHECKED_STORAGE_KEY,
      JSON.stringify({ signature: listSignature, items: checkedItems })
    )
  }, [checkedItems, listSignature])

  const toggleItem = (category: string, index: number) => {
    const key = `${category}-${index}`
    setCheckedItems((prev) => ({
      ...prev,
      [key]: !prev[key],
    }))
  }

  const getCategoryIcon = (category: string) => {
    const icons: { [key: string]: string } = {
      'Warzywa': '🥕',
      'Owoce': '🍎',
      'Mięso': '🥩',
      'Nabiał': '🥛',
      'Pieczywo': '🍞',
      'Przyprawy': '🧂',
      'Inne': '📦',
    }
    return icons[category] || '📦'
  }

  const totalItems = shoppingList
    ? Object.values(shoppingList).reduce((sum, items) => sum + items.length, 0)
    : 0

  const checkedCount = Object.values(checkedItems).filter(Boolean).length

  const remainingItemsByCategory = useMemo(
    () => getRemainingItemsByCategory(shoppingList, checkedItems),
    [shoppingList, checkedItems]
  )

  const remainingCount = useMemo(
    () => countRemainingItems(remainingItemsByCategory),
    [remainingItemsByCategory]
  )

  const printLayout = useMemo(
    () => getPrintLayoutConfig(remainingItemsByCategory),
    [remainingItemsByCategory]
  )

  const printDate = useMemo(() => new Date().toLocaleDateString('pl-PL'), [])

  const printStyles = {
    '--print-columns': String(printLayout.columns),
    '--print-font-size': `${printLayout.fontSize}px`,
  } as CSSProperties

  const copyToClipboard = async (text: string) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return
    }
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }

  const handleShareOrCopy = async () => {
    if (remainingCount === 0) {
      showToast('Brak produktów do udostępnienia', 'info')
      return
    }
    const text = buildShareText(remainingItemsByCategory)
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Lista zakupów', text })
        showToast('Lista udostępniona', 'success')
      } else {
        await copyToClipboard(text)
        showToast('Lista skopiowana', 'success')
      }
    } catch (error) {
      if ((error as DOMException)?.name !== 'AbortError') {
        showToast('Nie udało się udostępnić listy', 'error')
      }
    }
  }

  const handleExportPdf = () => {
    if (remainingCount === 0) {
      showToast('Brak produktów do PDF', 'info')
      return
    }
    window.print()
  }

  if (!shoppingList || Object.keys(shoppingList).length === 0) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-foreground">Lista Zakupów</h1>
          <p className="text-muted-foreground">
            Wygeneruj listę z planera, aby zobaczyć produkty
          </p>
        </div>
        <EmptyState
          type="shopping"
          title="Brak listy zakupów"
          description="Najpierw dodaj przepisy do planera i wygeneruj listę zakupów."
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section id="shopping-print" className="print-root" style={printStyles}>
        <div className="print-header">
          <div className="print-title">Lista zakupów</div>
          <div className="print-meta">{printDate}</div>
        </div>
        <div className="print-list">
          {Object.entries(remainingItemsByCategory).map(([category, items]) => (
            <div key={`print-${category}`} className="print-category">
              <div className="print-category-title">{category}</div>
              <ul>
                {items.map((item, index) => (
                  <li key={`${category}-${index}`}>
                    <span className="print-item-name">{item.name}</span>
                    {item.amount && <span className="print-item-amount">{item.amount}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <div className="no-print space-y-6">
        {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-foreground">Lista Zakupów</h1>
          <p className="text-muted-foreground">
            Odznaczaj produkty podczas zakupów
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isStale && (
            <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700">
              <span>Lista nieaktualna</span>
              {isLoading && <span className="text-amber-600/80">Odświeżanie...</span>}
            </div>
          )}
          <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-card/60 px-4 py-2 backdrop-blur-xl">
            <ShoppingBag className="h-4 w-4 icon-rose" />
            <span className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">{checkedCount}</span> / {totalItems}
            </span>
          </div>
          <button
            onClick={handleShareOrCopy}
            disabled={remainingCount === 0}
            title="Udostępnij lub skopiuj listę (tylko nieodznaczone)"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border/50 bg-card/60 text-muted-foreground backdrop-blur-xl transition-all hover:border-primary/50 hover:text-primary disabled:opacity-50"
          >
            <Share2 className="h-5 w-5" />
          </button>
          <button
            onClick={handleExportPdf}
            disabled={remainingCount === 0}
            title="Eksportuj PDF (1 strona, kilka kolumn)"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border/50 bg-card/60 text-muted-foreground backdrop-blur-xl transition-all hover:border-primary/50 hover:text-primary disabled:opacity-50"
          >
            <FileDown className="h-5 w-5" />
          </button>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border/50 bg-card/60 text-muted-foreground backdrop-blur-xl transition-all hover:border-primary/50 hover:text-primary disabled:opacity-50"
          >
            <RefreshCw className={`h-5 w-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="h-2 overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${totalItems > 0 ? (checkedCount / totalItems) * 100 : 0}%` }}
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {checkedCount === totalItems && totalItems > 0
            ? 'Wszystkie produkty kupione!'
            : `${totalItems - checkedCount} produktów pozostało`}
        </p>
      </div>

      {/* Categories */}
      <div className="space-y-4">
        {Object.entries(shoppingList).map(([category, items]) => (
          <div
            key={category}
            className="overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl"
          >
            <div className="flex items-center gap-3 border-b border-border/50 bg-secondary/30 px-4 py-3">
              <span className="text-xl">{getCategoryIcon(category)}</span>
              <h3 className="font-semibold text-foreground">{category}</h3>
              <span className="ml-auto text-sm text-muted-foreground">{items.length} produktów</span>
            </div>
            <div className="divide-y divide-border/30">
              {items.map((item, index) => {
                const key = `${category}-${index}`
                const isChecked = checkedItems[key]

                return (
                  <button
                    key={key}
                    onClick={() => toggleItem(category, index)}
                    className="flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-secondary/30"
                  >
                    <div
                      className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg border-2 transition-all ${
                        isChecked
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-transparent'
                      }`}
                    >
                      {isChecked && <Check className="h-4 w-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span
                        className={`block truncate transition-all ${
                          isChecked
                            ? 'text-muted-foreground line-through opacity-50'
                            : 'text-foreground'
                        }`}
                      >
                        {item.name}
                      </span>
                    </div>
                    <span
                      className={`flex-shrink-0 text-sm ${
                        isChecked ? 'text-muted-foreground/50' : 'text-muted-foreground'
                      }`}
                    >
                      {item.amount}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Empty Completed State */}
      {checkedCount === totalItems && totalItems > 0 && (
        <div className="rounded-2xl border border-primary/30 bg-primary/10 p-6 text-center">
          <Package className="mx-auto mb-3 h-12 w-12 text-primary" />
          <h3 className="mb-1 font-semibold text-foreground">Zakupy ukończone!</h3>
          <p className="text-sm text-muted-foreground">
            Wszystkie produkty zostały kupione. Miłego gotowania!
          </p>
        </div>
      )}
    </div>
    </div>
  )
}
