'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  login as apiLogin,
  registerAccount as apiRegisterAccount,
  fetchMe,
  bootstrapAdmin as apiBootstrapAdmin,
  setAuthToken,
  getAuthToken,
  type AuthUser,
} from '@/lib/api'

interface AuthContextValue {
  user: AuthUser | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  registerAccount: (payload: {
    first_name: string
    last_name: string
    email: string
    password: string
  }) => Promise<void>
  bootstrapAdmin: (email: string, password: string, token?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    const init = async () => {
      const token = getAuthToken()
      if (!token) {
        if (isMounted) {
          setUser(null)
          setIsLoading(false)
        }
        return
      }
      try {
        const me = await fetchMe()
        if (isMounted) {
          setUser(me)
        }
      } catch {
        setAuthToken(null)
        if (isMounted) {
          setUser(null)
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    init()

    const handleLogout = () => {
      setAuthToken(null)
      setUser(null)
    }

    window.addEventListener('kitchenos:logout', handleLogout)

    return () => {
      isMounted = false
      window.removeEventListener('kitchenos:logout', handleLogout)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const token = await apiLogin(email, password)
    setAuthToken(token.access_token)
    const me = await fetchMe()
    setUser(me)
  }

  const bootstrapAdmin = async (email: string, password: string, token?: string) => {
    await apiBootstrapAdmin(email, password, token)
    await login(email, password)
  }

  const registerAccount = async (payload: {
    first_name: string
    last_name: string
    email: string
    password: string
  }) => {
    await apiRegisterAccount(payload)
  }

  const logout = () => {
    setAuthToken(null)
    setUser(null)
  }

  const value = useMemo(
    () => ({ user, isLoading, login, registerAccount, bootstrapAdmin, logout }),
    [user, isLoading]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
