import {
  Children,
  Fragment,
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import Markdown, { type Components } from 'react-markdown'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { streamChat } from '../api/chatStream'
import { ApiError } from '../api/client'
import {
  queryKeys,
  useConfig,
  useConversation,
  useConversations,
  useDeleteConversation,
  useIndexStats,
  usePatchConversation,
} from '../api/hooks'
import type { Citation, Conversation, Message, Scope } from '../api/types'
import { CitationMarker } from '../components/CitationMarker'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import {
  IconChat,
  IconCheck,
  IconChevronDown,
  IconClose,
  IconEdit,
  IconPlus,
  IconStop,
  IconTrash,
} from '../components/Icons'
import { useTopbarSlot } from '../components/topbarSlot'
import { IndexStrip } from '../components/IndexStrip'
import { LibraryBrief } from '../components/LibraryBrief'
import { ReferenceList } from '../components/ReferenceList'
import { Skeleton } from '../components/Spinner'
import { fmtNumber, fmtRelativeDate } from '../utils/format'
import './ChatPage.css'

interface StreamState {
  streamKey: string
  originConvId: number | null
  resolvedConvId: number | null
  userMessageId: number | null
  userContent: string
  assistantContent: string
  citations: Citation[]
  phase: 'streaming' | 'syncing' | 'error'
  errorDetail: string | null
  scope: Scope
}

interface TurnPair {
  key: string
  userMessage: { id?: number; content: string } | null
  assistantMessage: {
    id?: number
    content: string
    citations: Citation[]
    streaming?: boolean
    errorDetail?: string | null
  } | null
}

function normalizeMultiBrackets(text: string): string {
  return text.replace(/\[(\d+(?:\s*,\s*\d+)+)\]/g, (_match, nums: string) =>
    nums
      .split(',')
      .map((part) => `[${part.trim()}]`)
      .join(''),
  )
}

interface AnswerMarkdownProps {
  content: string
  citations: readonly Citation[]
  activeN: number | null
  onActivateCitation: (n: number | null) => void
  onSelectCitation: (n: number, citation?: Citation) => void
}

function AnswerMarkdown({
  content,
  citations,
  activeN,
  onActivateCitation,
  onSelectCitation,
}: AnswerMarkdownProps) {
  const citationMap = useMemo(() => {
    const map = new Map<number, Citation>()
    for (const c of citations) {
      map.set(c.n, c)
    }
    return map
  }, [citations])

  const injectMarkers = useCallback(
    function inject(nodes: ReactNode): ReactNode {
      return Children.map(nodes, (child, idx) => {
        if (typeof child === 'string') {
          const parts = child.split(/\[(\d+)\]/g)
          if (parts.length === 1) return child
          return (
            <Fragment key={idx}>
              {parts.map((part, partIdx) => {
                if (partIdx % 2 === 1) {
                  const n = Number(part)
                  const cit = citationMap.get(n)
                  return (
                    <CitationMarker
                      key={`cite-${idx}-${partIdx}-${n}`}
                      n={n}
                      citation={cit}
                      active={activeN === n}
                      onActivate={onActivateCitation}
                      onSelect={onSelectCitation}
                    />
                  )
                }
                return part
              })}
            </Fragment>
          )
        }
        if (
          isValidElement<{ children?: ReactNode }>(child) &&
          child.props.children !== undefined &&
          child.type !== 'code' &&
          child.type !== 'pre'
        ) {
          const el = child as ReactElement<{ children?: ReactNode }>
          return cloneElement(el, undefined, inject(el.props.children))
        }
        return child
      })
    },
    [activeN, citationMap, onActivateCitation, onSelectCitation],
  )

  const components = useMemo<Components>(
    () => ({
      p: ({ children }) => <p>{injectMarkers(children)}</p>,
      li: ({ children }) => <li>{injectMarkers(children)}</li>,
      blockquote: ({ children }) => <blockquote>{injectMarkers(children)}</blockquote>,
      td: ({ children }) => <td>{injectMarkers(children)}</td>,
    }),
    [injectMarkers],
  )

  const normalized = useMemo(() => normalizeMultiBrackets(content), [content])

  return (
    <div className="chat-answer-prose">
      <Markdown components={components}>{normalized}</Markdown>
    </div>
  )
}

function pairMessages(messages: readonly Message[]): TurnPair[] {
  const turns: TurnPair[] = []
  for (const msg of messages) {
    if (msg.role === 'user') {
      turns.push({
        key: `turn-u-${msg.id}`,
        userMessage: { id: msg.id, content: msg.content },
        assistantMessage: null,
      })
    } else {
      const last = turns[turns.length - 1]
      if (last && last.assistantMessage === null) {
        last.key = `turn-${last.userMessage?.id ?? 'x'}-${msg.id}`
        last.assistantMessage = {
          id: msg.id,
          content: msg.content,
          citations: msg.citations,
        }
      } else {
        turns.push({
          key: `turn-a-${msg.id}`,
          userMessage: null,
          assistantMessage: {
            id: msg.id,
            content: msg.content,
            citations: msg.citations,
          },
        })
      }
    }
  }
  return turns
}

export function ChatPage() {
  const { conversationId: rawConvId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const parsedId = rawConvId !== undefined ? Number(rawConvId) : null
  const activeConvId =
    parsedId !== null && Number.isFinite(parsedId) && parsedId > 0 ? parsedId : null
  const invalidConvParam = rawConvId !== undefined && activeConvId === null

  const { data: stats, isLoading: statsLoading } = useIndexStats()
  const { data: config } = useConfig()
  const { data: conversations, isLoading: convsLoading } = useConversations()
  const {
    data: convDetail,
    isLoading: convDetailLoading,
    error: convDetailError,
    refetch: refetchConvDetail,
  } = useConversation(activeConvId)

  const patchConv = usePatchConversation()
  const deleteConv = useDeleteConversation()

  const [draftScope, setDraftScope] = useState<Scope>({ podcast_ids: null, episode_ids: null })
  const [composerText, setComposerText] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  // The app shell renders a top-bar slot; the Conversations menu is portalled into it.
  const topbarSlot = useTopbarSlot()

  // Inline rename & delete confirm state
  const [editingConvId, setEditingConvId] = useState<number | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [deletingConv, setDeletingConv] = useState<Conversation | null>(null)

  // Streaming state (persists across `/` -> `/c/:id` navigation because parent route stays mounted)
  const [stream, setStream] = useState<StreamState | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamCounterRef = useRef(1)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)

  // Auto-grow the composer (fallback for browsers without CSS field-sizing).
  useLayoutEffect(() => {
    const el = composerRef.current
    if (!el || CSS.supports('field-sizing', 'content')) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [composerText])
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  // Active citation synchronization between prose markers and References column
  const [activeCitation, setActiveCitation] = useState<{ turnKey: string; n: number } | null>(null)
  const [selectedTurnKey, setSelectedTurnKey] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawerOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  const effectiveScope: Scope = activeConvId !== null && convDetail ? convDetail.scope : draftScope

  const handleScopeChange = (next: Scope) => {
    setDraftScope(next)
    if (activeConvId !== null) {
      patchConv.mutate({ id: activeConvId, patch: { scope: next } })
    }
  }

  const isStreamVisibleHere =
    stream !== null &&
    ((activeConvId === null && stream.originConvId === null && stream.resolvedConvId === null) ||
      (activeConvId !== null &&
        (stream.resolvedConvId === activeConvId || stream.originConvId === activeConvId)))

  const isStreamingNow =
    stream !== null && (stream.phase === 'streaming' || stream.phase === 'syncing')

  const turns = useMemo<TurnPair[]>(() => {
    const baseMessages = activeConvId !== null && convDetail ? convDetail.messages : []
    const paired = pairMessages(baseMessages)

    if (!isStreamVisibleHere || !stream) {
      return paired
    }

    // Check if the persisted user message from `meta` is already in convDetail.messages
    const existingTurnWithUser =
      stream.userMessageId !== null
        ? paired.find(
            (t) => t.userMessage?.id === stream.userMessageId && t.assistantMessage === null,
          )
        : undefined

    if (existingTurnWithUser) {
      existingTurnWithUser.key = stream.streamKey
      existingTurnWithUser.assistantMessage = {
        content: stream.assistantContent,
        citations: stream.citations,
        streaming: stream.phase === 'streaming' || stream.phase === 'syncing',
        errorDetail: stream.errorDetail,
      }
      return paired
    }

    // Avoid duplicating if the completed assistant turn already arrived in convDetail
    if (stream.phase === 'syncing' && paired.length > 0) {
      const last = paired[paired.length - 1]
      if (last && last.userMessage?.content === stream.userContent && last.assistantMessage) {
        return paired
      }
    }

    return [
      ...paired,
      {
        key: stream.streamKey,
        userMessage: { content: stream.userContent },
        assistantMessage: {
          content: stream.assistantContent,
          citations: stream.citations,
          streaming: stream.phase === 'streaming' || stream.phase === 'syncing',
          errorDetail: stream.errorDetail,
        },
      },
    ]
  }, [activeConvId, convDetail, isStreamVisibleHere, stream])

  // Determine which turn drives the desktop References aside
  const activeRefsTurn = useMemo<TurnPair | null>(() => {
    const withAssistant = turns.filter((t) => t.assistantMessage !== null)
    if (withAssistant.length === 0) return null
    if (activeCitation) {
      const match = withAssistant.find((t) => t.key === activeCitation.turnKey)
      if (match) return match
    }
    if (isStreamVisibleHere && stream) {
      const streamTurn = withAssistant.find((t) => t.key === stream.streamKey)
      if (streamTurn) return streamTurn
    }
    if (selectedTurnKey) {
      const chosen = withAssistant.find((t) => t.key === selectedTurnKey)
      if (chosen) return chosen
    }
    return withAssistant[withAssistant.length - 1] ?? null
  }, [activeCitation, isStreamVisibleHere, selectedTurnKey, stream, turns])

  const sendQuestion = useCallback(
    async (rawMessage: string, targetConvId: number | null, scopeToUse: Scope) => {
      const trimmed = rawMessage.trim()
      if (!trimmed) return

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const streamKey = `live-turn-${streamCounterRef.current++}`
      setSelectedTurnKey(streamKey)
      setActiveCitation(null)

      setStream({
        streamKey,
        originConvId: targetConvId,
        resolvedConvId: targetConvId,
        userMessageId: null,
        userContent: trimmed,
        assistantContent: '',
        citations: [],
        phase: 'streaming',
        errorDetail: null,
        scope: scopeToUse,
      })

      // Per-request bookkeeping, mutated by the stream callbacks below.
      const run = { convId: targetConvId, hadError: false }

      try {
        await streamChat(
          {
            conversation_id: targetConvId,
            message: trimmed,
            scope: scopeToUse,
          },
          {
            onMeta: (data) => {
              run.convId = data.conversation_id
              setStream((prev) =>
                prev && prev.streamKey === streamKey
                  ? {
                      ...prev,
                      resolvedConvId: data.conversation_id,
                      userMessageId: data.user_message_id,
                    }
                  : prev,
              )
              void queryClient.invalidateQueries({ queryKey: queryKeys.conversations })
              if (targetConvId === null) {
                navigate(`/chat/${data.conversation_id}`, { replace: true })
              }
            },
            onCitations: (data) => {
              setStream((prev) =>
                prev && prev.streamKey === streamKey
                  ? { ...prev, citations: data.citations }
                  : prev,
              )
            },
            onToken: (data) => {
              setStream((prev) =>
                prev && prev.streamKey === streamKey
                  ? { ...prev, assistantContent: prev.assistantContent + data.text }
                  : prev,
              )
            },
            onDone: (data) => {
              setStream((prev) =>
                prev && prev.streamKey === streamKey
                  ? { ...prev, citations: data.citations, phase: 'syncing' }
                  : prev,
              )
            },
            onError: (data) => {
              run.hadError = true
              setStream((prev) =>
                prev && prev.streamKey === streamKey
                  ? { ...prev, phase: 'error', errorDetail: data.detail }
                  : prev,
              )
            },
          },
          controller.signal,
        )

        if (controller.signal.aborted) {
          if (run.convId !== null) {
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: queryKeys.conversation(run.convId) }),
              queryClient.invalidateQueries({ queryKey: queryKeys.conversations }),
            ])
          }
          setStream((prev) => (prev && prev.streamKey === streamKey ? null : prev))
          return
        }

        if (!run.hadError) {
          if (run.convId !== null) {
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: queryKeys.conversation(run.convId) }),
              queryClient.invalidateQueries({ queryKey: queryKeys.conversations }),
            ])
          }
          setStream((prev) =>
            prev && prev.streamKey === streamKey && prev.phase !== 'error' ? null : prev,
          )
        }
      } catch (err) {
        const detail =
          err instanceof ApiError
            ? err.detail
            : err instanceof Error
              ? err.message
              : 'Connection interrupted while streaming answer.'
        setStream((prev) =>
          prev && prev.streamKey === streamKey
            ? { ...prev, phase: 'error', errorDetail: detail }
            : prev,
        )
      }
    },
    [navigate, queryClient],
  )

  // A question handed over from the home page (/chat?q=...) is sent once on arrival.
  // Deferred so a remount (StrictMode, fast navigation) cancels the pending send instead of
  // aborting a stream that already started; the q param is consumed when it fires.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const q = searchParams.get('q')
    if (!q || activeConvId !== null) return
    const timer = window.setTimeout(() => {
      setSearchParams({}, { replace: true })
      void sendQuestion(q, null, draftScope)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [searchParams, setSearchParams, activeConvId, sendQuestion, draftScope])

  const handleComposerSubmit = (e?: FormEvent) => {
    e?.preventDefault()
    if (isStreamingNow) return
    const text = composerText.trim()
    if (!text) return
    if (stats && stats.episodes_indexed === 0) return

    setComposerText('')
    void sendQuestion(text, activeConvId, effectiveScope)
  }

  const handleComposerKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleComposerSubmit()
    }
  }

  const handleStopStream = () => {
    abortRef.current?.abort()
  }

  const handleNewChat = () => {
    if (isStreamingNow) {
      abortRef.current?.abort()
    }
    setStream(null)
    setActiveCitation(null)
    setSelectedTurnKey(null)
    setDrawerOpen(false)
    navigate('/chat')
    window.setTimeout(() => {
      composerRef.current?.focus()
    }, 0)
  }

  const startRename = (conv: Conversation) => {
    setEditingConvId(conv.id)
    setEditingTitle(conv.title)
  }

  const commitRename = (convId: number) => {
    const trimmed = editingTitle.trim()
    setEditingConvId(null)
    if (!trimmed) return
    patchConv.mutate({ id: convId, patch: { title: trimmed } })
  }

  const confirmDeleteConv = () => {
    if (!deletingConv) return
    const targetId = deletingConv.id
    deleteConv.mutate(targetId, {
      onSuccess: () => {
        setDeletingConv(null)
        if (activeConvId === targetId) {
          setStream(null)
          navigate('/chat')
        }
      },
    })
  }

  const handleSelectCitation = useCallback(
    (turnKey: string, n: number, citation?: Citation) => {
      setSelectedTurnKey(turnKey)
      setActiveCitation({ turnKey, n })
      if (citation) {
        navigate(`/episodes/${citation.episode_id}?t=${Math.max(0, Math.floor(citation.start))}`)
      }
    },
    [navigate],
  )

  useEffect(() => {
    if (stream?.phase === 'streaming') {
      transcriptEndRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [stream?.assistantContent, stream?.phase])

  const indexEmpty = Boolean(stats && stats.episodes_indexed === 0)
  const assistantTurnList = turns.filter((t) => t.assistantMessage !== null)

  return (
    <div className="chat-layout">
      {topbarSlot
        ? createPortal(
            <button
              type="button"
              className="chat-convs-trigger"
              aria-expanded={drawerOpen}
              aria-controls="chat-convs-panel"
              onClick={() => setDrawerOpen((open) => !open)}
            >
              <IconChat size={15} />
              <span className="chat-convs-trigger-label">Conversations</span>
              {conversations && conversations.length > 0 ? (
                <span className="chat-convs-trigger-count">
                  {fmtNumber(conversations.length)}
                </span>
              ) : null}
            </button>,
            topbarSlot,
          )
        : null}
      {drawerOpen ? (
        <div
          className="chat-drawer-backdrop"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      <aside
        id="chat-convs-panel"
        className={`chat-convs ${drawerOpen ? 'chat-convs--open' : ''}`.trim()}
        aria-label="Conversations"
        inert={!drawerOpen}
      >
        <div className="chat-convs-head">
          <h2 className="chat-panel-heading">Conversations</h2>
          <div className="chat-convs-head-actions">
            <button type="button" className="btn btn-sm" onClick={handleNewChat}>
              <IconPlus size={12} />
              <span>New</span>
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm chat-convs-close"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close conversations"
            >
              <IconClose size={13} />
            </button>
          </div>
        </div>

        {convsLoading && !conversations ? (
          <div className="chat-convs-skeletons">
            <Skeleton height="44px" />
            <Skeleton height="44px" />
            <Skeleton height="44px" />
          </div>
        ) : !conversations || conversations.length === 0 ? (
          <p className="chat-convs-empty">
            No conversations yet. Ask a question to save your first thread.
          </p>
        ) : (
          <ul className="chat-conv-list">
            {conversations.map((conv) => {
              const isCurrent = activeConvId === conv.id
              const isEditing = editingConvId === conv.id

              return (
                <li
                  key={conv.id}
                  className={`chat-conv-item ${isCurrent ? 'chat-conv-item--on' : ''}`.trim()}
                >
                  {isEditing ? (
                    <form
                      className="chat-conv-rename-form"
                      onSubmit={(e) => {
                        e.preventDefault()
                        commitRename(conv.id)
                      }}
                    >
                      <label htmlFor={`rename-conv-${conv.id}`} className="sr-only">
                        Conversation title
                      </label>
                      <input
                        id={`rename-conv-${conv.id}`}
                        type="text"
                        className="input input-sm chat-conv-rename-input"
                        value={editingTitle}
                        autoFocus
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') {
                            e.preventDefault()
                            setEditingConvId(null)
                          }
                        }}
                      />
                      <button
                        type="submit"
                        className="btn btn-ghost btn-sm"
                        aria-label="Save conversation title"
                      >
                        <IconCheck size={13} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEditingConvId(null)}
                        aria-label="Cancel rename"
                      >
                        <IconClose size={13} />
                      </button>
                    </form>
                  ) : (
                    <div className="chat-conv-row">
                      <Link
                        to={`/chat/${conv.id}`}
                        className="chat-conv-link"
                        onClick={() => {
                          setDrawerOpen(false)
                          setActiveCitation(null)
                          setSelectedTurnKey(null)
                        }}
                      >
                        <span className="chat-conv-title">{conv.title}</span>
                        <small className="chat-conv-meta">
                          {fmtRelativeDate(conv.updated_at)} · {fmtNumber(conv.message_count)}{' '}
                          {conv.message_count === 1 ? 'message' : 'messages'}
                        </small>
                      </Link>
                      <div className="chat-conv-actions">
                        <button
                          type="button"
                          className="chat-conv-icon-btn"
                          onClick={() => startRename(conv)}
                          aria-label={`Rename "${conv.title}"`}
                        >
                          <IconEdit size={13} />
                        </button>
                        <button
                          type="button"
                          className="chat-conv-icon-btn chat-conv-icon-btn--danger"
                          onClick={() => setDeletingConv(conv)}
                          aria-label={`Delete "${conv.title}"`}
                        >
                          <IconTrash size={13} />
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </aside>

      <main id="main-content" className="chat-main">
        <IndexStrip
          stats={stats}
          statsLoading={statsLoading}
          config={config}
          scope={effectiveScope}
          onScopeChange={handleScopeChange}
        />

        <div className="chat-transcript">
          {invalidConvParam ? (
            <ErrorBanner
              message="Invalid conversation address."
              recovery="Select an existing conversation from the list or start a new chat."
              onRetry={handleNewChat}
              retryLabel="New chat"
            />
          ) : convDetailError && !isStreamVisibleHere ? (
            <ErrorBanner
              message="Could not load conversation."
              recovery={
                convDetailError instanceof ApiError
                  ? convDetailError.detail
                  : 'Check that the conversation still exists.'
              }
              onRetry={() => void refetchConvDetail()}
            />
          ) : activeConvId !== null && convDetailLoading && !convDetail && !isStreamVisibleHere ? (
            <div className="chat-loading-turn">
              <Skeleton width="72%" height="26px" />
              <Skeleton width="100%" height="18px" />
              <Skeleton width="94%" height="18px" />
              <Skeleton width="68%" height="18px" />
            </div>
          ) : turns.length === 0 ? (
            indexEmpty ? (
              <div className="chat-empty-wrap">
                <EmptyState
                  title="Your podcast library is empty"
                  description="Build your library once in the Library tab: add an RSS feed, pick episodes, confirm the estimated cost, and let Recall download, diarize speakers, and index passages locally. Every future session opens straight into cited answers with no reprocessing."
                  action={
                    <Link to="/library" className="btn btn-primary">
                      Open Library to add episodes
                    </Link>
                  }
                />
              </div>
            ) : (
              <LibraryBrief
                stats={stats}
                onAskAbout={(ep) => {
                  handleScopeChange({ podcast_ids: null, episode_ids: [ep.id] })
                  composerRef.current?.focus()
                }}
              />
            )
          ) : (
            <div className="chat-turns">
              {turns.map((turn, idx) => {
                const isTurnActiveForRefs = activeRefsTurn?.key === turn.key
                const turnActiveN =
                  activeCitation && activeCitation.turnKey === turn.key ? activeCitation.n : null
                const assistant = turn.assistantMessage
                const isLastTurn = idx === turns.length - 1

                return (
                  <article
                    key={turn.key}
                    className="chat-turn"
                    onClick={() => {
                      if (assistant) {
                        setSelectedTurnKey(turn.key)
                      }
                    }}
                  >
                    {turn.userMessage ? (
                      <h2 className="chat-question">{turn.userMessage.content}</h2>
                    ) : null}

                    {assistant ? (
                      <div
                        className="chat-answer-region"
                        aria-live={assistant.streaming ? 'polite' : undefined}
                        aria-busy={assistant.streaming ? 'true' : undefined}
                      >
                        {assistant.streaming && !assistant.content && !assistant.errorDetail ? (
                          <div className="chat-answer-skeleton">
                            <Skeleton width="88%" height="18px" />
                            <Skeleton width="76%" height="18px" />
                            <Skeleton width="54%" height="18px" />
                          </div>
                        ) : assistant.content ? (
                          <AnswerMarkdown
                            content={assistant.content}
                            citations={assistant.citations}
                            activeN={turnActiveN}
                            onActivateCitation={(n) =>
                              setActiveCitation(n !== null ? { turnKey: turn.key, n } : null)
                            }
                            onSelectCitation={(n, cit) => handleSelectCitation(turn.key, n, cit)}
                          />
                        ) : null}

                        {assistant.errorDetail ? (
                          <div className="chat-turn-error">
                            <ErrorBanner
                              message="Answer stream failed."
                              recovery={assistant.errorDetail}
                              onRetry={
                                stream && turn.key === stream.streamKey
                                  ? () =>
                                      void sendQuestion(
                                        stream.userContent,
                                        stream.resolvedConvId ?? activeConvId,
                                        stream.scope,
                                      )
                                  : undefined
                              }
                              onDismiss={
                                stream && turn.key === stream.streamKey
                                  ? () => setStream(null)
                                  : undefined
                              }
                            />
                          </div>
                        ) : null}

                        {/* Inline collapsible references for viewports < 1200px */}
                        {assistant.citations.length > 0 || assistant.streaming ? (
                          <details
                            className="chat-inline-refs"
                            open={isLastTurn || isTurnActiveForRefs}
                          >
                            <summary className="chat-inline-refs-summary">
                              <span className="chat-inline-refs-chevron" aria-hidden="true">
                                <IconChevronDown size={12} />
                              </span>
                              References ({fmtNumber(assistant.citations.length)})
                            </summary>
                            <div className="chat-inline-refs-body">
                              <ReferenceList
                                citations={assistant.citations}
                                activeN={turnActiveN}
                                onActivate={(n) =>
                                  setActiveCitation(n !== null ? { turnKey: turn.key, n } : null)
                                }
                                streaming={assistant.streaming}
                                idPrefix={`inline-ref-${turn.key}`}
                              />
                            </div>
                          </details>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                )
              })}
              <div ref={transcriptEndRef} />
            </div>
          )}
        </div>

        <form className="chat-composer" onSubmit={handleComposerSubmit}>
          <div className="chat-composer-box">
            <label htmlFor="chat-composer-input" className="sr-only">
              Ask a question about your podcast library
            </label>
            <textarea
              id="chat-composer-input"
              ref={composerRef}
              className="chat-composer-textarea"
              rows={2}
              placeholder={
                indexEmpty
                  ? 'Index at least one episode in Library to start asking questions…'
                  : 'Ask about anything in your library…'
              }
              value={composerText}
              disabled={indexEmpty}
              onChange={(e) => setComposerText(e.target.value)}
              onKeyDown={handleComposerKeyDown}
            />
            <div className="chat-composer-controls">
              {indexEmpty ? (
                <span className="chat-composer-disabled-note">
                  No indexed episodes yet · <Link to="/library">Go to Library</Link>
                </span>
              ) : (
                <span className="chat-composer-hint">Enter to send · Shift+Enter for new line</span>
              )}

              {isStreamingNow ? (
                <button
                  type="button"
                  className="btn btn-danger chat-send-btn"
                  onClick={handleStopStream}
                >
                  <IconStop size={11} />
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  type="submit"
                  className="btn btn-primary chat-send-btn"
                  disabled={indexEmpty || !composerText.trim()}
                >
                  Send
                </button>
              )}
            </div>
          </div>
        </form>
      </main>

      <aside className="chat-refs" aria-label="References">
        <div className="chat-refs-head">
          <h2 className="chat-panel-heading">References</h2>
          {assistantTurnList.length > 1 && !isStreamingNow ? (
            <div className="chat-refs-switcher" aria-label="Select answer turn">
              {assistantTurnList.map((t, i) => {
                const isSelected = activeRefsTurn?.key === t.key
                return (
                  <button
                    key={t.key}
                    type="button"
                    className={`chat-refs-turn-btn ${isSelected ? 'chat-refs-turn-btn--on' : ''}`.trim()}
                    onClick={() => setSelectedTurnKey(t.key)}
                    aria-label={`Show references for answer ${i + 1}`}
                  >
                    Q{i + 1}
                  </button>
                )
              })}
            </div>
          ) : null}
        </div>

        <ReferenceList
          citations={activeRefsTurn?.assistantMessage?.citations ?? []}
          activeN={
            activeCitation && activeRefsTurn && activeCitation.turnKey === activeRefsTurn.key
              ? activeCitation.n
              : null
          }
          onActivate={(n) => {
            if (!activeRefsTurn) return
            setActiveCitation(n !== null ? { turnKey: activeRefsTurn.key, n } : null)
          }}
          streaming={Boolean(activeRefsTurn?.assistantMessage?.streaming)}
          idPrefix="aside-ref"
        />
      </aside>

      <ConfirmDialog
        open={deletingConv !== null}
        title="Delete conversation"
        description={
          deletingConv
            ? `Delete "${deletingConv.title}" and all of its messages? Indexed episodes are not affected.`
            : ''
        }
        confirmLabel="Delete conversation"
        danger
        busy={deleteConv.isPending}
        onConfirm={confirmDeleteConv}
        onClose={() => {
          if (!deleteConv.isPending) setDeletingConv(null)
        }}
      />
    </div>
  )
}
