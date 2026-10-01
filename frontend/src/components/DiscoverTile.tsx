import { useState } from 'react'
import { Link } from 'react-router'
import { Check } from 'lucide-react'
import type { DiscoverItem } from '@/hooks/use-discover'
import { cn } from '@/lib/utils'

/**
 * One provider search result.
 *
 * A link, like `CardTile` — the mock makes every card open the card, Discover's
 * included (`d-archive.html:882`), and `web/` opened a full preview modal on
 * click. The first version of this was neither: a thumbnail with a hover
 * button, so there was no way to read a card before deciding to keep it.
 *
 * `Get` and the creator name sit inside the link and stop the click from
 * reaching it, so the tile has three targets without three overlapping regions.
 */
export function DiscoverTile({
  item,
  have,
  ignored = false,
  onAdd,
  onBrowseCreator,
  adding,
  search,
  batchMode = false,
  selected = false,
  onToggleSelect,
}: {
  item: DiscoverItem
  have: boolean
  /** Marked "don't want". Shown rather than merged into `have` because the two
   *  are different claims — this card is not in the archive — and badging it
   *  "Have" would say something untrue. Only ever visible with "Hide cards I
   *  have" off, which is the one state where you need to know why a card would
   *  otherwise be missing. */
  ignored?: boolean
  onAdd: () => void
  onBrowseCreator: () => void
  adding: boolean
  /** Discover's query string, carried onto the link so the preview can rebuild
   *  this grid for its prev/next — the same trick `CardTile` uses. */
  search: string
  /** Batch-select mode — see `use-batch-selection`. Keyed on `item.key` rather
   *  than the provider id, since a Chub node can arrive without one. */
  batchMode?: boolean
  selected?: boolean
  onToggleSelect?: (key: string) => void
}) {
  // Provider avatars arrive at wildly different sizes and connection speeds,
  // and popping in fully-decoded reads as the grid "snapping" mid-scroll. A
  // fade removes the pop without waiting on anything extra to load.
  const [loaded, setLoaded] = useState(false)
  return (
    <Link
      to={{
        pathname: `/discover/${item.provider}/${encodeURIComponent(item.providerId)}`,
        search,
      }}
      className={cn('group block', selected && 'rounded-xl ring-2 ring-sage')}
      onClick={(event) => {
        // In batch mode the tile is a checkbox, not a link — the same trade
        // `CardTile` makes, so the two grids behave identically once batch mode
        // is on.
        if (batchMode) {
          event.preventDefault()
          onToggleSelect?.(item.key)
        }
      }}
    >
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-xl border border-line-soft bg-raised group-hover:border-sage-line">
        {batchMode && (
          <span
            className={cn(
              'absolute top-1.5 left-1.5 z-3 grid size-6 place-items-center rounded-[7px] border backdrop-blur-[6px]',
              selected
                ? 'border-sage bg-sage text-on-sage'
                : 'border-white/30 bg-ground/72 text-transparent',
            )}
          >
            <Check className="size-3.5" />
          </span>
        )}
        {have ? (
          <span className="absolute top-[7px] right-[7px] z-2 rounded-[6px] border border-sage-line bg-ground/80 px-1.5 py-px text-[10px] font-bold tracking-[0.05em] text-sage uppercase backdrop-blur-[6px]">
            Have
          </span>
        ) : (
          ignored && (
            <span className="absolute top-[7px] right-[7px] z-2 rounded-[6px] border border-white/12 bg-ground/80 px-1.5 py-px text-[10px] font-bold tracking-[0.05em] text-faint uppercase backdrop-blur-[6px]">
              Ignored
            </span>
          )
        )}
        {item.avatarUrl ? (
          <img
            src={item.avatarUrl}
            alt=""
            loading="lazy"
            onLoad={() => setLoaded(true)}
            className={cn(
              'size-full object-cover transition-[opacity,transform] duration-[450ms] ease-[cubic-bezier(.2,.7,.3,1)] group-hover:scale-105',
              loaded ? 'opacity-100' : 'opacity-0',
            )}
          />
        ) : (
          <div className="size-full bg-raised" />
        )}
        <span className="pointer-events-none absolute inset-0 shadow-[inset_0_-54px_44px_-30px_#0f1113de]" />
        {/* Hidden in batch mode: a hover button that acquires one card sits
            badly over a grid whose clicks are selecting many. */}
        {!batchMode && (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onAdd()
            }}
            disabled={adding}
            className="absolute inset-x-[7px] bottom-[7px] z-3 hidden h-7 items-center justify-center rounded-lg bg-sage text-[12px] font-semibold text-on-sage group-hover:flex disabled:opacity-60"
          >
            {adding ? 'Adding…' : have ? 'Add again' : 'Get'}
          </button>
        )}
      </div>
      <h3 className="mt-2 line-clamp-2 text-[13.5px] leading-[1.3] font-medium">
        {item.name}
      </h3>
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          // Navigating to a creator mid-selection would strand the selection on
          // a feed that no longer holds those rows, so in batch mode the
          // creator line selects like the rest of the tile.
          if (batchMode) onToggleSelect?.(item.key)
          else onBrowseCreator()
        }}
        className={cn(
          'mt-px block max-w-full truncate text-left text-[11.5px] text-faint',
          !batchMode && 'hover:text-sage hover:underline',
        )}
      >
        {item.creator || 'unknown'}
      </button>
    </Link>
  )
}
