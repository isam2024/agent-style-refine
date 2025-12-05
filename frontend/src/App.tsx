import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Session from './pages/Session'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-800">
            Style Refine Agent
          </h1>
          <a
            href="/"
            className="text-sm text-slate-500 hover:text-slate-700"
          >
            Sessions
          </a>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/session/:sessionId" element={<Session />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
