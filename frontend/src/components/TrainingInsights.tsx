import { useMemo } from 'react'
import { Iteration } from '../types'

interface TrainingInsightsProps {
  iterations: Iteration[]
}

interface AggregatedData {
  totalIterations: number
  approvedCount: number
  rejectedCount: number
  averageScore: number | null
  dimensionScores: Record<string, number[]>
  dimensionAverages: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  preservedTraits: Record<string, number>
  lostTraits: Record<string, number>
  feedbackNotes: { approved: string[]; rejected: string[] }
}

function TrainingInsights({ iterations }: TrainingInsightsProps) {
  const data = useMemo<AggregatedData>(() => {
    const result: AggregatedData = {
      totalIterations: iterations.length,
      approvedCount: 0,
      rejectedCount: 0,
      averageScore: null,
      dimensionScores: {},
      dimensionAverages: {},
      strengths: [],
      weaknesses: [],
      preservedTraits: {},
      lostTraits: {},
      feedbackNotes: { approved: [], rejected: [] },
    }

    const overallScores: number[] = []

    for (const it of iterations) {
      // Count approvals
      if (it.approved === true) result.approvedCount++
      else if (it.approved === false) result.rejectedCount++

      // Collect scores
      if (it.scores) {
        for (const [dim, score] of Object.entries(it.scores)) {
          if (!result.dimensionScores[dim]) {
            result.dimensionScores[dim] = []
          }
          result.dimensionScores[dim].push(score as number)
          if (dim === 'overall') {
            overallScores.push(score as number)
          }
        }
      }

      // Collect critique data
      if (it.critique_data) {
        for (const trait of it.critique_data.preserved_traits || []) {
          result.preservedTraits[trait] = (result.preservedTraits[trait] || 0) + 1
        }
        for (const trait of it.critique_data.lost_traits || []) {
          result.lostTraits[trait] = (result.lostTraits[trait] || 0) + 1
        }
      }

      // Collect feedback notes
      if (it.feedback) {
        if (it.approved) {
          result.feedbackNotes.approved.push(it.feedback)
        } else {
          result.feedbackNotes.rejected.push(it.feedback)
        }
      }
    }

    // Calculate averages
    if (overallScores.length > 0) {
      result.averageScore = Math.round(
        overallScores.reduce((a, b) => a + b, 0) / overallScores.length
      )
    }

    for (const [dim, scores] of Object.entries(result.dimensionScores)) {
      if (dim === 'overall') continue
      const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
      result.dimensionAverages[dim] = avg
      if (avg >= 75) result.strengths.push(dim)
      else if (avg < 60) result.weaknesses.push(dim)
    }

    return result
  }, [iterations])

  if (iterations.length === 0) {
    return null
  }

  const topPreserved = Object.entries(data.preservedTraits)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  const topLost = Object.entries(data.lostTraits)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  return (
    <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl border border-indigo-200 p-4">
      <h3 className="text-sm font-semibold text-indigo-800 mb-3 flex items-center gap-2">
        <span className="text-lg">🧠</span>
        Training Insights
      </h3>

      {/* Stats Summary */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-slate-700">{data.totalIterations}</div>
          <div className="text-xs text-slate-500">Iterations</div>
        </div>
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-green-600">{data.approvedCount}</div>
          <div className="text-xs text-slate-500">Approved</div>
        </div>
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-red-500">{data.rejectedCount}</div>
          <div className="text-xs text-slate-500">Rejected</div>
        </div>
      </div>

      {/* Average Score */}
      {data.averageScore !== null && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-600">Average Score</span>
            <span className={`text-sm font-bold ${
              data.averageScore >= 75 ? 'text-green-600' :
              data.averageScore >= 60 ? 'text-yellow-600' : 'text-red-500'
            }`}>
              {data.averageScore}%
            </span>
          </div>
          <div className="h-2 bg-white/60 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${
                data.averageScore >= 75 ? 'bg-green-500' :
                data.averageScore >= 60 ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${data.averageScore}%` }}
            />
          </div>
        </div>
      )}

      {/* Dimension Scores */}
      {Object.keys(data.dimensionAverages).length > 0 && (
        <div className="mb-4">
          <div className="text-xs text-slate-600 mb-2">Dimension Performance</div>
          <div className="space-y-1.5">
            {Object.entries(data.dimensionAverages)
              .sort((a, b) => b[1] - a[1])
              .map(([dim, avg]) => (
                <div key={dim} className="flex items-center gap-2">
                  <span className="text-xs text-slate-500 w-20 capitalize truncate">
                    {dim.replace('_', ' ')}
                  </span>
                  <div className="flex-1 h-1.5 bg-white/60 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        avg >= 75 ? 'bg-green-500' :
                        avg >= 60 ? 'bg-yellow-500' : 'bg-red-400'
                      }`}
                      style={{ width: `${avg}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-500 w-6">{avg}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Strengths & Weaknesses */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {data.strengths.length > 0 && (
          <div>
            <div className="text-xs text-green-700 font-medium mb-1">Strengths</div>
            <div className="space-y-1">
              {data.strengths.map((s) => (
                <div
                  key={s}
                  className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded capitalize"
                >
                  {s.replace('_', ' ')}
                </div>
              ))}
            </div>
          </div>
        )}
        {data.weaknesses.length > 0 && (
          <div>
            <div className="text-xs text-amber-700 font-medium mb-1">Needs Work</div>
            <div className="space-y-1">
              {data.weaknesses.map((w) => (
                <div
                  key={w}
                  className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded capitalize"
                >
                  {w.replace('_', ' ')}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Preserved Traits */}
      {topPreserved.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-slate-600 mb-1">Key Traits (preserved)</div>
          <div className="flex flex-wrap gap-1">
            {topPreserved.map(([trait, count]) => (
              <span
                key={trait}
                className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded"
                title={`Preserved ${count} times`}
              >
                {trait}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Lost Traits (need emphasis) */}
      {topLost.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-slate-600 mb-1">Needs Emphasis (frequently lost)</div>
          <div className="flex flex-wrap gap-1">
            {topLost.map(([trait, count]) => (
              <span
                key={trait}
                className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded"
                title={`Lost ${count} times`}
              >
                {trait}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Feedback Summary */}
      {(data.feedbackNotes.approved.length > 0 || data.feedbackNotes.rejected.length > 0) && (
        <div className="border-t border-indigo-200 pt-3 mt-3">
          <div className="text-xs text-slate-600 mb-2">Training Feedback</div>
          {data.feedbackNotes.approved.length > 0 && (
            <div className="mb-2">
              <div className="text-xs text-green-600 font-medium mb-1">What worked:</div>
              <ul className="text-xs text-slate-600 space-y-0.5">
                {data.feedbackNotes.approved.slice(0, 3).map((note, i) => (
                  <li key={i} className="flex items-start gap-1">
                    <span className="text-green-500">+</span>
                    <span className="line-clamp-1">{note}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.feedbackNotes.rejected.length > 0 && (
            <div>
              <div className="text-xs text-red-600 font-medium mb-1">What to avoid:</div>
              <ul className="text-xs text-slate-600 space-y-0.5">
                {data.feedbackNotes.rejected.slice(0, 3).map((note, i) => (
                  <li key={i} className="flex items-start gap-1">
                    <span className="text-red-500">-</span>
                    <span className="line-clamp-1">{note}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default TrainingInsights
