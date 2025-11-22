import { useEffect, useState } from 'react'
import { api, getCsrfToken, setCsrfToken } from '../api/client'

export function useAuth() {
  const [logged, setLogged] = useState<boolean>(!!getCsrfToken())
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let ignore = false
    async function checkConfig() {
      try {
        const cfg = await api.getConfig() as any
        if (!ignore && cfg && typeof cfg === 'object' && cfg.disable_auth) {
          setLogged(true)
        }
      } catch {
        /* ignore */
      }
    }
    checkConfig()
    return () => { ignore = true }
  }, [])

  const login = async (user: string, password: string) => {
    setLoading(true)
    try {
      const res = await api.login(user, password)
      setCsrfToken(res.csrf_token)
      setLogged(true)
      return true
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }
  const logout = async () => {
    try { await api.logout() } catch (e) { /* ignore */ }
    setCsrfToken('')
    setLogged(false)
  }
  useEffect(() => { /* could check /health */ }, [])
  return { logged, loading, login, logout }
}


