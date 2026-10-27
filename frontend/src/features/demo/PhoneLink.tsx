import { useEffect, useState } from 'react'
import qrcode from 'qrcode-generator'
import { getPhoneLink } from '../../services/runsApi'

/** A QR code for opening this sample on a phone on the same Wi-Fi. Only shown when the person who started the server supplied the address (RECALL_PUBLIC_URL). */
export default function PhoneLink() {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getPhoneLink(controller.signal).then(result => setUrl(result.url)).catch(() => undefined)
    return () => controller.abort()
  }, [])
  if (!url) return null
  const code = qrcode(0, 'M')
  code.addData(url)
  code.make()
  return <section className="phone-link" aria-label="Open on your phone">
    <div className="phone-link-qr" role="img" aria-label={`QR code for ${url}`} dangerouslySetInnerHTML={{ __html: code.createSvgTag({ cellSize: 4, margin: 2, scalable: true }) }} />
    <div>
      <strong>Explore on your phone</strong>
      <p>Same Wi-Fi as this computer. Scan, then open the Try it tab. pingo is built phone-first.</p>
      <small>{url}</small>
    </div>
  </section>
}
