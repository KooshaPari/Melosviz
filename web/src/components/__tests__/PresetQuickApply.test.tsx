import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PresetQuickApply } from '../PresetQuickApply'
import { BUILTIN_PRESETS } from '../PresetEditor'
import { setLocale } from '../../i18n'

describe('PresetQuickApply', () => {
  it('lists built-in presets with i18n labels and applies on change', () => {
    setLocale('en')
    const onApply = vi.fn()
    render(<PresetQuickApply onApply={onApply} />)

    const select = screen.getByRole('combobox', { name: /quick-apply built-in visual preset/i })
    expect(select).toBeInTheDocument()

    const energetic = BUILTIN_PRESETS.find((p) => p.id === 'energetic')!
    fireEvent.change(select, { target: { value: energetic.id } })

    expect(onApply).toHaveBeenCalledWith(energetic)
  })

  it('localizes placeholder and preset names in Spanish', () => {
    setLocale('es')
    render(<PresetQuickApply onApply={vi.fn()} />)

    const select = screen.getByRole('combobox', { name: /aplicar rápido un preset visual integrado/i })
    const option = Array.from(select.querySelectorAll('option')).find(
      (o) => o.textContent === 'Enérgico',
    )
    expect(option).toBeDefined()
  })
})
