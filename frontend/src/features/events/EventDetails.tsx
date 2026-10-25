import { Check, ExternalLink, ImageOff, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { EventTypeBadge, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/primitives'
import { useEventStatus } from '@/hooks/queries'
import { errorMessage, resourceUrl } from '@/lib/api'
import { formatDateTime, formatDuration } from '@/lib/utils'
import { eventsApi } from '@/services/resources'
import type { MonitoringEvent } from '@/types/api'

export function EventDetails({ event, onClose }: { event: MonitoringEvent | null; onClose: () => void }) {
  const status = useEventStatus()
  const [notes, setNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    setNotes(event?.notes ?? '')
    setImgError(false)
  }, [event])

  if (!event) return null
  const rows: [string, React.ReactNode][] = [
    ['Event ID', <span key="id" className="font-mono text-[11px]">{event.id}</span>],
    ['Video', event.video_name ?? '—'],
    ['Zone', event.zone_name ?? '—'],
    ['Video time', event.video_timestamp != null ? `${formatDuration(event.video_timestamp, true)} (frame ${event.frame_index})` : '—'],
    ['Occurred at', formatDateTime(event.occurred_at)],
    ['Object class', event.class_name ?? '—'],
    ['Track ID', event.track_id ?? '—'],
    ['Confidence', event.confidence != null ? `${(event.confidence * 100).toFixed(1)}%` : '—'],
  ]
  if (event.occupancy != null) rows.push(['Occupancy', `${event.occupancy} (threshold ${String(event.details.threshold ?? '—')})`])
  if (event.details.message) rows.push(['Message', String(event.details.message)])
  if (event.reviewed_at) rows.push(['Reviewed', formatDateTime(event.reviewed_at)])

  const saveNotes = async () => {
    setSavingNotes(true)
    try {
      await eventsApi.update(event.id, { notes })
      toast.success('Notes saved')
    } catch (e) {
      toast.error('Could not save notes', { description: errorMessage(e) })
    } finally {
      setSavingNotes(false)
    }
  }

  return (
    <Dialog open={!!event} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Event details" className="max-w-2xl">
        <div className="mb-3 flex items-center gap-3">
          <EventTypeBadge type={event.event_type} severity={event.severity} />
          <StatusBadge status={event.status} />
        </div>
        <div className="mb-4 overflow-hidden rounded-md border border-border bg-black">
          {event.snapshot_url && !imgError ? (
            <img src={resourceUrl(event.snapshot_url)} alt="Event snapshot" className="w-full" onError={() => setImgError(true)} />
          ) : (
            <div className="flex h-32 items-center justify-center gap-2 text-xs text-muted">
              <ImageOff className="size-4" /> No snapshot available
            </div>
          )}
        </div>
        <dl className="grid grid-cols-[140px_1fr] gap-x-3 gap-y-1.5 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="min-w-0 break-words">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 space-y-2">
          <label className="text-xs font-medium text-muted" htmlFor="event-notes">
            Review notes
          </label>
          <Textarea id="event-notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} placeholder="Add context for this event…" />
          <div className="flex justify-end">
            <Button size="xs" variant="outline" onClick={saveNotes} disabled={savingNotes || notes === (event.notes ?? '')}>
              Save notes
            </Button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap justify-between gap-2 border-t border-border pt-4">
          {event.video_timestamp != null ? (
            <Button variant="outline" size="sm" asChild>
              <Link to={`/analysis/${event.video_id}?t=${event.video_timestamp}&event=${event.id}`}>
                <ExternalLink /> Open at {formatDuration(event.video_timestamp, true)}
              </Link>
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            {event.status !== 'dismissed' && (
              <Button variant="outline" size="sm" onClick={() => status.mutate({ ids: [event.id], status: 'dismissed' }, { onSuccess: onClose })}>
                <X /> Dismiss
              </Button>
            )}
            {event.status !== 'reviewed' && (
              <Button size="sm" onClick={() => status.mutate({ ids: [event.id], status: 'reviewed' }, { onSuccess: onClose })}>
                <Check /> Mark reviewed
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
