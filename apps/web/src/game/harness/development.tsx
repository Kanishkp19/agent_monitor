import { createRoot } from 'react-dom/client'
import { DevelopmentFloor } from '../DevelopmentFloor'
import '@/styles/globals.css'

// No automatic fixtures: the visible demo control explicitly opts in.
createRoot(document.getElementById('root')!).render(<DevelopmentFloor onSelect={() => {}} />)
