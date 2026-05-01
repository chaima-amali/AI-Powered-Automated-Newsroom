// ─── Fake user database ───────────────────────────────────────────────
export const FAKE_USERS = [
  {
    id: 1,
    name: 'Alex Johnson',
    email: 'alex@newsdispatch.com',
    password: 'news1234',
    avatar: 'AJ',
    avatarColor: '#4F46E5',
    joinedDate: 'January 2024',
    preferences: ['Technology', 'Business', 'Politics'],
  },
];

const SESSION_KEY = 'nd_user';

export function login(email, password) {
  const user = FAKE_USERS.find(
    (u) => u.email === email && u.password === password
  );
  if (!user) return { success: false, error: 'Invalid email or password.' };
  const { password: _, ...safeUser } = user;
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(safeUser));
  return { success: true, user: safeUser };
}

export function logout() {
  sessionStorage.removeItem(SESSION_KEY);
}

export function getSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
