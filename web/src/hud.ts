// HUD overlay renderer for melosviz.
// Displays current note names and detected chord labels over the canvas
// using a lightweight DOM overlay so text remains crisp at any DPI.

export interface NoteDisplay {
  /** MIDI note number. */
  pitch: number
  /** Note name with octave, e.g. "C4". */
  label: string
  /** Normalized velocity in [0,1]. */
  velocity: number
}

export interface ChordDisplay {
  /** Human-readable chord label, e.g. "Cmaj7". */
  label: string
  /** Confidence score in [0,1]. */
  confidence: number
}

export interface HUDState {
  notes: NoteDisplay[]
  chords: ChordDisplay[]
  /** Optional subtitle shown beneath the chord list. */
  subtitle: string
}

/** MIDI note names (sharps) for one octave. */
const NOTE_NAMES = [
  'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B',
]

/** Convert a MIDI pitch to a note name with octave (e.g. 60 -> "C4"). */
export function midiToNoteName(pitch: number): string {
  const octave = Math.floor(pitch / 12) - 1
  const name = NOTE_NAMES[pitch % 12]
  return `${name}${octave}`
}

export class HUD {
  private overlay: HTMLDivElement
  private notesEl: HTMLDivElement
  private chordsEl: HTMLDivElement
  private subtitleEl: HTMLDivElement
  private _state: HUDState = { notes: [], chords: [], subtitle: '' }

  constructor(canvas: HTMLCanvasElement) {
    // Overlay div positioned exactly over the canvas
    const overlay = document.createElement('div')
    overlay.className =
      'absolute inset-0 pointer-events-none flex flex-col items-center justify-center'
    overlay.style.fontFamily =
      'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'

    // Note pills row (bottom-center)
    const notesEl = document.createElement('div')
    notesEl.className =
      'absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-wrap gap-2 justify-center'
    overlay.appendChild(notesEl)

    // Chord label (top-center)
    const chordsEl = document.createElement('div')
    chordsEl.className =
      'absolute top-1/3 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2'
    overlay.appendChild(chordsEl)

    // Subtitle below chords
    const subtitleEl = document.createElement('div')
    subtitleEl.className =
      'absolute top-1/3 left-1/2 -translate-x-1/2 mt-16 text-xs text-white/40 font-medium tracking-wide'
    overlay.appendChild(subtitleEl)

    this.overlay = overlay
    this.notesEl = notesEl
    this.chordsEl = chordsEl
    this.subtitleEl = subtitleEl

    // Append overlay as a sibling so it sits on top of the canvas via z-index
    const parent = canvas.parentElement
    if (parent) {
      parent.style.position = 'relative'
      parent.appendChild(overlay)
    }
  }

  /** Push a new note into the HUD. */
  addNote(pitch: number, velocity: number): void {
    this._state.notes.push({
      pitch,
      label: midiToNoteName(pitch),
      velocity,
    })
    this.render()
  }

  /** Push a new chord label into the HUD. */
  addChord(label: string, confidence: number): void {
    this._state.chords.push({ label, confidence })
    this.render()
  }

  /** Replace the entire note list. */
  setNotes(notes: NoteDisplay[]): void {
    this._state.notes = notes
    this.render()
  }

  /** Replace the entire chord list. */
  setChords(chords: ChordDisplay[]): void {
    this._state.chords = chords
    this.render()
  }

  /** Set the subtitle text. */
  setSubtitle(text: string): void {
    this._state.subtitle = text
    this.render()
  }

  /** Full state replacement. */
  setState(state: Partial<HUDState>): void {
    this._state = { ...this._state, ...state }
    this.render()
  }

  private render(): void {
    // Render note pills
    const maxNotes = 12
    const notes = this._state.notes.slice(-maxNotes)
    this.notesEl.innerHTML = notes
      .map(
        (n) =>
          `<span class="px-3 py-1 rounded-full text-sm font-semibold text-white/90 bg-white/10 border border-white/10 shadow-sm backdrop-blur-sm" style="opacity:${0.4 + n.velocity * 0.6}">${n.label}</span>`,
      )
      .join('')

    // Render chord labels
    const chords = this._state.chords
    this.chordsEl.innerHTML = chords
      .map(
        (c) =>
          `<span class="text-lg font-bold tracking-tight text-white/90 drop-shadow-sm" style="opacity:${0.3 + c.confidence * 0.7}">${c.label}</span>`,
      )
      .join('')

    // Render subtitle
    this.subtitleEl.textContent = this._state.subtitle
    this.subtitleEl.style.display = this._state.subtitle ? 'block' : 'none'
  }

  /** Remove the overlay from the DOM. */
  dispose(): void {
    this.overlay.remove()
  }
}
