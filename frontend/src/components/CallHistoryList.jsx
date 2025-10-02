import React, { useEffect, useState } from 'react'
import { Calls } from '../api/apiClient.js'

export default function CallHistoryList({ onSelect }) {
  const [data, setData] = useState({ items: [], total: 0 })
  const [refresh, setRefresh] = useState(0)
  useEffect(()=>{ Calls.list({ page: 1, page_size: 50 }).then(setData) }, [refresh])
  useEffect(()=>{ const id = setInterval(()=> setRefresh(x=>x+1), 3000); return ()=> clearInterval(id) }, [])
  return (
    <div>
      <h3>Call History</h3>
      <table className="table">
        <thead>
          <tr>
            <th>call_id</th><th>driver</th><th>load</th><th>created_at</th><th>status</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map(c => (
            <tr key={c.id} onClick={()=> onSelect && onSelect(c.id)}>
              <td>{c.id}</td>
              <td>{c.driver_name}</td>
              <td>{c.load_number}</td>
              <td>{c.created_at}</td>
              <td>
                <span className={`status-badge status-${(c.status || '').replace('_','-')}`}>{c.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
