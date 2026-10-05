import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { apiClient, unwrap } from '@/lib/api-client'
import type { components } from '@/lib/api-schema'

export type Lorebook = components['schemas']['LorebookOut']
export type LorebookDetail = components['schemas']['LorebookDetailOut']
export type LorebookEntry = components['schemas']['LorebookEntryOut']
export type LorebookEntryDetail =
  components['schemas']['LorebookEntryDetailOut']
export type LorebookCard = components['schemas']['LorebookCardOut']

/** Every distinct lorebook, whole. A few hundred rows even on the full
 *  archive, so filtering and sorting happen client-side over one response. */
export function useLorebooks() {
  return useQuery({
    queryKey: ['lorebooks'],
    queryFn: () =>
      unwrap(apiClient.GET('/api/v1/lorebooks'), 'could not load lorebooks'),
  })
}

export function useLorebook(id: string) {
  return useQuery({
    queryKey: ['lorebook', id],
    queryFn: () =>
      unwrap(
        apiClient.GET('/api/v1/lorebooks/{lorebook_id}', {
          params: { path: { lorebook_id: id } },
        }),
        'could not load the lorebook',
      ),
  })
}

export type EntryQuery = {
  q: string
  changed: boolean
  unresolved: boolean
  sort: 'versions' | 'cards' | 'title'
  limit: number
}

/** Entries are the one lorebook list too long to send whole (~10k lines), so
 *  search and the changed-only filter run server-side. */
export function useLorebookEntries(query: EntryQuery) {
  return useQuery({
    queryKey: ['lorebook-entries', query],
    queryFn: () =>
      unwrap(
        apiClient.GET('/api/v1/lorebooks/entries', {
          params: { query },
        }),
        'could not load lorebook entries',
      ),
    placeholderData: keepPreviousData,
  })
}

export function useLorebookEntry(id: string) {
  return useQuery({
    queryKey: ['lorebook-entry', id],
    queryFn: () =>
      unwrap(
        apiClient.GET('/api/v1/lorebooks/entries/{entry_id}', {
          params: { path: { entry_id: id } },
        }),
        'could not load the entry',
      ),
  })
}

const FAMILY = ['lorebooks', 'lorebook', 'lorebook-entries', 'lorebook-entry']

function useAction<A, R>(run: (args: A) => Promise<R>) {
  const client = useQueryClient()
  return useMutation<R, Error, A>({
    mutationFn: run,
    onSuccess: () =>
      Promise.all(
        FAMILY.map((key) => client.invalidateQueries({ queryKey: [key] })),
      ),
  })
}

/** For the DELETEs that answer 204: there is no body to unwrap. */
async function done(call: Promise<{ response: Response }>, what: string) {
  const { response } = await call
  if (!response.ok)
    throw new Error(`${what}: ${response.status} ${response.statusText}`)
}

/**
 * The lorebook decisions: choose a version, merge two entries or two
 * lorebooks, and the undo of each.
 *
 * None of them writes to a card -- they are recorded server-side
 * (`data/lorebooks.json`) and change what these pages report. Every one moves
 * counts on every lorebook view at once (a merge even changes ids), so they
 * all invalidate the whole family rather than patching caches.
 */
export function useLorebookActions() {
  return {
    choose: useAction(({ entry, hash }: { entry: string; hash: string }) =>
      unwrap(
        apiClient.PUT('/api/v1/lorebooks/entries/{entry_id}/chosen', {
          params: { path: { entry_id: entry } },
          body: { hash },
        }),
        'could not choose the version',
      ),
    ),
    clearChoice: useAction((entry: string) =>
      unwrap(
        apiClient.DELETE('/api/v1/lorebooks/entries/{entry_id}/chosen', {
          params: { path: { entry_id: entry } },
        }),
        'could not clear the choice',
      ),
    ),
    chooseNewest: useAction((lorebook: string) =>
      unwrap(
        apiClient.POST('/api/v1/lorebooks/{lorebook_id}/choose-newest', {
          params: { path: { lorebook_id: lorebook } },
        }),
        'could not choose the newest versions',
      ),
    ),
    mergeEntries: useAction(
      ({ entry, into }: { entry: string; into: string }) =>
        unwrap(
          apiClient.POST('/api/v1/lorebooks/entries/{entry_id}/merge', {
            params: { path: { entry_id: entry } },
            body: { into },
          }),
          'could not merge the entries',
        ),
    ),
    unmergeEntries: useAction((merge: string) =>
      done(
        apiClient.DELETE('/api/v1/lorebooks/entries/merges/{merge_id}', {
          params: { path: { merge_id: merge } },
        }),
        'could not undo the merge',
      ),
    ),
    mergeLorebooks: useAction(
      ({ lorebook, into }: { lorebook: string; into: string }) =>
        unwrap(
          apiClient.POST('/api/v1/lorebooks/{lorebook_id}/merge', {
            params: { path: { lorebook_id: lorebook } },
            body: { into },
          }),
          'could not merge the lorebooks',
        ),
    ),
    unmergeLorebooks: useAction((merge: string) =>
      done(
        apiClient.DELETE('/api/v1/lorebooks/merges/{merge_id}', {
          params: { path: { merge_id: merge } },
        }),
        'could not undo the merge',
      ),
    ),
  }
}
