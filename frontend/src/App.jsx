import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import './styles/App.css'

export default function App() {
  return (
    <div className="container">
      <header>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>AI Voice Agent Admin</h2>
          <nav>
            <Link to="/">Dashboard</Link>
          </nav>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
      </Routes>
    </div>
  )
}
