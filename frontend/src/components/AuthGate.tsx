import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useLogin, useSession } from '@/hooks/use-auth'
import { UNAUTHORIZED_EVENT } from '@/lib/api-client'

/**
 * The login gate's client half: the app, or the login screen in its place.
 *
 * The gate is off unless Settings → Security turned it on, and then it is the
 * *server* that enforces it — every API route answers 401 without a session.
 * This component only decides what to show: it never hides data the browser
 * already has, it just declines to mount an app whose every request would
 * fail.
 *
 * It wraps the router rather than being a route, so there is no `/login`
 * address: the URL stays whatever was asked for, and logging in lands there.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const session = useSession()
  const qc = useQueryClient()

  // A 401 mid-session — the cookie expired, or the password was changed from
  // another browser. Re-asking the session flips this to the login screen.
  useEffect(() => {
    const recheck = () =>
      void qc.invalidateQueries({ queryKey: ['auth-session'] })
    window.addEventListener(UNAUTHORIZED_EVENT, recheck)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, recheck)
  }, [qc])

  if (session.isPending) return null
  // An unreachable server is not a locked one: let the app mount and report
  // the failure the way it reports any other.
  if (session.data?.enabled && !session.data.authenticated) {
    return <LoginScreen />
  }
  return children
}

function LoginScreen() {
  const login = useLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    login.mutate({ username, password })
  }

  const field =
    'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-text outline-none focus:border-sage'

  return (
    <div className="flex min-h-dvh items-center justify-center bg-ground px-5">
      <form
        onSubmit={submit}
        className="flex w-full max-w-[340px] flex-col gap-4 rounded-2xl border border-line bg-surface p-6"
      >
        <h1 className="font-serif text-[23px] font-normal">Log in</h1>
        <label className="flex flex-col gap-1.5 text-[12.5px] text-muted">
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-[12.5px] text-muted">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className={field}
          />
        </label>
        {login.isError && (
          <p role="alert" className="text-[12.5px] text-bad">
            {login.error.message}
          </p>
        )}
        <button
          type="submit"
          disabled={login.isPending || !username || !password}
          className="h-9 rounded-lg border border-sage-line bg-sage-dim text-[13.5px] text-sage hover:bg-sage-dim/70 disabled:opacity-50"
        >
          Log in
        </button>
      </form>
    </div>
  )
}
