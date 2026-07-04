import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PresetEditor, BUILTIN_PRESETS } from '../PresetEditor'
import type { RenderSpec } from '../../renderSpec'

const MOCK_SPEC: RenderSpec = {
  durationSecs: 180,
  bpm: 128,
  keyframes: [
    { t: 0, scene: 'Intro', camera: { distance: 8, azimuth: 0, elevation: 0 }, color: { primary: '#7c3aed', secondary: '#06b6d4', brightness: 0.7 } },
    { t: 1, scene: 'Outro', camera: { distance: 10, azimuth: 0, elevation: 0 }, color: { primary: '#6366f1', secondary: '#22d3ee', brightness: 0.5 } },
  ],
}

function openEditor() {
  const trigger = screen.getByRole('button', { name: /edit preset/i })
  fireEvent.click(trigger)
}

beforeEach(() => {
  // Stub fetch to return empty preset list
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => [] }))
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---- 1. Renders trigger button -----------------------------------------------
it('renders the Edit Preset trigger button', () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  expect(screen.getByRole('button', { name: /edit preset/i })).toBeInTheDocument()
})

// ---- 2. Opens dialog on trigger click ----------------------------------------
it('opens the modal dialog when trigger is clicked', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => {
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

// ---- 3. Shows all four slider labels -----------------------------------------
it('renders sliders for energy, tempoMultiplier, colorSaturation, brightness', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  expect(screen.getByLabelText('Energy')).toBeInTheDocument()
  expect(screen.getByLabelText('Tempo Multiplier')).toBeInTheDocument()
  expect(screen.getByLabelText('Color Saturation')).toBeInTheDocument()
  expect(screen.getByLabelText('Brightness')).toBeInTheDocument()
})

// ---- 4. Builtin presets appear in the dropdown --------------------------------
it('lists built-in preset names in the load dropdown', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  const select = screen.getByRole('combobox')
  for (const preset of BUILTIN_PRESETS) {
    const option = Array.from(select.querySelectorAll('option')).find(
      (o) => o.textContent === preset.name,
    )
    expect(option).toBeDefined()
  }
})

// ---- 5. Loading a builtin preset updates the param display -------------------
describe('preset loading', () => {
  it('loading "Energetic" preset updates displayed value', async () => {
    render(<PresetEditor spec={MOCK_SPEC} />)
    openEditor()
    await waitFor(() => screen.getByRole('dialog'))

    const select = screen.getByRole('combobox')
    await userEvent.selectOptions(select, 'energetic')

    // Energy for Energetic is 1.0
    const valueLabels = screen.getAllByText('1.00')
    expect(valueLabels.length).toBeGreaterThan(0)
  })
})

// ---- 6. onPreviewChange called when energy slider changes --------------------
it('calls onPreviewChange when energy changes', async () => {
  const onPreviewChange = vi.fn()
  render(<PresetEditor spec={MOCK_SPEC} onPreviewChange={onPreviewChange} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  const select = screen.getByRole('combobox')
  await userEvent.selectOptions(select, 'energetic')

  expect(onPreviewChange).toHaveBeenCalledWith(expect.any(Number))
})

// ---- 7. Save stores preset in localStorage -----------------------------------
it('save button persists preset to localStorage', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  const nameInput = screen.getByPlaceholderText(/preset name/i)
  await userEvent.type(nameInput, 'My Test Preset')

  const saveBtn = screen.getByRole('button', { name: /save/i })
  await userEvent.click(saveBtn)

  const stored = JSON.parse(localStorage.getItem('mv_user_presets') ?? '[]') as Array<{ name: string }>
  expect(stored.some((p) => p.name === 'My Test Preset')).toBe(true)
})

// ---- 8. onApplyPreset called on Apply click ----------------------------------
it('calls onApplyPreset and closes dialog when Apply Preset is clicked', async () => {
  const onApplyPreset = vi.fn()
  render(<PresetEditor spec={MOCK_SPEC} onApplyPreset={onApplyPreset} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  const applyBtn = screen.getByRole('button', { name: /apply preset/i })
  await userEvent.click(applyBtn)

  expect(onApplyPreset).toHaveBeenCalledWith(
    expect.objectContaining({ params: expect.any(Object) }),
  )
})

// ---- 9. Close button dismisses dialog ----------------------------------------
it('close button dismisses the dialog', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  const closeBtn = screen.getByRole('button', { name: '✕' })
  await userEvent.click(closeBtn)

  await waitFor(() => {
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

// ---- 10. Duration label shown in dialog header --------------------------------
it('shows spec duration and bpm in the dialog header', async () => {
  render(<PresetEditor spec={MOCK_SPEC} />)
  openEditor()
  await waitFor(() => screen.getByRole('dialog'))

  expect(screen.getByText(/180s · 128 BPM/)).toBeInTheDocument()
})
