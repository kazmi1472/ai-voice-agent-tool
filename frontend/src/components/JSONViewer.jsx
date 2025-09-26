import React from 'react'

export default function JSONViewer({ json }) {
  const text = JSON.stringify(json, null, 2)
  const download = () => {
    const blob = new Blob([text], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'summary.json'
    a.click()
  }
  return (
    <div>
      <h4>Structured Summary</h4>
      <pre className="json-viewer">{text}</pre>
      <button className="btn btn-secondary" onClick={()=> navigator.clipboard.writeText(text)}>Copy JSON</button>
      <button className="btn" style={{ marginLeft: 8 }} onClick={download}>Download</button>
    </div>
  )
}
