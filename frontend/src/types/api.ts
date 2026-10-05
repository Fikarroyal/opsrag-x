export interface Page<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface Incident {
  id: string
  ticket_number: string
  title: string
  description: string
  reporter_name: string | null
  affected_unit: string | null
  affected_device: string | null
  affected_service: string | null
  severity: string | null
  category: string | null
  status: string
  occurred_at: string
  created_at: string
  resolved_at: string | null
  scenario_id: string | null
}

export interface IncidentCreate {
  title: string
  description: string
  reported_by?: string
  affected_unit?: string
  affected_device?: string
  affected_service?: string
  occurred_at?: string
}

export interface StageState {
  status: string
  detail?: string
  started_at?: string
  finished_at?: string
}

export interface InvestigationBrief {
  id: string
  incident_id: string
  status: string
  root_cause_category: string | null
  confidence_score: number | null
  ai_mode: string | null
  duration_ms: number | null
  started_at: string
  completed_at: string | null
  parent_investigation_id?: string | null
}

export interface EvidenceItem {
  key: string
  source_type: string
  source_id: string | null
  timestamp: string | null
  content: string
  kind: string
  relevance_score: number
  temporal_score: number | null
  temporal_relation: string | null
  role: string
  confidence_contribution: number | null
  priority_rank: number
  reliability: number
  tags: string[]
  hypothesis_roles: Record<string, string>
}

export interface EvidenceRef {
  key: string
  text: string
  source_type: string
}

export interface Explainability {
  why: string
  supporting_sources: string[]
  contradicting: string[]
  missing_indicators: string[]
  next_diagnostic: string
  recommended_next_diagnostic: string
}

export interface Hypothesis {
  id: string
  category: string
  description: string
  score: number
  confidence: number
  status: string
  components: Record<string, number>
  supporting_evidence: EvidenceRef[]
  contradicting_evidence: EvidenceRef[]
  indicators_supported: string[]
  indicators_contradicted: string[]
  indicators_missing: string[]
  explainability: Explainability
}

export interface Recommendation {
  order: number
  type: string
  text: string
  evidence_refs: string[]
  sop_reference: string | null
  requires_human_approval: boolean
}

export interface ToolExec {
  tool: string
  purpose: string
  arguments: Record<string, unknown>
  status: string
  execution_ms: number
  error: string | null
  summary: string
  evidence_keys: string[]
}

export interface SopRef {
  sop_code: string
  title: string
  version: string
  effective_date: string
  relevance: number
  matched_sections: string[]
  selection_reason: string
}

export interface HistRef {
  incident_key: string
  timestamp: string
  unit: string | null
  device: string | null
  description: string
  category: string
  severity: string
  affected_service: string | null
  root_cause: string
  root_cause_category: string
  resolution: string | null
  resolution_time_minutes: number | null
  similarity: number
  score: number
  age_days: number
  usage: string
}

export interface TimelineItem {
  timestamp: string
  source: string
  event: string
  relevance: number
  relation: string | null
  evidence_key: string | null
  domain?: string
}

export interface Finding {
  id: string
  statement: string
  type: string
  evidence_refs: string[]
  role: string
  timestamp: string | null
}

export interface CorrelationPattern {
  name: string
  cause_domain: string
  cause_onset: string
  symptom_onset: string
  lag_seconds: number
  order_ok: boolean
  event_count: number
  correlation_score: number
}

export interface Report {
  incident_summary: string
  ai_narrative: string | null
  incident: { id: string; ticket_number: string; title: string; description: string; affected_unit: string | null; affected_device: string | null; affected_service: string | null; occurred_at: string }
  classification: { category: string; secondary_category: string | null; severity: string; affected_scope: string; affected_service: string | null; confidence: number; method: string }
  investigation_status: string
  findings: Finding[]
  root_cause_hypotheses: Hypothesis[]
  root_cause_conclusion: { status: string; description: string; confidence: number; confidence_label?: string; note?: string }
  recommended_actions: Recommendation[]
  verification_steps: string[]
  next_diagnostic: string
  sop_procedures: { sop_code: string; version: string; effective_date: string; remediation_steps: string[]; verification: string | null; rollback: string | null }[]
  evidence: EvidenceItem[]
  sop_reference: SopRef[]
  sop_version_decisions: { sop_code: string; version: string; effective_date: string; selected: boolean; reason: string }[]
  historical_incidents: HistRef[]
  tools_executed: ToolExec[]
  tool_plan: { reason: string; domains: string[]; selected_tools: { tool: string; purpose: string }[] }
  correlation: { onsets: Record<string, string>; patterns: CorrelationPattern[]; impact_units: string[]; affected_endpoints: Record<string, { events: number; avg_loss: number; avg_latency: number }>; counts: Record<string, number> }
  timeline: TimelineItem[]
  topology: { path: string[]; access_switch: string | null; uplink: { interface: string; peer: string } | null; affected_hosts: string[]; shared_access_switch: string | null; scope_level: string; impact_units: string[] }
  decision_trace: { classification: Record<string, string>; reasoning_summary: string[]; selected_tools: { tool: string; why: string; status: string; result_summary: string; evidence_generated: string[] }[] }
  limitations: string[]
  ai_mode: string
  model_used: string
  audit: Record<string, unknown>
}

export interface Investigation extends InvestigationBrief {
  summary: string | null
  stages: Record<string, StageState>
  report: Report | null
  model_used: string | null
  error_message: string | null
}

