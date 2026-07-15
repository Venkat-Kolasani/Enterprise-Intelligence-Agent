import { useCallback, useEffect, useState } from 'react'
import { getJson } from '../lib/api'

export function useExecutiveData() {
  const [status, setStatus] = useState(null)
  const [metrics, setMetrics] = useState([])
  const [signals, setSignals] = useState([])
  const [insights, setInsights] = useState([])
  const [latestBriefing, setLatestBriefing] = useState(null)
  const [briefingResult, setBriefingResult] = useState(null)
  const [chatResult, setChatResult] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState({})

  const refresh = useCallback(async () => {
    const requests = await Promise.allSettled([
      getJson('/agent/status'),
      getJson('/metrics/live'),
      getJson('/signals'),
      getJson('/insights'),
      getJson('/briefings/latest'),
    ])

    const [statusResult, metricsResult, signalsResult, insightsResult, briefingResult] = requests
    const nextErrors = {}

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value)
    } else {
      nextErrors.connection = statusResult.reason.message
    }

    if (metricsResult.status === 'fulfilled') {
      setMetrics(metricsResult.value.metrics)
    } else {
      nextErrors.connection ??= metricsResult.reason.message
    }

    if (signalsResult.status === 'fulfilled') {
      setSignals(signalsResult.value.signals)
    } else {
      nextErrors.evidence = signalsResult.reason.message
    }

    if (insightsResult.status === 'fulfilled') {
      setInsights(insightsResult.value.insights)
    } else {
      nextErrors.decisions = insightsResult.reason.message
    }

    if (briefingResult.status === 'fulfilled') {
      setLatestBriefing(briefingResult.value.briefing)
    } else {
      nextErrors.executive = briefingResult.reason.message
    }

    setErrors(nextErrors)
  }, [])

  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 1_000)
    return () => window.clearInterval(interval)
  }, [refresh])

  async function run(taskName, task, errorKey) {
    setBusy((current) => ({ ...current, [taskName]: true }))
    try {
      const result = await task()
      setErrors((current) => ({ ...current, [errorKey]: undefined }))
      return result
    } catch (requestError) {
      setErrors((current) => ({ ...current, [errorKey]: requestError.message }))
      return null
    } finally {
      setBusy((current) => ({ ...current, [taskName]: false }))
    }
  }

  async function startSimulation() {
    const result = await run('simulation', () => getJson('/simulation/start', { method: 'POST' }), 'connection')
    if (result) await refresh()
  }

  async function runSignalAnalysis() {
    const result = await run('analysis', () => getJson('/signals/run', { method: 'POST' }), 'evidence')
    if (result) {
      setSignals(result.signals)
      await refresh()
    }
  }

  async function generateInsight() {
    const result = await run('insight', () => getJson('/insights/generate', { method: 'POST' }), 'decisions')
    if (result) await refresh()
  }

  async function updateRecommendationStatus(recommendationId, lifecycleStatus) {
    const result = await run(
      `status-${recommendationId}`,
      () => getJson(`/recommendations/${recommendationId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: lifecycleStatus }),
      }),
      'decisions',
    )
    if (result) await refresh()
  }

  async function recordOutcome(recommendationId, draft) {
    const result = await run(
      `outcome-${recommendationId}`,
      () => getJson(`/recommendations/${recommendationId}/outcomes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          implemented_at: new Date().toISOString(),
          outcome_metric: draft.metric,
          outcome_value: Number(draft.value),
          measured_at: new Date().toISOString(),
          notes: draft.notes,
        }),
      }),
      'decisions',
    )
    if (result) await refresh()
  }

  async function generateBriefing() {
    const result = await run('briefing', () => getJson('/briefings/generate', { method: 'POST' }), 'executive')
    if (result) setBriefingResult(result)
  }

  async function askGroundedQuestion(question) {
    const result = await run(
      'chat',
      () => getJson('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          prior_insight_ids: chatResult?.insight_ids ?? [],
        }),
      }),
      'executive',
    )
    if (result) setChatResult(result)
  }

  async function generateForecast(inputChangePercent, horizonDays) {
    const result = await run(
      'forecast',
      () => getJson('/scenarios/forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_metric: 'marketing_spend',
          input_change_percent: Number(inputChangePercent),
          horizon_days: Number(horizonDays),
        }),
      }),
      'executive',
    )
    if (result) setForecast(result.forecast)
  }

  return {
    status,
    metrics,
    signals,
    insights,
    latestBriefing,
    briefingResult,
    chatResult,
    forecast,
    errors,
    busy,
    isRunning: status?.simulation_state === 'running',
    coldBlocked: Boolean(status?.last_cold_error),
    readOnlyDemo: status?.demo_access === 'read_only',
    startSimulation,
    runSignalAnalysis,
    generateInsight,
    updateRecommendationStatus,
    recordOutcome,
    generateBriefing,
    askGroundedQuestion,
    generateForecast,
  }
}
