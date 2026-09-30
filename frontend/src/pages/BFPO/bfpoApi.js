import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// The BFPO portal shares the platform's session. Auth travels on the HttpOnly
// `ga_session` cookie (withCredentials) with an `Authorization: Bearer cookie`
// marker — mirroring the global axios auth interceptor in App.js. An explicit
// localStorage token (impersonation / legacy) still wins when present.
function authHeader() {
  let t = null;
  try { t = localStorage.getItem('token'); } catch { /* ignore */ }
  return t && t !== 'cookie' ? `Bearer ${t}` : 'Bearer cookie';
}

const client = axios.create({ baseURL: `${API}/bfpo`, withCredentials: true });
client.interceptors.request.use((cfg) => { cfg.headers.Authorization = authHeader(); return cfg; });

export const bfpo = client;

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await axios.post(`${API}/files/upload?category=service`, fd, {
    headers: { Authorization: authHeader(), 'Content-Type': 'multipart/form-data' },
    withCredentials: true,
  });
  return r.data;
}

export async function changePassword(current_password, new_password) {
  const r = await axios.post(`${API}/account/change-password`,
    { current_password, new_password },
    { headers: { Authorization: authHeader() }, withCredentials: true });
  return r.data;
}
