import { onBeforeUnmount } from 'vue'
import { api } from '../../api/client'

export const POLICY_DOCUMENT_KEY = Symbol('policyDocument')

export function usePolicyDocument(getClaimId) {
  let cache = null

  function release() {
    const current = cache
    cache = null
    current?.promise.then((doc) => URL.revokeObjectURL(doc.url)).catch(() => {})
  }

  function load() {
    const claimId = getClaimId()
    if (cache && cache.claimId !== claimId) release()
    if (!cache) {
      const promise = api.claimPolicyDocument(claimId)
      const entry = { claimId, promise }
      cache = entry
      promise.catch(() => {
        if (cache === entry) cache = null
      })
    }
    return cache.promise
  }

  // Opens the tab synchronously inside the click so popup blockers allow it.
  async function open(page) {
    const win = window.open('', '_blank')
    try {
      const { url } = await load()
      const target = url + (page ? `#page=${page}` : '')
      if (win && !win.closed) {
        win.location.href = target
      } else {
        const link = document.createElement('a')
        link.href = target
        link.target = '_blank'
        link.rel = 'noopener'
        document.body.appendChild(link)
        link.click()
        link.remove()
      }
      return true
    } catch {
      win?.close()
      return false
    }
  }

  onBeforeUnmount(release)

  return { open }
}
