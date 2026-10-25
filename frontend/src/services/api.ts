// Shared FastAPI base URL. The Check-in adapter lives in pages/checkin/checkInService.ts.
// Set VITE_API_BASE_URL in .env.local when the backend is ready.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
