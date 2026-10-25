import {
  Bell,
  ChartNoAxesCombined,
  Film,
  Hexagon,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  ScanSearch,
  Settings,
  Siren,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useHealth, useOverview } from '@/hooks/queries'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/videos', label: 'Video Library', icon: Film },
  { to: '/analysis', label: 'Analysis Workspace', icon: ScanSearch },
  { to: '/zones', label: 'Monitoring Zones', icon: Hexagon },
  { to: '/events', label: 'Events', icon: Siren },
  { to: '/analytics', label: 'Analytics', icon: ChartNoAxesCombined },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function HealthIndicator() {
  const { data, isError } = useHealth()
  const status = isError ? 'unavailable' : data?.status
  const color = status === 'ok' ? 'bg-success' : status === 'degraded' ? 'bg-warning' : status ? 'bg-danger' : 'bg-subtle'
  const label =
    status === 'ok'
      ? 'All systems operational'
      : status === 'degraded'
        ? 'Degraded (see Settings)'
        : status
          ? 'API or database unavailable'
          : 'Checking…'
  return (
    <Link to="/settings" className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2" title={label}>
      <span className={cn('size-2 rounded-full', color, status === 'ok' && 'shadow-[0_0_8px] shadow-success/60')} />
      <span className="hidden sm:inline">{label}</span>
    </Link>
  )
}

function AlertsBell() {
  const { data } = useOverview({}, 15_000)
  const n = data?.unreviewed_alerts ?? 0
  return (
    <Link
      to="/events?status=new&alerts=1"
      className="relative rounded-md p-2 text-muted hover:bg-surface-2 hover:text-foreground"
      aria-label={`${n} unreviewed alerts`}
      title={`${n} unreviewed alert(s)`}
    >
      <Bell className="size-4" />
      {n > 0 && (
        <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-danger px-1 text-center text-[10px] font-semibold leading-4 text-white tabular">
          {n > 99 ? '99+' : n}
        </span>
      )}
    </Link>
  )
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('zv.sidebar') === 'collapsed')
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => setMobileOpen(false), [location.pathname])
  useEffect(() => localStorage.setItem('zv.sidebar', collapsed ? 'collapsed' : 'open'), [collapsed])

  const current = NAV.find((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)))

  return (
    <div className="flex h-full">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex flex-col border-r border-border bg-surface transition-[width,transform] duration-200 lg:static lg:translate-x-0',
          collapsed ? 'w-16' : 'w-60',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className={cn('flex h-14 items-center gap-2.5 border-b border-border px-4', collapsed && 'justify-center px-0')}>
          <img src="/favicon.svg" alt="" className="size-7" />
          {!collapsed && (
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">ZoneVision</div>
              <div className="text-[10px] uppercase tracking-wider text-subtle">Zone monitoring</div>
            </div>
          )}
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  collapsed && 'justify-center px-0',
                  isActive ? 'bg-primary/10 text-primary' : 'text-muted hover:bg-surface-2 hover:text-foreground',
                )
              }
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="hidden items-center gap-2 border-t border-border px-4 py-3 text-xs text-muted hover:text-foreground lg:flex"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen className="mx-auto size-4" /> : <PanelLeftClose className="size-4" />}
          {!collapsed && 'Collapse'}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface/80 px-4 backdrop-blur">
          <button className="rounded-md p-2 text-muted hover:bg-surface-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-4" />
          </button>
          <div className="text-sm font-medium text-muted">{current?.label ?? 'ZoneVision'}</div>
          <div className="ml-auto flex items-center gap-1">
            <HealthIndicator />
            <AlertsBell />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1600px] p-4 sm:p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
