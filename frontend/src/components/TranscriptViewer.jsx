import React from 'react'

export default function TranscriptViewer({ segments }) {
  return (
    <div>
      <h4>Transcript</h4>
      <div className="transcript-viewer">
        {(segments||[]).map((s, i) => (
          <div key={i} className={`transcript-segment ${s.speaker}`}>
            <div className="transcript-speaker">{s.speaker} <span className="transcript-timestamp">{s.timestamp}</span></div>
            <div className="transcript-text">{s.text}</div>
          </div>
        ))}
      </div>
      <button className="btn btn-secondary" onClick={()=> navigator.clipboard.writeText(JSON.stringify(segments, null, 2))}>Copy Transcript JSON</button>
    </div>
  )
}
