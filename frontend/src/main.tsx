import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './ui/App'
import HomePage from './ui/pages/HomePage'
import LoginPage from './ui/pages/LoginPage'
import TrackingPage from './ui/pages/TrackingPage'
import OneClickImportPage from './ui/pages/OneClickImportPage'
import ServiceFreight from './ui/pages/services/ServiceFreight'
import ServiceWarehousing from './ui/pages/services/ServiceWarehousing'
import ServiceEcommerce from './ui/pages/services/ServiceEcommerce'

const router = createBrowserRouter([
	{
		path: '/',
		element: <App />,
		children: [
			{ path: '/', element: <HomePage /> },
			{ path: '/login', element: <LoginPage /> },
			{ path: '/tracking', element: <TrackingPage /> },
			{ path: '/import', element: <OneClickImportPage /> },
			{ path: '/services/freight', element: <ServiceFreight /> },
			{ path: '/services/warehousing', element: <ServiceWarehousing /> },
			{ path: '/services/ecommerce', element: <ServiceEcommerce /> }
		]
	}
])

ReactDOM.createRoot(document.getElementById('root')!).render(
	<React.StrictMode>
		<RouterProvider router={router} />
	</React.StrictMode>
)
