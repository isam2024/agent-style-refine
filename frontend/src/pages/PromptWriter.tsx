import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  listStyles,
  getStyle,
  writePrompt,
  writeAndGenerate,
} from '../api/client'
import { PromptWriteResponse, PromptGenerateResponse } from '../types'

function PromptWriter() {
  const { styleId: urlStyleId } = useParams<{ styleId?: string }>()

  const [selectedStyleId, setSelectedStyleId] = useState<string | null>(
    urlStyleId || null
  )
  const [subject, setSubject] = useState('')
  const [additionalContext, setAdditionalContext] = useState('')
  const [includeNegative, setIncludeNegative] = useState(true)
  const [result, setResult] = useState<PromptWriteResponse | null>(null)
  const [generatedImage, setGeneratedImage] = useState<string | null>(null)
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null)

  // Update selected style when URL changes
  useEffect(() => {
    if (urlStyleId) {
      setSelectedStyleId(urlStyleId)
    }
  }, [urlStyleId])

  const { data: styles } = useQuery({
    queryKey: ['styles'],
    queryFn: () => listStyles(),
  })

  const { data: selectedStyle } = useQuery({
    queryKey: ['style', selectedStyleId],
    queryFn: () => getStyle(selectedStyleId!),
    enabled: !!selectedStyleId,
  })

  const writeMutation = useMutation({
    mutationFn: () =>
      writePrompt(
        selectedStyleId!,
        subject,
        additionalContext || undefined,
        includeNegative
      ),
    onSuccess: (data) => {
      setResult(data)
      setGeneratedImage(null)
    },
  })

  const generateMutation = useMutation({
    mutationFn: () =>
      writeAndGenerate(
        selectedStyleId!,
        subject,
        additionalContext || undefined
      ),
    onSuccess: (data: PromptGenerateResponse) => {
      setResult({
        positive_prompt: data.positive_prompt,
        negative_prompt: data.negative_prompt,
        style_name: data.style_name,
        prompt_breakdown: null,
      })
      setGeneratedImage(data.image_b64)
    },
  })

  const copyToClipboard = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text)
    setCopyFeedback(label)
    setTimeout(() => setCopyFeedback(null), 2000)
  }

  const handleWritePrompt = () => {
    if (!selectedStyleId || !subject.trim()) return
    writeMutation.mutate()
  }

  const handleWriteAndGenerate = () => {
    if (!selectedStyleId || !subject.trim()) return
    generateMutation.mutate()
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Prompt Writer</h2>
        <p className="text-slate-500 mt-1">
          Generate styled prompts using your trained styles
        </p>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Left: Input Panel */}
        <div className="col-span-5 space-y-4">
          {/* Style Selector */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Select Style
            </label>
            {styles && styles.length > 0 ? (
              <div className="grid grid-cols-3 gap-2">
                {styles.map((style) => (
                  <button
                    key={style.id}
                    onClick={() => setSelectedStyleId(style.id)}
                    className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                      selectedStyleId === style.id
                        ? 'border-green-500 ring-2 ring-green-200'
                        : 'border-transparent hover:border-slate-300'
                    }`}
                  >
                    {style.thumbnail_b64 ? (
                      <img
                        src={`data:image/jpeg;base64,${style.thumbnail_b64}`}
                        alt={style.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-2xl">
                        🎨
                      </div>
                    )}
                    <div className="absolute inset-x-0 bottom-0 bg-black/60 text-white text-xs p-1 truncate">
                      {style.name}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-slate-400">
                <p>No styles available.</p>
                <Link
                  to="/"
                  className="text-blue-600 hover:underline text-sm"
                >
                  Train a style first
                </Link>
              </div>
            )}
          </div>

          {/* Selected Style Info */}
          {selectedStyle && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-medium text-slate-800">
                {selectedStyle.style_profile.style_name}
              </h3>
              {selectedStyle.description && (
                <p className="text-sm text-slate-500 mt-1">
                  {selectedStyle.description}
                </p>
              )}
              <div className="mt-3 space-y-2">
                <div>
                  <span className="text-xs text-slate-400 uppercase">
                    Core Traits
                  </span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {selectedStyle.style_profile.core_invariants
                      .slice(0, 3)
                      .map((trait, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded"
                        >
                          {trait}
                        </span>
                      ))}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-slate-400 uppercase">
                    Palette
                  </span>
                  <div className="flex gap-1 mt-1">
                    {selectedStyle.style_profile.palette.dominant_colors.map(
                      (color, i) => (
                        <div
                          key={i}
                          className="w-6 h-6 rounded border border-slate-200"
                          style={{ backgroundColor: color }}
                          title={color}
                        />
                      )
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Subject Input */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Subject / Scene
            </label>
            <textarea
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Describe what you want to generate...&#10;e.g., a fox sitting in a moonlit forest"
              className="w-full h-24 px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 resize-none"
            />

            <label className="block text-sm font-medium text-slate-700 mt-4 mb-2">
              Additional Context (optional)
            </label>
            <input
              type="text"
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              placeholder="e.g., highly detailed, cinematic"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
            />

            <label className="flex items-center gap-2 mt-4">
              <input
                type="checkbox"
                checked={includeNegative}
                onChange={(e) => setIncludeNegative(e.target.checked)}
                className="rounded text-green-600"
              />
              <span className="text-sm text-slate-600">
                Include negative prompt
              </span>
            </label>

            <div className="flex gap-2 mt-4">
              <button
                onClick={handleWritePrompt}
                disabled={
                  !selectedStyleId ||
                  !subject.trim() ||
                  writeMutation.isPending
                }
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                {writeMutation.isPending ? 'Writing...' : 'Write Prompt'}
              </button>
              <button
                onClick={handleWriteAndGenerate}
                disabled={
                  !selectedStyleId ||
                  !subject.trim() ||
                  generateMutation.isPending
                }
                className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {generateMutation.isPending ? 'Generating...' : 'Write & Generate'}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Output Panel */}
        <div className="col-span-7 space-y-4">
          {/* Generated Image */}
          {generatedImage && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-medium text-slate-700 mb-3">
                Generated Image
              </h3>
              <img
                src={generatedImage}
                alt="Generated"
                className="w-full rounded-lg"
              />
            </div>
          )}

          {/* Prompt Output */}
          {result && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-slate-700">
                  Styled Prompt
                </h3>
                <span className="text-xs text-slate-400">
                  Style: {result.style_name}
                </span>
              </div>

              {/* Positive Prompt */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-green-600 uppercase font-medium">
                    Positive Prompt
                  </span>
                  <button
                    onClick={() =>
                      copyToClipboard(result.positive_prompt, 'positive')
                    }
                    className="text-xs text-slate-500 hover:text-slate-700"
                  >
                    {copyFeedback === 'positive' ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-slate-700 font-mono whitespace-pre-wrap">
                  {result.positive_prompt}
                </div>
              </div>

              {/* Negative Prompt */}
              {result.negative_prompt && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-red-600 uppercase font-medium">
                      Negative Prompt
                    </span>
                    <button
                      onClick={() =>
                        copyToClipboard(result.negative_prompt!, 'negative')
                      }
                      className="text-xs text-slate-500 hover:text-slate-700"
                    >
                      {copyFeedback === 'negative' ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-slate-700 font-mono whitespace-pre-wrap">
                    {result.negative_prompt}
                  </div>
                </div>
              )}

              {/* Prompt Breakdown */}
              {result.prompt_breakdown && (
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <span className="text-xs text-slate-400 uppercase">
                    Prompt Breakdown
                  </span>
                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                    <div>
                      <span className="text-slate-400">Subject:</span>{' '}
                      <span className="text-slate-600">
                        {result.prompt_breakdown.subject}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">Lighting:</span>{' '}
                      <span className="text-slate-600">
                        {result.prompt_breakdown.lighting}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">Texture:</span>{' '}
                      <span className="text-slate-600">
                        {result.prompt_breakdown.texture}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">Rules Applied:</span>{' '}
                      <span className="text-slate-600">
                        {result.prompt_breakdown.style_rules_applied}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Empty State */}
          {!result && !generatedImage && (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
              <div className="text-4xl mb-4">✨</div>
              <h3 className="text-lg font-medium text-slate-700">
                Ready to write prompts
              </h3>
              <p className="text-slate-500 mt-2 max-w-md mx-auto">
                Select a style, enter a subject, and click "Write Prompt" to
                generate a styled prompt for image generation.
              </p>
            </div>
          )}

          {/* Error Display */}
          {(writeMutation.isError || generateMutation.isError) && (
            <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
              {(writeMutation.error as Error)?.message ||
                (generateMutation.error as Error)?.message}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default PromptWriter
