import { ApiError, extractErrorDetail } from './client'
import type { ChatEvent, ChatRequest, Citation } from './types'

export interface ChatStreamHandlers {
  onEvent?: (event: ChatEvent) => void
  onMeta?: (data: { conversation_id: number; user_message_id: number; query: string }) => void
  onCitations?: (data: { citations: Citation[] }) => void
  onToken?: (data: { text: string }) => void
  onDone?: (data: { assistant_message_id: number; citations: Citation[] }) => void
  onError?: (data: { detail: string }) => void
}

function isAbortError(err: unknown, signal?: AbortSignal): boolean {
  if (signal?.aborted) return true
  return err instanceof DOMException && err.name === 'AbortError'
}

/**
 * Stream a RAG chat answer from POST /api/chat using fetch + ReadableStream.
 * Parses SSE frames (event: / data:, CRLF or LF separated, across arbitrary chunk boundaries)
 * and dispatches typed ChatEvents. Resolves cleanly on user abort.
 */
export async function streamChat(
  req: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(req),
      signal,
    })
  } catch (err) {
    if (isAbortError(err, signal)) return
    throw err
  }

  if (!res.ok) {
    const detail = await extractErrorDetail(res)
    throw new ApiError(res.status, detail)
  }

  if (!res.body) {
    throw new ApiError(500, 'Empty response stream from server')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let currentEvent = 'message'
  let dataLines: string[] = []

  const dispatchFrame = () => {
    if (dataLines.length === 0) {
      currentEvent = 'message'
      return
    }
    const rawData = dataLines.join('\n')
    const eventName = currentEvent
    currentEvent = 'message'
    dataLines = []

    let parsed: unknown
    try {
      parsed = JSON.parse(rawData)
    } catch {
      return
    }

    switch (eventName) {
      case 'meta': {
        const data = parsed as { conversation_id: number; user_message_id: number; query: string }
        const ev: ChatEvent = { event: 'meta', data }
        handlers.onEvent?.(ev)
        handlers.onMeta?.(data)
        break
      }
      case 'citations': {
        const data = parsed as { citations: Citation[] }
        const ev: ChatEvent = { event: 'citations', data }
        handlers.onEvent?.(ev)
        handlers.onCitations?.(data)
        break
      }
      case 'token': {
        const data = parsed as { text: string }
        const ev: ChatEvent = { event: 'token', data }
        handlers.onEvent?.(ev)
        handlers.onToken?.(data)
        break
      }
      case 'done': {
        const data = parsed as { assistant_message_id: number; citations: Citation[] }
        const ev: ChatEvent = { event: 'done', data }
        handlers.onEvent?.(ev)
        handlers.onDone?.(data)
        break
      }
      case 'error': {
        const data = parsed as { detail: string }
        const ev: ChatEvent = { event: 'error', data }
        handlers.onEvent?.(ev)
        handlers.onError?.(data)
        break
      }
      default:
        break
    }
  }

  const processLine = (rawLine: string) => {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
    if (line === '') {
      dispatchFrame()
      return
    }
    if (line.startsWith(':')) {
      return
    }
    const colonIdx = line.indexOf(':')
    const field = colonIdx === -1 ? line : line.slice(0, colonIdx)
    let value = colonIdx === -1 ? '' : line.slice(colonIdx + 1)
    if (value.startsWith(' ')) {
      value = value.slice(1)
    }

    if (field === 'event') {
      currentEvent = value.trim()
    } else if (field === 'data') {
      dataLines.push(value)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        break
      }
      buffer += decoder.decode(value, { stream: true })

      let newlineIdx = buffer.indexOf('\n')
      while (newlineIdx !== -1) {
        const line = buffer.slice(0, newlineIdx)
        buffer = buffer.slice(newlineIdx + 1)
        processLine(line)
        newlineIdx = buffer.indexOf('\n')
      }
    }

    if (buffer.length > 0) {
      processLine(buffer)
    }
    dispatchFrame()
  } catch (err) {
    if (isAbortError(err, signal)) return
    throw err
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // Ignore lock release errors on already closed streams
    }
  }
}
