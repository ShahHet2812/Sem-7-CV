import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Link } from 'react-router-dom'
import { AppShell } from '@/app/AppShell'
import { EmptyState, LoadingState } from '@/components/common'
import { Button } from '@/components/ui/button'

const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'))
const VideoLibraryPage = lazy(() => import('@/features/videos/VideoLibraryPage'))
const AnalysisPage = lazy(() => import('@/features/analysis/AnalysisPage'))
const ZonesPage = lazy(() => import('@/features/zones/ZonesPage'))
const EventsPage = lazy(() => import('@/features/events/EventsPage'))
const AnalyticsPage = lazy(() => import('@/features/analytics/AnalyticsPage'))
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage'))

const page = (el: ReactNode) => <Suspense fallback={<LoadingState />}>{el}</Suspense>

function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you requested does not exist."
      action={
        <Button asChild>
          <Link to="/">Back to overview</Link>
        </Button>
      }
    />
  )
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: page(<DashboardPage />) },
      { path: 'videos', element: page(<VideoLibraryPage />) },
      { path: 'analysis', element: page(<AnalysisPage />) },
      { path: 'analysis/:videoId', element: page(<AnalysisPage />) },
      { path: 'zones', element: page(<ZonesPage />) },
      { path: 'events', element: page(<EventsPage />) },
      { path: 'analytics', element: page(<AnalyticsPage />) },
      { path: 'settings', element: page(<SettingsPage />) },
      { path: '*', element: <NotFound /> },
    ],
  },
])
