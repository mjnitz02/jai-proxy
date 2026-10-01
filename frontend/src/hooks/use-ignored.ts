import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '@/lib/api-client'
import type { Provider } from '@/lib/discover-state'

/**
 * Provider cards marked "don't want" — Discover's second hide list.
 *
 * The exact peer of `useHaveFragments`, and shaped like it on purpose: the
 * whole list is fetched once and matched locally, rather than asking the server
 * about the ids loaded so far on every scroll tick (see that hook's docstring
 * for what the per-id version cost).
 *
 * The two lists stay separate here although `DiscoverPage` concatenates them at
 * its filter. Merging them server-side into the fragment set would hide the
 * same cards for free, and would also make a tile you do not own badge itself
 * "Have" and the result count claim it is in the archive.
 *
 * Matching is on the provider's own id, not the `_<id8>` fragment the archive
 * files cards under: there is no file here, we are holding the provider id
 * already, and a whole-id match never has to wonder whether two cards sharing
 * eight characters are the same card.
 */
export function useIgnoredIds() {
  return useQuery({
    queryKey: ['discover-ignored'],
    queryFn: () =>
      unwrap(
        apiClient.GET('/api/v1/discover/ignored', {}),
        'could not read the ignore list',
      ),
    // The list only changes when this app writes it, and the write updates the
    // cache directly -- so this is the page-load read, like the settings blob.
    staleTime: 60_000,
    select: (data) =>
      new Map<string, Set<string>>(
        Object.entries(data.ignored ?? {}).map(([provider, ids]) => [
          provider,
          new Set(ids),
        ]),
      ),
  })
}

/**
 * Mark a batch of provider cards "don't want".
 *
 * Append-only by design — there is no un-ignore, because turning "Hide cards I
 * have" off shows every ignored card again and acquiring one makes it a card
 * you have, at which point its entry is inert (both lists feed one filter).
 *
 * The response carries the provider's whole bucket after the write, so the
 * cache is updated from it rather than invalidated: the grid re-filters on the
 * same tick the toast appears, with no round trip in between for the ignored
 * cards to linger through.
 */
export function useIgnoreCards() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, ids }: { provider: Provider; ids: string[] }) =>
      unwrap(
        apiClient.POST('/api/v1/discover/ignored', { body: { provider, ids } }),
        'could not save the ignore list',
      ),
    onSuccess: (result) => {
      client.setQueryData<{ ignored: Record<string, string[]> }>(
        ['discover-ignored'],
        (current) => ({
          ignored: { ...(current?.ignored ?? {}), [result.provider]: result.ids },
        }),
      )
    },
  })
}
