from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Category(str, Enum):
    BILLING_PAYMENTS = "Billing & Payments"
    ACCOUNT_ACCESS = "Account & Access"
    PERFORMANCE_RELIABILITY = "Performance & Reliability"
    FUNCTIONAL_ISSUES = "Functional Issues"
    FEATURE_REQUESTS = "Feature Requests & Enhancements"
    USABILITY_UX = "Usability & User Experience"
    SUPPORT_EXPERIENCE = "Support Experience"
    OTHER = "Other"


class Theme(str, Enum):
    FAILED_PAYMENT = "Failed Payment"
    DUPLICATE_CHARGE = "Duplicate Charge"
    REFUND_DELAY = "Refund Delay"
    UNEXPECTED_CHARGE = "Unexpected Charge"
    SUBSCRIPTION_RENEWAL_ISSUE = "Subscription/Renewal Issue"

    LOGIN_FAILURE = "Login Failure"
    PASSWORD_RESET = "Password Reset"
    OTP_2FA_PROBLEM = "OTP/2FA Problem"
    ACCOUNT_LOCKED = "Account Locked"
    PROFILE_SETTINGS_ISSUE = "Profile Settings Issue"

    APP_CRASH = "App Crash"
    SLOW_PERFORMANCE = "Slow Performance"
    DOWNTIME_OUTAGE = "Downtime/Outage"
    TIMEOUT_ERROR = "Timeout Error"
    HIGH_RESOURCE_USAGE = "High Resource Usage"

    FUNCTION_NOT_WORKING = "Function Not Working"
    INCORRECT_DATA_DISPLAYED = "Incorrect Data Displayed"
    UI_ELEMENT_BROKEN = "UI Element Broken"
    SYNC_ISSUE = "Sync Issue"
    VALIDATION_ERROR = "Validation Error"

    NEW_FEATURE_REQUEST = "New Feature Request"
    ENHANCEMENT_REQUEST = "Enhancement Request"
    INTEGRATION_REQUEST = "Integration Request"
    WORKFLOW_IMPROVEMENT = "Workflow Improvement"

    CONFUSING_NAVIGATION = "Confusing Navigation"
    POOR_LAYOUT = "Poor Layout"
    HARD_TO_FIND_FEATURE = "Hard to Find Feature"
    ACCESSIBILITY_ISSUE = "Accessibility Issue"
    POSITIVE_EXPERIENCE = "Positive Experience"

    SLOW_RESPONSE = "Slow Response"
    UNHELPFUL_AGENT = "Unhelpful Agent"
    ISSUE_UNRESOLVED = "Issue Unresolved"
    DIFFICULT_TO_REACH_SUPPORT = "Difficult to Reach Support"

    GENERAL_FEEDBACK = "General Feedback"
    UNCLEAR = "Unclear"


