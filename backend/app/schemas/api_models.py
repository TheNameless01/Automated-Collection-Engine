"""Pydantic request and response schemas for DZ Car Rental Finder API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CollectionStartRequest(BaseModel):
    wilaya_codes: list[int] = Field(default_factory=list)
    commune_ids: list[int] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    search_depth: Literal["quick", "standard", "deep"] = "standard"
    notes: str = ""


class BusinessCreateRequest(BaseModel):
    primary_name: str = Field(min_length=2, max_length=200)
    name_ar: str = ""
    name_fr: str = ""
    name_en: str = ""
    primary_phone: str = ""
    full_address: str = ""
    wilaya_code: int | None = None
    commune_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    website: str = ""
    facebook_url: str = ""
    instagram_url: str = ""
    google_maps_url: str = ""
    notes: str = ""


class BusinessUpdateRequest(BaseModel):
    primary_name: str | None = None
    name_ar: str | None = None
    name_fr: str | None = None
    name_en: str | None = None
    primary_phone: str | None = None
    full_address: str | None = None
    wilaya_code: int | None = None
    commune_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    website: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    google_maps_url: str | None = None
    verification_status: Literal["VERIFIED", "UNVERIFIED", "NEEDS_REVIEW", "CLOSED"] | None = None
    notes: str | None = None
    review_notes: str = ""


class DuplicateResolveRequest(BaseModel):
    decision: Literal["merge_into_a", "merge_into_b", "reject_separate"]
    notes: str = ""


class SourceUpdateRequest(BaseModel):
    enabled: bool | None = None
    rate_limit_seconds: float | None = Field(default=None, ge=0.0, le=60.0)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    config: dict[str, Any] | None = None


class ExportCreateRequest(BaseModel):
    format: Literal["xlsx", "csv"] = "xlsx"
    scope: Literal["all", "selected_wilayas", "selected_records", "verified_only", "review_required"] = "all"
    wilaya_codes: list[int] = Field(default_factory=list)
    business_ids: list[int] = Field(default_factory=list)


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any]


class RestoreBackupRequest(BaseModel):
    filename: str
