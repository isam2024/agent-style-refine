interface SideBySideProps {
  originalImage: string | null
  generatedImage: string | null
  iterationNum?: number
}

function SideBySide({ originalImage, generatedImage, iterationNum }: SideBySideProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Original */}
        <div>
          <p className="text-xs text-slate-500 uppercase mb-2">Original Reference</p>
          <div className="aspect-square bg-slate-100 rounded-lg overflow-hidden">
            {originalImage ? (
              <img
                src={originalImage}
                alt="Original"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-slate-400">
                No image
              </div>
            )}
          </div>
        </div>

        {/* Generated */}
        <div>
          <p className="text-xs text-slate-500 uppercase mb-2">
            {iterationNum ? `Iteration #${iterationNum}` : 'Generated'}
          </p>
          <div className="aspect-square bg-slate-100 rounded-lg overflow-hidden">
            {generatedImage ? (
              <img
                src={generatedImage}
                alt="Generated"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-slate-400 text-sm">
                Generate an image to compare
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default SideBySide