class Sentiment(str, Enum):
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class Urgency(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


CATEGORY_THEMES: dict[Category, list[Theme]] = {
    Category.BILLING_PAYMENTS: [
        Theme.FAILED_PAYMENT,
        Theme.DUPLICATE_CHARGE,
        Theme.REFUND_DELAY,
        Theme.UNEXPECTED_CHARGE,
        Theme.SUBSCRIPTION_RENEWAL_ISSUE,
    ],
    Category.ACCOUNT_ACCESS: [
        Theme.LOGIN_FAILURE,
        Theme.PASSWORD_RESET,
        Theme.OTP_2FA_PROBLEM,
        Theme.ACCOUNT_LOCKED,
        Theme.PROFILE_SETTINGS_ISSUE,
    ],
    Category.PERFORMANCE_RELIABILITY: [
        Theme.APP_CRASH,
        Theme.SLOW_PERFORMANCE,
        Theme.DOWNTIME_OUTAGE,
        Theme.TIMEOUT_ERROR,
        Theme.HIGH_RESOURCE_USAGE,
    ],
    Category.FUNCTIONAL_ISSUES: [
        Theme.FUNCTION_NOT_WORKING,
        Theme.INCORRECT_DATA_DISPLAYED,
        Theme.UI_ELEMENT_BROKEN,
        Theme.SYNC_ISSUE,
        Theme.VALIDATION_ERROR,
    ],
    Category.FEATURE_REQUESTS: [
        Theme.NEW_FEATURE_REQUEST,
        Theme.ENHANCEMENT_REQUEST,
        Theme.INTEGRATION_REQUEST,
        Theme.WORKFLOW_IMPROVEMENT,
    ],
    Category.USABILITY_UX: [
        Theme.CONFUSING_NAVIGATION,
        Theme.POOR_LAYOUT,
        Theme.HARD_TO_FIND_FEATURE,
        Theme.ACCESSIBILITY_ISSUE,
        Theme.POSITIVE_EXPERIENCE,
    ],
    Category.SUPPORT_EXPERIENCE: [
        Theme.SLOW_RESPONSE,
        Theme.UNHELPFUL_AGENT,
        Theme.ISSUE_UNRESOLVED,
        Theme.DIFFICULT_TO_REACH_SUPPORT,
    ],
    Category.OTHER: [
        Theme.GENERAL_FEEDBACK,
        Theme.UNCLEAR,
    ],
}

CATEGORY_SCOPE: dict[Category, str] = {
    Category.BILLING_PAYMENTS: "Charges, refunds, failed/duplicate payments, invoices, subscription/pricing.",
    Category.ACCOUNT_ACCESS: "Login, passwords, OTP/2FA, lockouts, profile/permission settings.",
    Category.PERFORMANCE_RELIABILITY: (
        "The app fails to run properly: crashes, slowness, freezes, downtime, timeouts."
    ),
    Category.FUNCTIONAL_ISSUES: (
        "The app runs but behaves wrong: a feature misbehaves, data is incorrect, sync/validation errors."
    ),
    Category.FEATURE_REQUESTS: "Requests for a new capability or improvements to an existing one.",
    Category.USABILITY_UX: "Works, but confusing, awkward, or hard to navigate; also positive UX feedback.",
    Category.SUPPORT_EXPERIENCE: (
        "Feedback about the support process itself: response time, agent quality, resolution."
    ),
    Category.OTHER: "Uncategorized, unclear, or general feedback.",
}


class AdditionalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    theme: Theme
    urgency: Urgency

    @model_validator(mode="after")
    def theme_belongs_to_category(self) -> "AdditionalIssue":
        if self.theme not in CATEGORY_THEMES[self.category]:
            raise ValueError(
                f"theme '{self.theme.value}' does not belong to category '{self.category.value}'"
            )
        return self


class LLMClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_category: Category
    primary_theme: Theme
    sentiment: Sentiment
    urgency: Urgency
    actionable: bool
    additional_issues: list[AdditionalIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def primary_theme_belongs_to_category(self) -> "LLMClassification":
        if self.primary_theme not in CATEGORY_THEMES[self.primary_category]:
            raise ValueError(
                f"primary_theme '{self.primary_theme.value}' does not belong to "
                f"primary_category '{self.primary_category.value}'"
            )
        return self


class TicketClassification(LLMClassification):
    ticket_id: str
    feedback_text: str = ""


def fallback_classification(ticket_id: str, feedback_text: str = "") -> TicketClassification:
    return TicketClassification(
        ticket_id=ticket_id,
        feedback_text=feedback_text,
        primary_category=Category.OTHER,
        primary_theme=Theme.UNCLEAR,
        sentiment=Sentiment.NEUTRAL,
        urgency=Urgency.LOW,
        actionable=False,
        additional_issues=[],
    )


class ValidationReport(BaseModel):
    total_rows: int
    processed: int
    skipped: int
    skip_reasons: dict[str, int]


class RankedCount(BaseModel):
    name: str
    count: int


class AnalyticsResult(BaseModel):
    total_processed: int
    total_skipped: int
    category_distribution: dict[str, int]
    sentiment_distribution: dict[str, int]
    theme_frequency: dict[str, int]
    urgency_distribution: dict[str, int]
    urgency_distribution_with_additional: dict[str, int]
    actionable_count: int
    top_categories: list[RankedCount]
    top_themes: list[RankedCount]
    processing_success_rate: float
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    high_urgency_count: int


class AnalyzeResponse(BaseModel):
    validation_report: ValidationReport
    items: list[TicketClassification]
    analytics: AnalyticsResult
    summary: str
