import { useCallback, useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Slider from '@radix-ui/react-slider'
import type { RenderSpec } from '../renderSpec'

// ---- Types ------------------------------------------------------------------

export interface PresetParams {
  energy: number           // [0, 1]
  tempoMultiplier: number  // [0.5, 2.0]
  colorSaturation: number  // [0, 1]
  brightness: number       // [0, 1]
}

export interface NamedPreset {
  id: string
  name: string
  params: PresetParams
}

interface PresetEditorProps {
  spec: RenderSpec
  /** Called with the new playbackT when the user drags a slider for live preview. */
  onPreviewChange?: (t: number) => void
  /** Called when a preset is saved/applied. */
  onApplyPreset?: (preset: NamedPreset) => void
}

// ---- Built-in presets -------------------------------------------------------

export const BUILTIN_PRESETS: NamedPreset[] = [
  { id: 'dark_street',  name: 'Dark Street',  params: { energy: 0.7, tempoMultiplier: 1.1, colorSaturation: 0.9, brightness: 0.3 } },
  { id: 'classy',       name: 'Classy',       params: { energy: 0.4, tempoMultiplier: 0.9, colorSaturation: 0.5, brightness: 0.6 } },
  { id: 'energetic',    name: 'Energetic',    params: { energy: 1.0, tempoMultiplier: 1.6, colorSaturation: 1.0, brightness: 0.9 } },
  { id: 'ambient',      name: 'Ambient',      params: { energy: 0.2, tempoMultiplier: 0.7, colorSaturation: 0.6, brightness: 0.4 } },
  { id: 'chillout',     name: 'Chillout',     params: { energy: 0.3, tempoMultiplier: 0.8, colorSaturation: 0.4, brightness: 0.5 } },
  { id: 'retro_disco',  name: 'Retro Disco',  params: { energy: 0.8, tempoMultiplier: 1.3, colorSaturation: 1.0, brightness: 0.8 } },
  { id: 'urban',        name: 'Urban',        params: { energy: 0.75, tempoMultiplier: 1.2, colorSaturation: 0.7, brightness: 0.5 } },
  { id: 'euphoria',     name: 'Euphoria',     params: { energy: 0.95, tempoMultiplier: 1.5, colorSaturation: 1.0, brightness: 1.0 } },
]

const DEFAULT_PARAMS: PresetParams = {
  energy: 0.5,
  tempoMultiplier: 1.0,
  colorSaturation: 0.7,
  brightness: 0.7,
}

// ---- Local storage helpers --------------------------------------------------

const LS_KEY = 'mv_user_presets'

function loadUserPresets(): NamedPreset[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    return JSON.parse(raw) as NamedPreset[]
  } catch {
    return []
  }
}

function saveUserPresets(presets: NamedPreset[]): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(presets))
  } catch {
    // ignore quota errors
  }
}

// ---- Sub-components ---------------------------------------------------------

interface LabeledSliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}

function LabeledSlider({ label, value, min, max, step, onChange }: LabeledSliderProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-white/60 font-medium">{label}</span>
        <span className="text-white/40 font-mono tabular-nums">{value.toFixed(2)}</span>
      </div>
      <Slider.Root
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={([v]) => { if (v !== undefined) onChange(v) }}
        className="relative flex items-center select-none touch-none w-full h-5"
        aria-label={label}
      >
        <Slider.Track className="bg-white/10 relative grow rounded-full h-1.5">
          <Slider.Range className="absolute bg-[var(--mv-primary,#7c6af7)] rounded-full h-full" />
        </Slider.Track>
        <Slider.Thumb className="block w-4 h-4 bg-white rounded-full shadow focus:outline-none focus:ring-2 focus:ring-[var(--mv-primary,#7c6af7)] focus:ring-offset-1 focus:ring-offset-[var(--mv-bg,#080808)] cursor-pointer" />
      </Slider.Root>
    </div>
  )
}

// ---- Main component ---------------------------------------------------------

