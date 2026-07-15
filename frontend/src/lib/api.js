const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export async function getJson(path, options) {
  const response = await fetch(`${apiBase}${path}`, options)
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : null
    throw new Error(detail ?? `Request failed (${response.status})`)
  }

  if (payload === null) {
    throw new Error('The server returned an empty response.')
  }

  return payload
}

export function humanizeMetric(metricName) {
  return metricName.replaceAll('_', ' ')
}

export function shortId(id) {
  return id?.slice(0, 8) ?? '—'
}

export function formatValue(value, maximumFractionDigits = 2) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits })
}
