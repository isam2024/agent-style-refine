import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listStyles,
  getStyle,
  writePrompt,
  writeAndGenerate,
  getGenerationHistory,
} from '../api/client'
import { PromptWriteResponse, PromptGenerateResponse, GenerationHistoryResponse } from '../types'

function PromptWriter() {
  const { styleId: urlStyleId } = useParams<{ styleId?: string }>()
  const queryClient = useQueryClient()

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

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['generation-history', selectedStyleId],
    queryFn: () => getGenerationHistory(selectedStyleId!, 20),
    enabled: !!selectedStyleId,
  })

  // Fetch style breakdown when style is selected
  const { data: styleBreakdown } = useQuery({
    queryKey: ['style-breakdown', selectedStyleId],
    queryFn: () => writePrompt(selectedStyleId!, 'preview', undefined, false),
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
      // Invalidate history query to refresh the list
      queryClient.invalidateQueries({
        queryKey: ['generation-history', selectedStyleId],
      })
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

  // Use result breakdown if available, otherwise use styleBreakdown
  const activeBreakdown = result?.prompt_breakdown || styleBreakdown?.prompt_breakdown
  const activeStyleName = result?.style_name || styleBreakdown?.style_name

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

          {/* Selected Style Info - shows prompt breakdown */}
          {activeBreakdown && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-medium text-slate-700 mb-3">
                Style Agent: {activeStyleName}
              </h3>

              {/* Technique & Mood */}
              <div className="space-y-3 text-xs">
                {activeBreakdown.technique?.length > 0 && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Technique:</span>
                    <div className="flex flex-wrap gap-1">
                      {activeBreakdown.technique.map((t: string, i: number) => (
                        <span key={i} className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {activeBreakdown.mood?.length > 0 && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Mood:</span>
                    <div className="flex flex-wrap gap-1">
                      {activeBreakdown.mood.map((m: string, i: number) => (
                        <span key={i} className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded">
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Lighting, Texture, Composition */}
                {activeBreakdown.lighting && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Lighting:</span>
                    <div className="text-slate-600 space-y-0.5">
                      <div>{activeBreakdown.lighting.type}</div>
                      <div className="text-slate-400 text-[10px]">Shadows: {activeBreakdown.lighting.shadows}</div>
                      <div className="text-slate-400 text-[10px]">Highlights: {activeBreakdown.lighting.highlights}</div>
                    </div>
                  </div>
                )}
                {activeBreakdown.texture && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Texture:</span>
                    <div className="text-slate-600 space-y-0.5">
                      <div>{activeBreakdown.texture.surface}</div>
                      <div className="text-slate-400 text-[10px]">Noise: {activeBreakdown.texture.noise}</div>
                    </div>
                  </div>
                )}
                {activeBreakdown.composition && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Composition:</span>
                    <div className="text-slate-600 space-y-0.5">
                      <div>{activeBreakdown.composition.camera}</div>
                      <div className="text-slate-400 text-[10px]">{activeBreakdown.composition.framing}</div>
                    </div>
                  </div>
                )}

                {/* Palette */}
                {activeBreakdown.palette?.length > 0 && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Color Palette:</span>
                    <div className="flex flex-wrap gap-1">
                      {activeBreakdown.palette.map((c: string, i: number) => (
                        <span key={i} className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Core Invariants */}
                {activeBreakdown.core_invariants?.length > 0 && (
                  <div>
                    <span className="text-slate-400 font-medium block mb-1">Core Invariants:</span>
                    <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                      {activeBreakdown.core_invariants.slice(0, 3).map((r: string, i: number) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
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
                <div className="mt-4 pt-4 border-t border-slate-100 space-y-4">
                  <span className="text-xs text-slate-400 uppercase">
                    Prompt Breakdown
                  </span>

                  {/* Subject */}
                  <div className="text-sm">
                    <span className="text-slate-400 font-medium">Subject:</span>{' '}
                    <span className="text-slate-700">{result.prompt_breakdown.subject}</span>
                  </div>

                  {/* Technique & Mood */}
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    {result.prompt_breakdown.technique?.length > 0 && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Technique:</span>
                        <div className="flex flex-wrap gap-1">
                          {result.prompt_breakdown.technique.map((t: string, i: number) => (
                            <span key={i} className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                              {t}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {result.prompt_breakdown.mood?.length > 0 && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Mood:</span>
                        <div className="flex flex-wrap gap-1">
                          {result.prompt_breakdown.mood.map((m: string, i: number) => (
                            <span key={i} className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded">
                              {m}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Lighting, Texture, Composition */}
                  <div className="grid grid-cols-3 gap-4 text-xs">
                    {result.prompt_breakdown.lighting && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Lighting:</span>
                        <div className="text-slate-600 space-y-0.5">
                          <div>{result.prompt_breakdown.lighting.type}</div>
                          <div className="text-slate-400">Shadows: {result.prompt_breakdown.lighting.shadows}</div>
                          <div className="text-slate-400">Highlights: {result.prompt_breakdown.lighting.highlights}</div>
                        </div>
                      </div>
                    )}
                    {result.prompt_breakdown.texture && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Texture:</span>
                        <div className="text-slate-600 space-y-0.5">
                          <div>{result.prompt_breakdown.texture.surface}</div>
                          <div className="text-slate-400">Noise: {result.prompt_breakdown.texture.noise}</div>
                          {result.prompt_breakdown.texture.effects?.length > 0 && (
                            <div className="text-slate-400">Effects: {result.prompt_breakdown.texture.effects.join(', ')}</div>
                          )}
                        </div>
                      </div>
                    )}
                    {result.prompt_breakdown.composition && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Composition:</span>
                        <div className="text-slate-600 space-y-0.5">
                          <div>{result.prompt_breakdown.composition.camera}</div>
                          <div className="text-slate-400">{result.prompt_breakdown.composition.framing}</div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Palette */}
                  {result.prompt_breakdown.palette?.length > 0 && (
                    <div className="text-xs">
                      <span className="text-slate-400 font-medium block mb-1">Color Palette:</span>
                      <div className="flex flex-wrap gap-1">
                        {result.prompt_breakdown.palette.map((c: string, i: number) => (
                          <span key={i} className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Style Rules */}
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    {result.prompt_breakdown.always_include?.length > 0 && (
                      <div>
                        <span className="text-green-600 font-medium block mb-1">Always Include:</span>
                        <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                          {result.prompt_breakdown.always_include.map((r: string, i: number) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {result.prompt_breakdown.always_avoid?.length > 0 && (
                      <div>
                        <span className="text-red-600 font-medium block mb-1">Always Avoid:</span>
                        <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                          {result.prompt_breakdown.always_avoid.map((r: string, i: number) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Emphasize / De-emphasize from training */}
                  {(result.prompt_breakdown.emphasize?.length > 0 || result.prompt_breakdown.de_emphasize?.length > 0) && (
                    <div className="grid grid-cols-2 gap-4 text-xs border-t border-slate-100 pt-3">
                      {result.prompt_breakdown.emphasize?.length > 0 && (
                        <div>
                          <span className="text-amber-600 font-medium block mb-1">Emphasize (from training):</span>
                          <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                            {result.prompt_breakdown.emphasize.map((r: string, i: number) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.prompt_breakdown.de_emphasize?.length > 0 && (
                        <div>
                          <span className="text-slate-500 font-medium block mb-1">De-emphasize:</span>
                          <ul className="list-disc list-inside text-slate-400 space-y-0.5">
                            {result.prompt_breakdown.de_emphasize.map((r: string, i: number) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
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

      {/* Generation History */}
      {selectedStyleId && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">
            Generation History
          </h3>

          {historyLoading && (
            <div className="text-center py-8 text-slate-400">
              Loading history...
            </div>
          )}

          {!historyLoading && history && history.length === 0 && (
            <div className="text-center py-8 text-slate-400">
              <p>No generations yet.</p>
              <p className="text-sm mt-1">
                Use "Write & Generate" to create images with this style.
              </p>
            </div>
          )}

          {!historyLoading && history && history.length > 0 && (
            <div className="grid grid-cols-4 gap-4">
              {history.map((entry) => (
                <div
                  key={entry.id}
                  className="border border-slate-200 rounded-lg overflow-hidden hover:border-slate-300 transition-colors"
                >
                  {/* Image */}
                  {entry.image_b64 ? (
                    <img
                      src={`data:image/png;base64,${entry.image_b64}`}
                      alt={entry.subject}
                      className="w-full aspect-square object-cover"
                    />
                  ) : (
                    <div className="w-full aspect-square bg-slate-100 flex items-center justify-center text-4xl">
                      🎨
                    </div>
                  )}

                  {/* Info */}
                  <div className="p-3 space-y-2">
                    <div>
                      <p className="text-sm font-medium text-slate-700 line-clamp-2">
                        {entry.subject}
                      </p>
                      {entry.additional_context && (
                        <p className="text-xs text-slate-500 line-clamp-1 mt-1">
                          {entry.additional_context}
                        </p>
                      )}
                    </div>

                    <div className="text-xs text-slate-400">
                      {new Date(entry.created_at).toLocaleDateString()} {new Date(entry.created_at).toLocaleTimeString()}
                    </div>

                    {/* Prompts (collapsible) */}
                    <details className="text-xs">
                      <summary className="cursor-pointer text-blue-600 hover:text-blue-700">
                        View prompts
                      </summary>
                      <div className="mt-2 space-y-2">
                        <div>
                          <span className="text-green-600 font-medium">Positive:</span>
                          <p className="text-slate-600 mt-1 font-mono text-[10px] leading-tight">
                            {entry.positive_prompt}
                          </p>
                        </div>
                        {entry.negative_prompt && (
                          <div>
                            <span className="text-red-600 font-medium">Negative:</span>
                            <p className="text-slate-600 mt-1 font-mono text-[10px] leading-tight">
                              {entry.negative_prompt}
                            </p>
                          </div>
                        )}
                      </div>
                    </details>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default PromptWriter
