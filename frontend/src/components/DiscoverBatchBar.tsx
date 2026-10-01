import { EyeOff } from 'lucide-react'
import { BatchBarShell } from '@/components/BatchBarShell'
import { useBatchSelection } from '@/hooks/use-batch-selection'
import type { DiscoverItem } from '@/hooks/use-discover'
import { useIgnoreCards } from '@/hooks/use-ignored'
import { toast } from '@/lib/toast'

/**
 * Batch mode's one action over Discover's grid: mark the selection "don't want".
 *
 * One action, deliberately — the other thing you could do to a selection of
 * provider cards is acquire it, and a bulk Get is a different feature with
 * different failure modes (a write each, an avatar fetch each, partial
 * success). This only records a decision.
 *
 * Rendered by `DiscoverPage` rather than `AppShell` because it needs the rows on
 * screen: the selection holds `DiscoverItem.key`, which is unique in the grid,
 * and turning those back into the provider ids the ignore list stores means
 * looking them up. `BatchActionBar` stands aside on this route.
 */
export function DiscoverBatchBar({ items }: { items: DiscoverItem[] }) {
  const { active, selected, clear } = useBatchSelection()
  const ignore = useIgnoreCards()

  if (!active) return null

  // Selected rows, resolved against what is loaded. A key whose row has since
  // scrolled out of the result set simply is not ignorable -- there is no id to
  // record -- and the same goes for a Chub node that arrived without an id,
  // which the grid keys by `fullPath` instead.
  const chosen = items.filter(
    (item) => selected.has(item.key) && item.providerId,
  )

  const byProvider = new Map<DiscoverItem['provider'], string[]>()
  for (const item of chosen) {
    const ids = byProvider.get(item.provider) ?? []
    ids.push(item.providerId)
    byProvider.set(item.provider, ids)
  }

  const onIgnore = async () => {
    try {
      // Grouped by provider because the list is per provider. In practice the
      // grid only ever shows one at a time, so this is almost always one call;
      // grouping means a selection that outlived a provider switch still lands
      // in the right buckets rather than the active one.
      const results = await Promise.all(
        [...byProvider].map(([provider, ids]) =>
          ignore.mutateAsync({ provider, ids }),
        ),
      )
      const added = results.reduce((sum, result) => sum + result.added, 0)
      clear()
      toast(
        added === 0
          ? 'Already ignored.'
          : `Ignoring ${added} card${added === 1 ? '' : 's'}.`,
      )
    } catch (error) {
      toast((error as Error).message, 'bad')
    }
  }

  return (
    <BatchBarShell>
      <button
        type="button"
        onClick={() => void onIgnore()}
        disabled={chosen.length === 0 || ignore.isPending}
        className="flex h-[34px] items-center gap-2 rounded-[10px] border border-sage-line bg-sage px-3.5 text-[13px] font-semibold text-on-sage hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <EyeOff className="size-3.5" />
        {ignore.isPending ? 'Ignoring…' : 'Ignore'}
      </button>
    </BatchBarShell>
  )
}
