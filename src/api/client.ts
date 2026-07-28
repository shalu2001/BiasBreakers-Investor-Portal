import axios from 'axios';

// FastAPI backend base URL — set VITE_API_BASE_URL in .env / .env.local.
// FastAPI validates request/response bodies against its own Pydantic models,
// so a malformed request comes back as a 422 with a `detail` array explaining
// which field failed, rather than a generic error.
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10_000,
});
