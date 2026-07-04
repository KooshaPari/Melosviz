import { useRef } from 'react'
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
import type { PlaylistItem, UsePlaylistReturn } from '../hooks/usePlaylist'

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

      {/* File picker button */}
      <button
        onClick={() => fileInputRef.current?.click()}
        className="px-3 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium transition-colors border border-cyan-500/30 text-center"
      >
        + Add files
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Queue list */}
      {queue.length === 0 ? (
        <p className="text-xs text-white/20 text-center py-3">
          No files added yet
        </p>
      ) : (
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
      )}
    </div>
  )
}
