import { FilterX } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/primitives'
import { useSettings, useVideoOptions, useZones } from '@/hooks/queries'
import { toIsoOrUndefined } from '@/lib/utils'
import type { AnalyticsFilters } from '@/types/api'

/** Analytics filters persisted in the URL so views are shareable. */
export function useAnalyticsFilters(): [AnalyticsFilters, (patch: Record<string, string | undefined>) => void, () => void, URLSearchParams] {
  const [params, setParams] = useSearchParams()
  const filters: AnalyticsFilters = {
    video_id: params.get('video_id') || undefined,
    zone_id: params.get('zone_id') || undefined,
    class_name: params.get('class_name') || undefined,
    date_from: toIsoOrUndefined(params.get('from') || undefined),
    date_to: toIsoOrUndefined(params.get('to') || undefined),
  }
  const update = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  return [filters, update, () => setParams({}, { replace: true }), params]
}

export function AnalyticsFilterBar({ showZone = true, showClass = true }: { showZone?: boolean; showClass?: boolean }) {
  const [, update, clear, params] = useAnalyticsFilters()
  const videos = useVideoOptions()
  const zones = useZones(params.get('video_id') || undefined)
  const settings = useSettings()
  const active = [...params.keys()].length > 0
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Select value={params.get('video_id') ?? ''} onChange={(e) => update({ video_id: e.target.value, zone_id: undefined })} className="w-56" aria-label="Video">
        <option value="">All videos</option>
        {videos.data?.items.map((v) => (
          <option key={v.id} value={v.id}>
            {v.original_filename}
          </option>
        ))}
      </Select>
      {showZone && (
        <Select value={params.get('zone_id') ?? ''} onChange={(e) => update({ zone_id: e.target.value })} className="w-44" aria-label="Zone">
          <option value="">All zones</option>
          {zones.data?.map((z) => (
            <option key={z.id} value={z.id}>
              {z.name}
            </option>
          ))}
        </Select>
      )}
      {showClass && (
        <Select value={params.get('class_name') ?? ''} onChange={(e) => update({ class_name: e.target.value })} className="w-36" aria-label="Class">
          <option value="">All classes</option>
          {(settings.data?.processing.classes ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      )}
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <Input type="datetime-local" value={params.get('from') ?? ''} onChange={(e) => update({ from: e.target.value })} className="w-48" aria-label="From" title="From" />
        –
        <Input type="datetime-local" value={params.get('to') ?? ''} onChange={(e) => update({ to: e.target.value })} className="w-48" aria-label="To" title="To" />
      </div>
      {active && (
        <Button variant="ghost" size="sm" onClick={clear}>
          <FilterX /> Reset
        </Button>
      )}
    </div>
  )
}
