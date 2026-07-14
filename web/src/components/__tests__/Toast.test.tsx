import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Toast } from '../Toast'

describe('Toast', () => {
  it('renders nothing when not visible', () => {
    const { container } = render(<Toast message="Hello" visible={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders polite status region when visible', () => {
    render(<Toast message="Copied!" visible={true} />)
    const toast = screen.getByRole('status')
    expect(toast).toHaveAttribute('aria-live', 'polite')
    expect(toast).toHaveAttribute('aria-atomic', 'true')
    expect(toast).toHaveTextContent('Copied!')
  })
})
