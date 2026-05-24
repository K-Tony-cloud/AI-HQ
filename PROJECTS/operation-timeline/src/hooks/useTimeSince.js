import { useState, useEffect } from 'react'

export const useTimeSince = (date) => {
  const [label, setLabel] = useState('')

  useEffect(() => {
    if (!date) { setLabel(''); return }

    const update = () => {
      const secs = Math.floor((Date.now() - date.getTime()) / 1000)
      if (secs < 5)        setLabel('เพิ่งซิงก์')
      else if (secs < 60)  setLabel(`${secs} วินาทีที่แล้ว`)
      else                 setLabel(`${Math.floor(secs / 60)} นาทีที่แล้ว`)
    }

    update()
    const id = setInterval(update, 5000)
    return () => clearInterval(id)
  }, [date])

  return label
}