export function PresetEditor({ spec, onPreviewChange, onApplyPreset }: PresetEditorProps) {
  const [open, setOpen] = useState(false)
  const [params, setParams] = useState<PresetParams>(DEFAULT_PARAMS)
  const [saveName, setSaveName] = useState('')
  const [userPresets, setUserPresets] = useState<NamedPreset[]>([])
  const [serverPresets, setServerPresets] = useState<NamedPreset[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState<string>('')

  // Load user presets from localStorage on mount
  useEffect(() => {
    setUserPresets(loadUserPresets())
  }, [])

  // Try to fetch presets from backend
  useEffect(() => {
    if (!open) return
    fetch('/api/presets')
      .then((r) => r.ok ? r.json() : null)
      .then((data: unknown) => {
        if (Array.isArray(data)) {
          setServerPresets(data as NamedPreset[])
        }
      })
      .catch(() => {
        // backend not available — fall back to builtin
      })
  }, [open])

  // Merged preset list: server → builtin → user
  const allPresets: NamedPreset[] = [
    ...BUILTIN_PRESETS,
    ...serverPresets.filter((sp) => !BUILTIN_PRESETS.some((b) => b.id === sp.id)),
    ...userPresets,
  ]

  // Live preview: map energy → playbackT preview window around current pos
  const handleParamChange = useCallback(
    (key: keyof PresetParams, value: number) => {
      const next = { ...params, [key]: value }
      setParams(next)
      // energy drives a quick scrub preview: show the mid-point of the track
      // adjusted by energy so the user sees colour/brightness shift
      if (onPreviewChange && key === 'energy') {
        const midT = Math.min(1, Math.max(0, next.energy))
        onPreviewChange(midT)
      }
    },
    [params, onPreviewChange],
  )

  const handleLoadPreset = useCallback(
    (id: string) => {
      const preset = allPresets.find((p) => p.id === id)
      if (!preset) return
      setParams(preset.params)
      setSelectedPresetId(id)
      if (onPreviewChange) {
        onPreviewChange(Math.min(1, Math.max(0, preset.params.energy)))
      }
    },
    [allPresets, onPreviewChange],
  )

  const handleSave = useCallback(async () => {
    const name = saveName.trim() || 'Custom Preset'
    const id = `user_${Date.now()}`
    const preset: NamedPreset = { id, name, params }

    // Try POST to backend
    try {
      const res = await fetch('/api/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, params }),
      })
      if (!res.ok) throw new Error('backend unavailable')
    } catch {
      // fall through to localStorage
    }

    const updated = [...userPresets, preset]
    setUserPresets(updated)
    saveUserPresets(updated)
    setSaveName('')
    onApplyPreset?.(preset)
  }, [saveName, params, userPresets, onApplyPreset])

  const handleApply = useCallback(() => {
    const id = selectedPresetId || `user_apply_${Date.now()}`
    const preset: NamedPreset = { id, name: saveName.trim() || 'Custom', params }
    onApplyPreset?.(preset)
    setOpen(false)
  }, [selectedPresetId, saveName, params, onApplyPreset])

  const durationLabel = `${spec.durationSecs}s · ${spec.bpm ?? 120} BPM`

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          className="px-3 py-1.5 rounded bg-fuchsia-500/20 hover:bg-fuchsia-500/30 text-fuchsia-300 text-xs font-medium transition-colors border border-fuchsia-500/30"
          title="Edit visual preset"
        >
          Edit Preset
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 w-[380px] max-w-[95vw] rounded-xl bg-[var(--mv-surface,#111118)] border border-white/10 p-6 shadow-2xl focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          aria-describedby="preset-editor-desc"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-5">
            <div>
              <Dialog.Title className="text-sm font-semibold text-white/90">
                Preset Editor
              </Dialog.Title>
              <p id="preset-editor-desc" className="text-xs text-white/40 mt-0.5">{durationLabel}</p>
            </div>
            <Dialog.Close className="w-7 h-7 rounded-full flex items-center justify-center text-white/40 hover:text-white/80 hover:bg-white/10 transition-colors">
              ✕
            </Dialog.Close>
          </div>

          {/* Load preset dropdown */}
          <div className="mb-5">
            <label className="text-xs text-white/50 font-medium uppercase tracking-wider block mb-1.5">
              Load Preset
            </label>
            <select
              value={selectedPresetId}
              onChange={(e) => handleLoadPreset(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded bg-white/5 border border-white/10 text-xs text-white/80 focus:outline-none focus:border-fuchsia-500/50 appearance-none cursor-pointer"
            >
              <option value="">— choose a preset —</option>
              <optgroup label="Built-in">
                {BUILTIN_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </optgroup>
              {userPresets.length > 0 && (
                <optgroup label="Saved">
                  {userPresets.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>

          {/* Sliders */}
          <div className="flex flex-col gap-4 mb-5">
            <LabeledSlider
              label="Energy"
              value={params.energy}
              min={0} max={1} step={0.01}
              onChange={(v) => handleParamChange('energy', v)}
            />
            <LabeledSlider
              label="Tempo Multiplier"
              value={params.tempoMultiplier}
              min={0.5} max={2.0} step={0.05}
              onChange={(v) => handleParamChange('tempoMultiplier', v)}
            />
            <LabeledSlider
              label="Color Saturation"
              value={params.colorSaturation}
              min={0} max={1} step={0.01}
              onChange={(v) => handleParamChange('colorSaturation', v)}
            />
            <LabeledSlider
              label="Brightness"
              value={params.brightness}
              min={0} max={1} step={0.01}
              onChange={(v) => handleParamChange('brightness', v)}
            />
          </div>

          {/* Save / name row */}
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Preset name…"
              className="flex-1 px-2.5 py-1.5 rounded bg-white/5 border border-white/10 text-xs text-white/80 placeholder:text-white/30 focus:outline-none focus:border-cyan-500/50"
            />
            <button
              onClick={() => void handleSave()}
              className="px-3 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium transition-colors border border-cyan-500/30"
            >
              Save
            </button>
          </div>

          {/* Apply */}
          <button
            onClick={handleApply}
            className="w-full py-2 rounded-lg bg-fuchsia-500/25 hover:bg-fuchsia-500/35 text-fuchsia-200 text-sm font-medium transition-colors border border-fuchsia-500/40"
          >
            Apply Preset
          </button>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
