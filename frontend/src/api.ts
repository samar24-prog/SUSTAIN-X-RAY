import { createClient } from '@supabase/supabase-js';
const env = import.meta.env;
export const supabase = env.VITE_SUPABASE_URL && env.VITE_SUPABASE_ANON_KEY ? createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY) : null;
export const login = async (email: string, password: string) => { if (!supabase)
    throw Error('Supabase is not configured'); const { error } = await supabase.auth.signInWithPassword({ email, password }); if (error)
    throw error; };
export const logout = () => supabase?.auth.signOut();
export async function request(path: string, method = 'GET', body?: unknown, raw = false) {
    const token = (await supabase?.auth.getSession())?.data.session?.access_token;
    const response = await fetch(`${env.VITE_API_URL || ''}/api${path}`, { method, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body !== undefined ? { 'Content-Type': raw ? 'text/plain' : 'application/json' } : {}) }, body: body === undefined ? undefined : raw ? String(body) : JSON.stringify(body) });
    if (!response.ok) {
        let message;
        try {
            const data = await response.json();
            message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
        catch {
            message = response.statusText;
        }
        throw Error(message || 'Request failed');
    }
    return response.headers.get('content-type')?.includes('text/csv') ? response.text() : response.json();
}
export function download(text: string, name: string) { const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' })); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
