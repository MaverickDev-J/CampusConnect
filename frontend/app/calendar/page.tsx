"use client";

import { useState, useEffect, useCallback } from "react";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import { 
    ChevronLeft, 
    ChevronRight, 
    Calendar as CalendarIcon,
    Clock,
    MapPin,
    Plus,
    Filter,
    X,
    Loader2,
    Trash2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { useClassroomSocket } from "@/app/hooks/useClassroomSocket";

export default function CalendarPage() {
    const { user } = useAuth();
    const { classrooms } = useClassrooms();
    const [currentDate, setCurrentDate] = useState(new Date());
    const [events, setEvents] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [showAddModal, setShowAddModal] = useState(false);
    const [selectedEvent, setSelectedEvent] = useState<any>(null);
    const [newEvent, setNewEvent] = useState({
        title: "",
        description: "",
        date: new Date().toISOString().split("T")[0],
        type: "event",
        classroom_id: ""
    });

    const fetchEvents = async () => {
        if (!user?.token) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/calendar/events`, {
                headers: {
                    "Authorization": `Bearer ${user?.token}`
                }
            });
            if (res.ok) {
                const data = await res.json();
                setEvents(data.events.map((e: any) => ({
                    ...e,
                    date: new Date(e.date)
                })));
            }
        } catch (err) {
            console.error("Failed to fetch events:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleWebSocketMessage = useCallback((msg: any) => {
        if (msg.type === "connection_established") {
            console.log(`[useClassroomSocket] ✅ Global Success: ${msg.status}`);
            return;
        }
        if (msg.type === "calendar_updated") {
            console.log(`[useClassroomSocket] 🔔 Calendar refresh triggered`);
            fetchEvents();
        }
    }, [fetchEvents]);

    // ── WebSocket Integration ──
    useClassroomSocket("global_events", user, handleWebSocketMessage);

    useEffect(() => {
        if (user?.token) {
            fetchEvents();
        }
    }, [user?.token]);

    const handleAddEvent = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const res = await fetch(`${API_BASE_URL}/api/calendar/events`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${user?.token}`
                },
                body: JSON.stringify(newEvent)
            });
            if (res.ok) {
                setShowAddModal(false);
                setNewEvent({ title: "", description: "", date: new Date().toISOString().split("T")[0], type: "event", classroom_id: "" });
                fetchEvents();
            }
        } catch (err) {
            console.error("Failed to add event:", err);
        }
    };

    const handleDeleteEvent = async (eventId: string) => {
        if (!confirm("Are you sure you want to delete this event?")) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/calendar/events/${eventId}`, {
                method: "DELETE",
                headers: {
                    "Authorization": `Bearer ${user?.token}`
                }
            });
            if (res.ok) {
                fetchEvents();
            }
        } catch (err) {
            console.error("Failed to delete event:", err);
        }
    };

    const daysInMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
    const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1).getDay();
    
    const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const eventColors: any = {
        exam: "bg-red-500",
        event: "bg-primary",
        deadline: "bg-amber-500",
        workshop: "bg-emerald-500"
    };
    
    const prevMonth = () => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
    const nextMonth = () => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));

    const renderDays = () => {
        const days = [];
        // Empty cells for days of prev month
        for (let i = 0; i < firstDayOfMonth; i++) {
            days.push(<div key={`empty-${i}`} className="h-32 border-b border-r border-slate-100 bg-slate-50/30" />);
        }
        
        // Actual days
        for (let day = 1; day <= daysInMonth; day++) {
            const date = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
            const dayEvents = events.filter(e => e.date.toDateString() === date.toDateString());
            const isToday = new Date().toDateString() === date.toDateString();

            days.push(
                <div 
                    key={day} 
                    onClick={() => {
                        if (user?.role === "teacher" || user?.role === "superadmin") {
                            setNewEvent(prev => ({ ...prev, date: date.toISOString().split("T")[0] }));
                            setShowAddModal(true);
                        }
                    }}
                    className="h-32 border-b border-r border-slate-100 p-2 hover:bg-slate-50 transition-colors group relative cursor-pointer"
                >
                    <span className={`text-xs font-black w-6 h-6 flex items-center justify-center rounded-full ${
                        isToday ? "bg-primary text-white shadow-lg shadow-primary/10" : "text-slate-400 group-hover:text-slate-900"
                    }`}>
                        {day}
                    </span>
                    <div className="mt-2 space-y-1 overflow-y-auto max-h-20 scrollbar-hide">
                        {dayEvents.map(event => (
                            <div 
                                key={event.event_id || event.id} 
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedEvent(event);
                                }}
                                className={`px-2 py-1 rounded-md ${eventColors[event.type] || "bg-indigo-500"} text-white text-[9px] font-bold truncate cursor-pointer hover:brightness-110 transition shadow-sm flex items-center justify-between group/event`}
                            >
                                <span className="truncate">{event.title}</span>
                                {(user?.role === "superadmin" || event.created_by === user?.user_id) && (
                                    <button 
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleDeleteEvent(event.event_id);
                                        }}
                                        className="opacity-0 group-hover/event:opacity-100 p-0.5 hover:bg-white/20 rounded transition"
                                    >
                                        <Trash2 size={10} />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            );
        }
        return days;
    };

    return (
        <div className="min-h-screen bg-slate-50 flex relative overflow-hidden">
            <div className="fixed inset-0 pointer-events-none">
                <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-yellow-400/5 blur-[120px] rounded-full" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full" />
            </div>
            <Sidebar />
            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300 relative">
                <Header />
                
                <div className="max-w-7xl mx-auto px-6 py-10">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-primary flex items-center justify-center shadow-lg shadow-primary/10">
                                <CalendarIcon size={24} className="text-white" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-black text-slate-900 tracking-tighter">Academic Calendar</h1>
                                <p className="text-slate-500 font-medium">Keep track of your classes and exams</p>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-3 bg-white p-2 rounded-2xl shadow-soft border border-slate-100">
                                <button suppressHydrationWarning onClick={prevMonth} className="p-2 hover:bg-slate-50 rounded-xl transition-colors text-slate-400 hover:text-primary">
                                    <ChevronLeft size={20} />
                                </button>
                                <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest min-w-[140px] text-center">
                                    {monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}
                                </h2>
                                <button suppressHydrationWarning onClick={nextMonth} className="p-2 hover:bg-slate-50 rounded-xl transition-colors text-slate-400 hover:text-primary">
                                    <ChevronRight size={20} />
                                </button>
                            </div>

                            {(user?.role === "teacher" || user?.role === "superadmin") && (
                                <button 
                                    onClick={() => setShowAddModal(true)}
                                    className="flex items-center gap-2 bg-primary text-white px-5 py-3.5 rounded-2xl font-black text-xs uppercase tracking-widest hover:brightness-110 shadow-lg shadow-primary/10 transition-all active:scale-95"
                                >
                                    <Plus size={18} /> Add Event
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                        {/* Calendar Grid */}
                        <div className="lg:col-span-3">
                            <div className="bg-white rounded-3xl shadow-premium border border-slate-200 overflow-hidden">
                                <div className="grid grid-cols-7 bg-slate-50 border-b border-slate-200">
                                    {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => (
                                        <div key={day} className="py-3 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center border-r border-slate-100">
                                            {day}
                                        </div>
                                    ))}
                                </div>
                                <div className="grid grid-cols-7">
                                    {renderDays()}
                                </div>
                            </div>
                        </div>

                        {/* Sidebar Info */}
                        <div className="space-y-6">
                            <div className="bg-white p-6 rounded-3xl shadow-soft border border-slate-100">
                                <h3 className="text-xs font-black text-slate-400 uppercase tracking-[0.2em] mb-4 flex items-center justify-between">
                                    Activity Guide
                                </h3>
                                <div className="space-y-2">
                                    {[
                                        { label: "Exams", color: "bg-red-500" },
                                        { label: "Workshops", color: "bg-primary" },
                                        { label: "Deadlines", color: "bg-amber-500" },
                                        { label: "Lectures", color: "bg-emerald-500" },
                                    ].map(item => (
                                        <div key={item.label} className="flex items-center gap-3">
                                            <div className={`w-3 h-3 rounded-full ${item.color}`} />
                                            <span className="text-xs font-bold text-slate-600">{item.label}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {(() => {
                                const upcomingEvents = events
                                    .filter(e => e.date > new Date())
                                    .sort((a, b) => a.date.getTime() - b.date.getTime());
                                
                                const nextEvent = upcomingEvents[0];
                                if (!nextEvent) return null;

                                const diffDays = Math.ceil((nextEvent.date.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24));

                                return (
                                    <div className="bg-slate-900 text-white p-8 rounded-[2rem] shadow-xl relative overflow-hidden group">
                                        <div className="absolute top-0 right-0 p-4 opacity-10">
                                            <Clock size={80} />
                                        </div>
                                        <div className="relative z-10">
                                            <h4 className="text-xs font-black text-primary uppercase tracking-widest mb-2">Next up</h4>
                                            <p className="text-lg font-black leading-tight mb-4">{nextEvent.title} {diffDays === 0 ? "today" : diffDays === 1 ? "tomorrow" : `in ${diffDays} days`}</p>
                                            <button 
                                                onClick={() => setSelectedEvent(nextEvent)}
                                                className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest hover:gap-3 transition-all duration-300"
                                            >
                                                View Details <ChevronRight size={14} />
                                            </button>
                                        </div>
                                        <div className="absolute bottom-0 left-0 w-full h-1 bg-gradient-to-r from-primary to-transparent" />
                                    </div>
                                );
                            })()}
                        </div>
                    </div>
                </div>

                {/* Add Event Modal */}
                <AnimatePresence>
                    {showAddModal && (
                        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                            <motion.div 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                onClick={() => setShowAddModal(false)}
                                className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
                            />
                            <motion.div 
                                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                                className="relative w-full max-w-lg bg-white rounded-[2.5rem] shadow-2xl overflow-hidden border border-slate-100"
                            >
                                <div className="p-8 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0">
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-2xl bg-indigo-100 flex items-center justify-center text-indigo-600">
                                            <Plus size={20} />
                                        </div>
                                        <div>
                                            <h3 className="text-xl font-black text-slate-900 tracking-tight">Add New Event</h3>
                                            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest mt-0.5">Schedule Academic Activity</p>
                                        </div>
                                    </div>
                                    <button onClick={() => setShowAddModal(false)} className="p-2 hover:bg-slate-50 rounded-xl text-slate-400 transition-colors">
                                        <X size={20} />
                                    </button>
                                </div>
                                
                                <form onSubmit={handleAddEvent} className="p-8 space-y-6">
                                    <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Event Title</label>
                                        <input 
                                            required
                                            value={newEvent.title}
                                            onChange={e => setNewEvent({...newEvent, title: e.target.value})}
                                            placeholder="e.g. Mid-Semester Exam"
                                            className="w-full bg-slate-50 border-2 border-transparent focus:border-indigo-600/10 focus:bg-white p-4 rounded-2xl font-bold text-slate-900 outline-none transition-all placeholder:text-slate-300"
                                        />
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Date</label>
                                            <input 
                                                type="date"
                                                required
                                                value={newEvent.date}
                                                onChange={e => setNewEvent({...newEvent, date: e.target.value})}
                                                className="w-full bg-slate-50 border-2 border-transparent focus:border-indigo-600/10 focus:bg-white p-4 rounded-2xl font-bold text-slate-900 outline-none transition-all"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Type</label>
                                            <select 
                                                value={newEvent.type}
                                                onChange={e => setNewEvent({...newEvent, type: e.target.value})}
                                                className="w-full bg-slate-50 border-2 border-transparent focus:border-indigo-600/10 focus:bg-white p-4 rounded-2xl font-bold text-slate-900 outline-none transition-all"
                                            >
                                                <option value="event">General Event</option>
                                                <option value="exam">Exam</option>
                                                <option value="deadline">Deadline</option>
                                                <option value="workshop">Workshop</option>
                                            </select>
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Description (Optional)</label>
                                        <textarea 
                                            value={newEvent.description}
                                            onChange={e => setNewEvent({...newEvent, description: e.target.value})}
                                            placeholder="Further details..."
                                            className="w-full bg-slate-50 border-2 border-transparent focus:border-indigo-600/10 focus:bg-white p-4 rounded-2xl font-bold text-slate-900 outline-none transition-all placeholder:text-slate-300 min-h-[100px]"
                                        />
                                    </div>

                                    {(user?.role === "teacher" || user?.role === "superadmin") && (
                                        <div className="space-y-2">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Target Classroom</label>
                                            <select 
                                                value={newEvent.classroom_id}
                                                onChange={e => setNewEvent({...newEvent, classroom_id: e.target.value})}
                                                className="w-full bg-slate-50 border-2 border-transparent focus:border-indigo-600/10 focus:bg-white p-4 rounded-2xl font-bold text-slate-900 outline-none transition-all"
                                            >
                                                <option value="">Global (All Students)</option>
                                                {classrooms.map(cls => (
                                                    <option key={cls.classroom_id} value={cls.classroom_id}>
                                                        {cls.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    <button 
                                        type="submit"
                                        className="w-full py-4 bg-indigo-600 text-white rounded-2xl font-black uppercase tracking-widest text-sm shadow-xl shadow-indigo-100 hover:bg-indigo-700 transition-all active:scale-95 flex items-center justify-center gap-2"
                                    >
                                        Create Event
                                    </button>
                                </form>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>

                {/* Event Details Modal */}
                <AnimatePresence>
                    {selectedEvent && (
                        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
                            <motion.div 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                onClick={() => setSelectedEvent(null)}
                                className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
                            />
                            <motion.div 
                                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                                className="relative w-full max-w-md bg-white rounded-[2.5rem] shadow-2xl overflow-hidden border border-slate-100"
                            >
                                <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                        <div className={`w-12 h-12 rounded-2xl ${eventColors[selectedEvent.type] || "bg-indigo-500"} flex items-center justify-center text-white shadow-lg`}>
                                            <CalendarIcon size={24} />
                                        </div>
                                        <div>
                                            <h3 className="text-xl font-black text-slate-900 tracking-tight">{selectedEvent.title}</h3>
                                            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest mt-0.5">{selectedEvent.type}</p>
                                        </div>
                                    </div>
                                    <button onClick={() => setSelectedEvent(null)} className="p-2 hover:bg-slate-50 rounded-xl text-slate-400">
                                        <X size={20} />
                                    </button>
                                </div>
                                
                                <div className="p-8 space-y-6">
                                    <div className="grid grid-cols-2 gap-6">
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Date</label>
                                            <p className="text-sm font-bold text-slate-900 flex items-center gap-2">
                                                <CalendarIcon size={14} className="text-indigo-600" />
                                                {selectedEvent.date.toLocaleDateString()}
                                            </p>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Posted By</label>
                                            <p className="text-sm font-bold text-slate-900 flex items-center gap-2">
                                                <MapPin size={14} className="text-indigo-600" />
                                                {selectedEvent.creator_name || "Teacher"}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="space-y-1">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Classroom / Subject</label>
                                        <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                            <p className="text-sm font-black text-slate-900">{selectedEvent.classroom_name || "Global"}</p>
                                            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mt-1">{selectedEvent.subject || "General"}</p>
                                        </div>
                                    </div>

                                    {selectedEvent.description && (
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Description</label>
                                            <p className="text-sm font-medium text-slate-600 leading-relaxed bg-slate-50/50 p-4 rounded-2xl italic border border-slate-50">
                                                "{selectedEvent.description}"
                                            </p>
                                        </div>
                                    )}

                                    <div className="pt-4 flex gap-3">
                                        {(user?.role === "superadmin" || selectedEvent.created_by === user?.user_id) && (
                                            <button 
                                                onClick={() => {
                                                    handleDeleteEvent(selectedEvent.event_id);
                                                    setSelectedEvent(null);
                                                }}
                                                className="flex-1 py-4 bg-red-50 text-red-600 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-red-100 transition-all flex items-center justify-center gap-2"
                                            >
                                                <Trash2 size={16} /> Delete Event
                                            </button>
                                        )}
                                        <button 
                                            onClick={() => setSelectedEvent(null)}
                                            className="flex-1 py-4 bg-slate-900 text-white rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-slate-800 transition-all"
                                        >
                                            Close
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
