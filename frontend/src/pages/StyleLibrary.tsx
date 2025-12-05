import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listStyles, deleteStyle, regenerateThumbnail } from '../api/client'
import { TrainedStyleSummary } from '../types'

function StyleLibrary() {
  const queryClient = useQueryClient()
  const [selectedTag, setSelectedTag] = useState<string | null>(null)

  const { data: styles, isLoading } = useQuery({
    queryKey: ['styles', selectedTag],
    queryFn: () => listStyles(selectedTag || undefined),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteStyle,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['styles'] })
    },
  })

  const regenerateThumbnailMutation = useMutation({
    mutationFn: regenerateThumbnail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['styles'] })
    },
  })

  // Collect all unique tags
  const allTags = Array.from(
    new Set(styles?.flatMap((s) => s.tags) || [])
  ).sort()

  const handleDelete = (style: TrainedStyleSummary) => {
    if (confirm(`Delete style "${style.name}"?`)) {
      deleteMutation.mutate(style.id)
    }
  }

  const handleRegenerateThumbnail = (style: TrainedStyleSummary) => {
    regenerateThumbnailMutation.mutate(style.id)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Style Library</h2>
          <p className="text-slate-500 mt-1">
            Trained styles ready for prompt writing
          </p>
        </div>
      </div>

      {/* Tag Filter */}
      {allTags.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-slate-500">Filter:</span>
          <button
            onClick={() => setSelectedTag(null)}
            className={`px-3 py-1 text-sm rounded-full transition-colors ${
              selectedTag === null
                ? 'bg-slate-800 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setSelectedTag(tag)}
              className={`px-3 py-1 text-sm rounded-full transition-colors ${
                selectedTag === tag
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="text-center py-12 text-slate-500">
          Loading styles...
        </div>
      )}

      {/* Empty State */}
      {!isLoading && styles?.length === 0 && (
        <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
          <div className="text-4xl mb-4">🎨</div>
          <h3 className="text-lg font-medium text-slate-700">
            No trained styles yet
          </h3>
          <p className="text-slate-500 mt-2 max-w-md mx-auto">
            Train a style in the Training section, then finalize it to add it
            to your library.
          </p>
          <Link
            to="/"
            className="inline-block mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Start Training
          </Link>
        </div>
      )}

      {/* Style Grid */}
      {styles && styles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {styles.map((style) => (
            <div
              key={style.id}
              className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-lg transition-shadow"
            >
              {/* Thumbnail */}
              <div className="aspect-video bg-slate-100 relative">
                {style.thumbnail_b64 ? (
                  <img
                    src={`data:image/jpeg;base64,${style.thumbnail_b64}`}
                    alt={style.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-4xl text-slate-300">
                    🎨
                  </div>
                )}
                {style.final_score !== null && (
                  <div className="absolute top-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded">
                    Score: {style.final_score}
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="p-4">
                <h3 className="font-semibold text-slate-800">{style.name}</h3>
                {style.description && (
                  <p className="text-sm text-slate-500 mt-1 line-clamp-2">
                    {style.description}
                  </p>
                )}

                <div className="flex items-center gap-2 mt-3 text-xs text-slate-400">
                  <span>{style.iterations_trained} iterations</span>
                  <span>•</span>
                  <span>
                    {new Date(style.created_at).toLocaleDateString()}
                  </span>
                </div>

                {/* Tags */}
                {style.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {style.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 bg-slate-100 text-slate-500 text-xs rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div className="space-y-2 mt-4">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/write/${style.id}`}
                      className="flex-1 text-center px-3 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700"
                    >
                      Use Style
                    </Link>
                    <button
                      onClick={() => handleDelete(style)}
                      className="px-3 py-2 text-red-600 text-sm rounded-lg hover:bg-red-50"
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  </div>
                  <button
                    onClick={() => handleRegenerateThumbnail(style)}
                    className="w-full px-3 py-1.5 text-blue-600 text-xs rounded-lg hover:bg-blue-50 border border-blue-200"
                    disabled={regenerateThumbnailMutation.isPending}
                  >
                    {regenerateThumbnailMutation.isPending ? 'Regenerating...' : '🔄 Regenerate Thumbnail'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default StyleLibrary
