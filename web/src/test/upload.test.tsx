import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Upload } from '../upload'

describe('Upload', () => {
  it('renders drag-and-drop area', () => {
    render(<Upload onUpload={vi.fn()} />)
    expect(screen.getByText('Drop a .mid file here or click to browse')).toBeInTheDocument()
  })

  it('triggers onUpload when a .mid file is dropped', () => {
    const onUpload = vi.fn()
    render(<Upload onUpload={onUpload} />)
    const dropZone = screen.getByText('Drop a .mid file here or click to browse').parentElement!

    const file = new File([''], 'test.mid', { type: 'audio/midi' })
    const dataTransfer = { files: [file] } as unknown as DataTransfer

    fireEvent.dragOver(dropZone)
    fireEvent.drop(dropZone, { dataTransfer })

    expect(onUpload).toHaveBeenCalledWith(file)
  })

  it('shows preview after drop', () => {
    const onUpload = vi.fn()
    render(<Upload onUpload={onUpload} />)
    const dropZone = screen.getByText('Drop a .mid file here or click to browse').parentElement!

    const file = new File([''], 'test.mid', { type: 'audio/midi' })
    const dataTransfer = { files: [file] } as unknown as DataTransfer

    fireEvent.drop(dropZone, { dataTransfer })
    expect(screen.getByText('test.mid')).toBeInTheDocument()
  })

  it('does not upload non-midi files', () => {
    const onUpload = vi.fn()
    render(<Upload onUpload={onUpload} />)
    const dropZone = screen.getByText('Drop a .mid file here or click to browse').parentElement!

    const file = new File([''], 'test.wav', { type: 'audio/wav' })
    const dataTransfer = { files: [file] } as unknown as DataTransfer

    fireEvent.drop(dropZone, { dataTransfer })
    expect(onUpload).not.toHaveBeenCalled()
  })
})
