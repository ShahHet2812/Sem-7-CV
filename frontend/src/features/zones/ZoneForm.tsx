import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import { Field } from '@/components/common'
import { Input, Select, Switch } from '@/components/ui/primitives'
import { cn, ZONE_COLORS, ZONE_TYPE_LABELS } from '@/lib/utils'
import type { ZoneType } from '@/types/api'

export const zoneFormSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(100, 'Max 100 characters'),
  zone_type: z.enum(['general', 'entry', 'exit', 'restricted']),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, 'Use a hex color like #22d3ee'),
  enabled: z.boolean(),
  emit_entries: z.boolean(),
  emit_exits: z.boolean(),
  occupancy_threshold: z
    .union([z.literal(''), z.coerce.number().int('Whole number').min(0, 'Must be ≥ 0').max(10000)])
    .transform((v) => (v === '' ? null : v)),
  class_filter: z.array(z.string()),
})

export type ZoneFormInput = z.input<typeof zoneFormSchema>
export type ZoneFormValues = z.output<typeof zoneFormSchema>

export const TYPE_DEFAULTS: Record<ZoneType, { emit_entries: boolean; emit_exits: boolean }> = {
  general: { emit_entries: true, emit_exits: true },
  entry: { emit_entries: true, emit_exits: false },
  exit: { emit_entries: false, emit_exits: true },
  restricted: { emit_entries: true, emit_exits: true },
}

export function ZoneForm({
  id,
  defaultValues,
  classes,
  onSubmit,
  onColorChange,
}: {
  id: string
  defaultValues: ZoneFormInput
  classes: string[]
  onSubmit: (v: ZoneFormValues) => void
  onColorChange?: (c: string) => void
}) {
  const form = useForm<ZoneFormInput, unknown, ZoneFormValues>({
    resolver: zodResolver(zoneFormSchema),
    defaultValues,
  })
  const { register, control, handleSubmit, watch, setValue, formState } = form
  const type = watch('zone_type')
  const color = watch('color')
  const selected = watch('class_filter') ?? []

  useEffect(() => {
    onColorChange?.(color)
  }, [color, onColorChange])

  return (
    <form id={id} onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <Field label="Name" error={formState.errors.name?.message}>
        <Input {...register('name')} placeholder="e.g. Entrance" autoComplete="off" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type">
          <Select
            {...register('zone_type', {
              onChange: (e) => {
                const d = TYPE_DEFAULTS[e.target.value as ZoneType]
                setValue('emit_entries', d.emit_entries)
                setValue('emit_exits', d.emit_exits)
              },
            })}
          >
            {(Object.keys(ZONE_TYPE_LABELS) as ZoneType[]).map((t) => (
              <option key={t} value={t}>
                {ZONE_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Max occupancy (optional)" error={formState.errors.occupancy_threshold?.message}>
          <Input type="number" min={0} placeholder="No limit" {...register('occupancy_threshold')} />
        </Field>
      </div>
      <Field label="Color" error={formState.errors.color?.message}>
        <div className="flex flex-wrap items-center gap-1.5">
          {ZONE_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setValue('color', c, { shouldDirty: true })}
              className={cn('size-6 rounded-md border-2', color === c ? 'border-white' : 'border-transparent')}
              style={{ background: c }}
              aria-label={`Color ${c}`}
            />
          ))}
          <Input {...register('color')} className="ml-1 h-7 w-24 font-mono text-xs" />
        </div>
      </Field>
      <div className="grid grid-cols-3 gap-2 text-xs">
        {(
          [
            ['enabled', 'Enabled'],
            ['emit_entries', type === 'restricted' ? 'Alert on entry' : 'Count entries'],
            ['emit_exits', 'Count exits'],
          ] as const
        ).map(([name, label]) => (
          <Controller
            key={name}
            control={control}
            name={name}
            render={({ field }) => (
              <label className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5">
                <Switch checked={field.value} onCheckedChange={field.onChange} />
                {label}
              </label>
            )}
          />
        ))}
      </div>
      {classes.length > 0 && (
        <Field label="Monitored classes" hint={selected.length ? `${selected.length} selected` : 'All tracked classes'}>
          <div className="flex flex-wrap gap-1.5">
            {classes.map((c) => {
              const on = selected.includes(c)
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() =>
                    setValue('class_filter', on ? selected.filter((x) => x !== c) : [...selected, c], { shouldDirty: true })
                  }
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
      )}
    </form>
  )
}
