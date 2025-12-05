import { useState } from 'react'

interface FeedbackPanelProps {
  critique: {
    match_scores: Record<string, number>
    preserved_traits: string[]
    lost_traits: string[]
    interesting_mutations: string[]
  }
  onApprove: (notes?: string) => void
  onReject: (notes?: string) => void
  isLoading: boolean
}

function FeedbackPanel({
  critique,
  onApprove,
  onReject,
  isLoading,
}: FeedbackPanelProps) {
  const [notes, setNotes] = useState('')

  const overallScore = critique.match_scores.overall ?? 0

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <h3 className="text-sm font-medium text-slate-700 mb-3">Critique Results</h3>

      {/* Overall Score */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-slate-600">Overall Match</span>
          <span
            className={`text-lg font-bold ${
              overallScore >= 70
                ? 'text-green-600'
                : overallScore >= 50
                ? 'text-yellow-600'
                : 'text-red-600'
            }`}
          >
            {overallScore}%
          </span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              overallScore >= 70
                ? 'bg-green-500'
                : overallScore >= 50
                ? 'bg-yellow-500'
                : 'bg-red-500'
            }`}
            style={{ width: `${overallScore}%` }}
          />
        </div>
      </div>

      {/* Score Breakdown */}
      <div className="space-y-2 mb-4">
        {Object.entries(critique.match_scores)
          .filter(([key]) => key !== 'overall')
          .map(([key, value]) => (
            <div key={key} className="flex items-center gap-2">
              <span className="text-xs text-slate-500 capitalize w-20">
                {key.replace('_', ' ')}
              </span>
              <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full"
                  style={{ width: `${value}%` }}
                />
              </div>
              <span className="text-xs text-slate-400 w-6">{value}</span>
            </div>
          ))}
      </div>

      {/* Traits */}
      <div className="space-y-3 mb-4 text-sm">
        {critique.preserved_traits.length > 0 && (
          <div>
            <p className="text-xs text-green-600 uppercase mb-1">Preserved</p>
            <ul className="text-slate-600 space-y-0.5">
              {critique.preserved_traits.slice(0, 3).map((t, i) => (
                <li key={i}>+ {t}</li>
              ))}
            </ul>
          </div>
        )}

        {critique.lost_traits.length > 0 && (
          <div>
            <p className="text-xs text-red-600 uppercase mb-1">Lost</p>
            <ul className="text-slate-600 space-y-0.5">
              {critique.lost_traits.slice(0, 3).map((t, i) => (
                <li key={i}>- {t}</li>
              ))}
            </ul>
          </div>
        )}

        {critique.interesting_mutations.length > 0 && (
          <div>
            <p className="text-xs text-blue-600 uppercase mb-1">Mutations</p>
            <ul className="text-slate-600 space-y-0.5">
              {critique.interesting_mutations.slice(0, 3).map((t, i) => (
                <li key={i}>* {t}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Notes Input */}
      <div className="mb-4">
        <label className="block text-xs text-slate-500 mb-1">
          Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="What to emphasize or avoid in next iteration..."
          className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
          rows={2}
        />
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => onReject(notes || undefined)}
          disabled={isLoading}
          className="flex-1 px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 disabled:opacity-50"
        >
          Reject
        </button>
        <button
          onClick={() => onApprove(notes || undefined)}
          disabled={isLoading}
          className="flex-1 px-4 py-2 bg-green-50 text-green-600 rounded-lg hover:bg-green-100 disabled:opacity-50"
        >
          {isLoading ? 'Applying...' : 'Approve & Apply'}
        </button>
      </div>
    </div>
  )
}

export default FeedbackPanel
