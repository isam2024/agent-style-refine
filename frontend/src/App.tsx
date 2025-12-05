import { Routes, Route, NavLink } from 'react-router-dom'
import Home from './pages/Home'
import Session from './pages/Session'
import StyleLibrary from './pages/StyleLibrary'
import PromptWriter from './pages/PromptWriter'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-8">
            <h1 className="text-xl font-semibold text-slate-800">
              Style Refine Agent
            </h1>
            <nav className="flex items-center gap-1">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                Train
              </NavLink>
              <NavLink
                to="/styles"
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-purple-100 text-purple-700'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                Style Library
              </NavLink>
              <NavLink
                to="/write"
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-green-100 text-green-700'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                Write Prompts
              </NavLink>
            </nav>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Routes>
          {/* Training Mode */}
          <Route path="/" element={<Home />} />
          <Route path="/session/:sessionId" element={<Session />} />

          {/* Style Library */}
          <Route path="/styles" element={<StyleLibrary />} />

          {/* Prompt Writer */}
          <Route path="/write" element={<PromptWriter />} />
          <Route path="/write/:styleId" element={<PromptWriter />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
