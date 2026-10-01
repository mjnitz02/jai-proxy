import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import { server } from '@/test/msw-server'
import { renderApp } from '@/test/render'
import { DiscoverPage } from './DiscoverPage'

/**
 * Discover's two hide lists.
 *
 * The thing worth testing is not that an id can be stored -- `tests/state/
 * test_ignored.py` covers the store -- it is that the grid treats the ignore
 * list exactly like the archive's own fragment set while still telling the two
 * apart. Those two requirements pull against each other, and the bug they
 * guard is a card badged "Have" that is not in the archive.
 */

const NODES = [
  { id: 412233, fullPath: 'kornypony/abbie', name: 'Abbie', topics: ['Female'] },
  { id: 891020, fullPath: 'someone/bella', name: 'Bella', topics: ['Female'] },
]

const chubSearch = http.get('*//api.chub.ai/search', () =>
  HttpResponse.json({ nodes: NODES }),
)

/** The archive holds nothing, so "hidden" can only come from the ignore list. */
const emptyArchive = http.get('*/api/v1/characters/have-fragments', () =>
  HttpResponse.json({ fragments: [] }),
)

const settings = http.get('*/api/v1/settings', () => HttpResponse.json({}))

function ignoredList(ignored: Record<string, string[]>) {
  return http.get('*/api/v1/discover/ignored', () =>
    HttpResponse.json({ ignored }),
  )
}

beforeEach(() => {
  server.use(chubSearch, emptyArchive, settings)
})

describe('the ignore list as a hide filter', () => {
  it('hides an ignored card when “Hide cards I have” is on', async () => {
    server.use(ignoredList({ chub: ['412233'] }))
    renderApp(<DiscoverPage />, { route: '/discover?have=0' })

    await waitFor(() => expect(screen.getByText('Bella')).toBeInTheDocument())
    // The card is not in the archive at all -- only the ignore list hides it,
    // which is the whole point of concatenating the two sets.
    expect(screen.queryByText('Abbie')).not.toBeInTheDocument()
  })

  it('shows an ignored card, badged, when the toggle is off', async () => {
    server.use(ignoredList({ chub: ['412233'] }))
    renderApp(<DiscoverPage />, { route: '/discover' })

    await waitFor(() => expect(screen.getByText('Abbie')).toBeInTheDocument())
    // Turning the toggle off *is* the un-ignore, so the card has to come back
    // -- and say why it would otherwise be missing.
    expect(screen.getByText('Ignored')).toBeInTheDocument()
    expect(screen.queryByText('Have')).not.toBeInTheDocument()
  })

  it('counts the two lists separately', async () => {
    server.use(ignoredList({ chub: ['412233', '891020'] }))
    renderApp(<DiscoverPage />, { route: '/discover' })

    await waitFor(() =>
      expect(screen.getByText(/2 ignored/)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/already in the archive/)).not.toBeInTheDocument()
  })

  it('keeps the list per provider', async () => {
    // The same id ignored on DataCat says nothing about the Chub card.
    server.use(ignoredList({ datacat: ['412233'] }))
    renderApp(<DiscoverPage />, { route: '/discover?have=0' })

    await waitFor(() => expect(screen.getByText('Abbie')).toBeInTheDocument())
  })

  it('does not badge an ignored card “Have”', async () => {
    // The regression this whole separation exists to prevent: folding ignores
    // into the fragment set would hide the right cards and lie about why.
    server.use(ignoredList({ chub: ['412233'] }))
    renderApp(<DiscoverPage />, { route: '/discover' })

    await waitFor(() => expect(screen.getByText('Ignored')).toBeInTheDocument())
    expect(screen.queryByText('Add again')).not.toBeInTheDocument()
  })
})

describe('marking cards ignored', () => {
  it('posts the selected provider ids and hides them', async () => {
    const posted: unknown[] = []
    server.use(
      ignoredList({}),
      http.post('*/api/v1/discover/ignored', async ({ request }) => {
        const body = (await request.json()) as {
          provider: string
          ids: string[]
        }
        posted.push(body)
        return HttpResponse.json({
          provider: body.provider,
          added: body.ids.length,
          ids: body.ids,
        })
      }),
    )

    const user = userEvent.setup()
    // `?have=0` so the effect of the write is visible in the grid itself.
    const { container } = renderApp(<DiscoverPage />, {
      route: '/discover?have=0',
    })
    await waitFor(() => expect(screen.getByText('Abbie')).toBeInTheDocument())

    // The page's own control, not the top bar's icon: Discover is where every
    // other filter for this grid lives, and the icon was missable enough that
    // it read as the feature being absent.
    await user.click(screen.getByRole('button', { name: 'Select to ignore' }))

    await user.click(screen.getByText('Abbie'))
    expect(screen.getByText('1 selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Ignore$/ }))

    await waitFor(() =>
      expect(posted).toEqual([{ provider: 'chub', ids: ['412233'] }]),
    )
    // The response carries the whole bucket back, so the grid re-filters off
    // the cache rather than waiting on a refetch.
    await waitFor(() =>
      expect(screen.queryByText('Abbie')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Bella')).toBeInTheDocument()
    // Batch mode exits on success; nothing is left selected.
    expect(container.querySelector('.ring-sage')).toBeNull()
  })
})
