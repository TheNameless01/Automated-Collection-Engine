export type AppLang = 'fr' | 'ar' | 'en';

export type NavSection =
  | 'dashboard'
  | 'collect'
  | 'businesses'
  | 'wilayas'
  | 'map'
  | 'duplicates'
  | 'verification'
  | 'review'
  | 'exports'
  | 'sources'
  | 'history'
  | 'logs'
  | 'settings';

export type VerificationStatus = 'VERIFIED' | 'UNVERIFIED' | 'NEEDS_REVIEW' | 'CLOSED';

export interface DashboardSummary {
  total_businesses: number;
  verified_count: number;
  unverified_count: number;
  review_count: number;
  closed_count: number;
  missing_phone_count: number;
  missing_address_count: number;
  missing_coords_count: number;
  missing_website_count: number;
  suspected_duplicates_count: number;
  collection_runs_count: number;
  last_collection_run: {
    id: number;
    status: string;
    started_at: string;
    finished_at: string | null;
    discovered_count: number;
  } | null;
  active_run_id: number | null;
  by_wilaya: Array<{
    code: number;
    code_str: string;
    name_fr: string;
    name_ar: string;
    total_count: number;
    verified_count: number;
  }>;
  source_coverage: Array<{
    key: string;
    name: string;
    enabled: number;
    last_status: string;
    last_run_at: string | null;
    business_count: number;
  }>;
}

export interface WilayaSummary {
  code: number;
  code_str: string;
  name_fr: string;
  name_ar: string;
  name_en: string;
  parent_wilaya_code: number | null;
  center_lat: number;
  center_lon: number;
  total_communes: number;
  discovered_count: number;
  verified_count: number;
  unverified_count: number;
  review_count: number;
  communes_covered: number;
  sources_used: string[];
  collection_status: string;
}

export interface CommuneItem {
  id: number;
  code_commune: string;
  wilaya_code: number;
  name_fr: string;
  name_ar: string;
  daira_name_fr: string;
  daira_name_ar: string;
  lat: number;
  lon: number;
}

export interface BusinessRecord {
  id: number;
  primary_name: string;
  name_ar: string;
  name_fr: string;
  name_en: string;
  primary_phone: string;
  primary_phone_raw: string;
  primary_phone_status: string;
  full_address: string;
  commune_id: number | null;
  commune_name: string;
  wilaya_code: number | null;
  wilaya_code_str?: string;
  wilaya_name: string;
  wilaya_name_ar?: string;
  lat: number | null;
  lon: number | null;
  geo_assignment_method: string;
  geo_uncertain: number;
  website: string;
  facebook_url: string;
  instagram_url: string;
  other_socials: string[];
  google_maps_url: string;
  verification_status: VerificationStatus;
  confidence_score: number;
  verification_notes: string;
  last_verified_at: string | null;
  first_collected_at: string;
  last_collected_at: string;
  notes: string;
  source_keys?: string[];
}

export interface BusinessDetailResponse {
  business: BusinessRecord;
  phones: Array<{
    id: number;
    original_number: string;
    normalized_e164: string;
    national_format: string;
    validation_status: string;
    number_type: string;
    carrier_hint: string;
    is_primary: number;
  }>;
  source_records: Array<{
    id: number;
    source_key: string;
    source_name: string;
    license_info: string;
    external_id: string;
    source_url: string;
    raw_name: string;
    raw_phones_json: string;
    raw_address: string;
    raw_wilaya: string;
    raw_commune: string;
    attribution_text: string;
    collected_at: string;
  }>;
  verification_records: Array<{
    id: number;
    previous_status: string;
    new_status: string;
    verification_method: string;
    confidence_score: number;
    checks_json: string;
    notes: string;
    verified_by: string;
    verified_at: string;
  }>;
  audit_logs: Array<{
    id: number;
    action: string;
    actor: string;
    details_json: string;
    created_at: string;
  }>;
}

export interface DuplicateCandidate {
  id: number;
  business_a_id: number;
  business_b_id: number;
  overall_score: number;
  signals: Record<string, unknown>;
  status: string;
  created_at: string;
  business_a: BusinessRecord & { sources: Array<{ name: string; source_url: string; raw_address: string; raw_phones_json: string }> };
  business_b: BusinessRecord & { sources: Array<{ name: string; source_url: string; raw_address: string; raw_phones_json: string }> };
}

export interface MergeHistoryItem {
  id: number;
  target_business_id: number;
  source_business_id: number;
  target_name: string;
  source_name: string;
  merge_type: string;
  confidence_score: number;
  is_reverted: number;
  reverted_at: string | null;
  created_at: string;
}

export interface SourceItem {
  id: number;
  key: string;
  name: string;
  source_type: string;
  base_url: string;
  license_info: string;
  attribution: string;
  enabled: number;
  rate_limit_seconds: number;
  max_retries: number;
  config: Record<string, unknown>;
  last_run_at: string | null;
  last_status: string;
  last_error: string;
  pbf_local_exists?: boolean;
  pbf_local_size_mb?: number;
  pbf_download_state?: {
    downloading: boolean;
    downloaded_bytes: number;
    total_bytes: number;
    error: string;
    completed: boolean;
  };
}

export interface CollectionRun {
  id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  stop_requested: number;
  search_depth: string;
  selected_wilayas: number[];
  selected_sources: string[];
  total_tasks: number;
  completed_tasks: number;
  discovered_count: number;
  processed_count: number;
  new_businesses_count: number;
  merged_count: number;
  rejected_count: number;
  review_required_count: number;
  error_count: number;
  notes: string;
}

export interface ExportFileItem {
  filename: string;
  format: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
}
