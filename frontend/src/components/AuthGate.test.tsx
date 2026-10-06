import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '@/test/msw-server'
import { renderApp } from '@/test/render'
import { apiClient } from '@/lib/api-client'
import { AuthGate } from './AuthGate'

const session = (enabled: boolean, authenticated: boolean) =>
  http.get('*/api/v1/auth/session', () =>
    HttpResponse.json({ enabled, authenticated }),
  )

describe('AuthGate', () => {
  it('mounts the app untouched when the gate is off', async () => {
    server.use(session(false, true))
    renderApp(<AuthGate>the app</AuthGate>)
    expect(await screen.findByText('the app')).toBeInTheDocument()
  })

  it('shows the login screen instead of the app, and lets a login through', async () => {
    let posted: unknown
    server.use(
      session(true, false),
      http.post('*/api/v1/auth/login', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ enabled: true, authenticated: true })
      }),
    )
    renderApp(<AuthGate>the app</AuthGate>)

    await userEvent.type(await screen.findByLabelText('Username'), 'matt')
    expect(screen.queryByText('the app')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Password'), 'hunter2')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('the app')).toBeInTheDocument()
    expect(posted).toEqual({ username: 'matt', password: 'hunter2' })
  })

  it('reports a wrong password and stays on the login screen', async () => {
    server.use(
      session(true, false),
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 }),
      ),
    )
    renderApp(<AuthGate>the app</AuthGate>)

    await userEvent.type(await screen.findByLabelText('Username'), 'matt')
    await userEvent.type(screen.getByLabelText('Password'), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Invalid credentials',
    )
    expect(screen.queryByText('the app')).not.toBeInTheDocument()
  })

  it('falls back to the login screen when a request comes back 401', async () => {
    let live = true
    server.use(
      http.get('*/api/v1/auth/session', () =>
        HttpResponse.json({ enabled: true, authenticated: live }),
      ),
      http.get('*/api/v1/stats', () =>
        HttpResponse.json({ detail: 'login required' }, { status: 401 }),
      ),
    )
    renderApp(<AuthGate>the app</AuthGate>)
    expect(await screen.findByText('the app')).toBeInTheDocument()

    live = false
    await apiClient.GET('/api/v1/stats')

    await waitFor(() =>
      expect(screen.getByLabelText('Username')).toBeInTheDocument(),
    )
  })
})
