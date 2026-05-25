export type Card = {
  id: number;
  name: string;
  set_name?: string | null;
  set_code?: string | null;
  card_number?: string | null;
  language?: string | null;
  rarity?: string | null;
  variant?: string | null;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type OwnedCard = {
  id: number;
  card_id: number;
  copy_label?: string | null;
  status?: string | null;
  acquired_at?: string | null;
  acquired_price_huf?: number | null;
  acquired_source?: string | null;
  storage_location?: string | null;
  personal_notes?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type CardMedia = {
  id: number;
  owned_card_id?: number | null;
  media_type: string;
  label: string;
  file_path: string;
  original_filename?: string | null;
  width?: number | null;
  height?: number | null;
  file_size_bytes?: number | null;
  derived_from_media_id?: number | null;
  edit_type?: string | null;
  edit_metadata?: string | null;
  created_at: string;
};

export type MediaUploadResponse = {
  ok: boolean;
  media: CardMedia;
  filename?: string | null;
  content_type?: string | null;
};

export type DerivedMediaCreate = {
  label?: string | null;
  edit_type?: string;
  brightness?: number;
  contrast?: number;
  saturation?: number;
  sharpness?: number;
  gamma?: number;
  exposure?: number;
  rotate_degrees?: number;
  crop_x?: number | null;
  crop_y?: number | null;
  crop_width?: number | null;
  crop_height?: number | null;
  edit_metadata?: Record<string, unknown> | null;
};

export type PriceObservation = {
  id: number;
  card_id: number;
  owned_card_id?: number | null;
  source_name?: string | null;
  currency?: string | null;
  raw_price_huf?: number | null;
  psa_7_price_huf?: number | null;
  psa_8_price_huf?: number | null;
  psa_9_price_huf?: number | null;
  psa_10_price_huf?: number | null;
  price_confidence?: number | null;
  observed_at: string;
  notes?: string | null;
};

export type PriceHistoryEntry = {
  id: number;
  card_id: number;
  owned_card_id?: number | null;
  source: string;
  source_card_id?: string | null;
  source_url?: string | null;
  raw_price?: number | null;
  market_price?: number | null;
  low_price?: number | null;
  high_price?: number | null;
  psa_7?: number | null;
  psa_8?: number | null;
  psa_9?: number | null;
  psa_10?: number | null;
  currency: string;
  converted_currency?: string | null;
  converted_market_price?: number | null;
  converted_raw_price?: number | null;
  converted_psa_7?: number | null;
  converted_psa_8?: number | null;
  converted_psa_9?: number | null;
  converted_psa_10?: number | null;
  confidence?: string | null;
  condition_hint?: string | null;
  fetched_at: string;
  raw_response_json?: string | null;
  debug_metadata_json?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type ManualPriceCreate = {
  card_id: number;
  owned_card_id?: number | null;
  raw_price?: number | null;
  market_price?: number | null;
  low_price?: number | null;
  high_price?: number | null;
  psa_7?: number | null;
  psa_8?: number | null;
  psa_9?: number | null;
  psa_10?: number | null;
  currency: string;
  confidence?: string | null;
  condition_hint?: string | null;
  source_url?: string | null;
};

export type PriceFetchRequest = {
  owned_card_id?: number | null;
  sources?: string[] | null;
  force?: boolean;
};

export type PriceFetchResult = {
  ok: boolean;
  source: string;
  price_history_id?: number | null;
  source_card_id?: string | null;
  source_url?: string | null;
  skipped?: boolean;
  match_score?: number | null;
  rate_limit_remaining?: number | null;
  warning?: string | null;
  error?: string | null;
  message?: string | null;
  duration_seconds?: number | null;
};

export type PriceFetchResponse = {
  ok: boolean;
  card_id: number;
  fetched_count: number;
  failed_count: number;
  latest_price?: PriceHistoryEntry | null;
  results: PriceFetchResult[];
  error?: string | null;
  message?: string | null;
};

export type PriceLatestResponse = {
  ok: boolean;
  card_id: number;
  owned_card_id?: number | null;
  latest?: PriceHistoryEntry | null;
  error?: string | null;
  message?: string | null;
};

export type PriceHistoryResponse = {
  ok: boolean;
  card_id: number;
  latest?: PriceHistoryEntry | null;
  history: PriceHistoryEntry[];
};

export type PriceRefreshResponse = {
  ok: boolean;
  cards_checked: number;
  success_count: number;
  failure_count: number;
  started_at: string;
  finished_at: string;
  message?: string | null;
};

export type PriceProviderStatus = {
  provider: "manual" | "local_json" | "poketrace" | "tcgdex" | "pokemontcg" | string;
  enabled: boolean;
  configured: boolean;
  source: "database" | "env" | "default" | string;
  missing: string[];
  masked_api_key?: string | null;
  secret_encrypted?: boolean;
  plan?: "free" | "pro" | "scale" | string | null;
  market?: "US" | "EU" | string | null;
  base_url?: string | null;
  daily_limit?: number | null;
  burst_limit?: number | null;
  burst_window_seconds?: number | null;
  timeout_seconds?: number | null;
  cache_ttl_hours?: number | null;
  rate_limit_seconds?: number | null;
  min_match_score?: number | null;
  fetch_history?: boolean | null;
  history_period?: string | null;
  respect_retry_after?: boolean | null;
  expected_sources?: string[];
  path_info?: string | null;
};

export type PriceProvidersStatusResponse = {
  ok: boolean;
  providers: PriceProviderStatus[];
};

export type PriceProviderSettingsResponse = PriceProvidersStatusResponse;

export type PriceProviderSettingsUpdate = {
  enabled: boolean;
  api_key?: string | null;
  clear_secret?: boolean;
  plan?: string | null;
  market?: string | null;
  base_url?: string | null;
  daily_limit?: number | null;
  burst_limit?: number | null;
  burst_window_seconds?: number | null;
  timeout_seconds?: number | null;
  cache_ttl_hours?: number | null;
  rate_limit_seconds?: number | null;
  min_match_score?: number | null;
  fetch_history?: boolean | null;
  history_period?: string | null;
  respect_retry_after?: boolean | null;
};

export type PriceProviderSettingResponse = {
  ok: boolean;
  provider: PriceProviderStatus;
};

export type PriceProviderTestResponse = {
  ok: boolean;
  provider: string;
  configured: boolean;
  plan?: string | null;
  rate_limit_remaining?: number | null;
  rate_limit?: Record<string, unknown> | null;
  error?: string | null;
  message?: string | null;
};

export type CollectionValuation = {
  ok: boolean;
  currency: string;
  total_value_huf: number;
  raw_value_huf: number;
  graded_value_huf: number;
  owned_cards_count: number;
  unique_cards_count: number;
  missing_price_cards: number;
  price_change_24h_huf?: number | null;
  price_change_7d_huf?: number | null;
  latest_refresh_at?: string | null;
};

export type CollectionSummary = {
  total_cards: number;
  unique_cards: number;
  raw_cards: number;
  graded_cards: number;
  collection_value_huf: number;
  cost_basis_huf: number;
  unrealized_profit_huf: number;
  conservative_value_huf: number;
  expected_value_huf: number;
  optimistic_value_huf: number;
  cards_missing_price_total: number;
};

export type CollectionSnapshot = {
  id: number;
  snapshot_date: string;
  total_cards?: number | null;
  unique_cards?: number | null;
  raw_cards?: number | null;
  graded_cards?: number | null;
  collection_value_huf?: number | null;
  cost_basis_huf?: number | null;
  unrealized_profit_huf?: number | null;
  conservative_value_huf?: number | null;
  expected_value_huf?: number | null;
  optimistic_value_huf?: number | null;
  created_at: string;
};

export type AnalysisRun = {
  id: number;
  owned_card_id: number;
  mode?: string | null;
  status?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
  opencv_version?: string | null;
  analysis_version?: string | null;
  centering_score?: number | null;
  corners_score?: number | null;
  edges_score?: number | null;
  surface_score?: number | null;
  overall_score?: number | null;
  estimated_grade_low?: string | null;
  estimated_grade_high?: string | null;
  psa_10_probability?: number | null;
  psa_9_probability?: number | null;
  psa_8_probability?: number | null;
  psa_7_or_lower_probability?: number | null;
  confidence_level?: string | null;
  human_summary?: string | null;
  recommendation?: string | null;
  recommendation_reason?: string | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type AnalysisAsset = {
  id: number;
  analysis_run_id: number;
  asset_type?: string | null;
  file_path: string;
  label?: string | null;
  created_at: string;
};

export type AnalysisRunDetail = {
  analysis_run: AnalysisRun;
  findings: AnalysisFinding[];
  assets: AnalysisAsset[];
};

export type CenteringMeasurement = {
  id: number;
  owned_card_id: number;
  analysis_run_id?: number | null;
  media_id?: number | null;
  side: "front" | "back";
  source: string;
  image_label?: string | null;
  image_width: number;
  image_height: number;
  outer_left_px: number;
  outer_right_px: number;
  outer_top_px: number;
  outer_bottom_px: number;
  inner_left_px: number;
  inner_right_px: number;
  inner_top_px: number;
  inner_bottom_px: number;
  outer_left_pct?: number | null;
  outer_right_pct?: number | null;
  outer_top_pct?: number | null;
  outer_bottom_pct?: number | null;
  inner_left_pct?: number | null;
  inner_right_pct?: number | null;
  inner_top_pct?: number | null;
  inner_bottom_pct?: number | null;
  left_border_px?: number | null;
  right_border_px?: number | null;
  top_border_px?: number | null;
  bottom_border_px?: number | null;
  horizontal_ratio_label?: string | null;
  vertical_ratio_label?: string | null;
  horizontal_left_percent?: number | null;
  horizontal_right_percent?: number | null;
  vertical_top_percent?: number | null;
  vertical_bottom_percent?: number | null;
  horizontal_offcenter_percent?: number | null;
  vertical_offcenter_percent?: number | null;
  centering_score?: number | null;
  estimated_grade_label?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type AnalysisFinding = {
  id: number;
  analysis_run_id: number;
  media_id?: number | null;
  finding_type?: string | null;
  severity?: string | null;
  confidence?: number | null;
  location_label?: string | null;
  bbox_x?: number | null;
  bbox_y?: number | null;
  bbox_width?: number | null;
  bbox_height?: number | null;
  title?: string | null;
  description?: string | null;
  grade_impact?: string | null;
  side?: "front" | "back" | "unknown" | null;
  confirmed?: boolean | null;
  uncertainty_reason?: string | null;
  photo_quality_issue?: boolean | null;
  created_at: string;
};

export type OpportunityPrecheck = {
  raw_price_huf?: number | null;
  psa_7_price_huf?: number | null;
  psa_8_price_huf?: number | null;
  psa_9_price_huf?: number | null;
  psa_10_price_huf?: number | null;
  grading_cost_huf: number;
  profit_if_psa_7?: number | null;
  profit_if_psa_8?: number | null;
  profit_if_psa_9?: number | null;
  profit_if_psa_10?: number | null;
  minimum_profitable_grade?: string | null;
  opportunity_score: number;
  recommendation: string;
};

export type AnalysisReport = {
  card: Card;
  owned_card: OwnedCard;
  scores: {
    centering_score?: number | null;
    corners_score?: number | null;
    edges_score?: number | null;
    surface_score?: number | null;
    overall_score?: number | null;
  };
  probabilities: {
    psa_10_probability?: number | null;
    psa_9_probability?: number | null;
    psa_8_probability?: number | null;
    psa_7_or_lower_probability?: number | null;
  };
  estimated_grade_range: {
    estimated_grade_low?: string | null;
    estimated_grade_high?: string | null;
  };
  confidence_level?: string | null;
  human_summary?: string | null;
  recommendation?: string | null;
  recommendation_reason?: string | null;
  latest_price?: PriceObservation | null;
  latest_centering?: CenteringMeasurement | null;
  opportunity_precheck?: OpportunityPrecheck | null;
  assets: AnalysisAsset[];
  findings: AnalysisFinding[];
  strengths: string[];
  main_grade_limiters: string[];
  manual_review_recommendations: string[];
};

export type OwnedCardWithCard = OwnedCard & {
  card?: Card | null;
  latest_raw_price_huf?: number | null;
};

export type AppInfo = {
  name: string;
  mode: string;
  external_apis_enabled: boolean;
  local_ai_enabled: boolean;
  database: string;
  media_storage: string;
};

export type DemoSeedResponse = {
  card: Card;
  owned_card: OwnedCard;
  created?: boolean;
  created_card: boolean;
  created_owned_card: boolean;
  message: string;
};

export type ResetLocalDataResponse = {
  status: string;
  message: string;
  deleted: Record<string, number>;
};

export type CleanupGeneratedMediaResponse = {
  status: string;
  message: string;
  deleted_files: number;
  deleted: Record<string, number>;
};

export type LocalAIStatus = {
  mode: "disabled" | "server_local" | "remote_worker" | string;
  enabled: boolean;
  provider: string;
  base_url: string;
  worker_base_url?: string | null;
  model_name?: string | null;
  is_localhost: boolean;
  reachable: boolean;
  worker_reachable?: boolean;
  vision_capable: string;
  server_role?: string;
  client_role?: string;
  message: string;
};

export type LocalAIConfig = {
  mode: "disabled" | "server_local" | "remote_worker" | string;
  enabled: boolean;
  provider: string;
  base_url: string;
  worker_base_url?: string | null;
  model_name?: string | null;
  timeout_seconds: number;
  max_images: number;
  max_tokens: number;
  disable_thinking: boolean;
  is_localhost: boolean;
  server_role?: string;
  client_role?: string;
};

export type LocalAITestConnection = {
  ok: boolean;
  reachable: boolean;
  mode?: string;
  worker_reachable?: boolean;
  models: string[];
  selected_model?: string | null;
  selected_model_found: boolean;
  message: string;
};

export type LocalAIAnalysisResponse = {
  analysis_run: AnalysisRun;
  finding_count: number;
  images_sent?: number;
  image_labels_sent?: string[];
  status: string;
};

export type RemoteAIWorkerResult = {
  estimated_grade?: number | string | null;
  grade_range?: {
    low?: number | string | null;
    high?: number | string | null;
  };
  confidence?: string | null;
  subscores?: {
    centering?: number | string | null;
    corners?: number | string | null;
    edges?: number | string | null;
    surface?: number | string | null;
  };
  detected_issues?: Array<{
    area?: string | null;
    severity?: string | null;
    description?: string | null;
  }>;
  summary?: string | null;
  psa_10_risk?: string | null;
  recommended_action?: string | null;
};

export type RemoteAIGradeResponse = {
  ok: boolean;
  analysis_run?: AnalysisRun;
  worker_result: RemoteAIWorkerResult | Record<string, unknown>;
  worker_meta?: Record<string, unknown>;
  finding_count?: number;
  images_sent?: number;
  image_labels_sent?: string[];
};

export type RecognitionExtracted = {
  name?: string | null;
  card_number?: string | null;
  set_text?: string | null;
  set_code?: string | null;
  rarity?: string | null;
  language?: string | null;
};

export type RecognitionAttempt = {
  id: number;
  media_id: number;
  owned_card_id?: number | null;
  status: string;
  mode: string;
  extracted: RecognitionExtracted;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type RecognitionCandidate = {
  id: number;
  recognition_attempt_id: number;
  catalog_card_id: number;
  rank: number;
  score: number;
  name: string;
  set_name?: string | null;
  set_code?: string | null;
  card_number?: string | null;
  rarity?: string | null;
  language?: string | null;
  thumbnail_file_path?: string | null;
  match_reasons: string[];
  name_score?: number | null;
  number_score?: number | null;
  set_score?: number | null;
  rarity_score?: number | null;
  language_score?: number | null;
};

export type RecognitionResponse = {
  ok: boolean;
  recognition_attempt?: RecognitionAttempt | null;
  candidates: RecognitionCandidate[];
  error?: string | null;
  message?: string | null;
  recognition_attempt_id?: number | null;
};

export type RecognitionAcceptResponse = {
  ok: boolean;
  owned_card: {
    id: number;
    catalog_card_id: number;
    card_id: number;
    name: string;
    set_name?: string | null;
    set_code?: string | null;
    card_number?: string | null;
    rarity?: string | null;
    language?: string | null;
  };
};

export type LocalAIDryRun = {
  config: LocalAIConfig;
  opencv_analysis_run_id: number;
  max_images: number;
  max_tokens: number;
  images_would_send: number;
  image_labels_would_send: string[];
  selected_asset_file_paths: string[];
  model_name: string;
  base_url: string;
  prompt_preview: string;
};

export type LocalAIDebugSingleImageResponse = {
  status: string;
  model: string;
  image_label_sent?: string | null;
  finish_reason?: string | null;
  content: string;
  reasoning_content_present: boolean;
  reasoning_content_preview?: string | null;
  parsed_json_success: boolean;
  parsed_json?: unknown;
  error_message?: string | null;
  raw_response_asset?: AnalysisAsset | null;
};

export type AnnotationResponse = {
  message: string;
  assets: AnalysisAsset[];
};
