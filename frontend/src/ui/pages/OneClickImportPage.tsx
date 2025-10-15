import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function OneClickImportPage() {
    const navigate = useNavigate()
    const user = typeof window !== 'undefined' ? localStorage.getItem('airsea_user') : null
    const [running, setRunning] = useState(false)
    const [msg, setMsg] = useState('')
    const STORAGE_KEY = 'airsea_import_state'
    const tips = [
        '正在连接云端服务…',
        '唤醒小仓鼠为服务器供电…',
        '装载集装箱数据…',
        '打通太平洋海底光缆…',
        '预热引擎与缓存…',
        '再次确认航线…',
    ]
    const [tipIdx, setTipIdx] = useState(0)
    const [percent, setPercent] = useState(0)
    const [startedAt, setStartedAt] = useState<number | null>(null)
    const [jobId, setJobId] = useState<number | null>(null)
    const [serverData, setServerData] = useState<any>(null)
    const tipTimerRef = useRef<number | null>(null)
    const progTimerRef = useRef<number | null>(null)
    const pollTimerRef = useRef<number | null>(null)
    const abortRef = useRef<AbortController | null>(null)

    function saveState(partial?: Record<string, unknown>) {
        try {
            const data = {
                running,
                percent,
                msg,
                tipIdx,
                startedAt,
                jobId,
                ...partial,
            }
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
        } catch {}
    }

    function startTimers() {
        if (tipTimerRef.current == null) {
            tipTimerRef.current = window.setInterval(() => {
                setTipIdx((i) => (i + 1) % tips.length)
            }, 1200)
        }
        if (progTimerRef.current == null) {
            progTimerRef.current = window.setInterval(() => {
                setPercent((p) => Math.min(99, p + Math.floor(Math.random() * 7) + 3))
            }, 350)
        }
    }

    function stopTimers() {
        if (tipTimerRef.current != null) {
            window.clearInterval(tipTimerRef.current)
            tipTimerRef.current = null
        }
        if (progTimerRef.current != null) {
            window.clearInterval(progTimerRef.current)
            progTimerRef.current = null
        }
        if (pollTimerRef.current != null) {
            window.clearInterval(pollTimerRef.current)
            pollTimerRef.current = null
        }
    }

    useEffect(() => {
        if (!user) {
            navigate('/login')
            return
        }
        // 恢复状态（跨页面保持 loading）；若本地无 jobId，则尝试询问后端是否存在活跃任务
        try {
            const raw = localStorage.getItem(STORAGE_KEY)
            if (raw) {
                const s = JSON.parse(raw)
                if (s) {
                    setRunning(!!s.running)
                    setPercent(typeof s.percent === 'number' ? s.percent : 0)
                    setMsg(typeof s.msg === 'string' ? s.msg : '')
                    setTipIdx(typeof s.tipIdx === 'number' ? s.tipIdx : 0)
                    setStartedAt(typeof s.startedAt === 'number' ? s.startedAt : Date.now())
                    setJobId(typeof s.jobId === 'number' ? s.jobId : null)
                    if (s.running && s.jobId) {
                        startTimers()
                        beginPolling(s.jobId)
                    }
                }
            }
        } catch {}
        if (!jobId) {
            // 询问后端活跃任务
            fetch('/api/import/active').then(r=>r.json()).then(data=>{
                if (data?.ok && typeof data.jobId === 'number') {
                    setJobId(data.jobId)
                    setRunning(true)
                    saveState({ jobId: data.jobId, running: true })
                    startTimers()
                    beginPolling(data.jobId)
                }
            }).catch(()=>{})
        }
        // 卸载时保存当前状态
        return () => { stopTimers(); abortRef.current?.abort(); saveState() }
    }, [user, navigate])

    async function startImport() {
        if (running) return
        setRunning(true)
        setMsg('Starting...')
        setPercent(0)
        setTipIdx(0)
        setStartedAt(Date.now())
        startTimers()
        saveState({ running: true, percent: 0, tipIdx: 0, msg: 'Starting...', startedAt: Date.now() })
        try {
            const res = await fetch('/api/import/start', { method: 'POST' })
            const data = await res.json()
            if (data && typeof data.jobId === 'number') {
                setJobId(data.jobId)
                saveState({ jobId: data.jobId })
                setMsg('已发送启动请求')
                // 开始轮询后端状态
                beginPolling(data.jobId)
            } else {
                setMsg('启动失败，请重试')
            }
        } catch (e) {
            setMsg('启动失败，请重试')
            saveState({ msg: '启动失败，请重试' })
        } finally {
            // 不在这里结束，等待轮询结果决定
        }
    }

    async function pollOnce(curJobId: number) {
        try {
            // 取消前一次请求，避免堆积
            if (abortRef.current) abortRef.current.abort()
            abortRef.current = new AbortController()
            const res = await fetch(`/api/import/status/${curJobId}` , { signal: abortRef.current.signal })
            const json = await res.json()
            const s = json?.data || {}
            setServerData(s)
            // 根据服务端状态调整 UI
            if (typeof s.lastLog === 'string') setMsg(s.lastLog)
            if (s.status === 'success') {
                setPercent(100)
                finishAndCleanup()
            } else if (s.status === 'failed' || (typeof s.error === 'string' && s.error)) {
                setPercent(100)
                finishAndCleanup()
            }
        } catch {}
    }

    function beginPolling(curJobId: number) {
        // 先立即拉一次
        pollOnce(curJobId)
        if (pollTimerRef.current == null) {
            pollTimerRef.current = window.setInterval(() => pollOnce(curJobId), 5000)
        }
    }

    function finishAndCleanup() {
        stopTimers()
        setRunning(false)
        saveState({ running: false })
        setTimeout(() => {
            try { localStorage.removeItem(STORAGE_KEY) } catch {}
        }, 2000)
    }

    return (
        <div style={{ padding: 24 }}>
            <h2>
                One-Click Import
                <button onClick={startImport} disabled={running} className="login-btn" style={{marginLeft:12}}>
                    {running ? 'Running...' : 'Start'}
                </button>
                {running ? <span className="spinner" /> : null}
            </h2>
            <p>在这里发起一键导入操作（仅登录用户可见）。</p>
            {running || percent > 0 ? (
                <div style={{marginTop:8}}>
                    <div className="progress"><div className="bar" style={{width: `${percent}%`}} /></div>
                    <div className="tip">{serverData?.phase ? `当前阶段：${serverData.phase}` : tips[tipIdx]}</div>
                </div>
            ) : null}
            {msg ? <div className="msg">{msg}</div> : null}
            {serverData ? (
                <div style={{marginTop:8,color:'#64748b'}}>
                    <div>状态：{serverData.status || '-'}</div>
                    {serverData.error ? <div style={{color:'#b91c1c'}}>错误：{String(serverData.error)}</div> : null}
                </div>
            ) : null}
        </div>
    )
}


