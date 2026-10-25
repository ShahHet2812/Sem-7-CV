import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog, EmptyState, Pagination, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { validateFile } from '@/features/videos/UploadDialog'
import { apiUrl, parseError } from '@/lib/api'
import { formatBytes, formatDuration } from '@/lib/utils'

describe('validateFile', () => {
  const exts = ['.mp4', '.mov']
  const file = (name: string, size: number) => new File([new Uint8Array(size)], name)
  it('accepts supported files', () => expect(validateFile(file('a.MP4', 10), exts, 1)).toBeNull())
  it('rejects unsupported extensions', () => expect(validateFile(file('a.txt', 10), exts, 1)).toMatch(/Unsupported/))
  it('rejects empty files', () => expect(validateFile(file('a.mp4', 0), exts, 1)).toMatch(/empty/))
  it('rejects oversized files', () => expect(validateFile(file('a.mp4', 2 * 1024 * 1024), exts, 1)).toMatch(/1 MB/))
})

describe('api helpers', () => {
  it('builds query strings, skipping empty values and repeating arrays', () => {
    expect(apiUrl('/api/v1/events', { q: 'door', zone_id: '', event_type: ['a', 'b'], page: 2 })).toBe(
      '/api/v1/events?q=door&event_type=a&event_type=b&page=2',
    )
  })
  it('turns error envelopes into readable messages', async () => {
    const res = new Response(
      JSON.stringify({ error: { code: 'validation_error', message: 'x', details: [{ loc: ['body', 'polygon'], msg: 'Value error, Polygon edges must not cross each other.' }] } }),
      { status: 422 },
    )
    const err = await parseError(res)
    expect(err.code).toBe('validation_error')
    expect(err.message).toBe('polygon: Polygon edges must not cross each other.')
  })
})

describe('formatters', () => {
  it('formats durations and sizes', () => {
    expect(formatDuration(75.25, true)).toBe('1:15.3')
    expect(formatDuration(3725)).toBe('1:02:05')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})

describe('common components', () => {
  it('renders status badges', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('renders empty state with action', () => {
    render(<EmptyState title="Nothing here" description="Add something" action={<Button>Add</Button>} />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
  })

  it('paginates', () => {
    const onChange = vi.fn()
    render(<Pagination page={2} pages={3} total={60} onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Next page'))
    fireEvent.click(screen.getByLabelText('Previous page'))
    expect(onChange.mock.calls).toEqual([[3], [1]])
  })

  it('asks for confirmation before destructive actions', async () => {
    const onConfirm = vi.fn()
    render(<ConfirmDialog title="Delete video?" description="Gone forever" destructive confirmLabel="Delete" onConfirm={onConfirm} trigger={<Button>Remove</Button>} />)
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(await screen.findByText('Gone forever')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
  })
})
