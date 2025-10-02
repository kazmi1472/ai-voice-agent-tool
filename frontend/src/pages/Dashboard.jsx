import React, { useState } from 'react'
import AgentConfigEditor from './AgentConfigEditor.jsx'
import CallTriggerForm from './CallTriggerForm.jsx'
import CallDetailView from './CallDetailView.jsx'
import CallHistoryList from '../components/CallHistoryList.jsx'
import { Calls } from '../api/apiClient.js'

export default function Dashboard() {
  const [tab, setTab] = useState('config')
  const [selectedCallId, setSelectedCallId] = useState(null)

  return (
    <div>
      <div className="tab-nav">
        <button onClick={() => setTab('config')} disabled={tab==='config'}>Agent Configuration</button>
        <button onClick={() => setTab('trigger')} disabled={tab==='trigger'}>Call Triggering</button>
        <button onClick={() => setTab('history')} disabled={tab==='history'}>Call Review / History</button>
      </div>

      {tab === 'config' && (
        <div className="card">
          <AgentConfigEditor />
        </div>
      )}

      {tab === 'trigger' && (
        <div className="card">
          <CallTriggerForm onQueued={(id)=>{setTab('history'); setSelectedCallId(id)}} />
        </div>
      )}

      {tab === 'history' && (
        <div className="grid grid-cols-2">
          <div className="card">
            <CallHistoryList onSelect={(id)=> setSelectedCallId(id)} />
          </div>
          {selectedCallId && (
            <div className="card">
              <CallDetailView callId={selectedCallId} />
            </div>
          )}
        </div>
      )}

      {/* tip removed as requested */}
    </div>
  )
}
