import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const bfpoToken = {
  get: () => { try { return localStorage.getItem('bfpo_token'); } catch { return null; } },
  set: (t) => { try { localStorage.setItem('bfpo_token', t); } catch {} },
  clear: () => { try { localStorage.removeItem('bfpo_token'); } catch {} },
};

const client = axios.create({ baseURL: `${API}/bfpo`, withCredentials: false });
client.interceptors.request.use((cfg) => {
  const t = bfpoToken.get();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export const bfpo = client;

export async function bfpoLogin(email, password) {
  const r = await axios.post(`${API}/auth/login`, { email, password, portal: 'mod' }, { withCredentials: false });
  return r.data;
}

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await axios.post(`${API}/files/upload?category=service`, fd, {
    headers: { Authorization: `Bearer ${bfpoToken.get()}`, 'Content-Type': 'multipart/form-data' },
    withCredentials: false,
  });
  return r.data;
}
