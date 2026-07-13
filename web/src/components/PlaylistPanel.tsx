import { useId, useRef } from 'react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button, EmptyState } from '@melosviz/ui'
import type { PlaylistItem, UsePlaylistReturn } from '../hooks/usePlaylist'

/** Compact spectrum mark — mirrors desktop/assets/brand/gfx/empty-state.svg */
function EmptyQueueArt() {
  const uid = useId().replace(/:/g, '')
  const grad = `eq-${uid}`
  const glow = `gl-${uid}`

  return (
    <svg
      viewBox="0 0 320 200"
      className="w-full max-w-[180px] mx-auto opacity-90"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--mv-accent, #4c40b0)" />
          <stop offset="50%" stopColor="var(--mv-primary, #7c6af7)" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
        <filter id={glow}>
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <circle cx="160" cy="90" r="70" fill="none" stroke="var(--mv-primary, #7c6af7)" strokeWidth="1" opacity="0.08" />
      <circle cx="160" cy="90" r="52" fill="none" stroke="var(--mv-primary, #7c6af7)" strokeWidth="1" opacity="0.12" />
      <circle cx="160" cy="90" r="34" fill="none" stroke="var(--mv-primary, #7c6af7)" strokeWidth="1.5" opacity="0.18" />
      <circle cx="160" cy="90" r="16" fill="none" stroke="var(--mv-primary, #7c6af7)" strokeWidth="2" opacity="0.25" />
      <g filter={`url(#${glow})`} opacity="0.65">
        <rect x="122" y="80" width="8" height="20" rx="2" fill={`url(#${grad})`} />
        <rect x="134" y="72" width="8" height="28" rx="2" fill={`url(#${grad})`} />
        <rect x="146" y="66" width="8" height="34" rx="2" fill={`url(#${grad})`} />
        <rect x="158" y="62" width="8" height="38" rx="2" fill={`url(#${grad})`} />
        <rect x="170" y="66" width="8" height="34" rx="2" fill={`url(#${grad})`} />
        <rect x="182" y="72" width="8" height="28" rx="2" fill={`url(#${grad})`} />
        <rect x="194" y="80" width="8" height="20" rx="2" fill={`url(#${grad})`} />
      </g>
      <line x1="110" y1="100" x2="210" y2="100" stroke={`url(#${grad})`} strokeWidth="1.5" opacity="0.3" />
    </svg>
  )
}

// ---- Status badge -------------------------------------------------------

const STATUS_STYLES: Record<PlaylistItem['status'], string> = {
  pending: 'bg-white/10 text-white/40',
  analyzing: 'bg-cyan-500/20 text-cyan-300 animate-pulse',
  done: 'bg-fuchsia-500/20 text-fuchsia-300',
  error: 'bg-red-500/20 text-red-400',
}

const STATUS_LABELS: Record<PlaylistItem['status'], string> = {
  pending: 'pending',
  analyzing: 'analyzing…',
  done: 'done',
  error: 'error',
}

function formatDuration(secs?: number): string {
  if (!secs) return ''
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// ---- Sortable row -------------------------------------------------------

interface SortableItemProps {
  item: PlaylistItem
  isActive: boolean
  onSelect: () => void
  onRemove: () => void
}

function SortableRow({ item, isActive, onSelect, onRemove }: SortableItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer select-none border transition-colors ${
        isActive
          ? 'bg-fuchsia-500/20 border-fuchsia-500/40'
          : 'bg-white/5 border-white/10 hover:bg-white/10'
      }`}
      onClick={onSelect}
    >
      {/* Drag handle */}
      <span
        {...attributes}
        {...listeners}
        className="text-white/20 hover:text-white/50 cursor-grab active:cursor-grabbing text-xs flex-shrink-0"
        onClick={(e) => e.stopPropagation()}
      >
        ⠿
      </span>

      {/* File name */}
      <span className="flex-1 text-xs text-white/80 truncate min-w-0" title={item.file.name}>
        {item.file.name}
      </span>

      {/* Duration */}
      {item.durationSecs != null && (
        <span className="text-[10px] text-white/30 flex-shrink-0">
          {formatDuration(item.durationSecs)}
        </span>
      )}

      {/* Status badge */}
      <span
        className={`text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 ${STATUS_STYLES[item.status]}`}
      >
        {STATUS_LABELS[item.status]}
      </span>

      {/* Remove button */}
      <button
        className="flex-shrink-0 text-white/20 hover:text-red-400 text-xs transition-colors"
        onClick={(e) => {
          e.stopPropagation()
          onRemove()
        }}
        title="Remove"
      >
        ✕
      </button>
    </div>
  )
}

// ---- PlaylistPanel -------------------------------------------------------

interface PlaylistPanelProps {
  playlist: UsePlaylistReturn
  /** Called when user clicks a done item to view its spec */
  onSelectItem: (item: PlaylistItem) => void
}

export function PlaylistPanel({ playlist, onSelectItem }: PlaylistPanelProps) {
  const { queue, currentIndex, isProcessing, addFiles, removeItem, reorder, clearQueue, setCurrentIndex } =
    playlist

  const fileInputRef = useRef<HTMLInputElement>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const fromIdx = queue.findIndex((i) => i.id === active.id)
    const toIdx = queue.findIndex((i) => i.id === over.id)
    if (fromIdx !== -1 && toIdx !== -1) reorder(fromIdx, toIdx)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) addFiles(files)
    // Reset input so same file can be re-added
    e.target.value = ''
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg bg-black/40 border border-white/10 p-3 w-64">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-white/50 font-medium uppercase tracking-wider">
          Playlist {queue.length > 0 && `(${queue.length})`}
        </span>
        <div className="flex items-center gap-1">
          {isProcessing && (
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" title="Processing" />
          )}
          {queue.length > 0 && (
            <button
              onClick={clearQueue}
              className="text-[10px] text-white/30 hover:text-red-400 transition-colors px-1"
              title="Clear all"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Queue list / empty state */}
      {queue.length === 0 ? (
        <EmptyState
          icon={<EmptyQueueArt />}
          title="Queue is empty"
          description="Load audio to analyze beats and build a scene — or drop files here."
          action={
            <Button className="mt-0.5 w-full" onClick={() => fileInputRef.current?.click()}>
              Load audio
            </Button>
          }
          footnote="WAV · MP3 · audio/*"
        />
      ) : (
        <>
          <Button onClick={() => fileInputRef.current?.click()}>+ Add files</Button>
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={queue.map((i) => i.id)} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-1 max-h-64 overflow-y-auto pr-1">
                {queue.map((item, idx) => (
                  <SortableRow
                    key={item.id}
                    item={item}
                    isActive={idx === currentIndex}
                    onSelect={() => {
                      setCurrentIndex(idx)
                      if (item.status === 'done') onSelectItem(item)
                    }}
                    onRemove={() => removeItem(item.id)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </>
      )}
    </div>
  )
}
