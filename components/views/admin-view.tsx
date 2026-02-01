'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  fetchAdminUsers,
  createAdminUser,
  updateAdminUser,
  resetAdminUserPassword,
  deleteAdminUser,
  fetchAdminStats,
  fetchParseLogs,
  type AuthUser,
  type AdminStatsResponse,
  type ParseLogEntry,
} from '@/lib/api'
import { useToast } from '@/components/toast-provider'
import { Shield, Users, Activity, FileWarning } from 'lucide-react'

type TabKey = 'users' | 'stats' | 'logs'

export function AdminView() {
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState<TabKey>('users')
  const [users, setUsers] = useState<AuthUser[]>([])
  const [stats, setStats] = useState<AdminStatsResponse | null>(null)
  const [logs, setLogs] = useState<ParseLogEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newIsAdmin, setNewIsAdmin] = useState(false)
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  const refreshUsers = async () => {
    const data = await fetchAdminUsers()
    setUsers(data)
  }

  const refreshStats = async () => {
    const data = await fetchAdminStats()
    setStats(data)
  }

  const refreshLogs = async () => {
    const data = await fetchParseLogs(100)
    setLogs(data)
  }

  useEffect(() => {
    setIsLoading(true)
    Promise.all([refreshUsers(), refreshStats(), refreshLogs()])
      .catch(() => showToast('Nie udało się pobrać danych admina', 'error'))
      .finally(() => setIsLoading(false))
  }, [showToast])

  const handleCreateUser = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!newEmail.trim()) {
      showToast('Podaj email użytkownika', 'error')
      return
    }
    setIsLoading(true)
    try {
      const result = await createAdminUser({
        email: newEmail.trim(),
        password: newPassword.trim() || undefined,
        is_admin: newIsAdmin,
      })
      setNewEmail('')
      setNewPassword('')
      setNewIsAdmin(false)
      setTempPassword(result.temporary_password ?? null)
      await refreshUsers()
      showToast('Użytkownik utworzony', 'success')
    } catch {
      showToast('Nie udało się utworzyć użytkownika', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const toggleUser = async (user: AuthUser, key: 'is_active' | 'is_admin') => {
    setIsLoading(true)
    try {
      await updateAdminUser(user.id, { [key]: !user[key] })
      await refreshUsers()
    } catch {
      showToast('Nie udało się zaktualizować użytkownika', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleResetPassword = async (user: AuthUser) => {
    setIsLoading(true)
    try {
      const result = await resetAdminUserPassword(user.id)
      setTempPassword(result.temporary_password)
      showToast('Hasło zresetowane', 'success')
    } catch {
      showToast('Nie udało się zresetować hasła', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteUser = async (user: AuthUser) => {
    if (!confirm(`Usunąć użytkownika ${user.email}?`)) return
    setIsLoading(true)
    try {
      await deleteAdminUser(user.id)
      await refreshUsers()
      showToast('Użytkownik usunięty', 'success')
    } catch {
      showToast('Nie udało się usunąć użytkownika', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const statsCards = useMemo(() => {
    if (!stats) return []
    return [
      { label: 'Użytkownicy', value: stats.total_users },
      { label: 'DAU', value: stats.active_users_dau },
      { label: 'MAU', value: stats.active_users_mau },
      { label: 'Przepisy', value: stats.total_recipes },
      { label: 'Przepisy z obrazem', value: stats.recipes_with_images },
    ]
  }, [stats])

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-primary">
          <Shield className="h-5 w-5" />
          <span className="text-sm font-medium">Panel administratora</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground">Administracja</h1>
        <p className="text-muted-foreground">Zarządzaj użytkownikami i monitoruj system</p>
      </div>

      <div className="flex flex-wrap gap-2 rounded-2xl border border-border/50 bg-card/60 p-2 backdrop-blur-xl">
        {([
          { key: 'users', label: 'Użytkownicy', icon: Users },
          { key: 'stats', label: 'Statystyki', icon: Activity },
          { key: 'logs', label: 'Logi parsowania', icon: FileWarning },
        ] as const).map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
                isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'users' && (
        <div className="space-y-6">
          <form
            onSubmit={handleCreateUser}
            className="rounded-2xl border border-border/50 bg-card/60 p-5 backdrop-blur-xl"
          >
            <h3 className="mb-4 text-lg font-semibold text-foreground">Dodaj użytkownika</h3>
            <div className="grid gap-4 md:grid-cols-3">
              <input
                type="email"
                placeholder="Email"
                value={newEmail}
                onChange={(event) => setNewEmail(event.target.value)}
                className="rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm"
              />
              <input
                type="text"
                placeholder="Hasło (opcjonalne)"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className="rounded-xl border border-border/50 bg-background/80 px-4 py-3 text-sm"
              />
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={newIsAdmin}
                  onChange={(event) => setNewIsAdmin(event.target.checked)}
                />
                Administrator
              </label>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <button
                type="submit"
                disabled={isLoading}
                className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
              >
                Utwórz użytkownika
              </button>
              {tempPassword && (
                <div className="text-xs text-muted-foreground">
                  Hasło tymczasowe: <span className="font-semibold text-foreground">{tempPassword}</span>
                </div>
              )}
            </div>
          </form>

          <div className="overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl">
            <div className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-4 border-b border-border/50 px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">
              <span>Email</span>
              <span>Rola</span>
              <span>Status</span>
              <span>Akcje</span>
            </div>
            <div className="divide-y divide-border/30">
              {users.map((user) => (
                <div key={user.id} className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-4 px-4 py-3 text-sm">
                  <span className="truncate">{user.email}</span>
                  <button
                    onClick={() => toggleUser(user, 'is_admin')}
                    className={`rounded-lg px-2 py-1 text-xs font-semibold ${
                      user.is_admin ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {user.is_admin ? 'Admin' : 'User'}
                  </button>
                  <button
                    onClick={() => toggleUser(user, 'is_active')}
                    className={`rounded-lg px-2 py-1 text-xs font-semibold ${
                      user.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                    }`}
                  >
                    {user.is_active ? 'Aktywny' : 'Zablokowany'}
                  </button>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handleResetPassword(user)}
                      className="text-xs font-semibold text-primary hover:underline"
                    >
                      Reset hasła
                    </button>
                    <button
                      onClick={() => handleDeleteUser(user)}
                      className="text-xs font-semibold text-destructive hover:underline"
                    >
                      Usuń
                    </button>
                  </div>
                </div>
              ))}
              {users.length === 0 && (
                <div className="px-4 py-6 text-center text-sm text-muted-foreground">Brak użytkowników</div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'stats' && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {statsCards.map((card) => (
              <div key={card.label} className="rounded-2xl border border-border/50 bg-card/60 p-5 backdrop-blur-xl">
                <p className="text-sm text-muted-foreground">{card.label}</p>
                <p className="text-2xl font-bold text-foreground">{card.value}</p>
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-border/50 bg-card/60 p-5 backdrop-blur-xl">
            <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Top domeny importu</h3>
            <div className="space-y-2">
              {stats?.top_domains.length ? (
                stats.top_domains.map((entry) => (
                  <div key={entry.domain} className="flex items-center justify-between text-sm">
                    <span>{entry.domain}</span>
                    <span className="font-semibold text-foreground">{entry.count}</span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">Brak danych</p>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'logs' && (
        <div className="rounded-2xl border border-border/50 bg-card/60 backdrop-blur-xl">
          <div className="grid grid-cols-[2fr_1fr_1fr] gap-4 border-b border-border/50 px-4 py-3 text-xs font-semibold uppercase text-muted-foreground">
            <span>URL</span>
            <span>Status</span>
            <span>Data</span>
          </div>
          <div className="divide-y divide-border/30">
            {logs.map((log) => (
              <div key={log.id} className="grid grid-cols-[2fr_1fr_1fr] gap-4 px-4 py-3 text-sm">
                <div className="truncate">
                  <span className="block truncate text-foreground">{log.url}</span>
                  {log.error_message && (
                    <span className="block truncate text-xs text-rose-500">{log.error_message}</span>
                  )}
                </div>
                <span className={log.status === 'success' ? 'text-emerald-600' : 'text-rose-600'}>
                  {log.status}
                </span>
                <span className="text-muted-foreground">
                  {new Date(log.created_at).toLocaleString('pl-PL')}
                </span>
              </div>
            ))}
            {logs.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">Brak logów</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
