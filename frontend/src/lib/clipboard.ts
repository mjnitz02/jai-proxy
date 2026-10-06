/**
 * Put text on the clipboard, and say whether it got there.
 *
 * `navigator.clipboard` only exists in a secure context, and the archive is
 * usually reached over plain http on a LAN address — where it is `undefined`,
 * so a bare `navigator.clipboard.writeText(...)` throws and the button does
 * nothing. `localhost` counts as secure, which is why that never shows up in
 * development. The fallback is the old selection-based copy, which works
 * anywhere as long as it runs inside the click that asked for it.
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Permission denied or the document lost focus — try the other way.
    }
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  // Off-screen but still selectable; `display: none` would not be.
  area.style.position = 'fixed'
  area.style.top = '0'
  area.style.left = '-9999px'
  document.body.appendChild(area)
  area.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    area.remove()
  }
}
