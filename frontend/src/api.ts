import type { ChatMessage, ChatResponse, Detection, EventRecommendations, Plan, PlanEvent, PreparationTask, Preferences, Progress, Recommendation, Scan, ShoppingSearch, VoiceCommandResponse, WardrobeItem } from "./types";

export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
type AccessTokenProvider = () => Promise<string | null>;
let accessTokenProvider: AccessTokenProvider = async () => null;

export function setAccessTokenProvider(provider: AccessTokenProvider): void {
  accessTokenProvider = provider;
}

export function getLocalUserId(): string {
  if (!import.meta.env.DEV) throw new Error("Local profile IDs are available only in development.");
  const key = "stylemate-local-user-id";
  let value = localStorage.getItem(key);
  if (!value) {
    value = `local-${crypto.randomUUID()}`;
    localStorage.setItem(key, value);
  }
  return value;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const accessToken = await accessTokenProvider();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  else if (import.meta.env.DEV && !(
    import.meta.env.VITE_SUPABASE_URL
    && (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY)
  )) {
    headers.set("X-User-Id", getLocalUserId());
  }
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  deleteAccount: () => request<void>("/api/account", { method: "DELETE" }),
  profile: () => request<{ id: string; display_name: string; wardrobe_target: number }>("/api/profile"),
  updateProfile: (body: { display_name?: string; wardrobe_target?: number }) => request<{ id: string; display_name: string; wardrobe_target: number }>("/api/profile", { method: "PATCH", body: JSON.stringify(body) }),
  progress: () => request<Progress>("/api/progress/summary"),
  wardrobe: (filters?: { category?: string; colour?: string }) => request<WardrobeItem[]>(`/api/wardrobe?${new URLSearchParams(filters as Record<string, string>).toString()}`),
  updateWardrobe: (id: string, body: Partial<WardrobeItem>) => request<WardrobeItem>(`/api/wardrobe/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteWardrobe: (id: string) => request<void>(`/api/wardrobe/${id}`, { method: "DELETE" }),
  analyze: (file: File) => {
    const body = new FormData();
    body.append("image", file);
    return request<Scan>("/api/scanner/analyze", { method: "POST", body });
  },
  addScanPhoto: (scanId: string, file: File) => {
    const body = new FormData();
    body.append("image", file);
    return request<Scan>(`/api/scanner/${scanId}/photos`, { method: "POST", body });
  },
  updateDetection: (scanId: string, detectionId: string, body: Partial<Detection>) => request<Detection>(`/api/scanner/${scanId}/detections/${detectionId}`, { method: "PATCH", body: JSON.stringify(body) }),
  confirm: (scanId: string, detectionIds: string[]) => request<WardrobeItem[]>(`/api/scanner/${scanId}/confirm`, { method: "POST", body: JSON.stringify({ detection_ids: detectionIds }) }),
  plans: (date?: string) => request<Plan[]>(`/api/plans${date ? `?plan_date=${date}` : ""}`),
  createPlan: (body: { plan_date: string; events: Omit<PlanEvent, "id" | "order_index">[] }) => request<Plan>("/api/plans", { method: "POST", body: JSON.stringify(body) }),
  updatePlan: (id: string, body: { plan_date: string; events: Omit<PlanEvent, "id" | "order_index">[] }) => request<Plan>(`/api/plans/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  cancelPlanEvent: (planId: string, eventId: string) => request<Plan>(`/api/plans/${planId}/events/${eventId}/cancel`, { method: "POST" }),
  savePlan: (id: string) => request<Plan>(`/api/plans/${id}/save`, { method: "POST" }),
  recommendations: (planId: string, eventId?: string) => request<EventRecommendations[]>("/api/outfits/generate", { method: "POST", body: JSON.stringify({ plan_id: planId, event_id: eventId }) }),
  replaceOutfit: (id: string) => request<Recommendation[]>(`/api/outfits/${id}/replace`, { method: "POST" }),
  acceptOutfit: (id: string) => request<Recommendation>(`/api/outfits/${id}/accept`, { method: "POST" }),
  saveOutfit: (id: string) => request<Recommendation>(`/api/outfits/${id}/save`, { method: "POST" }),
  markWorn: (id: string) => request<Recommendation>(`/api/outfits/${id}/mark-worn`, { method: "POST" }),
  rejectOutfit: (id: string) => request<Recommendation>(`/api/outfits/${id}/reject`, { method: "POST" }),
  history: () => request<{ id: string; plan_date: string; event_type: string; status: string; outfit_signature: string[]; created_at: string }[]>("/api/outfits/history"),
  preferences: () => request<Preferences>("/api/preferences"),
  updatePreferences: (body: Partial<Preferences>) => request<Preferences>("/api/preferences", { method: "PATCH", body: JSON.stringify(body) }),
  preparationTasks: (includeCompleted = false) => request<PreparationTask[]>(`/api/preparation/tasks?include_completed=${includeCompleted}`),
  completeTask: (id: string) => request<PreparationTask>(`/api/preparation/tasks/${id}/complete`, { method: "POST" }),
  snoozeTask: (id: string, until: string) => request<PreparationTask>(`/api/preparation/tasks/${id}/snooze`, { method: "POST", body: JSON.stringify({ until }) }),
  notifications: () => request<{ id: string; title: string; message: string; status: string; scheduled_for: string; created_at: string }[]>("/api/notifications"),
  readNotification: (id: string) => request(`/api/notifications/${id}/read`, { method: "POST" }),
  chatStatus: () => request<{ configured: boolean; provider: string }>("/api/chat/status"),
  chatHistory: (conversationId: string) => request<ChatMessage[]>(`/api/chat/${conversationId}`),
  sendChat: (body: { conversation_id?: string; content: string; language?: "en" | "te" | "mixed" }) => request<ChatResponse>("/api/chat/messages", { method: "POST", body: JSON.stringify(body) }),
  voiceCommand: (body: { request_id: string; utterance: string; language?: "en" | "te" | "mixed" }, signal?: AbortSignal) => request<VoiceCommandResponse>("/api/voice/commands", { method: "POST", body: JSON.stringify(body), signal }),
  shoppingSearch: (body: { query?: string; occasion?: string; budget?: number; size?: string; colour?: string; style?: string; use_wardrobe_first?: boolean; providers?: string[] }) => request<ShoppingSearch>("/api/shopping/search", { method: "POST", body: JSON.stringify(body) }),
  shoppingSearches: () => request<ShoppingSearch[]>("/api/shopping/searches"),
};
