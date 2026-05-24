import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchAttachments, uploadAttachment } from '../../services/eventService'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'

/* ── Constants ────────────────────────────────────────────────── */
const MAX_IMAGE_BYTES     = 20 * 1024 * 1024   // 20 MB raw — reject before even trying
const MAX_NONIMAGE_BYTES  =  5 * 1024 * 1024   //  5 MB for PDF / other
const TARGET_MAX_PX       = 1600               // resize images to fit inside 1600×1600
const JPEG_QUALITY        = 0.82

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif', 'application/pdf']

/* ── Image compression via Canvas ────────────────────────────── */
function compressImage(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(objectUrl)
      const scale = Math.min(1, TARGET_MAX_PX / Math.max(img.width, img.height))
      const w = Math.round(img.width  * scale)
      const h = Math.round(img.height * scale)
      const canvas = document.createElement('canvas')
      canvas.width  = w
      canvas.height = h
      canvas.getContext('2d').drawImage(img, 0, 0, w, h)
      canvas.toBlob(
        blob => {
          if (!blob) { reject(new Error('Image compression failed')); return }
          const outName = file.name.replace(/\.[^.]+$/, '.jpg')
          resolve(new File([blob], outName, { type: 'image/jpeg' }))
        },
        'image/jpeg',
        JPEG_QUALITY,
      )
    }
    img.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error('Cannot read image')) }
    img.src = objectUrl
  })
}

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload  = (e) => resolve(e.target.result.split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/* ── Helpers ──────────────────────────────────────────────────── */
const isImageType = (mimeType) => mimeType?.startsWith('image/')

const thumbUrl = (fileUrl) => {
  const m = fileUrl?.match(/\/d\/([^/]+)\//)
  return m ? `https://drive.google.com/thumbnail?id=${m[1]}&sz=w300` : null
}

const fmtBytes = (n) =>
  n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`

/* ── Component ────────────────────────────────────────────────── */
export const EventAttachments = ({ event, isAdmin }) => {
  const { operationMeta } = useApp()
  const { addToast }      = useToast()

  const [attachments, setAttachments] = useState([])
  const [isLoading,   setIsLoading]   = useState(true)
  const [uploadPhase, setUploadPhase] = useState(null)  // null | 'compressing' | 'uploading'

  const fileInputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    fetchAttachments(event.id)
      .then(data => { if (!cancelled) setAttachments(data || []) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setIsLoading(false) })
    return () => { cancelled = true }
  }, [event.id])

  const handleFile = useCallback(async (e) => {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file) return

    // Type check
    const isImage = isImageType(file.type)
    if (!isImage && !ALLOWED_TYPES.includes(file.type)) {
      addToast(`ไฟล์ประเภท "${file.type || 'ไม่รู้จัก'}" ไม่รองรับ — ใช้ภาพหรือ PDF เท่านั้น`, 'error')
      return
    }

    // Size check (before compression)
    const limit = isImage ? MAX_IMAGE_BYTES : MAX_NONIMAGE_BYTES
    if (file.size > limit) {
      addToast(`ไฟล์ใหญ่เกินไป (${fmtBytes(file.size)}) — สูงสุด ${fmtBytes(limit)}`, 'error')
      return
    }

    try {
      let toUpload = file

      // Compress images
      if (isImage && file.type !== 'image/gif') {
        setUploadPhase('compressing')
        toUpload = await compressImage(file)
      }

      setUploadPhase('uploading')
      const base64 = await readAsBase64(toUpload)

      const result = await uploadAttachment({
        operationId:    event.operation_id,
        operationTitle: operationMeta?.title || '',
        operationDate:  operationMeta?.date  || '',
        eventId:        event.id,
        fileName:       toUpload.name,
        fileData:       base64,
        mimeType:       toUpload.type,
        uploadedBy:     'ADMIN',
      })

      setAttachments(prev => [...prev, result])
      addToast('แนบไฟล์สำเร็จ', 'success')
    } catch (ex) {
      addToast('แนบไฟล์ไม่สำเร็จ: ' + (ex.message || 'ลองใหม่อีกครั้ง'), 'error')
    } finally {
      setUploadPhase(null)
    }
  }, [event, operationMeta, addToast])

  if (isLoading) {
    return (
      <div className="mt-3 pt-3 border-t border-ops-border/50">
        <p className="ops-label mb-1.5">ไฟล์แนบ</p>
        <p className="text-xs text-ops-text-muted">กำลังโหลด...</p>
      </div>
    )
  }

  if (!isAdmin && attachments.length === 0) return null

  return (
    <div className="mt-3 pt-3 border-t border-ops-border/50">
      <p className="ops-label mb-2">ไฟล์แนบ</p>

      {/* Thumbnails */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((att) => {
            const thumb = isImageType(att.file_type) ? thumbUrl(att.file_url) : null
            return (
              <a
                key={att.attachment_id}
                href={att.file_url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                title={att.file_name}
                className="block flex-shrink-0"
              >
                {thumb ? (
                  <img
                    src={thumb}
                    alt={att.file_name}
                    className="w-16 h-16 object-cover rounded-lg border border-ops-border hover:opacity-80 transition-opacity"
                  />
                ) : (
                  <div className="w-16 h-16 flex flex-col items-center justify-center rounded-lg border border-ops-border bg-ops-bg hover:bg-ops-surface transition-colors gap-1 p-1">
                    <span className="text-xl leading-none">📎</span>
                    <span className="text-[8px] text-ops-text-muted text-center break-all line-clamp-2 leading-tight">
                      {att.file_name}
                    </span>
                  </div>
                )}
              </a>
            )
          })}
        </div>
      )}

      {/* Attach button — admin only */}
      {isAdmin && (
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={handleFile}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadPhase !== null}
            className="flex items-center gap-1.5 text-[10px] font-semibold text-ops-text-muted hover:text-ops-accent border border-dashed border-ops-border/60 hover:border-ops-accent/40 px-2.5 py-1.5 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploadPhase === 'compressing' ? (
              <>
                <span className="w-3 h-3 border border-ops-accent/40 border-t-ops-accent rounded-full animate-spin flex-shrink-0" />
                กำลังบีบอัดรูป...
              </>
            ) : uploadPhase === 'uploading' ? (
              <>
                <span className="w-3 h-3 border border-ops-accent/40 border-t-ops-accent rounded-full animate-spin flex-shrink-0" />
                กำลังอัปโหลด...
              </>
            ) : (
              <>
                <span className="text-sm leading-none">📎</span>
                แนบไฟล์ / ถ่ายรูป
              </>
            )}
          </button>
        </>
      )}
    </div>
  )
}
