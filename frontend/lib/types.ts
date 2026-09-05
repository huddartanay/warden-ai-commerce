// TypeScript types mirroring the backend schemas. Kept intentionally
// permissive (readonly-optional) because the backend adds fields
// non-breakingly and the UI should degrade gracefully when it does.

export type DecisionResult = "ALLOW" | "STEP_UP" | "BLOCK";

export type ActionStatus =
  | "PROPOSED"
  | "ALLOWED"
  | "BLOCKED"
  | "STEP_UP_PENDING"
  | "STEP_UP_APPROVED"
  | "STEP_UP_REJECTED"
  | "PAYMENT_INITIATED"
  | "PAYMENT_COMPLETED"
  | "PAYMENT_FAILED"
  | "PENDING_UNRESOLVED"
  | "REFUNDED";

export type ResolutionStatus =
  | "PENDING_UNRESOLVED"
  | "REQUIRES_HUMAN"
  | "RESOLVED";

export type MandateStatus =
  | "ACTIVE"
  | "PARTIALLY_USED"
  | "EXHAUSTED"
  | "EXPIRED"
  | "REVOKED";

export interface CheckResult {
  name: string;
  ok: boolean;
  verdict: "PASS" | "STEP_UP" | "BLOCK";
  reason_code: string | null;
  detail: string;
}

export interface DecisionResponse {
  action_id: string;
  decision: DecisionResult;
  reason_code: string;
  explanation: string;
  checks_performed: CheckResult[];
  duplicate?: boolean;
}

export interface MandateSummary {
  id: string;
  customer_id: string;
  max_amount: string;
  currency: string;
  allowed_categories: string[];
  transaction_limit: number;
  status: MandateStatus;
  current_period_spend: string;
  current_period_transactions: number;
  step_up_over_amount: string | null;
}

export interface CartSummary {
  id: string;
  items: Array<{
    catalog_item_id: string;
    name: string;
    category: string;
    quantity: number;
    unit_price: string;
    line_total: string;
  }>;
  total_amount: string;
  currency: string;
  period: string;
}

export interface ActionSummary {
  id: string;
  mandate_id: string;
  cart_id: string | null;
  amount: string;
  currency: string;
  idempotency_key: string;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
}

export interface DecisionSummary {
  id: string;
  result: DecisionResult;
  reason_code: string;
  explanation: string;
  created_at: string;
}

export interface RazorpayRefSummary {
  id: string;
  ref_type: string;
  razorpay_id: string;
  status: string | null;
  raw_response?: Record<string, unknown> | null;
  created_at: string;
}

export interface ResolutionSummary {
  status: ResolutionStatus;
  note: string;
  resolved_by: string | null;
  resolved_at: string | null;
  updated_at: string;
}

export interface AuditEntry {
  seq: number;
  event_id: string;
  action_id: string | null;
  event_type: string;
  event_data: Record<string, unknown>;
  previous_hash: string;
  current_hash: string;
  timestamp: string;
}

export interface AuditListResponse {
  count: number;
  entries: AuditEntry[];
}

export interface AuditVerifyResponse {
  valid: boolean;
  entries_checked: number;
  first_invalid_entry: Record<string, unknown> | null;
}

export interface AgentContext {
  intent_text: string;
  parsed_intent: {
    desired_category: string;
    max_spend: string | null;
    quantity_hint: number | null;
    urgency: string;
    confidence: number;
    rationale: string;
  } | null;
  candidates: Array<{
    id: string;
    name: string;
    category: string;
    price: string;
    currency: string;
  }>;
  selected: Array<{
    catalog_item_id: string;
    quantity: number;
    unit_price: string;
  }>;
  confidence: number;
  verdict: DecisionResult;
  explanation: string;
}

export interface ScenarioEnvelope {
  scenario: string;
  action?: ActionSummary;
  decision?: DecisionSummary | null;
  cart?: CartSummary | null;
  mandate?: MandateSummary | null;
  razorpay_refs?: RazorpayRefSummary[];
  resolution?: ResolutionSummary | null;
  audit?: AuditEntry[];
  agent?: AgentContext | null;
  duplicate_of?: string;
  second_call_duplicate_flag?: boolean;
}

export interface RecentAction {
  action_id: string;
  mandate_id: string;
  amount: string;
  currency: string;
  status: ActionStatus;
  created_at: string;
  decision_result: DecisionResult | null;
  reason_code: string | null;
  razorpay_order_id: string | null;
}

export interface DemoSummary {
  mandate_count: number;
  action_count: number;
  pending_review_count: number;
  audit_entry_count: number;
  audit_chain_valid: boolean;
  audit_chain_reason: string | null;
  latest_action_id: string | null;
  allowed_count: number;
  blocked_count: number;
  step_up_count: number;
  protected_value: string;
  blocked_value: string;
  currency: string;
  recent_actions: RecentAction[];
}

export interface ActionDetail {
  action: ActionSummary;
  decision: DecisionSummary | null;
  razorpay_refs: RazorpayRefSummary[];
}