export interface AuditEvent {
  id: string
  event_type: string
  message: string
  timestamp: string
  status: string
  duration_ms: number | null
  meta: Record<string, unknown>
}

export interface ToolExecution {
  id: string
  tool_name: string
  purpose: string | null
  arguments: Record<string, unknown>
  result: Record<string, unknown> | null
  execution_time: number | null
  status: string
  error_message: string | null
  created_at: string
}

export interface Device {
  id: string
  hostname: string
  ip_address: string
  mac_address: string | null
  unit: string
  vlan: number | null
  device_type: string
  operating_system: string | null
  status: string
  switch_port: string | null
  switch: string | null
  last_seen: string | null
}

export interface ServiceState { service: string; server: string; status: string; response_time_ms: number; http_status: number; last_checked: string; port: number; endpoint: string; availability: number | null; protocol: string | null }
export interface Server { hostname: string; ip_address: string; role: string; status: string; operating_system: string | null; cpu: number | null; memory: number | null; sample_timestamp: string | null; services: ServiceState[]; recent_errors: number }
export interface Metric { timestamp: string; cpu: number | null; memory: number | null }
export interface LogRow { id: string; timestamp: string; source: string; hostname: string; ip_address: string | null; destination: string | null; service: string | null; log_level: string; event_type: string; message: string; latency_ms: number | null; packet_loss: number | null }
export interface LogFilters { hostnames: string[]; services: string[]; event_types: string[]; levels: string[] }

export interface SopVersion { version: string; effective_date: string; status: string; sections: Record<string, string> }
export interface Sop { sop_code: string; title: string; category: string | null; active_version: string | null; effective_date: string | null; status: string | null; relevant_incidents: number; versions: SopVersion[] }

export interface Historical {
  incident_key: string
  timestamp: string
  unit: string | null
  device: string | null
  description: string
  category: string
  severity: string
  affected_service: string | null
  root_cause: string
  root_cause_category: string
  resolution: string | null
  resolution_time_minutes: number | null
  pattern: string | null
  similarity: number | null
  used_in_investigation: boolean
}

export interface TopoNode { id: string; hostname: string; ip: string; device_type: string; vlan: number; unit: string; status: string; layer: number }
export interface TopoEdge { source: string; target: string; source_interface: string; target_interface: string; link_type: string }
export interface Topology { hospital: string; vlans: Record<string, string>; nodes: TopoNode[]; edges: TopoEdge[] }

export interface NameValue { name: string; value: number }
export interface DashboardStats {
  total_incidents: number
  open_incidents: number
  critical_incidents: number
  investigations_running: number
  resolved_incidents: number
  historical_incidents: number
  average_resolution_minutes: number | null
  incident_by_category: NameValue[]
  incident_by_severity: NameValue[]
  incident_trend: { period: string; incidents: number }[]
  root_cause_distribution: NameValue[]
  resolution_time_trend: { period: string; avg_minutes: number }[]
  service_availability: { service: string; availability: number; checks: number }[]
  recent_incidents: { id: string; ticket_number: string; title: string; severity: string | null; status: string; occurred_at: string }[]
}

export interface IncidentScenario { id: string; name: string; description: string; incident_id: string | null; ticket_number: string | null; prefill: { title: string; description: string; affected_unit: string | null; affected_service: string | null; occurred_at: string } | null }

export interface Health { status: string; database: string; rag: string; mcp: string; llm: string; mode: string; demo_mode: boolean; rag_detail?: { sop_chunks: number; historical_incidents: number; embedding: string } }

export interface AiConfig {
  mode: string
  llm: { provider: string; model: string; available: boolean }
  embedding: { name: string; dim: number; configured_model: string; backend: string }
  retrieval_weights: Record<string, number>
  hypothesis_weights: Record<string, number>
  top_k: number
  history_half_life_days: number
  sop_half_life_days: number
  log_half_life_minutes: number
  correlation_window_minutes: number
  min_confidence_for_root_cause: number
  demo_mode: boolean
  mcp: { url: string; transport: string; healthy: boolean; tools: string[]; read_only: boolean }
}

export interface ExperimentResult { id: string; name: string; description: string; n: number; metrics: Record<string, number | null> }
export interface BenchmarkResult {
  available: boolean
  message?: string
  generated_at?: string
  benchmark_size?: number
  k?: number
  embedding?: string
  classifier?: string
  experiments?: ExperimentResult[]
  notes?: string[]
  run_state?: { status: string; error?: string }
}

export interface InvestigationAnalytics {
  total: number
  completed: number
  failed: number
  avg_duration_ms: number | null
  avg_confidence: number | null
  direct_evidence_share: number | null
  root_cause_distribution: NameValue[]
  recent: { id: string; incident_id: string; confidence: number | null; root_cause_category: string | null; duration_ms: number | null; ai_mode: string | null; started_at: string }[]
}

export interface CompareResult { reproducible: boolean; same_top_hypothesis: boolean; same_tools: boolean; same_evidence_content: boolean; confidence_a: number | null; confidence_b: number | null; confidence_delta: number }

export interface EvidenceRow {
  id: string
  evidence_key: string
  source_type: string
  source_id: string | null
  evidence_text: string
  kind: string
  role: string
  evidence_timestamp: string | null
  temporal_relation: string | null
  relevance_score: number
  temporal_score: number | null
  confidence_contribution: number | null
  priority_rank: number
  tags: string[]
  hypothesis_ids: Record<string, string>
}

export interface AuthUser { id: string; name: string; email: string; role: string }
