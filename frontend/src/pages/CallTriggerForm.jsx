import React, { useEffect, useState } from 'react'
import { AgentConfigs, Calls } from '../api/apiClient.js'

export default function CallTriggerForm({ onQueued }) {
  const [driver_name, setDriverName] = useState('')
  const [phone_number, setPhone] = useState('')
  const [load_number, setLoad] = useState('')
  const [agent_config_id, setAgent] = useState('')
  const [configs, setConfigs] = useState([])
  const [pending, setPending] = useState(false)
  const [simulate, setSimulate] = useState(false)
  const [toast, setToast] = useState(null)

  useEffect(()=>{ AgentConfigs.list().then(setConfigs) }, [])

  const submit = async () => {
    if (!phone_number) { setToast('Phone number required'); return }
    setPending(true)
    try {
      const res = await Calls.start({ driver_name, phone_number, load_number, agent_config_id }, simulate)
      setToast('Call queued')
      onQueued && onQueued(res.call_id)
    } catch (e) { setToast('Failed to start call') }
    setPending(false)
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <div className="grid">
        <div className="form-group">
          <label>Driver name</label>
          <input placeholder="Driver name" value={driver_name} onChange={e=>setDriverName(e.target.value)} />
        </div>
        <div className="form-group">
          <label>Phone number</label>
          <input placeholder="+E.164 preferred" value={phone_number} onChange={e=>setPhone(e.target.value)} />
        </div>
        <div className="form-group">
          <label>Load number</label>
          <input placeholder="Load number" value={load_number} onChange={e=>setLoad(e.target.value)} />
        </div>
        <div className="form-group">
          <label>Agent config</label>
          <select value={agent_config_id} onChange={e=>setAgent(e.target.value)}>
            <option value="">Select agent config</option>
            {configs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <label><input type="checkbox" checked={simulate} onChange={e=> setSimulate(e.target.checked)} /> Use local simulation (no real call)</label>
        <div>
          <button className="btn btn-primary" onClick={submit} disabled={pending}>{pending ? 'Queuing…' : 'Start Test Call'}</button>
        </div>
        {toast && <div className="toast" role="status" aria-live="polite">{toast}</div>}
      </div>
    </div>
  )
}
