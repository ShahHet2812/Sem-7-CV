import { useQueries } from '@tanstack/react-query'
import { useMemo } from 'react'
import { videosApi } from '@/services/videos'
import type { FrameDetections } from '@/types/api'

export const CHUNK_SECONDS = 20

/**
 * Loads detections in fixed 20 s windows around the playhead (previous,
 * current and next chunk) instead of downloading the whole video's
 * detections. Chunks are cached by React Query, so seeking back is free.
 */
export function useDetectionWindows(videoId: string | undefined, jobId: string | null | undefined, time: number) {
  const chunk = Math.max(0, Math.floor(time / CHUNK_SECONDS))
  const chunks = [chunk - 1, chunk, chunk + 1].filter((c) => c >= 0)
  const results = useQueries({
    queries: chunks.map((c) => ({
      queryKey: ['detections', videoId, jobId, c],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        videosApi.detections(videoId!, c * CHUNK_SECONDS, (c + 1) * CHUNK_SECONDS, signal),
      enabled: !!videoId && !!jobId,
      staleTime: Infinity,
    })),
  })

  const key = results.map((r) => r.dataUpdatedAt).join(',')
  const frames = useMemo<FrameDetections[]>(() => {
    const all = results.flatMap((r) => r.data?.frames ?? [])
    return all.sort((a, b) => a.timestamp - b.timestamp)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const meta = results.find((r) => r.data)?.data
  return {
    frames,
    sampleInterval: meta?.sample_interval ?? null,
    truncated: results.some((r) => r.data?.truncated),
    loading: results.some((r) => r.isLoading),
    error: results.find((r) => r.error)?.error ?? null,
  }
}
