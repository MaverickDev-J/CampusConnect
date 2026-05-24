"use client";

import {
    createContext,
    useContext,
    useState,
    useEffect,
    useCallback,
    type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
    apiLogin,
    apiSignup,
    apiGetProfile,
    apiUpdateProfile,
    apiChangePassword,
    apiLogout,
    type UserProfile,
} from "@/app/lib/api";

// ── Types ───────────────────────────────────────────────────

export interface User extends UserProfile {
    token: string;
}

interface AuthContextType {
    user: User | null;
    loading: boolean;
    error: string | null;
    login: (email: string, password: string) => Promise<void>;
    signup: (
        name: string,
        email: string,
        password: string,
        profileData?: { roll_no?: string }
    ) => Promise<void>;
    logout: () => void;
    updateProfile: (name: string) => Promise<void>;
    changePassword: (data: any) => Promise<void>;
    clearError: () => void;
}

// ── Cookie helpers ──────────────────────────────────────────

function setAuthCookie(token: string) {
    document.cookie = `neural-auth-token=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
}

function removeAuthCookie() {
    document.cookie = "neural-auth-token=; path=/; max-age=0";
}

function getAuthCookie(): string | null {
    if (typeof document === "undefined") return null;
    const match = document.cookie.match(/(?:^|; )neural-auth-token=([^;]*)/);
    return match ? match[1] : null;
}

// ── Context ─────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    // ── Hydrate session on mount ────────────────────────────
    useEffect(() => {
        const initAuth = async () => {
            const token = getAuthCookie();
            if (!token) {
                setLoading(false);
                return;
            }

            try {
                const profile = await apiGetProfile(token);
                setUser({ ...profile, token });
            } catch (err) {
                console.error("Session rehydration failed:", err);
                removeAuthCookie();
                setUser(null);
            } finally {
                setLoading(false);
            }
        };

        initAuth();
    }, []);

    // ── Login ───────────────────────────────────────────────
    const login = useCallback(
        async (email: string, password: string) => {
            setError(null);
            setLoading(true);

            try {
                const { access_token } = await apiLogin({ username: email, password });
                setAuthCookie(access_token);

                // Fetch full profile immediately
                const profile = await apiGetProfile(access_token);
                setUser({ ...profile, token: access_token });

                router.push("/");
            } catch (err) {
                setError(err instanceof Error ? err.message : "Login failed");
                throw err; // Re-throw so UI can handle shake animations etc.
            } finally {
                setLoading(false);
            }
        },
        [router]
    );

    // ── Signup ──────────────────────────────────────────────
    const signup = useCallback(
        async (
            name: string,
            email: string,
            password: string,
            profileData?: { roll_no?: string }
        ) => {
            setError(null);
            setLoading(true);

            try {
                // 1. Register (Role is hardcoded to student in api layer or inferred)
                await apiSignup({
                    name,
                    email,
                    password,
                    role: "student",
                    profile: profileData,
                });

                // 2. Auto-login
                const { access_token } = await apiLogin({ username: email, password });
                setAuthCookie(access_token);

                // 3. Fetch profile
                const profile = await apiGetProfile(access_token);
                setUser({ ...profile, token: access_token });

                router.push("/");
            } catch (err) {
                setError(err instanceof Error ? err.message : "Signup failed");
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [router]
    );

    // ── Logout ──────────────────────────────────────────────
    const logout = useCallback(() => {
        if (user?.token) {
            apiLogout(user.token).catch(() => { });
        }
        removeAuthCookie();
        setUser(null);
        router.push("/login");
    }, [router, user]);

    // ── Update Profile ──────────────────────────────────────
    const updateProfile = useCallback(
        async (name: string) => {
            if (!user?.token) return;
            try {
                const updated = await apiUpdateProfile(user.token, { name });
                setUser({ ...updated, token: user.token });
            } catch (err) {
                setError(err instanceof Error ? err.message : "Update failed");
                throw err;
            }
        },
        [user?.token]
    );

    // ── Change Password ──────────────────────────────────────
    const changePassword = useCallback(
        async (data: any) => {
            if (!user?.token) return;
            try {
                await apiChangePassword(user.token, data);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Password change failed");
                throw err;
            }
        },
        [user?.token]
    );

    // ── Clear error ─────────────────────────────────────────
    const clearError = useCallback(() => setError(null), []);

    return (
        <AuthContext.Provider
            value={{ 
                user, 
                loading, 
                error, 
                login, 
                signup, 
                logout, 
                updateProfile, 
                changePassword, 
                clearError 
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
    return ctx;
}
