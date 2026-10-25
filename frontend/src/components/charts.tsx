import type { ReactNode } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/primitives'
import { ErrorState, LoadingState } from '@/components/common'

export const CHART = {
  grid: '#232b38',
  axis: '#5d6779',
  tooltip: {
    contentStyle: { background: '#161c26', border: '1px solid #313b4b', borderRadius: 6, fontSize: 12, color: '#e6e9ef' },
    labelStyle: { color: '#8b95a7' },
    itemStyle: { color: '#e6e9ef' },
    cursor: { fill: 'rgba(255,255,255,0.04)' },
  },
  tick: { fill: '#8b95a7', fontSize: 11 },
  colors: {
    detections: '#22d3ee',
    entries: '#34d399',
    exits: '#a78bfa',
    alerts: '#f87171',
    tracks: '#fbbf24',
  },
}

export function ChartCard({
  title,
  description,
  children,
  loading,
  error,
  empty,
  emptyText = 'No data for the current filters.',
  action,
  height = 260,
}: {
  title: string
  description?: string
  children: ReactNode
  loading?: boolean
  error?: unknown
  empty?: boolean
  emptyText?: string
  action?: ReactNode
  height?: number
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent>
        <div style={{ height }}>
          {loading ? (
            <LoadingState className="h-full" />
          ) : error ? (
            <ErrorState error={error} className="h-full" />
          ) : empty ? (
            <div className="flex h-full items-center justify-center text-sm text-muted">{emptyText}</div>
          ) : (
            children
          )}
        </div>
      </CardContent>
    </Card>
  )
}
