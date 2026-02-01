'use client'

import { useState } from 'react'
import { ChefHat, LogIn, ShieldCheck, KeyRound } from 'lucide-react'
import { useAuth } from '@/components/auth-provider'
import { useToast } from '@/components/toast-provider'

export function LoginScreen() {
  const { login, bootstrapAdmin } = useAuth()
  const { showToast } = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showBootstrap, setShowBootstrap] = useState(false)
  const [bootstrapToken, setBootstrapToken] = useState('')

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!email.trim() || !password.trim()) {
      showToast('Podaj email i hasło', 'error')
      return
    }
    setIsLoading(true)
    try {
      await login(email.trim(), password)
      showToast('Zalogowano', 'success')
    } catch {
      showToast('Nieprawidłowy email lub hasło', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleBootstrap = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!email.trim() || !password.trim()) {
      showToast('Podaj email i hasło administratora', 'error')
      return
    }
    setIsLoading(true)
    try {
      await bootstrapAdmin(email.trim(), password, bootstrapToken.trim() || undefined)
      showToast('Administrator utworzony', 'success')
    } catch {
      showToast('Nie udało się utworzyć administratora', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen max-w-lg flex-col items-center justify-center p-6">
        <div className="w-full rounded-3xl border border-border/50 bg-card/70 p-8 shadow-lg backdrop-blur-xl">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
              <ChefHat className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">KitchenOS</h1>
              <p className="text-sm text-muted-foreground">Zaloguj się, aby kontynuować</p>
            </div>
          </div>

          <form onSubmit={showBootstrap ? handleBootstrap : handleLogin} className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Email</label>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Hasło</label>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>

            {showBootstrap && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Token bootstrap (opcjonalny)</label>
                <input
                  type="text"
                  value={bootstrapToken}
                  onChange={(event) => setBootstrapToken(event.target.value)}
                  placeholder="ADMIN_BOOTSTRAP_TOKEN"
                  className="w-full rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-primary py-3 text-sm font-semibold text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-60"
            >
              {showBootstrap ? <ShieldCheck className="h-4 w-4" /> : <LogIn className="h-4 w-4" />}
              {isLoading ? 'Przetwarzanie...' : showBootstrap ? 'Utwórz administratora' : 'Zaloguj'}
            </button>
          </form>

          <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
            <span>Brak konta? Skontaktuj się z administratorem.</span>
            <button
              type="button"
              onClick={() => setShowBootstrap((prev) => !prev)}
              className="inline-flex items-center gap-1 font-semibold text-primary hover:text-primary/80"
            >
              <KeyRound className="h-3.5 w-3.5" />
              {showBootstrap ? 'Logowanie' : 'Bootstrap admin'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
