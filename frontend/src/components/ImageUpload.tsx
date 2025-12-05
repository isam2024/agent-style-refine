import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'

interface ImageUploadProps {
  onImageSelect: (imageB64: string) => void
  currentImage: string | null
}

function ImageUpload({ onImageSelect, currentImage }: ImageUploadProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0]
      if (!file) return

      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        onImageSelect(result)
      }
      reader.readAsDataURL(file)
    },
    [onImageSelect]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp'],
    },
    maxFiles: 1,
  })

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
        isDragActive
          ? 'border-blue-500 bg-blue-50'
          : 'border-slate-300 hover:border-slate-400'
      }`}
    >
      <input {...getInputProps()} />
      {currentImage ? (
        <div className="space-y-2">
          <img
            src={currentImage}
            alt="Preview"
            className="max-h-48 mx-auto rounded"
          />
          <p className="text-sm text-slate-500">Click or drag to replace</p>
        </div>
      ) : (
        <div className="py-8">
          <svg
            className="w-12 h-12 mx-auto text-slate-400 mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <p className="text-slate-600">
            {isDragActive
              ? 'Drop the image here'
              : 'Drag & drop an image, or click to select'}
          </p>
          <p className="text-sm text-slate-400 mt-1">PNG, JPG, GIF up to 10MB</p>
        </div>
      )}
    </div>
  )
}

export default ImageUpload
