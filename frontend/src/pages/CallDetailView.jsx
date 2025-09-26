import React, { useEffect, useState } from 'react'
import { Calls } from '../api/apiClient.js'
import TranscriptViewer from '../components/TranscriptViewer.jsx'
import JSONViewer from '../components/JSONViewer.jsx'

export default function CallDetailView({ callId }) {
  const [call, setCall] = useState(null)
  useEffect(()=>{ if (callId) Calls.get(callId).then(setCall) }, [callId])
  if (!call) return <div />
  return (
    <div>
      <h3>Call {call.id}</h3>
      <div className="grid grid-cols-2">
        <TranscriptViewer segments={call.full_transcript || []} />
        <JSONViewer json={call.structured_summary || {}} />
      </div>
      <button className="btn btn-secondary" onClick={()=> Calls.process(call.id).then(()=> Calls.get(call.id).then(setCall))}>Reprocess</button>
    </div>
  )
}
