import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2, RefreshCw } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Card } from '@/components/ui/primitives'
import { errorMessage } from '@/lib/api'
import { cn, EVENT_LABELS } from '@/lib/utils'
import type { EventType, JobStatus, Severity, VideoStatus } from '@/types/api'

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = 'default',
  loading,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'primary' | 'success' | 'warning' | 'danger'
  loading?: boolean
}) {
  const toneCls = {
    default: 'text-muted bg-surface-3',
    primary: 'text-primary bg-primary/10',
    success: 'text-success bg-success/10',
    warning: 'text-warning bg-warning/10',
    danger: 'text-danger bg-danger/10',
  }[tone]
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted">{label}</p>
        {icon && <span className={cn('rounded-md p-1.5 [&_svg]:size-4', toneCls)}>{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular">
        {loading ? <span className="inline-block h-7 w-16 animate-pulse rounded bg-surface-3" /> : value}
      </div>
      {hint && <p className="mt-1 text-xs text-subtle">{hint}</p>}
    </Card>
  )
}

const STATUS_STYLES: Record<string, string> = {
  uploaded: 'bg-surface-3 text-muted',
  queued: 'bg-info/15 text-info',
  processing: 'bg-primary/15 text-primary',
  completed: 'bg-success/15 text-success',
  failed: 'bg-danger/15 text-danger',
  cancelled: 'bg-warning/15 text-warning',
  new: 'bg-info/15 text-info',
  reviewed: 'bg-success/15 text-success',
  dismissed: 'bg-surface-3 text-muted',
}

export function StatusBadge({ status, className }: { status: VideoStatus | JobStatus | string; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize',
        STATUS_STYLES[status] ?? 'bg-surface-3 text-muted',
        className,
      )}
    >
      {status === 'processing' && <Loader2 className="size-3 animate-spin" />}
      {status}
    </span>
  )
}

const SEVERITY_DOT: Record<Severity, string> = { info: 'bg-info', warning: 'bg-warning', critical: 'bg-danger' }

export function EventTypeBadge({ type, severity }: { type: EventType; severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium">
      <span className={cn('size-2 rounded-full', SEVERITY_DOT[severity])} />
      {EVENT_LABELS[type] ?? type}
    </span>
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-12 text-center', className)}>
      <div className="mb-3 rounded-full bg-surface-3 p-3 text-muted [&_svg]:size-5">{icon ?? <Inbox />}</div>
      <p className="text-sm font-medium">{title}</p>
      {description && <div className="mt-1 max-w-md text-sm text-muted">{description}</div>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}>
      <div className="mb-3 rounded-full bg-danger/10 p-3 text-danger">
        <AlertTriangle className="size-5" />
      </div>
      <p className="text-sm font-medium">Could not load data</p>
      <p className="mt-1 max-w-md text-sm text-muted">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw /> Retry
        </Button>
      )}
    </div>
  )
}

export function LoadingState({ label = 'Loading…', className }: { label?: string; className?: string }) {
  return (
    <div className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted', className)}>
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  )
}

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number
  pages: number
  total: number
  onChange: (p: number) => void
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2.5 text-xs text-muted">
      <span className="tabular">{total.toLocaleString()} result{total === 1 ? '' : 's'}</span>
      <div className="flex items-center gap-2">
        <span className="tabular">
          Page {page} of {pages}
        </span>
        <Button variant="outline" size="icon" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">
          <ChevronLeft />
        </Button>
        <Button variant="outline" size="icon" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Next page">
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}

export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel = 'Confirm',
  destructive,
  onConfirm,
}: {
  trigger: ReactNode
  title: string
  description: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => Promise<unknown> | void
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <span onClick={() => setOpen(true)} className="contents">
        {trigger}
      </span>
      <DialogContent title={title} description={description}>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                await onConfirm()
                setOpen(false)
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy && <Loader2 className="animate-spin" />}
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function Field({ label, children, hint, error }: { label: string; children: ReactNode; hint?: ReactNode; error?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium text-muted">{label}</label>
      {children}
      {error ? <p className="text-xs text-danger">{error}</p> : hint ? <p className="text-xs text-subtle">{hint}</p> : null}
    </div>
  )
}
