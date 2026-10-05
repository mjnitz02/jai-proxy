import { useState } from 'react'
import {
  EntryRow,
  FilterChip,
  LorebooksBar,
  Notice,
  SearchField,
} from '@/components/lorebooks/parts'
import { useDebounced } from '@/hooks/use-debounced'
import { useLorebookEntries } from '@/hooks/use-lorebooks'

const PAGE = 100

type Show = 'unresolved' | 'changed' | 'all'

const SHOW: { key: Show; label: string }[] = [
  { key: 'unresolved', label: 'To decide' },
  { key: 'changed', label: 'All changed' },
  { key: 'all', label: 'Everything' },
]

/**
 * Entries (`/lore/entries`) -- every entry of every lorebook, one row per
 * entry however many versions of its text the cards hold. "To decide" is the
 * upgrade queue: entries whose text differs between cards carrying the same
 * lorebook, with no version chosen yet.
 */
export function LorebookEntriesPage() {
  const [search, setSearch] = useState('')
  const [show, setShow] = useState<Show>('unresolved')
  const [limit, setLimit] = useState(PAGE)
  const q = useDebounced(search.trim())
  const query = useLorebookEntries({
    q,
    changed: show === 'changed',
    unresolved: show === 'unresolved',
    sort: 'versions',
    limit,
  })
  const data = query.data

  return (
    <>
      <LorebooksBar>
        <SearchField
          value={search}
          onChange={(value) => {
            setSearch(value)
            setLimit(PAGE)
          }}
          placeholder="Search titles, keys and text"
        />
        {SHOW.map((option) => (
          <FilterChip
            key={option.key}
            active={show === option.key}
            onClick={() => {
              setShow(option.key)
              setLimit(PAGE)
            }}
          >
            {option.label}
          </FilterChip>
        ))}
        <div className="flex-1" />
        {data && (
          <span className="text-[12.5px] whitespace-nowrap text-faint">
            {data.total.toLocaleString()} entr{data.total === 1 ? 'y' : 'ies'}
          </span>
        )}
      </LorebooksBar>

      <div className="mx-auto max-w-[1320px] px-5 pt-4 pb-24">
        {query.isPending && <Notice>Reading entries off the cards…</Notice>}
        {query.error && <Notice tone="bad">{query.error.message}</Notice>}
        {data && data.total === 0 && (
          <Notice>
            {show === 'unresolved' && !q
              ? 'Nothing left to decide.'
              : 'No entries match.'}
          </Notice>
        )}
        {data && data.entries.length > 0 && (
          <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
            {data.entries.map((entry) => (
              <EntryRow key={entry.id} entry={entry} showLorebook />
            ))}
          </div>
        )}
        {data && data.entries.length < data.total && limit < 500 && (
          <div className="mt-4 text-center">
            <button
              type="button"
              onClick={() => setLimit((n) => Math.min(n + PAGE, 500))}
              disabled={query.isFetching}
              className="rounded-full border border-line px-4 py-1.5 text-[13px] hover:bg-raised disabled:opacity-50"
            >
              Show more
            </button>
          </div>
        )}
        {data && data.total > 500 && limit >= 500 && (
          <p className="mt-4 text-center text-[12.5px] text-faint">
            Showing the first 500 — search to narrow it down.
          </p>
        )}
      </div>
    </>
  )
}
