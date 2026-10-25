import { useQuery } from '@tanstack/react-query'
import { Check, Download, ExternalLink, Hexagon, Loader2, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ErrorState, LoadingState } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/primitives'
import { useInvalidateAll } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { cn, formatDuration } from '@/lib/utils'
import { videosApi } from '@/services/videos'
import type { SampleInfo } from '@/types/api'

function SampleCard({
  s,
  busy,
  onImport,
}: {
  s: SampleInfo
  busy: boolean
  onImport: () => void
}) {
  const imported = !!s.imported_video_id
  return (
    <div className={cn('flex flex-col rounded-lg border bg-surface-2 p-3', s.category === 'Restricted zone' ? 'border-danger/40' : 'border-border')}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-snug">{s.title}</p>
        <span className="shrink-0 rounded bg-surface-3 px-1.5 py-0.5 text-[10px] text-muted">{s.category}</span>
      </div>
      <p className="mt-1 text-xs text-muted">{s.description}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {s.objects.map((o) => (
          <span key={o} className="rounded-full border border-border-strong px-1.5 text-[10px] text-muted">
            {o}
          </span>
        ))}
      </div>
      {s.scenario && (
        <p className="mt-2 flex gap-1.5 text-[11px] text-warning">
          {s.zones.some((z) => z.zone_type === 'restricted') ? <ShieldAlert className="mt-px size-3 shrink-0" /> : <Hexagon className="mt-px size-3 shrink-0" />}
          {s.scenario}
        </p>
      )}
      <div className="mt-auto flex items-end justify-between gap-2 pt-3">
        <p className="text-[10px] leading-tight text-subtle">
          {s.duration_s ? `${formatDuration(s.duration_s)} · ` : ''}~{s.approx_mb.toFixed(1)} MB{!s.fixed_camera && ' · moving camera'}
          <br />
          <a href={s.source_page} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 hover:text-primary">
            {s.license} · {s.attribution} <ExternalLink className="size-2.5" />
          </a>
        </p>
        {imported ? (
          <Button size="xs" variant="outline" asChild>
            <Link to={`/analysis/${s.imported_video_id}`}>
              <Check /> Open
            </Link>
          </Button>
        ) : (
          <Button size="xs" onClick={onImport} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Download />} Import
          </Button>
        )}
      </div>
    </div>
  )
}

export function SamplesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const samples = useQuery({ queryKey: ['samples'], queryFn: videosApi.samples, enabled: open })
  const invalidate = useInvalidateAll()
  const [setup, setSetup] = useState(true)
  const [pending, setPending] = useState<Set<string>>(new Set())

  const importOne = async (s: SampleInfo) => {
    setPending((p) => new Set(p).add(s.key))
    try {
      await videosApi.importCatalogSample(s.key, setup)
      toast.success(`Imported “${s.title}”`, {
        description: setup && (s.zones.length || s.scenario) ? 'Demo zones created and processing queued.' : undefined,
      })
    } catch (e) {
      toast.error(`Could not import “${s.title}”`, { description: errorMessage(e) })
    } finally {
      setPending((p) => {
        const n = new Set(p)
        n.delete(s.key)
        return n
      })
      samples.refetch()
      invalidate()
    }
  }

  const importAll = async () => {
    for (const s of samples.data ?? []) if (!s.imported_video_id) await importOne(s)
  }

  const groups = Object.entries(
    (samples.data ?? []).reduce<Record<string, SampleInfo[]>>((acc, s) => {
      ;(acc[s.category] ??= []).push(s)
      return acc
    }, {}),
  )
  const remaining = (samples.data ?? []).filter((s) => !s.imported_video_id).length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Sample video library"
        description="Freely licensed clips (CC BY 4.0 or public domain), downloaded on request, to test detection of different objects and the zone-monitoring scenarios."
        className="max-w-5xl"
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs">
          <label className="flex items-center gap-2">
            <Switch checked={setup} onCheckedChange={setSetup} />
            Set up demo scenario on import (preset zones + start processing with tuned classes)
          </label>
          <Button size="sm" variant="outline" onClick={importAll} disabled={!remaining || pending.size > 0}>
            {pending.size ? <Loader2 className="animate-spin" /> : <Download />} Import all ({remaining})
          </Button>
        </div>
        {samples.isLoading ? (
          <LoadingState />
        ) : samples.isError ? (
          <ErrorState error={samples.error} onRetry={() => samples.refetch()} />
        ) : (
          <div className="space-y-4">
            {groups.map(([category, items]) => (
              <section key={category}>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-subtle">{category}</h4>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {items.map((s) => (
                    <SampleCard key={s.key} s={s} busy={pending.has(s.key)} onImport={() => importOne(s)} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
        <p className="mt-4 text-[11px] text-subtle">
          Downloads come from github.com/intel-iot-devkit/sample-videos and upload.wikimedia.org. Large clips can take a minute to download; the
          parking-lot clip is trimmed to its fixed-camera part with ffmpeg.
        </p>
      </DialogContent>
    </Dialog>
  )
}
