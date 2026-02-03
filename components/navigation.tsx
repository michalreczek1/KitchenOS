'use client'

import {
  LayoutDashboard,
  BookOpen,
  Plus,
  Calendar,
  ShoppingCart,
  ChefHat,
  Shield,
  LogOut,
  MoreHorizontal,
} from 'lucide-react'
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'

type View = 'dashboard' | 'recipes' | 'add' | 'planner' | 'shopping' | 'admin'

interface NavigationProps {
  currentView: View
  onViewChange: (view: View) => void
  plannerCount: number
  isAdmin?: boolean
  userEmail?: string | null
  onLogout?: () => void
}

const navItems = [
  { id: 'dashboard' as const, label: 'Pulpit', icon: LayoutDashboard, colorClass: 'icon-mint' },
  { id: 'recipes' as const, label: 'Przepisy', icon: BookOpen, colorClass: 'icon-peach' },
  { id: 'add' as const, label: 'Dodaj', icon: Plus, colorClass: 'icon-lavender' },
  { id: 'planner' as const, label: 'Planer', icon: Calendar, colorClass: 'icon-sky' },
  { id: 'shopping' as const, label: 'Zakupy', icon: ShoppingCart, colorClass: 'icon-rose' },
]

export function Navigation({
  currentView,
  onViewChange,
  plannerCount,
  isAdmin,
  userEmail,
  onLogout,
}: NavigationProps) {
  const items = isAdmin
    ? [...navItems, { id: 'admin' as const, label: 'Admin', icon: Shield, colorClass: 'icon-sky' }]
    : navItems
  const mobileItems = navItems

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="fixed top-0 left-0 z-40 hidden h-full w-64 flex-col border-r border-border/50 bg-sidebar/80 backdrop-blur-xl md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-border/50 px-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <ChefHat className="h-5 w-5" />
          </div>
          <span className="text-lg font-bold text-foreground">KitchenOS</span>
        </div>
        
        <nav className="flex-1 space-y-1 p-4">
          {items.map((item) => {
            const Icon = item.icon
            const isActive = currentView === item.id
            const showBadge = item.id === 'planner' && plannerCount > 0
            
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`relative flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-primary/10 text-foreground'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                }`}
              >
                <Icon className={`h-5 w-5 ${item.colorClass}`} />
                <span>{item.label}</span>
                {showBadge && (
                  <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
                    {plannerCount}
                  </span>
                )}
                {isActive && (
                  <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary" />
                )}
              </button>
            )
          })}
        </nav>

        <div className="border-t border-border/50 p-4">
          <div className="space-y-3 rounded-xl border border-border/50 bg-card/60 p-4 backdrop-blur-xl">
            <p className="text-xs text-muted-foreground">Twój asystent kulinarny z AI</p>
            {userEmail && (
              <div className="text-xs text-muted-foreground">
                Zalogowany: <span className="font-semibold text-foreground">{userEmail}</span>
              </div>
            )}
            {onLogout && (
              <button
                onClick={onLogout}
                className="flex items-center gap-2 text-xs font-semibold text-foreground transition-colors hover:text-primary"
              >
                <LogOut className="h-3.5 w-3.5" />
                Wyloguj
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border/50 bg-sidebar/90 backdrop-blur-xl md:hidden">
        <div className="flex items-center justify-around py-2">
          {mobileItems.map((item) => {
            const Icon = item.icon
            const isActive = currentView === item.id
            const showBadge = item.id === 'planner' && plannerCount > 0
            
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`relative flex flex-col items-center gap-1 rounded-xl px-4 py-2 transition-all ${
                  isActive
                    ? 'text-foreground'
                    : 'text-muted-foreground'
                }`}
              >
                <div className="relative">
                  <Icon className={`h-5 w-5 ${item.colorClass}`} />
                  {showBadge && (
                    <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
                      {plannerCount}
                    </span>
                  )}
                </div>
                <span className="text-[10px] font-medium">{item.label}</span>
                {isActive && (
                  <span className="absolute -top-2 left-1/2 h-1 w-8 -translate-x-1/2 rounded-full bg-primary" />
                )}
              </button>
            )
          })}
          {isAdmin ? (
            <Sheet>
              <SheetTrigger asChild>
                <button className="relative flex flex-col items-center gap-1 rounded-xl px-4 py-2 text-muted-foreground transition-all hover:text-foreground">
                  <MoreHorizontal className="h-5 w-5" />
                  <span className="text-[10px] font-medium">Menu</span>
                </button>
              </SheetTrigger>
              <SheetContent side="bottom" className="rounded-t-3xl border-t border-border/50">
                <SheetHeader>
                  <SheetTitle>Menu</SheetTitle>
                  {userEmail && (
                    <p className="text-xs text-muted-foreground">Zalogowany: {userEmail}</p>
                  )}
                </SheetHeader>
                <div className="space-y-2 px-4 pb-6">
                  <SheetClose asChild>
                    <button
                      onClick={() => onViewChange('admin')}
                      className="flex w-full items-center gap-3 rounded-xl border border-border/50 bg-card/60 px-4 py-3 text-sm font-semibold text-foreground"
                    >
                      <Shield className="h-4 w-4 icon-sky" />
                      Panel admina
                    </button>
                  </SheetClose>
                  {onLogout && (
                    <SheetClose asChild>
                      <button
                        onClick={onLogout}
                        className="flex w-full items-center gap-3 rounded-xl border border-border/50 bg-card/60 px-4 py-3 text-sm font-semibold text-foreground"
                      >
                        <LogOut className="h-4 w-4" />
                        Wyloguj
                      </button>
                    </SheetClose>
                  )}
                </div>
              </SheetContent>
            </Sheet>
          ) : (
            onLogout && (
              <button
                onClick={onLogout}
                className="relative flex flex-col items-center gap-1 rounded-xl px-4 py-2 text-muted-foreground transition-all hover:text-foreground"
              >
                <LogOut className="h-5 w-5" />
                <span className="text-[10px] font-medium">Wyloguj</span>
              </button>
            )
          )}
        </div>
      </nav>
    </>
  )
}
