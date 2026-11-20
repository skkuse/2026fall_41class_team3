import { useState } from 'react'
import './App.css'

type Tab = 'chat' | 'map' | 'calendar'

const tabs: { id: Tab; label: string }[] = [
  { id: 'chat', label: '채팅' },
  { id: 'map', label: '학교 주변 지도' },
  { id: 'calendar', label: '학과 일정' },
]

function TabIcon({ tab }: { tab: Tab }) {
  if (tab === 'chat') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5.75A2.75 2.75 0 0 1 7.75 3h8.5A2.75 2.75 0 0 1 19 5.75v7.5A2.75 2.75 0 0 1 16.25 16H11l-4.5 3v-3.2A2.75 2.75 0 0 1 5 13.25z" />
        <path d="M8.5 8.5h7M8.5 11.5h4" />
      </svg>
    )
  }

  if (tab === 'map') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m3.5 6 5-2 7 2 5-2v14l-5 2-7-2-5 2z" />
        <path d="M8.5 4v14M15.5 6v14" />
        <path d="M12 9.5a2 2 0 1 0-4 0c0 1.5 2 3.5 2 3.5s2-2 2-3.5Z" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16M8 14h2M14 14h2M8 17h2" />
    </svg>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [isCollapsed, setIsCollapsed] = useState(false)

  return (
    <div className={`app-shell${isCollapsed ? ' sidebar-collapsed' : ''}`}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="SKKU MATE 홈">
          <span className="brand-mark" aria-hidden="true">◆</span>
          <span>SKKU MATE</span>
        </a>
        <button className="login-button" type="button">Login</button>
      </header>

      <div className="workspace">
        <aside className="sidebar" aria-label="주 메뉴">
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={isCollapsed ? '메뉴 펼치기' : '메뉴 접기'}
            aria-expanded={!isCollapsed}
            onClick={() => setIsCollapsed((collapsed) => !collapsed)}
          >
            <span aria-hidden="true">{isCollapsed ? '»' : '«'}</span>
          </button>

          <nav className="tab-list">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                className={`tab-button${activeTab === tab.id ? ' active' : ''}`}
                type="button"
                aria-label={tab.label}
                aria-current={activeTab === tab.id ? 'page' : undefined}
                title={isCollapsed ? tab.label : undefined}
                onClick={() => setActiveTab(tab.id)}
              >
                <TabIcon tab={tab.id} />
                <span className="tab-label">{tab.label}</span>
              </button>
            ))}
          </nav>
        </aside>

        <main className="main-content" aria-label={`${tabs.find((tab) => tab.id === activeTab)?.label} 화면`} />
      </div>
    </div>
  )
}

export default App
