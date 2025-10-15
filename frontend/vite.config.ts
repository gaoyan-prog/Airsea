import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
	plugins: [react()],
	server: {
		port: 5173,
		proxy: {
			"/auth": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/health": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/shipments": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/import": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/track": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/tracking": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/import/status/{jobId}": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			},
			"/import/active": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true
			}
		}
	}
})
