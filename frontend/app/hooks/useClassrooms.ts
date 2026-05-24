"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/app/context/auth-context";
import {
    apiGetClassrooms,
    apiCreateClassroom,
    apiJoinClassroom,
    type Classroom,
    type CreateClassroomRequest
} from "@/app/lib/api";

export function useClassrooms() {
    const { user } = useAuth();
    const [classrooms, setClassrooms] = useState<Classroom[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchClassrooms = useCallback(async () => {
        if (!user?.token) return;
        setLoading(true);
        setError(null);
        try {
            const data = await apiGetClassrooms(user.token);
            setClassrooms(data.classrooms);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load classrooms");
        } finally {
            setLoading(false);
        }
    }, [user?.token]);

    useEffect(() => {
        fetchClassrooms();
    }, [fetchClassrooms]);

    const createClassroom = async (data: CreateClassroomRequest) => {
        if (!user?.token) return;
        try {
            const newClass = await apiCreateClassroom(user.token, data);
            setClassrooms(prev => [newClass, ...prev]);
            return newClass;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to create classroom");
            throw err;
        }
    };

    const joinClassroom = async (joinCode: string) => {
        if (!user?.token) return;
        try {
            const joinedClass = await apiJoinClassroom(user.token, joinCode);
            setClassrooms(prev => [joinedClass, ...prev]);
            return joinedClass;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to join classroom");
            throw err;
        }
    };

    return {
        classrooms,
        loading,
        error,
        refresh: fetchClassrooms,
        createClassroom,
        joinClassroom
    };
}

export function useClassroom(id: string) {
  const { user } = useAuth();
  const [classroom, setClassroom] = useState<Classroom | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchClassroom = useCallback(async () => {
      if (!user?.token || !id) return;
      setLoading(true);
      setError(null);
      try {
          const data = await apiGetClassrooms(user.token);
          const found = data.classrooms.find(c => c.classroom_id === id);
          if (found) {
              setClassroom(found);
          } else {
              throw new Error("Classroom not found or access denied");
          }
      } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to load classroom");
      } finally {
          setLoading(false);
      }
  }, [user?.token, id]);

  useEffect(() => {
      fetchClassroom();
  }, [fetchClassroom]);

  return { classroom, loading, error, refresh: fetchClassroom };
}
