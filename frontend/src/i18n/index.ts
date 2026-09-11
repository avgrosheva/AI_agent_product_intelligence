import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ru from './locales/ru.json'

export type Language = 'en' | 'ru'

const STORAGE_KEY = 'language'

function initialLanguage(): Language {
  const stored = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null
  if (stored === 'en' || stored === 'ru') return stored
  const browserLang = typeof navigator !== 'undefined' ? navigator.language.slice(0, 2) : 'en'
  return browserLang === 'ru' ? 'ru' : 'en'
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ru: { translation: ru } },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnEmptyString: false,
})

export { i18n, STORAGE_KEY, initialLanguage }
