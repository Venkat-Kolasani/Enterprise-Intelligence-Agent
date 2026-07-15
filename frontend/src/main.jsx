import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AppWorkspace } from './components/AppWorkspace'
import { LandingPage } from './components/LandingPage'
import './styles.css'

function usePathname() {
  const [pathname, setPathname] = useState(window.location.pathname)

  useEffect(() => {
    function updatePathname() {
      setPathname(window.location.pathname)
    }

    window.addEventListener('popstate', updatePathname)
    return () => window.removeEventListener('popstate', updatePathname)
  }, [])

  return pathname
}

function MetricThreadApp() {
  const pathname = usePathname().replace(/\/+$/, '') || '/'

  if (pathname === '/app') return <AppWorkspace />
  return <LandingPage />
}

createRoot(document.getElementById('root')).render(<MetricThreadApp />)
