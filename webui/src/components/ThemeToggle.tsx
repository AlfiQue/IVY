import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const [theme, setTheme] = useState<string>(() => localStorage.getItem('theme') || 'dark')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button onClick={()=>setTheme(next)} aria-label="Basculer theme">Theme: {theme}</button>
  )
}

