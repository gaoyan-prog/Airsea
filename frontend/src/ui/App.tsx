import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import './styles.css'

export default function App() {
	const location = useLocation()
	const navigate = useNavigate()
	const user = typeof window !== 'undefined' ? localStorage.getItem('airsea_user') : null

	function onLogout() {
		try {
			localStorage.removeItem('airsea_user')
		} catch {}
		navigate('/login')
	}

	function scrollToBottomSmooth() {
		const height = document.documentElement.scrollHeight || document.body.scrollHeight
		window.scrollTo({ top: height, behavior: 'smooth' })
	}

	function onContactClick(e: React.MouseEvent) {
		e.preventDefault()
		if (location.pathname !== '/') {
			navigate('/')
			setTimeout(scrollToBottomSmooth, 0)
		} else {
			scrollToBottomSmooth()
		}
	}

	return (
		<div>
			<nav className="topbar">
				<Link to="/" className="brand">Air Sea <span className="sub">EXPRESS</span></Link>
				<ul className="nav">
					<li><Link className={location.pathname==='/' ? 'active' : ''} to="/">Home</Link></li>
					<li className="dropdown">
						<a href="#services">Our Services</a>
						<ul className="menu">
							<li><Link to="/services/freight">Freight Forwarding</Link></li>
							<li><Link to="/services/warehousing">Warehousing & Distribution</Link></li>
							<li><Link to="/services/ecommerce">E-Commerce Service</Link></li>
						</ul>
					</li>
					<li><a href="/" onClick={onContactClick}>Contact Us</a></li>
					{user ? <>
						<li><Link to="/tracking">Tracking</Link></li>
						<li><Link to="/import">One-Click Import</Link></li>
					</> : null}
				</ul>
				<div className="right">
					{user ? <span style={{marginRight:12, color:'#475569'}}>Hi</span> : null}
					<Link to="/login" className="login-btn">{user ? 'Switch' : 'Login'}</Link>
					{user ? <Link to="/login" onClick={(e)=>{e.preventDefault(); onLogout();}} className="login-btn" style={{marginLeft:8}}>Logout</Link> : null}
				</div>
			</nav>
			<main>
				<Outlet />
			</main>
		</div>
	)
}
