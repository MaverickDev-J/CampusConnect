import { API_BASE_URL as CONFIG_BASE } from "@/app/config";

export const API_BASE_URL = `${CONFIG_BASE}/api`;

// ── Types ───────────────────────────────────────────────────

export interface LoginRequest {
    username: string; // FastAPI OAuth2PasswordRequestForm expects 'username' (which is email)
    password: string;
}

export interface SignupRequest {
    email: string;
    name: string;
    password: string;
    role: "student"; // only students can self-register
    profile?: {
        roll_no?: string;
        [key: string]: any;
    };
}

export interface AuthResponse {
    access_token: string;
    token_type: string;
}

export interface UserProfile {
    user_id: string;
    email: string;
    name: string;
    role: "superadmin" | "teacher" | "student";
    enrolled_classroom_ids?: string[];
    profile: {
        roll_no?: string;
        [key: string]: any;
    };
}

export interface Classroom {
    classroom_id: string;
    name: string;
    description?: string;
    subject?: string;
    join_code: string;
    member_count: number;
    created_by: string;
    created_by_name?: string;
    created_at: string;
}

export interface CreateClassroomRequest {
    name: string;
    description?: string;
    subject?: string;
}

// ── API Functions ───────────────────────────────────────────

/**
 * POST /api/auth/login
 * Form-urlencoded per OAuth2 spec
 */
export async function apiLogin(data: LoginRequest): Promise<AuthResponse> {
    const formData = new URLSearchParams();
    formData.append("username", data.username);
    formData.append("password", data.password);

    const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData.toString(),
    });

    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Login failed");
    }

    return res.json();
}

/**
 * POST /api/auth/register
 */
export async function apiSignup(data: SignupRequest): Promise<UserProfile> { // Returns UserResponse, not Token
    const res = await fetch(`${API_BASE_URL}/auth/register`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
    });

    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Signup failed");
    }

    return res.json();
}

/**
 * GET /api/users/me
 */
export async function apiGetProfile(token: string): Promise<UserProfile> {
    const res = await fetch(`${API_BASE_URL}/users/me`, {
        method: "GET",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
    });

    if (!res.ok) {
        throw new Error("Failed to fetch profile");
    }
 
    return res.json();
}

/**
 * PATCH /api/users/me
 */
export async function apiUpdateProfile(token: string, data: { name: string }): Promise<UserProfile> {
    const res = await fetch(`${API_BASE_URL}/users/me`, {
        method: "PATCH",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update profile");
    }

    return res.json();
}

/**
 * POST /api/users/me/password
 */
export async function apiChangePassword(token: string, data: any): Promise<{ message: string }> {
    const res = await fetch(`${API_BASE_URL}/users/me/password`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update password");
    }

    return res.json();
}

/**
 * Logout (Client-side only)
 */
export async function apiLogout(token: string): Promise<void> {
    return Promise.resolve();
}

// ── Classroom API Functions ─────────────────────────────────────────

export async function apiGetClassrooms(token: string): Promise<{ classrooms: Classroom[]; count: number }> {
    const res = await fetch(`${API_BASE_URL}/classrooms`, {
        method: "GET",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
    });

    if (!res.ok) throw new Error("Failed to fetch classrooms");
    return res.json();
}

export async function apiGetClassroom(token: string, classroom_id: string): Promise<Classroom> {
    const res = await fetch(`${API_BASE_URL}/classrooms/${classroom_id}`, {
        method: "GET",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
    });

    if (!res.ok) throw new Error("Failed to fetch classroom metadata");
    return res.json();
}

export async function apiCreateClassroom(token: string, data: CreateClassroomRequest): Promise<Classroom> {
    const res = await fetch(`${API_BASE_URL}/classrooms`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create classroom");
    }
    return res.json();
}

export async function apiJoinClassroom(token: string, join_code: string): Promise<Classroom> {
    const res = await fetch(`${API_BASE_URL}/classrooms/join`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ join_code }),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to join classroom");
    }
    return res.json();
}
