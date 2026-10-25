import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { EventType, ZoneType } from '@/types/api'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`
}

/** Seconds -> m:ss or h:mm:ss (optionally with tenths). */
export function formatDuration(seconds: number | null | undefined, tenths = false): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const secStr = tenths ? sec.toFixed(1).padStart(4, '0') : Math.floor(sec).toString().padStart(2, '0')
  return h ? `${h}:${m.toString().padStart(2, '0')}:${secStr}` : `${m}:${secStr}`
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  return new Intl.NumberFormat().format(n)
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`
  return formatDateTime(iso)
}

export const EVENT_LABELS: Record<EventType, string> = {
  zone_entry: 'Entered zone',
  zone_exit: 'Exited zone',
  restricted_entry: 'Restricted entry',
  occupancy_exceeded: 'Occupancy exceeded',
  processing_failure: 'Processing failure',
}

export const ZONE_TYPE_LABELS: Record<ZoneType, string> = {
  general: 'General monitoring',
  entry: 'Entry zone',
  exit: 'Exit zone',
  restricted: 'Restricted zone',
}

export const ZONE_COLORS = ['#22d3ee', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#60a5fa', '#fb923c', '#f87171']

/** Stable color per object class for overlays/charts. */
export function classColor(name: string): string {
  const palette = ['#22d3ee', '#fbbf24', '#a78bfa', '#34d399', '#f472b6', '#60a5fa', '#fb923c', '#e879f9', '#4ade80']
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return palette[h % palette.length]
}

export function toIsoOrUndefined(local: string | undefined): string | undefined {
  if (!local) return undefined
  const d = new Date(local)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}
