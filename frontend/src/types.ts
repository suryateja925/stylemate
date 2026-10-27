export type PlanEvent = {
  id: string;
  event_name?: string | null;
  activity_type: string;
  occasion_type?: string | null;
  custom_activity?: string | null;
  start_time?: string | null;
  duration_minutes?: number | null;
  setting?: string | null;
  location?: string | null;
  dress_code?: string | null;
  formality?: string | null;
  budget?: number | null;
  preferences?: string | null;
  notes?: string | null;
  cancelled?: boolean;
  order_index: number;
};

export type Plan = {
  id: string;
  plan_date: string;
  status: string;
  saved_at?: string | null;
  events: PlanEvent[];
};

export type WardrobeItem = {
  id: string;
  category: string;
  subcategory?: string | null;
  primary_color?: string | null;
  secondary_colors: string[];
  pattern?: string | null;
  image_path: string;
  image_url: string;
  availability_status: string;
  laundry_status: string;
  confirmation_status: string;
  created_at: string;
};

export type Detection = {
  id: string;
  temporary_id: string;
  category: string;
  subcategory?: string | null;
  primary_color?: string | null;
  secondary_colors: string[];
  pattern?: string | null;
  visibility_status: string;
  confidence: number;
  bounding_box?: Record<string, number> | null;
  uncertainty_explanation?: string | null;
  requires_review: boolean;
  crop_path?: string | null;
  confirmed: boolean;
  rejected: boolean;
  image_url?: string | null;
};

export type Scan = {
  id: string;
  status: string;
  original_image_path: string;
  original_image_url: string;
  additional_image_paths: string[];
  needs_more_photos: boolean;
  error_message?: string | null;
  detections: Detection[];
};

export type RecommendationItem = {
  wardrobe_item_id: string;
  slot: string;
  wardrobe_item: WardrobeItem;
};

export type Recommendation = {
  id: string;
  event_id: string;
  rank: number;
  score: number;
  reason: string;
  limitation?: string | null;
  weather_note?: string | null;
  status: string;
  is_current: boolean;
  items: RecommendationItem[];
};

export type EventRecommendations = { event: PlanEvent; recommendations: Recommendation[] };

export type Progress = {
  confirmed_wardrobe_items: number;
  bundle_scans: number;
  successful_scans: number;
  failed_scans: number;
  awaiting_review: number;
  generated_outfits: number;
  saved_outfits: number;
  worn_outfits: number;
  weekly_activity: { date: string; count: number }[];
  category_coverage: { category: string; count: number }[];
  wardrobe_target: number;
  completion_percentage: number;
  upcoming_events: number;
  completed_preparation_tasks: number;
  pending_preparation_tasks: number;
};

export type Preferences = {
  preferred_styles: string[];
  favourite_colours: string[];
  disliked_colours: string[];
  preferred_formality?: string | null;
  comfort_preferences?: string | null;
  traditional_preferences?: string | null;
  preferred_sizes: string[];
  preferred_fits: string[];
  shopping_budget: number | null;
  repetition_window_days: number;
  reminders_enabled: boolean;
  reminder_time?: string | null;
};

export type PreparationTask = {
  id: string;
  event_id: string;
  task_type: string;
  title: string;
  due_at: string;
  status: string;
  snoozed_until?: string | null;
  completed_at?: string | null;
};

export type ChatMessage = { id: string; role: "user" | "assistant"; content: string; language?: string | null; created_at: string };
export type ChatResponse = { conversation_id: string; provider: string; configured: boolean; message: ChatMessage; follow_up_questions: string[] };
export type VoiceCommandResponse = { request_id: string; action: string; message: string; data: Record<string, unknown>; navigate_to?: string | null; warning?: string | null };
export type ShoppingResult = { provider: string; url: string; query: string; live_catalog: boolean; price?: number | null; delivery_estimate?: string | null; disclosure: string };
export type ShoppingSearch = { id: string; query: string; wardrobe_context: string[]; budget?: number | null; status: string; results: ShoppingResult[]; created_at: string };
