interface ProgressIndicatorProps {
  step: string
}

function ProgressIndicator({ step }: ProgressIndicatorProps) {
  const steps = [
    { id: 'extracting', label: 'Extracting Style' },
    { id: 'generating', label: 'Generating Image' },
    { id: 'critiquing', label: 'Analyzing Results' },
  ]

  const currentIndex = steps.findIndex((s) => s.id === step)

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
      <div className="flex items-center gap-4">
        {/* Spinner */}
        <div className="w-8 h-8 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />

        {/* Step Indicator */}
        <div className="flex-1">
          <div className="flex items-center gap-2">
            {steps.map((s, i) => (
              <div key={s.id} className="flex items-center">
                <div
                  className={`w-2 h-2 rounded-full ${
                    i < currentIndex
                      ? 'bg-green-500'
                      : i === currentIndex
                      ? 'bg-blue-600'
                      : 'bg-slate-300'
                  }`}
                />
                {i < steps.length - 1 && (
                  <div
                    className={`w-12 h-0.5 mx-1 ${
                      i < currentIndex ? 'bg-green-500' : 'bg-slate-300'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
          <p className="text-sm text-blue-700 mt-1">
            {steps[currentIndex]?.label || 'Processing...'}
          </p>
        </div>
      </div>
    </div>
  )
}

export default ProgressIndicator
