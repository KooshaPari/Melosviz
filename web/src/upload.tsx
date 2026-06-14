// Upload UI for melosviz — drag-and-drop MIDI file with preview.
// Styled with Tailwind CSS to match the dark HUD aesthetic.

import { useCallback, useState, useRef } from 'react'

export interface UploadProps {
  onUpload: (file: File) => void
  disabled?: boolean
}

export function Upload({ onUpload, disabled = false }: UploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      if (disabled) return
      const file = e.dataTransfer.files?.[0]
      if (file && file.name.endsWith('.mid')) {
        setPreview(file.name)
        onUpload(file)
      }
    },
    [disabled, onUpload]
  )

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file && file.name.endsWith('.mid')) {
        setPreview(file.name)
        onUpload(file)
      }
    },
    [onUpload]
  )

  const handleClick = useCallback(() => {
    inputRef.current?.click()
  }, [])

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        className={`
          flex flex-col items-center justify-center gap-2 px-6 py-8 rounded-xl border-2 border-dashed
          cursor-pointer transition-colors
          ${isDragging
            ? 'border-cyan-400 bg-cyan-500/10'
            : 'border-white/20 bg-white/5 hover:border-white/40 hover:bg-white/10'
          }
          ${disabled ? 'opacity-40 cursor-not-allowed' : ''}
        `}
      >
        <svg
          className="w-8 h-8 text-white/40"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
          />
        </svg>
        <span className="text-sm text-white/60">
          Drop a .mid file here or click to browse
        </span>
        <input
          ref={inputRef}
          type="file"
          accept=".mid,.midi"
          onChange={handleFileChange}
          disabled={disabled}
          className="hidden"
        />
      </div>
      {preview && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
          <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span className="text-sm text-cyan-300 truncate">{preview}</span>
        </div>
      )}
    </div>
  )
}
