import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Cpu, Database, Download, HardDrive, Loader2, Save, Server, XCircle } from 'lucide-react'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { ErrorState, Field, LoadingState, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Switch } from '@/components/ui/primitives'
import { useHealth, useSettings } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { cn, formatBytes } from '@/lib/utils'
import { settingsApi } from '@/services/resources'
import type { ProcessingConfig, SettingsResponse } from '@/types/api'

export const processingSchema = z.object({
  confidence_threshold: z.coerce.number().min(0.05, 'Min 0.05').max(0.95, 'Max 0.95'),
  image_size: z.coerce
    .number()
    .int()
    .min(160, 'Min 160')
    .max(1920, 'Max 1920')
    .refine((v) => v % 32 === 0, 'Must be a multiple of 32'),
  target_sample_fps: z.coerce.number().gt(0, 'Must be > 0').max(60, 'Max 60'),
  classes: z.array(z.string()),
  tracker: z.enum(['bytetrack', 'botsort']),
  zone_confirm_samples: z.coerce.number().int().min(1).max(10),
  track_lost_timeout: z.coerce.number().min(0.2).max(60),
  occupancy_alert_cooldown: z.coerce.number().min(0).max(3600),
  anchor_mode: z.enum(['bottom_center', 'center']),
  generate_snapshots: z.boolean(),
})
type FormIn = z.input<typeof processingSchema>
type FormOut = z.output<typeof processingSchema>

function ProcessingForm({ data }: { data: SettingsResponse }) {
  const qc = useQueryClient()
  const form = useForm<FormIn, unknown, FormOut>({ resolver: zodResolver(processingSchema), defaultValues: data.processing })
  const { register, handleSubmit, control, formState, reset, watch, setValue } = form
  useEffect(() => reset(data.processing), [data.processing, reset])
  const save = useMutation({
    mutationFn: (v: Partial<ProcessingConfig>) => settingsApi.update(v),
    onSuccess: (res) => {
      qc.setQueryData(['settings'], res)
      toast.success('Settings saved', { description: 'New processing jobs will use these values.' })
    },
    onError: (e) => toast.error('Settings not saved', { description: errorMessage(e) }),
  })
  const selected = watch('classes') ?? []
  const allClasses = data.supported_classes.length ? data.supported_classes : data.processing.classes
  const e = formState.errors

  return (
    <form onSubmit={handleSubmit((v) => save.mutate(v))}>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Processing configuration</CardTitle>
            <CardDescription>
              Detection settings are copied into each job when it is queued. Zone settings apply when events are (re)computed.
            </CardDescription>
          </div>
          <Button type="submit" size="sm" disabled={!formState.isDirty || save.isPending}>
            {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save
          </Button>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Confidence threshold" error={e.confidence_threshold?.message} hint="0.05–0.95; lower finds more objects but more false positives">
              <Input type="number" step="0.01" {...register('confidence_threshold')} />
            </Field>
            <Field label="Inference image size (px)" error={e.image_size?.message} hint="Multiple of 32; larger is slower but finds small objects">
              <Input type="number" step="32" {...register('image_size')} />
            </Field>
            <Field label="Target sampling rate (frames/s)" error={e.target_sample_fps?.message} hint="Frame stride = round(video fps / target)">
              <Input type="number" step="0.5" {...register('target_sample_fps')} />
            </Field>
            <Field label="Tracker">
              <Select {...register('tracker')}>
                <option value="bytetrack">ByteTrack</option>
                <option value="botsort">BoT-SORT</option>
              </Select>
            </Field>
          </div>

          <Field
            label="Detected object classes"
            hint={
              data.supported_classes.length
                ? `${selected.length} of ${data.supported_classes.length} model classes selected (empty = all)`
                : 'Load the model to choose from all of its classes.'
            }
          >
            <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-border p-2">
              {allClasses.map((c) => {
                const on = selected.includes(c)
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setValue('classes', on ? selected.filter((x) => x !== c) : [...selected, c], { shouldDirty: true })}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-xs',
                      on ? 'border-primary bg-primary/15 text-primary' : 'border-border-strong text-muted hover:text-foreground',
                    )}
                  >
                    {c}
                  </button>
                )
              })}
            </div>
          </Field>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Zone confirmation samples" error={e.zone_confirm_samples?.message} hint="Consecutive samples needed to confirm a crossing">
              <Input type="number" {...register('zone_confirm_samples')} />
            </Field>
            <Field label="Lost-track timeout (s)" error={e.track_lost_timeout?.message} hint="Forget a track's zone state after this gap">
              <Input type="number" step="0.1" {...register('track_lost_timeout')} />
            </Field>
            <Field label="Occupancy alert cooldown (s)" error={e.occupancy_alert_cooldown?.message} hint="Minimum time between repeated alerts">
              <Input type="number" step="1" {...register('occupancy_alert_cooldown')} />
            </Field>
            <Field label="Zone anchor point" hint="Point of each box tested against zones">
              <Select {...register('anchor_mode')}>
                <option value="bottom_center">Bottom-center (ground contact)</option>
                <option value="center">Box center</option>
              </Select>
            </Field>
          </div>
          <Controller
            control={control}
            name="generate_snapshots"
            render={({ field }) => (
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={field.value} onCheckedChange={field.onChange} /> Generate JPEG evidence snapshots for events
              </label>
            )}
          />
        </CardContent>
      </Card>
    </form>
  )
}

