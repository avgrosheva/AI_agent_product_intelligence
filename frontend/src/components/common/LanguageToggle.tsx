import { useLanguage } from '../../state/LanguageContext'

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage()
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      <button
        type="button"
        className={`lang-toggle-option${language === 'en' ? ' active' : ''}`}
        onClick={() => setLanguage('en')}
        aria-pressed={language === 'en'}
      >
        EN
      </button>
      <button
        type="button"
        className={`lang-toggle-option${language === 'ru' ? ' active' : ''}`}
        onClick={() => setLanguage('ru')}
        aria-pressed={language === 'ru'}
      >
        RU
      </button>
    </div>
  )
}
