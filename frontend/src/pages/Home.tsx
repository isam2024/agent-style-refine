import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listSessions, createSession, deleteSession, deleteAllSessions } from '../api/client'
import ImageUpload from '../components/ImageUpload'
import SessionList from '../components/SessionList'

function Home() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [newSessionName, setNewSessionName] = useState('')
  const [uploadedImage, setUploadedImage] = useState<string | null>(null)

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: listSessions,
  })

  const createMutation = useMutation({
    mutationFn: ({ name, imageB64 }: { name: string; imageB64: string }) =>
      createSession(name, imageB64),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      navigate(`/session/${session.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const deleteAllMutation = useMutation({
    mutationFn: deleteAllSessions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const handleDeleteAll = () => {
    if (window.confirm('⚠️ Are you sure? This will permanently delete ALL sessions and their files. This cannot be undone!')) {
      deleteAllMutation.mutate()
    }
  }

  const handleCreate = () => {
    if (!newSessionName.trim() || !uploadedImage) return
    createMutation.mutate({ name: newSessionName.trim(), imageB64: uploadedImage })
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Sessions</h2>
          <p className="text-slate-500 mt-1">
            Upload an image to extract and refine its visual style
          </p>
        </div>
        <div className="flex gap-2">
          {sessions && sessions.length > 0 && (
            <button
              onClick={handleDeleteAll}
              disabled={deleteAllMutation.isPending}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              {deleteAllMutation.isPending ? 'Deleting...' : 'Clear All'}
            </button>
          )}
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            New Session
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">
              Create New Session
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Session Name
                </label>
                <input
                  type="text"
                  value={newSessionName}
                  onChange={(e) => setNewSessionName(e.target.value)}
                  placeholder="e.g., Twilight Forest Style"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Reference Image
                </label>
                <ImageUpload
                  onImageSelect={setUploadedImage}
                  currentImage={uploadedImage}
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowCreate(false)
                  setNewSessionName('')
                  setUploadedImage(null)
                }}
                className="px-4 py-2 text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newSessionName.trim() || !uploadedImage || createMutation.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>

            {createMutation.isError && (
              <p className="text-red-500 text-sm mt-3">
                {(createMutation.error as Error).message}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Session List */}
      {isLoading ? (
        <div className="text-center py-12 text-slate-500">Loading sessions...</div>
      ) : sessions && sessions.length > 0 ? (
        <SessionList
          sessions={sessions}
          onDelete={(id) => {
            if (confirm('Delete this session and all its data?')) {
              deleteMutation.mutate(id)
            }
          }}
        />
      ) : (
        <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
          <p className="text-slate-500">No sessions yet</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-blue-600 hover:text-blue-700"
          >
            Create your first session
          </button>
        </div>
      )}
    </div>
  )
}

export default Home
