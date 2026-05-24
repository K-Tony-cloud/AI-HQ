import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchAttachments, uploadAttachment } from '../../services/eventService'
import { useToast } from '../../context/ToastContext'

const isImageType = (mimeType) => mimeType?.startsWith('image/')

const thumbUrl = (fileUrl) => {
  const m = fileUrl?.match(/\/d\/([^/]+)\//)
  return m ? `https://drive.google.com/thumbnail?id=${m[1]}&sz=w300` : null
}

const readAsBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload  = (e) => resolve(e.target.result.split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })

export const EventAttachments = ({ event, isAdmin }) => {
  const { addToast } = useToast()
  const [attachments, setAttachments] = useState([])
  const [isLoading,   setIsLoading]   = useState(true)
  const [isUploading, setIsUploading] = useState(false)
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

    setIsUploading(true)
    try {
      const base64 = await readAsBase64(file)
      const result = await uploadAttachment({
        operationId: event.operation_id,
        eventId:     event.id,
        fileName:    file.name,
        fileData:    base64,
        mimeType:    file.type,
        uploadedBy:  'ADMIN',
      })
      setAttachments(prev => [...prev, result])
      addToast('แนบไฟล์สำเร็จ', 'success')
    } catch (ex) {
      addToast('แนบไฟล์ไม่สำเร็จ: ' + (ex.message || 'ลองใหม่'), 'error')
    } finally {
      setIsUploading(false)
    }
  }, [event, addToast])

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
            disabled={isUploading}
            className="flex items-center gap-1.5 text-[10px] font-semibold text-ops-text-muted hover:text-ops-accent border border-dashed border-ops-border/60 hover:border-ops-accent/40 px-2.5 py-1.5 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUploading ? (
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