function Check({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {ok ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-danger" />}
      <span>{label}</span>
      {detail && <span className="ml-auto text-xs text-muted">{detail}</span>}
    </div>
  )
}

export default function SettingsPage() {
  const settings = useSettings()
  const health = useHealth()
  const qc = useQueryClient()
  const loadModel = useMutation({
    mutationFn: settingsApi.loadModel,
    onSuccess: (res) => {
      qc.setQueryData(['settings'], res)
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.success('Model loaded', { description: `${res.model.name} · ${res.model.class_count} classes` })
    },
    onError: (e) => toast.error('Model could not be loaded', { description: errorMessage(e) }),
  })

  if (settings.isLoading) return <LoadingState />
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
  const s = settings.data!
  const h = health.data

  return (
    <>
      <PageHeader title="Settings" description="Model, processing and system configuration. Only options listed here change backend behaviour." />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <ProcessingForm data={s} />
          <Card>
            <CardHeader>
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Cpu className="size-4 text-primary" /> Detection model
                </CardTitle>
                <CardDescription>{s.model.source}</CardDescription>
              </div>
              <Button size="sm" variant="outline" onClick={() => loadModel.mutate()} disabled={loadModel.isPending}>
                {loadModel.isPending ? <Loader2 className="animate-spin" /> : <Download />}
                {s.model.weights_present ? 'Load model' : 'Download & load'}
              </Button>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-muted">Weights</dt>
                  <dd className="font-mono">{s.model.name}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Status</dt>
                  <dd>{s.model.loaded ? 'Loaded' : s.model.weights_present ? 'Downloaded (lazy-loaded)' : s.model.auto_download ? 'Downloads on first job' : 'Missing'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Inference device</dt>
                  <dd className="font-mono">{s.model.device}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Classes</dt>
                  <dd>{s.model.class_count ?? '—'}</dd>
                </div>
              </dl>
              {!s.model.weights_present && !s.model.auto_download && (
                <p className="mt-3 rounded-md bg-warning/10 px-3 py-2 text-xs text-warning">
                  Weights are missing and automatic download is disabled. Place the .pt file in the models directory or set MODEL_AUTO_DOWNLOAD=true
                  (see README → Model weights).
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="size-4 text-primary" /> Health
              </CardTitle>
              <span className={cn('text-xs font-medium capitalize', h?.status === 'ok' ? 'text-success' : 'text-warning')}>
                {health.isError ? 'unavailable' : h?.status}
              </span>
            </CardHeader>
            <CardContent className="space-y-2">
              {health.isError ? (
                <p className="text-sm text-danger">{errorMessage(health.error)}</p>
              ) : h ? (
                <>
                  <Check ok label="API" detail={`v${h.version}`} />
                  <Check ok={h.checks.database.ok} label="Database" detail={String(s.system.database)} />
                  <Check ok={h.checks.storage.ok} label="Storage writable" />
                  <Check ok={h.checks.worker.ok} label="Background worker" detail={h.checks.worker.enabled ? 'in-process' : 'disabled'} />
                  <Check ok={h.checks.model.ok} label="Model weights" detail={h.checks.model.weights_present ? 'present' : 'not downloaded'} />
                </>
              ) : (
                <LoadingState className="py-4" />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="size-4 text-primary" /> Storage & uploads
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
                <dt className="text-muted">Max upload</dt>
                <dd className="text-right">{s.upload.max_upload_mb} MB</dd>
                <dt className="text-muted">Formats</dt>
                <dd className="text-right text-xs">{s.upload.allowed_extensions.join(' ')}</dd>
                <dt className="text-muted">Uploads</dt>
                <dd className="text-right tabular">{formatBytes(s.storage.uploads_bytes)}</dd>
                <dt className="text-muted">Thumbnails</dt>
                <dd className="text-right tabular">{formatBytes(s.storage.processed_bytes)}</dd>
                <dt className="text-muted">Snapshots</dt>
                <dd className="text-right tabular">{formatBytes(s.storage.snapshots_bytes)}</dd>
                <dt className="text-muted">Disk free</dt>
                <dd className="text-right tabular">
                  {formatBytes(s.storage.disk_free_bytes)} / {formatBytes(s.storage.disk_total_bytes)}
                </dd>
              </dl>
              <p className="mt-2 text-xs text-subtle">Upload limit is configured with the {s.upload.configured_via}.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="size-4 text-primary" /> Application
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
                {Object.entries(s.system).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="capitalize text-muted">{k.replace(/_/g, ' ')}</dt>
                    <dd className="truncate text-right font-mono text-xs leading-5" title={String(v)}>
                      {v === null ? '—' : String(v)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-subtle">
                Academic project: “Vision-Based Object Detection and Zone Monitoring Platform”. Local deployment without authentication — intended
                for development and demonstration only.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  )
}
