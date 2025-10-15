import { useState } from 'react'
import axios from 'axios'

export default function LoginPage() {
	const [username, setUsername] = useState('')
	const [password, setPassword] = useState('')
	const [message, setMessage] = useState<string | null>(null)
	const [loading, setLoading] = useState(false)

	async function handleSubmit(e: React.FormEvent) {
		e.preventDefault()
		setLoading(true)
		setMessage(null)
		try {
			const isEmail = username.includes('@')
			const body: any = { password }
			if (isEmail) body.email = username; else body.username = username
			const res = await axios.post('/auth/login', body)
			localStorage.setItem('airsea_user', JSON.stringify(res.data))
			window.location.href = '/tracking'
		} catch (err: any) {
			setMessage(err?.response?.data?.detail || '登录失败')
		} finally {
			setLoading(false)
		}
	}

	return (
		<div className="login-wrap">
			<h2>Login</h2>
			<form onSubmit={handleSubmit} className="login-form">
				<label>
					Username / Email
					<input value={username} onChange={e=>setUsername(e.target.value)} required/>
				</label>
				<label>
					Password
					<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required/>
				</label>
				<button type="submit" disabled={loading}>{loading ? '登录中...' : '登录'}</button>
			</form>
			{message && <p className="msg">{message}</p>}
		</div>
	)
}
