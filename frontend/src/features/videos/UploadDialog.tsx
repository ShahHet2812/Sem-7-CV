import { useQueryClient } from '@tanstack/react-query'
import { FileVideo, Loader2, UploadCloud, X } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { toast } from 'sonner'
import { Field } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input, Progress } from '@/components/ui/primitives'
import { useSettings } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { cn, formatBytes, toIsoOrUndefined } from '@/lib/utils'
import { videosApi } from '@/services/videos'
import type { Video } from '@/types/api'

const FALLBACK_EXTS = ['.avi', '.m4v', '.mkv', '.mov', '.mp4', '.webm']

export function validateFile(file: File, exts: string[], maxMb: number): string | null {
  const ext = file.name.includes('.') ? `.${file.name.split('.').pop()!.toLowerCase()}` : ''
  if (!exts.includes(ext)) return `Unsupported file type "${ext || 'none'}". Allowed: ${exts.join(', ')}`
  if (file.size === 0) return 'The file is empty.'
  if (file.size > maxMb * 1024 * 1024) return `File is larger than the ${maxMb} MB limit.`
  return null
}

export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onUploaded?: (v: Video) => void
}) {
  const settings = useSettings()
  const exts = settings.data?.upload.allowed_extensions ?? FALLBACK_EXTS
  const maxMb = settings.data?.upload.max_upload_mb ?? 500
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [recordedAt, setRecordedAt] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const uploading = progress !== null

  const pick = (f: File | undefined | null) => {
    if (!f) return
    setFile(f)
    setError(validateFile(f, exts, maxMb))
  }

  const reset = () => {
    setFile(null)
    setProgress(null)
    setError(null)
    setRecordedAt('')
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files?.[0])
  }

  const submit = async () => {
    if (!file || error) return
    abortRef.current = new AbortController()
    setProgress(0)
    try {
      const v = await videosApi.upload(file, toIsoOrUndefined(recordedAt), setProgress, abortRef.current.signal)
      toast.success('Upload complete', { description: `${v.original_filename} was validated and stored.` })
      await qc.invalidateQueries({ queryKey: ['videos'] })
      qc.invalidateQueries({ queryKey: ['analytics'] })
      onUploaded?.(v)
      reset()
      onOpenChange(false)
    } catch (e) {
      setProgress(null)
      setError(errorMessage(e))
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && uploading) abortRef.current?.abort()
        if (!o) reset()
        onOpenChange(o)
      }}
    >
      <DialogContent title="Upload video" description="The file is validated on the server (size, container signature and decodability).">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && inputRef.current?.click()}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border-strong px-4 py-8 text-center transition-colors hover:border-primary/60 hover:bg-surface-2',
            dragging && 'border-primary bg-primary/5',
            uploading && 'pointer-events-none opacity-70',
          )}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
        >
          <UploadCloud className="mb-2 size-8 text-primary" />
          <p className="text-sm font-medium">Drag & drop a video, or click to browse</p>
          <p className="mt-1 text-xs text-muted">
            {exts.join(', ').toUpperCase().replace(/\./g, '')} · up to {maxMb} MB
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={exts.join(',')}
            className="hidden"
            onChange={(e) => {
              pick(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>

        {file && (
          <div className="mt-4 flex items-center gap-3 rounded-md border border-border bg-surface-2 p-3">
            <FileVideo className="size-5 shrink-0 text-muted" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{file.name}</p>
              <p className="text-xs text-muted">{formatBytes(file.size)}</p>
            </div>
            {!uploading && (
              <Button variant="ghost" size="icon" onClick={reset} aria-label="Remove file">
                <X />
              </Button>
            )}
          </div>
        )}

        <div className="mt-4">
          <Field label="Recording start time (optional)" hint="Used to place events on a real-world timeline. Defaults to the upload time.">
            <Input type="datetime-local" value={recordedAt} onChange={(e) => setRecordedAt(e.target.value)} disabled={uploading} />
          </Field>
        </div>

        {uploading && (
          <div className="mt-4 space-y-1.5">
            <Progress value={progress} />
            <p className="text-xs text-muted tabular">
              {progress! < 1 ? `Uploading… ${Math.round(progress! * 100)}%` : 'Validating and decoding on the server…'}
            </p>
          </div>
        )}
        {error && <p className="mt-3 rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {uploading ? 'Cancel upload' : 'Cancel'}
          </Button>
          <Button onClick={submit} disabled={!file || !!error || uploading}>
            {uploading && <Loader2 className="animate-spin" />}
            Upload
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
