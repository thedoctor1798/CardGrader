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
  owned_card_id: number;
  media_type: string;
  label: string;
  file_path: string;
  original_filename?: string | null;
  width?: number | null;
  height?: number | null;
  file_size_bytes?: number | null;
  created_at: string;
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
  opportunity_precheck?: OpportunityPrecheck | null;
  assets: AnalysisAsset[];
};

export type OwnedCardWithCard = OwnedCard & {
  card?: Card | null;
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
