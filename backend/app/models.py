from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


ROLES = ("supporter", "founder", "verification_reviewer", "admin")
FUNDING_MODELS = ("donation", "reward", "business_support", "investment")
CAMPAIGN_STATUSES = (
    "draft",
    "submitted",
    "changes_requested",
    "approved",
    "published",
    "rejected",
    "suspended",
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="supporter")
    email_verified_at = db.Column(db.DateTime(timezone=True))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Bumped on password reset / account deletion; sessions carrying an older value stop working.
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at = db.Column(db.DateTime(timezone=True))


class BusinessProfile(db.Model):
    __tablename__ = "business_profiles"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    industry = db.Column(db.String(100))
    stage = db.Column(db.String(60))
    country = db.Column(db.String(80), default="South Africa")
    province = db.Column(db.String(80))
    city = db.Column(db.String(80))
    founded_on = db.Column(db.Date)
    website = db.Column(db.String(255))
    description = db.Column(db.Text)
    problem = db.Column(db.Text)
    solution = db.Column(db.Text)
    target_customers = db.Column(db.Text)
    business_model = db.Column(db.Text)
    competitive_advantage = db.Column(db.Text)
    # Public vs confidential is explicit: contact details are private unless the owner opts in.
    public_contact_email = db.Column(db.String(255))
    contact_is_public = db.Column(db.Boolean, nullable=False, default=False)
    logo_key = db.Column(db.String(255))  # private storage key; served via signed URL
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    PUBLIC_FIELDS = (
        "slug", "name", "industry", "stage", "country", "province", "city",
        "website", "description", "problem", "solution", "target_customers",
        "business_model", "competitive_advantage",
    )


class BusinessProfileRevision(db.Model):
    """Snapshot of a profile's material fields each time they change."""

    __tablename__ = "business_profile_revisions"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("business_profiles.id"), nullable=False, index=True)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    changed_fields = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("business_profiles.id"), nullable=False, index=True)
    slug = db.Column(db.String(180), unique=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    summary = db.Column(db.String(400))
    description = db.Column(db.Text)
    location = db.Column(db.String(160))
    stage = db.Column(db.String(60))
    objectives = db.Column(db.Text)
    funding_model = db.Column(db.String(32))
    currency = db.Column(db.String(3), nullable=False, default="ZAR")
    goal_cents = db.Column(db.BigInteger)
    duration_days = db.Column(db.Integer)
    funding_purpose = db.Column(db.Text)
    # [{"item": str, "amount_cents": int}] - owner-reported, not verified.
    use_of_funds = db.Column(JSONB, nullable=False, default=list)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    review_note = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime(timezone=True))
    published_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    cover_image_key = db.Column(db.String(255))  # private storage key; served via signed URL

    profile = db.relationship("BusinessProfile")
    milestones = db.relationship(
        "CampaignMilestone", order_by="CampaignMilestone.position", cascade="all, delete-orphan"
    )


class CampaignMilestone(db.Model):
    __tablename__ = "campaign_milestones"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text)
    target_date = db.Column(db.Date)


class ModerationDecision(db.Model):
    __tablename__ = "moderation_decisions"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(24), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class PitchDeck(db.Model):
    __tablename__ = "pitch_decks"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    content_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    page_count = db.Column(db.Integer)
    extracted_text = db.Column(db.Text)
    processing_status = db.Column(db.String(24), nullable=False, default="uploaded")
    processing_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class PitchDeckAnalysis(db.Model):
    __tablename__ = "pitch_deck_analyses"

    id = db.Column(db.Integer, primary_key=True)
    pitch_deck_id = db.Column(db.Integer, db.ForeignKey("pitch_decks.id"), nullable=False, index=True)
    provider = db.Column(db.String(60), nullable=False)
    methodology_version = db.Column(db.String(30), nullable=False)
    report = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class AiUsage(db.Model):
    __tablename__ = "ai_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    feature = db.Column(db.String(60), nullable=False)
    provider = db.Column(db.String(60), nullable=False)
    input_chars = db.Column(db.Integer, nullable=False, default=0)
    ok = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    target_type = db.Column(db.String(60))
    target_id = db.Column(db.Integer)
    detail = db.Column(JSONB)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class DeckDraft(db.Model):
    """A pitch deck being built from the guided questionnaire."""

    __tablename__ = "deck_drafts"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    theme = db.Column(db.String(30), nullable=False, default="classic")
    answers = db.Column(JSONB, nullable=False, default=dict)
    slides = db.Column(JSONB, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailToken(db.Model):
    """Single-use token for email verification or password reset. Only a hash is stored."""

    __tablename__ = "email_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class EmailOutbox(db.Model):
    """Development mail sink. Replace with a real provider before launch."""

    __tablename__ = "email_outbox"

    id = db.Column(db.Integer, primary_key=True)
    to_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(24), nullable=False)  # contribution | pitch_deck_fee
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), index=True)
    pitch_deck_id = db.Column(db.Integer, db.ForeignKey("pitch_decks.id"), index=True)
    amount_cents = db.Column(db.BigInteger, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="ZAR")
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    provider = db.Column(db.String(30), nullable=False)
    provider_ref = db.Column(db.String(80), nullable=False, unique=True, index=True)
    checkout_url = db.Column(db.String(500))
    # True for test-mode providers. Simulated money is never counted as raised or as revenue.
    simulated = db.Column(db.Boolean, nullable=False)
    idempotency_key = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    confirmed_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_payment_user_idem"),)


class PaymentEvent(db.Model):
    """Every webhook delivery, kept for audit and de-duplication."""

    __tablename__ = "payment_events"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(30), nullable=False)
    event_id = db.Column(db.String(120), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    payload = db.Column(JSONB, nullable=False)
    processed = db.Column(db.Boolean, nullable=False, default=False)
    error = db.Column(db.String(200))
    received_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_payment_event"),)


class Refund(db.Model):
    __tablename__ = "refunds"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False, index=True)
    amount_cents = db.Column(db.BigInteger, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="requested")  # requested | succeeded | failed
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))


class Follow(db.Model):
    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "campaign_id", name="uq_follow"),)


class CampaignUpdate(db.Model):
    __tablename__ = "campaign_updates"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    hidden_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


VERIFICATION_KINDS = ("identity", "business_registration", "proof_of_address", "bank_confirmation")
VERIFICATION_STATUSES = ("pending", "approved", "rejected", "info_requested", "escalated")


class VerificationDocument(db.Model):
    __tablename__ = "verification_documents"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    content_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    reviewer_note = db.Column(db.Text)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class CampaignTransparency(db.Model):
    """An owner-approved statement generated only from the owner's own campaign data."""
    __tablename__ = "campaign_transparency"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, unique=True)
    sections = db.Column(JSONB, nullable=False, default=list)
    owner_notes = db.Column(JSONB, nullable=False, default=dict)
    source_hash = db.Column(db.String(64), nullable=False)
    provider = db.Column(db.String(60), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="draft")  # draft | approved
    approved_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
