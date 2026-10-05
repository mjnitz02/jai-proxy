import { Link, useNavigate, useParams } from 'react-router'
import {
  ActionButton,
  CardStrip,
  LorebooksBar,
  Notice,
  Pill,
} from '@/components/lorebooks/parts'
import { useLorebookActions, useLorebookEntry } from '@/hooks/use-lorebooks'
import { toast } from '@/lib/toast'
import { cn } from '@/lib/utils'

/**
 * One entry (`/lore/entries/:id`): each version of its text side by side
 * with the cards holding it, newest first -- and where the decisions about it
 * are made. Choosing a version records which text every card should carry;
 * merging folds in an entry the index took for a different one. Neither
 * touches a card: that is the sync.
 */
export function LorebookEntryPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const query = useLorebookEntry(id)
  const actions = useLorebookActions()
  const entry = query.data
  const onError = (error: Error) => toast(error.message, 'bad')

  return (
    <>
      <LorebooksBar />
      <div className="mx-auto max-w-[1320px] px-5 pt-5 pb-24">
        {query.isPending && <Notice>Loading…</Notice>}
        {query.error && <Notice tone="bad">{query.error.message}</Notice>}
        {entry && (
          <>
            <Link
              to={`/lore/${entry.lorebook_id}`}
              className="text-[13px] text-muted hover:text-text"
            >
              ← {entry.lorebook_name}
            </Link>
            <h1 className="mt-1 font-serif text-[30px] leading-tight">
              {entry.title || 'Untitled entry'}
            </h1>
            <p className="mt-1.5 text-[13px] text-muted">
              {entry.versions.length === 1
                ? 'One version — every card carrying this lorebook has the same text.'
                : entry.chosen
                  ? `${entry.versions.length} versions. One is chosen; cards holding another will take it on the next sync.`
                  : `${entry.versions.length} versions across the cards carrying this lorebook. Choose the one to keep.`}
            </p>

            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              {entry.versions.map((version, index) => {
                const chosen = entry.chosen === version.hash
                return (
                  <div
                    key={version.hash}
                    className={cn(
                      'rounded-[15px] border bg-surface px-4 py-3.5',
                      chosen ? 'border-sage-line' : 'border-line-soft',
                    )}
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px] text-muted">
                      {chosen && <Pill tone="sage">chosen</Pill>}
                      {entry.versions.length > 1 && index === 0 && (
                        <Pill title="On the most recently created card — a guess at which version is current">
                          newest
                        </Pill>
                      )}
                      {version.constant && <Pill>always on</Pill>}
                      <span>
                        {version.cards.length} card
                        {version.cards.length === 1 ? '' : 's'} ·{' '}
                        {version.content.length.toLocaleString()} chars
                      </span>
                      {version.newest && (
                        <span className="text-faint">
                          · latest card {version.newest.slice(0, 10)}
                        </span>
                      )}
                      <span className="flex-1" />
                      {entry.versions.length > 1 &&
                        (chosen ? (
                          <ActionButton
                            disabled={actions.clearChoice.isPending}
                            onClick={() =>
                              actions.clearChoice.mutate(entry.id, { onError })
                            }
                          >
                            Clear choice
                          </ActionButton>
                        ) : (
                          <ActionButton
                            tone="sage"
                            disabled={actions.choose.isPending}
                            onClick={() =>
                              actions.choose.mutate(
                                { entry: entry.id, hash: version.hash },
                                { onError },
                              )
                            }
                          >
                            Use this version
                          </ActionButton>
                        ))}
                    </div>
                    {version.keys.length > 0 && (
                      <div className="mb-2 font-mono text-[11.5px] text-faint">
                        {version.keys.join(', ')}
                        {version.secondary_keys.length > 0 &&
                          ` + ${version.secondary_keys.join(', ')}`}
                      </div>
                    )}
                    <p className="max-h-[420px] overflow-y-auto text-[13.5px] leading-relaxed whitespace-pre-wrap">
                      {version.content}
                    </p>
                    <div className="mt-3 border-t border-line-soft pt-3">
                      <CardStrip cards={version.cards} />
                    </div>
                  </div>
                )
              })}
            </div>

            {entry.merges.length > 0 && (
              <>
                <h2 className="mt-7 mb-2.5 text-[15px] font-semibold">
                  Merged by hand
                </h2>
                <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
                  {entry.merges.map((merge) => (
                    <div
                      key={merge.id}
                      className="flex items-center gap-3 border-b border-line-soft px-4 py-2.5 text-[13px] text-muted last:border-b-0"
                    >
                      <span>
                        An entry was merged into this one
                        {merge.at && ` on ${merge.at.slice(0, 10)}`}.
                      </span>
                      <span className="flex-1" />
                      <ActionButton
                        disabled={actions.unmergeEntries.isPending}
                        onClick={() =>
                          actions.unmergeEntries.mutate(merge.id, {
                            onError,
                            onSuccess: () =>
                              navigate(`/lore/${entry.lorebook_id}`),
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

            {entry.candidates.length > 0 && (
              <>
                <h2 className="mt-7 text-[15px] font-semibold">
                  Possibly the same entry
                </h2>
                <p className="mt-1 mb-2.5 text-[12.5px] text-faint">
                  Entries of this lorebook with similar text that never appear
                  on the same card — likely this entry under another title.
                  Merging makes them versions of one entry.
                </p>
                <div className="overflow-hidden rounded-[15px] border border-line-soft bg-surface">
                  {entry.candidates.map((candidate) => (
                    <div
                      key={candidate.id}
                      className="flex items-start gap-3 border-b border-line-soft px-4 py-3 last:border-b-0"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            to={`/lore/entries/${candidate.id}`}
                            className="text-[14px] font-medium hover:underline"
                          >
                            {candidate.title || 'Untitled entry'}
                          </Link>
                          <Pill>
                            {Math.round(candidate.similarity * 100)}% alike
                          </Pill>
                          <span className="text-[12px] text-faint">
                            {candidate.card_count} card
                            {candidate.card_count === 1 ? '' : 's'}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[13px] text-muted">
                          {candidate.preview}
                        </p>
                      </div>
                      <ActionButton
                        disabled={actions.mergeEntries.isPending}
                        onClick={() =>
                          actions.mergeEntries.mutate(
                            { entry: candidate.id, into: entry.id },
                            {
                              onError,
                              onSuccess: (merged) => {
                                toast('Merged into one entry.')
                                navigate(`/lore/entries/${merged.id}`, {
                                  replace: true,
                                })
                              },
                            },
                          )
                        }
                      >
                        Merge
                      </ActionButton>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  )
}
