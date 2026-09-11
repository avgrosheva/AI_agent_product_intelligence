import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** React Router doesn't reset scroll position on navigation by itself --
 * without this, clicking a sidebar link (or any in-app link) while
 * scrolled down on a long page (Investigation, Release Decision, the
 * new marketing Landing page) lands the next page already scrolled
 * down too, which reads as broken. Keyed on pathname only, not the full
 * location (query-param-only filter changes on the same page, e.g.
 * Sessions pagination, should NOT yank the user back to the top). */
export function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}
