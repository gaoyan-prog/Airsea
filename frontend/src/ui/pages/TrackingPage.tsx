import { useState } from 'react'
import axios from 'axios'

type Shipment = {
    id: number
    company: string
    tracking_no: string
    status: string
    eta?: string
}

export default function TrackingPage() {
    const [list, setList] = useState<Shipment[]>([])
    const [reference, setReference] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    function formatEta(input?: string) {
        if (!input) return ''
        const m = input.match(/^\d{4}-\d{2}-\d{2}/)
        return m ? m[0] : input
    }

    async function onSearch(e: React.FormEvent) {
        e.preventDefault()
        setError('')
        const ref = reference.trim()
        if (!ref) { setList([]); return }
        setLoading(true)
        try {
            // 统一聚合接口：返回仅有结果的公司
            const res = await axios.get(`/api/tracking/query-all/${encodeURIComponent(ref)}`)
            const data = res?.data
            // 兼容多种返回：
            // 1) 数组 [{ carrier, eta, description }]
            // 2) 单对象 { carrier, eta|result, description }
            // 3) OCR 提前返回 { status:'ok', result: 'YYYY-MM-DD', source:'ocr' }
            if (Array.isArray(data)) {
                const rows = data.map((x:any, idx:number) => ({
                    id: idx+1,
                    company: x.carrier || '-',
                    tracking_no: ref,
                    status: x.description || 'Vessel Arrival',
                    eta: formatEta(x.eta)
                }))
                setList(rows)
            } else if (data && typeof data === 'object') {
                const carrier = (data as any).carrier || 'WANHAI'
                const etaRaw = (data as any).eta ?? (data as any).result
                const desc = (data as any).description || 'Vessel Arrival'
                setList([{ id: 1, company: carrier, tracking_no: ref, status: desc, eta: etaRaw ? formatEta(String(etaRaw)) : undefined }])
            } else {
                setList([])
            }
        } catch (err) {
            setError('查询失败，请稍后再试')
        } finally {
            setLoading(false)
        }
    }

    async function onStop() {
        try {
            await axios.post('/api/tracking/query-all/cancel')
        } catch (e) {
            // ignore network errors for cancel
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{padding:24}}>
            <h2>Tracking</h2>
            <form onSubmit={onSearch} style={{display:'flex',gap:12,flexWrap:'wrap',margin:'12px 0'}}>
                <input placeholder="Enter tracking reference" value={reference} onChange={e=>setReference(e.target.value)} />
                <button type="submit" disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
                <button type="button" onClick={onStop} disabled={!loading}>Stop</button>
            </form>
            {error ? <div style={{color:'#b91c1c',marginBottom:12}}>{error}</div> : null}
            <table style={{width:'100%',borderCollapse:'collapse'}}>
				<thead>
					<tr>
						<th style={{textAlign:'left',borderBottom:'1px solid #e5e7eb',padding:'8px'}}>Company</th>
						<th style={{textAlign:'left',borderBottom:'1px solid #e5e7eb',padding:'8px'}}>Tracking No.</th>
						<th style={{textAlign:'left',borderBottom:'1px solid #e5e7eb',padding:'8px'}}>Status</th>
                        <th style={{textAlign:'left',borderBottom:'1px solid #e5e7eb',padding:'8px'}}>ETA</th>
					</tr>
				</thead>
				<tbody>
					{list.map(item => (
						<tr key={item.id}>
							<td style={{padding:'8px',borderBottom:'1px solid #f1f5f9'}}>{item.company}</td>
							<td style={{padding:'8px',borderBottom:'1px solid #f1f5f9'}}>{item.tracking_no}</td>
							<td style={{padding:'8px',borderBottom:'1px solid #f1f5f9'}}>{item.status}</td>
                            <td style={{padding:'8px',borderBottom:'1px solid #f1f5f9'}}>{item.eta || '-'}</td>
						</tr>
					))}
                    {list.length === 0 && !loading ? (
                        <tr><td colSpan={4} style={{padding:'12px',color:'#64748b'}}>No results</td></tr>
                    ) : null}
				</tbody>
			</table>
		</div>
	)
}
