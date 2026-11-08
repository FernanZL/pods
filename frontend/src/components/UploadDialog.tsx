import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useUploadEpisode } from '../api/hooks'
import type { Episode, Podcast } from '../api/types'
import { isUploadShow } from '../utils/podcasts'
import { IconUpload } from './Icons'
import { Spinner } from './Spinner'
import './ConfirmDialog.css'
import './UploadDialog.css'

const ACCEPT = '.mp3,.m4a,.mp4,.aac,.wav,.flac,.ogg,.oga,.opus,.webm,.mpga,audio/*'
const DEFAULT_SHOW = 'My uploads'

interface UploadDialogProps {
  open: boolean
  /** Shows already in the library; upload shows are offered as suggestions. */
  podcasts: Podcast[] | undefined
  onClose: () => void
  onUploaded: (episode: Episode) => void
}

function titleFromFilename(name: string): string {
  return name
    .replace(/\.[^.]+$/, '')
    .replace(/[_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1024))} KB`
}

/**
 * Add an audio file from this computer as an episode. Uploading is free; the file
 * lands in the library as "downloaded", ready to transcribe and index like any
 * feed episode.
 */
export function UploadDialog({ open, podcasts, onClose, onUploaded }: UploadDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const upload = useUploadEpisode()

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [titleTouched, setTitleTouched] = useState(false)
  const [show, setShow] = useState('')
  const [description, setDescription] = useState('')
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const uploadShows = useMemo(
    () => (podcasts ?? []).filter(isUploadShow).map((p) => p.title),
    [podcasts],
  )

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      setFile(null)
      setTitle('')
      setTitleTouched(false)
      setShow('')
      setDescription('')
      setProgress(0)
      setError(null)
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  const busy = upload.isPending

  const pick = (f: File | null | undefined) => {
    if (!f) return
    setFile(f)
    setError(null)
    if (!titleTouched) setTitle(titleFromFilename(f.name))
  }

  const close = () => {
    if (busy) {
      abortRef.current?.abort()
      return
    }
    onClose()
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!file || busy) return
    setError(null)
    setProgress(0)
    const controller = new AbortController()
    abortRef.current = controller
    upload.mutate(
      {
        input: { file, title, show, description },
        onProgress: setProgress,
        signal: controller.signal,
      },
      {
        onSuccess: (episode) => onUploaded(episode),
        onError: (err) =>
          setError(err instanceof ApiError ? err.detail : 'The file could not be uploaded.'),
        onSettled: () => {
          abortRef.current = null
        },
      },
    )
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (!busy) pick(e.dataTransfer.files?.[0])
  }

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog upload-dialog"
      aria-labelledby="upload-dialog-title"
      onCancel={(e) => {
        e.preventDefault()
        close()
      }}
      onClick={(e) => {
        if (e.target === dialogRef.current && !busy) onClose()
      }}
    >
      <form className="confirm-dialog-inner" onSubmit={submit}>
        <h2 id="upload-dialog-title" className="confirm-dialog-title">
          Upload an audio file
        </h2>
        <p className="confirm-dialog-desc">
          A recording that is not in any feed: a talk, an interview, an episode you saved.
          Uploading is free; you see the cost before anything is transcribed.
        </p>

        <div
          className={`upload-drop ${dragging ? 'upload-drop--over' : ''} ${file ? 'upload-drop--has' : ''}`.trim()}
          onDragOver={(e) => {
            e.preventDefault()
            if (!busy) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <input
            ref={fileRef}
            id="upload-file"
            type="file"
            accept={ACCEPT}
            className="sr-only"
            disabled={busy}
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {file ? (
            <>
              <span className="upload-file-name" title={file.name}>
                {file.name}
              </span>
              <span className="upload-file-meta">{fmtBytes(file.size)}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
              >
                Choose another
              </button>
            </>
          ) : (
            <>
              <IconUpload size={18} className="upload-drop-icon" />
              <label htmlFor="upload-file" className="upload-drop-label">
                <span className="upload-drop-link">Choose a file</span> or drop it here
              </label>
              <span className="upload-file-meta">MP3, M4A, WAV, FLAC, OGG, OPUS or WEBM</span>
            </>
          )}
        </div>

        <div className="upload-fields">
          <label className="upload-field">
            <span className="upload-field-label">Title</span>
            <input
              className="input input-sm"
              value={title}
              disabled={busy}
              placeholder="Taken from the file name"
              onChange={(e) => {
                setTitle(e.target.value)
                setTitleTouched(true)
              }}
            />
          </label>
          <label className="upload-field">
            <span className="upload-field-label">Show</span>
            <input
              className="input input-sm"
              value={show}
              disabled={busy}
              placeholder={DEFAULT_SHOW}
              list="upload-show-options"
              onChange={(e) => setShow(e.target.value)}
            />
            <datalist id="upload-show-options">
              {uploadShows.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <label className="upload-field upload-field--wide">
            <span className="upload-field-label">
              About it <span className="upload-field-optional">optional</span>
            </span>
            <textarea
              className="textarea upload-textarea"
              value={description}
              disabled={busy}
              rows={2}
              placeholder="Who is speaking and what it is about. Helps name the speakers."
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </div>

        {busy ? (
          <div className="upload-progress" role="status" aria-live="polite">
            <span className="upload-progress-bar" aria-hidden="true">
              <span
                className="upload-progress-fill"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </span>
            <span className="upload-progress-text">
              {progress < 1 ? `Uploading ${Math.round(progress * 100)}%` : 'Reading the audio…'}
            </span>
          </div>
        ) : null}

        {error ? (
          <p className="upload-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="confirm-dialog-footer">
          <button type="button" className="btn" onClick={close}>
            {busy ? 'Cancel upload' : 'Cancel'}
          </button>
          <button type="submit" className="btn btn-primary" disabled={!file || busy}>
            {busy ? <Spinner size={12} label="Uploading" /> : <IconUpload size={13} />}
            <span>Upload</span>
          </button>
        </div>
      </form>
    </dialog>
  )
}
