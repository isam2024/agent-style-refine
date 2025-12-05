import { Link } from 'react-router-dom'
import { Session } from '../types'

interface SessionListProps {
  sessions: Session[]
  onDelete: (id: string) => void
}

function SessionList({ sessions, onDelete }: SessionListProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {sessions.map((session) => (
        <div
          key={session.id}
          className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:border-slate-300 transition-colors"
        >
          <Link to={`/session/${session.id}`} className="block p-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-medium text-slate-800">{session.name}</h3>
                <p className="text-sm text-slate-500 mt-1">
                  {session.iteration_count} iterations
                  {session.current_style_version &&
                    ` • v${session.current_style_version}`}
                </p>
              </div>
              <span
                className={`px-2 py-1 text-xs rounded-full ${
                  session.status === 'ready'
                    ? 'bg-green-100 text-green-700'
                    : session.status === 'error'
                    ? 'bg-red-100 text-red-700'
                    : session.status === 'completed'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-yellow-100 text-yellow-700'
                }`}
              >
                {session.status}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Created {new Date(session.created_at).toLocaleDateString()}
            </p>
          </Link>
          <div className="border-t border-slate-100 px-4 py-2 flex justify-end">
            <button
              onClick={(e) => {
                e.preventDefault()
                onDelete(session.id)
              }}
              className="text-sm text-red-500 hover:text-red-700"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default SessionList
