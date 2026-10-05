import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  ActionButton,
  CardStrip,
  EntryRow,
  FilterChip,
  LorebooksBar,
  Notice,
  Pill,
  SearchField,
} from '@/components/lorebooks/parts'
import {
  useLorebook,
  useLorebookActions,
  useLorebooks,
} from '@/hooks/use-lorebooks'
import { toast } from '@/lib/toast'

const RELATION = {
  subset: 'contained in',
  superset: 'contains',
  overlap: 'overlaps',
} as const

type Show = 'all' | 'changed' | 'undecided'

/**
 * One lorebook (`/lore/:id`): the revisions its cards hold, its entries
 * (undecided ones first), and the lorebooks it shares entries with -- plus the
 * two decisions made at this level: merging another lorebook into this one,
 * and accepting the newest version of every undecided entry at once.
 */
export function LorebookDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const query = useLorebook(id)
  const actions = useLorebookActions()
  const [show, setShow] = useState<Show>('all')
  const book = query.data
  const onError = (error: Error) => toast(error.message, 'bad')

  const merge = (other: string) =>
    actions.mergeLorebooks.mutate(
      { lorebook: other, into: id },
      {
        onError,
        onSuccess: (merged) => {
          toast('Merged. Undo it from “Merged by hand” below.')
          navigate(`/lore/${merged.id}`, { replace: true })
        },
      },
    )

  return (
    <>
      <LorebooksBar />
      <div className="mx-auto max-w-[1320px] px-5 pt-5 pb-24">
        {query.isPending && <Notice>Loading…</Notice>}
        {query.error && <Notice tone="bad">{query.error.message}</Notice>}
        {book && (
          <>
            <h1 className="font-serif text-[30px] leading-tight">
              {book.name}
            </h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px] text-muted">
              <span>
                {book.card_count} card{book.card_count === 1 ? '' : 's'} ·{' '}
                {book.entry_count} entries · {book.chars.toLocaleString()} chars
              </span>
              {book.creators.length > 0 && (
                <span className="text-faint">· {book.creators.join(', ')}</span>
              )}
              {book.refs.map((ref) => (
                <span key={ref} className="font-mono text-[11.5px] text-faint">
                  {ref}
                </span>
              ))}
            </div>

            {(book.unresolved_entries > 0 || book.pending_cards > 0) && (
              <div className="mt-4 flex flex-wrap items-center gap-3 rounded-[15px] border border-line-soft bg-surface px-4 py-3 text-[13px]">
                {book.unresolved_entries > 0 && (
                  <Pill tone="warn">
                    {book.unresolved_entries} entr
                    {book.unresolved_entries === 1 ? 'y' : 'ies'} to decide
                  </Pill>
                )}
                {book.pending_cards > 0 && (
                  <Pill tone="sage">
                    {book.pending_cards} card
                    {book.pending_cards === 1 ? '' : 's'} to sync
                  </Pill>
                )}
                <span className="text-muted">
                  {book.unresolved_entries > 0
                    ? 'Cards carrying this lorebook disagree on these entries.'
                    : 'Every entry is decided. Nothing is written to a card until a sync.'}
                </span>
                <span className="flex-1" />
                {book.unresolved_entries > 0 && (
                  <ActionButton
                    tone="sage"
                    disabled={actions.chooseNewest.isPending}
                    onClick={() =>
                      actions.chooseNewest.mutate(id, {
                        onError,
                        onSuccess: (result) =>
                          toast(
                            `Chose the newest version of ${result.chosen} entr${result.chosen === 1 ? 'y' : 'ies'}.`,
                          ),
                      })
                    }
                  >
                    Use the newest version of each
                  </ActionButton>
                )}
              </div>
            )}

            <Heading>
              {book.revisions.length === 1
                ? 'Every card holds the same copy'
                : `${book.revisions.length} revisions across its cards`}
            </Heading>
            <div className="space-y-2.5">
              {book.revisions.map((revision, index) => (
                <div
                  key={revision.fingerprint}
                  className="rounded-[15px] border border-line-soft bg-surface px-4 py-3"
                >
                  <div className="mb-2.5 flex flex-wrap items-center gap-2 text-[12.5px] text-muted">
                    {book.revisions.length > 1 && index === 0 && (
                      <Pill title="On the most recently created card — a guess at which copy is current">
                        newest
                      </Pill>
                    )}
                    <span>
                      {revision.entry_count} entries · {revision.cards.length}{' '}
                      card{revision.cards.length === 1 ? '' : 's'}
                    </span>
                    {revision.newest && (
                      <span className="text-faint">
                        · latest card {revision.newest.slice(0, 10)}
                      </span>
                    )}
                  </div>
                  <CardStrip cards={revision.cards} />
                </div>
              ))}
            </div>

            {book.similar.length > 0 && (
              <>
                <Heading>Shares entries with</Heading>
                <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
                  {book.similar.map((other) => (
                    <div
                      key={other.id}
                      className="flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-2.5 last:border-b-0"
                    >
                      <Pill>{RELATION[other.relation]}</Pill>
                      <Link
                        to={`/lore/${other.id}`}
                        className="text-[14px] hover:underline"
                      >
                        {other.name}
                      </Link>
                      <span className="ml-auto text-[12.5px] text-muted">
                        {other.shared} of {other.entry_count} entries shared ·{' '}
                        {other.card_count} card
                        {other.card_count === 1 ? '' : 's'}
                      </span>
                      <ActionButton
                        disabled={actions.mergeLorebooks.isPending}
                        onClick={() => merge(other.id)}
                      >
                        Merge into this
                      </ActionButton>
                    </div>
                  ))}
                </div>
              </>
            )}

            <MergePicker
              self={book.id}
              exclude={book.similar.map((s) => s.id)}
              disabled={actions.mergeLorebooks.isPending}
              onMerge={merge}
            />

            {book.merges.length > 0 && (
              <>
                <Heading>Merged by hand</Heading>
                <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
                  {book.merges.map((made) => (
                    <div
                      key={made.id}
                      className="flex items-center gap-3 border-b border-line-soft px-4 py-2.5 text-[13px] last:border-b-0"
                    >
                      <span>
                        {made.b_name || 'A lorebook'}{' '}
                        <span className="text-faint">merged into</span>{' '}
                        {made.a_name || 'this one'}
                      </span>
                      {made.at && (
                        <span className="text-[12px] text-faint">
                          {made.at.slice(0, 10)}
                        </span>
                      )}
                      <span className="flex-1" />
                      <ActionButton
                        disabled={actions.unmergeLorebooks.isPending}
                        onClick={() =>
                          actions.unmergeLorebooks.mutate(made.id, {
                            onError,
                            // The id this page is at may not survive the
                            // split, so go back to the list rather than 404.
                            onSuccess: () => navigate('/lore'),
                          })
                        }
                      >
                        Undo merge
                      </ActionButton>
                    </div>
                  ))}
                </div>
              </>
            )}

            <div className="mt-7 mb-2.5 flex flex-wrap items-center gap-2">
              <h2 className="mr-1 text-[15px] font-semibold">Entries</h2>
              {book.changed_entries > 0 && (
                <>
                  <FilterChip
                    active={show === 'all'}
                    onClick={() => setShow('all')}
                  >
                    All
                  </FilterChip>
                  <FilterChip
                    active={show === 'changed'}
                    onClick={() => setShow('changed')}
                  >
                    {book.changed_entries} changed
                  </FilterChip>
                  <FilterChip
                    active={show === 'undecided'}
                    onClick={() => setShow('undecided')}
                  >
                    {book.unresolved_entries} to decide
                  </FilterChip>
                </>
              )}
            </div>
            <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
              {book.entries
                .filter((entry) =>
                  show === 'undecided'
                    ? !entry.resolved
                    : show === 'changed'
                      ? entry.version_count > 1
                      : true,
                )
                .map((entry) => (
                  <EntryRow key={entry.id} entry={entry} />
                ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}

/**
 * Merge a lorebook the index did not connect to this one. The overlap list
 * above only offers books that already share entries; a book rewritten end to
 * end shares none, and can only be found by name.
 */
function MergePicker({
  self,
  exclude,
  disabled,
  onMerge,
}: {
  self: string
  exclude: string[]
  disabled: boolean
  onMerge: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const all = useLorebooks()
  const needle = search.trim().toLowerCase()
  const matches = needle
    ? (all.data?.lorebooks ?? [])
        .filter(
          (book) =>
            book.id !== self &&
            !exclude.includes(book.id) &&
            (book.name.toLowerCase().includes(needle) ||
              book.creators.some((c) => c.toLowerCase().includes(needle))),
        )
        .slice(0, 8)
    : []

  if (!open)
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 text-[12.5px] text-faint hover:text-text"
      >
        Merge another lorebook into this one…
      </button>
    )

  return (
    <div className="mt-3 rounded-[15px] border border-line-soft bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <SearchField
          value={search}
          onChange={setSearch}
          placeholder="Find a lorebook by name or creator"
        />
        <span className="text-[12.5px] text-faint">
          Its cards and entries join this lorebook. Reversible.
        </span>
      </div>
      {matches.map((book) => (
        <div
          key={book.id}
          className="mt-2 flex flex-wrap items-center gap-3 text-[13.5px]"
        >
          <Link to={`/lore/${book.id}`} className="hover:underline">
            {book.name}
          </Link>
          <span className="text-[12.5px] text-faint">
            {book.creators.slice(0, 2).join(', ')} · {book.card_count} card
            {book.card_count === 1 ? '' : 's'} · {book.entry_count} entries
          </span>
          <span className="flex-1" />
          <ActionButton disabled={disabled} onClick={() => onMerge(book.id)}>
            Merge into this
          </ActionButton>
        </div>
      ))}
      {needle && matches.length === 0 && all.data && (
        <p className="mt-2 text-[12.5px] text-faint">No lorebooks match.</p>
      )}
    </div>
  )
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-7 mb-2.5 text-[15px] font-semibold">{children}</h2>
}
