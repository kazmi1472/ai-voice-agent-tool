import React, { useEffect, useState } from 'react'
import { AgentConfigs } from '../api/apiClient.js'

// placeholders removed per request

export default function AgentConfigEditor() {
  const [configs, setConfigs] = useState([])
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState(null)

  const load = async () => setConfigs(await AgentConfigs.list())
  useEffect(() => { load() }, [])

  const updateField = (idx, field, value) => {
    const next = [...configs]
    next[idx] = { ...next[idx], [field]: value }
    setConfigs(next)
  }

  const save = async (cfg) => {
    console.log('Saving agent config:', cfg)
    const payload = { name: cfg.name, description: cfg.description, prompt_template: cfg.prompt_template, voice_settings: cfg.voice_settings }
    console.log('Payload:', payload)
    try {
      if (cfg.id) {
        console.log('Updating existing config:', cfg.id)
        await AgentConfigs.update(cfg.id, payload)
      } else {
        console.log('Creating new config')
        await AgentConfigs.create(payload)
      }
      console.log('Save successful, reloading...')
      await load()
    } catch (error) {
      console.error('Save failed:', error)
      alert('Failed to save agent config: ' + error.message)
    }
  }

  const insertPlaceholder = (idx, ph) => {
    const cfg = configs[idx]
    updateField(idx, 'prompt_template', (cfg.prompt_template || '') + ph)
  }

  const startCreating = () => {
    setDraft({
      name: '',
      description: '',
      prompt_template: '',
      voice_settings: { backchanneling: true, filler_words_allowed: false, interruption_sensitivity: 'medium', speech_rate: 0.95, volume: 1.0 },
    })
    setCreating(true)
  }

  const insertPlaceholderDraft = (ph) => {
    setDraft(d => ({ ...d, prompt_template: (d?.prompt_template || '') + ph }))
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={startCreating} disabled={creating}>New Agent Config</button>
        {creating && (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="form-group">
              <label>Name</label>
              <input placeholder="Name" value={draft?.name || ''} onChange={e=> setDraft(d => ({...d, name: e.target.value}))} />
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea placeholder="Description" value={draft?.description || ''} onChange={e=> setDraft(d => ({...d, description: e.target.value}))} />
            </div>
            <div className="form-group">
              <label>Prompt template</label>
              <textarea rows={6} placeholder="Prompt template" value={draft?.prompt_template || ''} onChange={e=> setDraft(d => ({...d, prompt_template: e.target.value}))} />
            </div>
            <VoiceSettingsEditor value={draft?.voice_settings || {}} onChange={(v)=> setDraft(d => ({...d, voice_settings: v}))} />
            <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" onClick={async ()=>{ await save(draft); setCreating(false); setDraft(null);}}>Create</button>
              <button className="btn" onClick={()=> { setCreating(false); setDraft(null); }}>Cancel</button>
            </div>
          </div>
        )}
      </div>
      {configs.map((cfg, idx) => (
        <div key={cfg.id || idx} className="card">
          <div className="grid grid-cols-2">
            <div className="form-group">
              <label>Name</label>
              <input value={cfg.name || ''} onChange={e=>updateField(idx,'name',e.target.value)} placeholder="Name" />
            </div>
            <div className="form-group">
              <label>Description</label>
              <input value={cfg.description || ''} onChange={e=>updateField(idx,'description',e.target.value)} placeholder="Description" />
            </div>
          </div>
          <div className="form-group">
            <textarea rows={6} style={{ width: '100%' }} value={cfg.prompt_template || ''} onChange={e=>updateField(idx,'prompt_template',e.target.value)} />
          </div>
          <VoiceSettingsEditor value={cfg.voice_settings || {}} onChange={(v)=> updateField(idx, 'voice_settings', v)} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={()=> save(cfg)}>Save</button>
            {cfg.id && <button className="btn btn-danger" onClick={async ()=>{ await AgentConfigs.delete(cfg.id); await load() }}>Delete</button>}
          </div>
        </div>
      ))}
    </div>
  )
}

function VoiceSettingsEditor({ value, onChange }) {
  const [local, setLocal] = useState({ backchanneling: true, filler_words_allowed: false, interruption_sensitivity: 'medium', speech_rate: 0.95, volume: 1.0, ...(value||{}) })
  useEffect(()=>{ onChange(local) }, [local])
  return (
    <div style={{ marginTop: 8, borderTop: '1px dashed #ddd', paddingTop: 8 }}>
      <h4>Voice Settings</h4>
      <label><input type="checkbox" checked={!!local.backchanneling} onChange={e=>setLocal({...local, backchanneling:e.target.checked})} /> backchanneling</label>
      <label style={{ marginLeft: 12 }}><input type="checkbox" checked={!!local.filler_words_allowed} onChange={e=>setLocal({...local, filler_words_allowed:e.target.checked})} /> filler_words_allowed</label>
      <div style={{ marginTop: 6 }}>
        <label>interruption_sensitivity
          <select value={local.interruption_sensitivity} onChange={e=>setLocal({...local, interruption_sensitivity:e.target.value})}>
            <option>low</option>
            <option>medium</option>
            <option>high</option>
          </select>
        </label>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
        <label>speech_rate <input type="number" step="0.05" value={local.speech_rate} onChange={e=>setLocal({...local, speech_rate: parseFloat(e.target.value)})} /></label>
        <label>volume <input type="number" step="0.1" value={local.volume} onChange={e=>setLocal({...local, volume: parseFloat(e.target.value)})} /></label>
      </div>
    </div>
  )
}
