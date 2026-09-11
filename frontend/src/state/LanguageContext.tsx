import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { i18n, initialLanguage, STORAGE_KEY, type Language } from '../i18n'

interface LanguageContextValue {
  language: Language
  setLanguage: (lang: Language) => void
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

/** Mirrors ThemeContext's pattern: an explicit, persisted choice (not a
 * silent browser-locale follow) -- defaults to the browser's own
 * language on first visit, then remembers whatever the user picks. */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(initialLanguage)

  useEffect(() => {
    i18n.changeLanguage(language)
    document.documentElement.setAttribute('lang', language)
    try {
      window.localStorage.setItem(STORAGE_KEY, language)
    } catch {
      // ignore -- private browsing / storage disabled, language still applies for this session
    }
  }, [language])

  const setLanguage = useCallback((lang: Language) => setLanguageState(lang), [])

  const value = useMemo(() => ({ language, setLanguage }), [language, setLanguage])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider')
  return ctx
}
