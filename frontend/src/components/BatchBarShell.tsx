import { X } from 'lucide-react'
import { useBatchSelection } from '@/hooks/use-batch-selection'

/**
 * The floating pill batch mode shows while it's on: "N selected", whatever
 * actions the grid underneath offers, Cancel.
 *
 * Shared because there are two grids and they select different things — a card
 * you own, which can be deleted (`BatchActionBar`), or a provider result you
 * don't, which can be ignored (`DiscoverBatchBar`). Only the buttons differ, so
 * only the buttons are per-grid; the count, the chrome and Cancel are here.
 */
export function BatchBarShell({ children }: { children: React.ReactNode }) {
  const { selected, clear } = useBatchSelection()

  return (
    <div className="fixed inset-x-0 bottom-6 z-30 flex justify-center">
      <div className="flex items-center gap-3 rounded-full border border-line bg-surface px-4 py-2.5 shadow-[0_20px_50px_#000000c0]">
        <span className="px-1 text-[13px] text-faint">
          {selected.size} selected
        </span>
        {children}
        <button
          type="button"
          onClick={clear}
          className="flex h-[34px] items-center gap-2 rounded-[10px] border border-line px-3.5 text-[13px] hover:bg-raised"
        >
          <X className="size-3.5" /> Cancel
        </button>
      </div>
    </div>
  )
}
