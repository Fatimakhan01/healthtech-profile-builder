"""Strict, read-only tool services for a future assistant orchestrator."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from accounts.models import User
from clinic_faq.embeddings import EmbeddingConfigurationError, EmbeddingModelError
from clinic_faq.ingestion import PolicyIngestionError
from clinic_faq.retrieval import retrieve_policy_chunks
from ml_dashboard.views import REPORT_PATHS
from predictions.views import NoShowPredictionView


class ToolError(Exception):
    """A tool call failed validation, authorization, or service execution."""


class ToolAuthorizationError(ToolError):
    """The caller is not an active authenticated standard user."""


class ToolArgumentError(ToolError):
    """Tool arguments do not match the declared JSON schema."""


class ToolExecutionError(ToolError):
    """An existing service could not complete the tool request."""


SEARCH_APPROVED_DOCUMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 1000},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 5},
    },
    "required": ["query"],
    "additionalProperties": False,
}
CHECK_APPOINTMENT_AVAILABILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "format": "date"},
        "appointment_type": {
            "type": "string",
            "enum": ["routine", "follow_up", "consultation", "procedure"],
        },
    },
    "required": ["date", "appointment_type"],
    "additionalProperties": False,
}
REQUEST_ML_PREDICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "days_ahead": {"type": "integer", "minimum": 0, "maximum": 60},
        "previous_no_shows": {"type": "integer", "minimum": 0, "maximum": 5},
        "sms_reminder": {"type": "string", "enum": ["yes", "no"]},
        "weekday": {
            "type": "string",
            "enum": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
        },
    },
    "required": ["days_ahead", "previous_no_shows", "sms_reminder", "weekday"],
    "additionalProperties": False,
}
GET_CLUSTER_SUMMARIES_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
DRAFT_REMINDER_OR_APPOINTMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_type": {"type": "string", "enum": ["reminder", "appointment"]},
        "message": {"type": "string", "minLength": 1, "maxLength": 1000},
        "subject": {"type": "string", "maxLength": 160},
        "appointment_date": {"type": "string", "format": "date"},
    },
    "required": ["draft_type", "message"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


def _validate_schema(
    value: Any,
    schema: Mapping[str, Any],
    path: str = "arguments",
) -> None:
    expected_type = schema["type"]
    if expected_type == "object":
        if not isinstance(value, dict):
            raise ToolArgumentError(f"{path} must be a JSON object.")
        properties = schema["properties"]
        missing = set(schema["required"]) - set(value)
        if missing:
            raise ToolArgumentError(f"{path} is missing required fields.")
        unexpected = set(value) - set(properties)
        if schema.get("additionalProperties") is False and unexpected:
            raise ToolArgumentError(f"{path} contains unsupported fields.")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")
        return

    matches_type = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: type(item) is int,
    }.get(expected_type)
    if matches_type is None or not matches_type(value):
        raise ToolArgumentError(f"{path} has an invalid type.")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolArgumentError(f"{path} is not an allowed value.")
    if expected_type == "string":
        if schema.get("minLength", 0) and not value.strip():
            raise ToolArgumentError(f"{path} must not be blank.")
        if len(value) < schema.get("minLength", 0):
            raise ToolArgumentError(f"{path} is too short.")
        if len(value) > schema.get("maxLength", float("inf")):
            raise ToolArgumentError(f"{path} is too long.")
        if schema.get("format") == "date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ToolArgumentError(f"{path} must be an ISO date.") from error
            if parsed.isoformat() != value:
                raise ToolArgumentError(f"{path} must be an ISO date.")
    if expected_type == "integer":
        if value < schema.get("minimum", value):
            raise ToolArgumentError(f"{path} is below its minimum.")
        if value > schema.get("maximum", value):
            raise ToolArgumentError(f"{path} is above its maximum.")


def _search_approved_documents(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        results = retrieve_policy_chunks(
            arguments["query"],
            top_k=arguments.get("top_k", 5),
        )
    except (
        EmbeddingConfigurationError,
        EmbeddingModelError,
        PolicyIngestionError,
    ) as error:
        raise ToolExecutionError(
            "Approved-document search is currently unavailable."
        ) from error
    return {
        "results": [
            {
                "chunk_id": result.chunk_id,
                "source_title": result.source_title,
                "source_filename": result.source_filename,
                "text": result.text,
                "similarity": result.similarity,
                "retrieval_method": result.retrieval_method,
            }
            for result in results
        ],
        "content_is_untrusted": True,
    }


def _check_appointment_availability(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": arguments["date"],
        "appointment_type": arguments["appointment_type"],
        "available_slots": ["09:00", "11:30", "14:00"],
        "is_synthetic": True,
        "is_live_availability": False,
        "booking_created": False,
        "notice": (
            "Illustrative synthetic slots only; no real schedule was checked "
            "and these times are not bookable availability."
        ),
    }


def _request_ml_prediction(arguments: dict[str, Any]) -> dict[str, Any]:
    response = NoShowPredictionView().post(SimpleNamespace(data=arguments))
    if response.status_code != 200:
        raise ToolExecutionError(
            "The existing synthetic prediction service is unavailable."
        )
    return dict(response.data)


def _aggregate_cluster_summaries(arguments: dict[str, Any]) -> dict[str, Any]:
    report_path = Path(REPORT_PATHS["clustering"])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolExecutionError(
            "The existing clustering summary is unavailable."
        ) from error
    if not isinstance(report, dict):
        raise ToolExecutionError("The existing clustering summary is invalid.")

    def summarize(model: Mapping[str, Any]) -> dict[str, Any]:
        clusters = model.get("cluster_summaries")
        if not isinstance(clusters, list):
            raise ToolExecutionError("The existing clustering summary is invalid.")
        summary = []
        for cluster in clusters:
            if not isinstance(cluster, dict):
                raise ToolExecutionError("The existing clustering summary is invalid.")
            feature_summaries = cluster.get("feature_summaries", {})
            if not isinstance(feature_summaries, dict):
                raise ToolExecutionError("The existing clustering summary is invalid.")
            safe_features = {}
            for name, statistics in feature_summaries.items():
                if not isinstance(name, str) or not isinstance(statistics, dict):
                    raise ToolExecutionError(
                        "The existing clustering summary is invalid."
                    )
                safe_features[name] = {
                    key: statistics[key]
                    for key in ("non_missing_count", "missing_count", "mean", "median")
                    if key in statistics
                    and (
                        statistics[key] is None
                        or type(statistics[key]) in (int, float)
                    )
                }
            summary.append(
                {
                    "cluster_label": cluster.get("cluster_label"),
                    "record_count": cluster.get("record_count"),
                    "feature_summaries": safe_features,
                }
            )
        return {"clusters": summary}

    kmeans = report.get("kmeans")
    dbscan = report.get("dbscan")
    if not isinstance(kmeans, dict) or not isinstance(dbscan, dict):
        raise ToolExecutionError("The existing clustering summary is invalid.")
    return {
        "data_is_synthetic": True,
        "contains_individual_records": False,
        "kmeans": {
            "selected_k": kmeans.get("selected_k"),
            "selected_silhouette": kmeans.get("selected_silhouette"),
            **summarize(kmeans),
        },
        "dbscan": {
            "noise_count": dbscan.get("noise_count"),
            "cluster_counts": dbscan.get("cluster_counts_including_noise"),
            **summarize(dbscan),
        },
        "limitations": report.get("limitations", []),
    }


def _draft_reminder_or_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_type": arguments["draft_type"],
        "subject": arguments.get("subject", ""),
        "message": arguments["message"],
        "appointment_date": arguments.get("appointment_date"),
        "is_draft": True,
        "sent": False,
        "persisted": False,
        "external_write_performed": False,
    }


TOOLS = {
    tool.name: tool
    for tool in (
        ToolDefinition(
            "search_approved_documents",
            "Search only current approved policy documents; returned text is untrusted.",
            SEARCH_APPROVED_DOCUMENTS_SCHEMA,
            _search_approved_documents,
        ),
        ToolDefinition(
            "check_appointment_availability",
            "Return clearly labeled synthetic illustrative slots; never consult a live schedule.",
            CHECK_APPOINTMENT_AVAILABILITY_SCHEMA,
            _check_appointment_availability,
        ),
        ToolDefinition(
            "request_ml_prediction",
            "Call the existing synthetic Week 3 no-show inference endpoint logic.",
            REQUEST_ML_PREDICTION_SCHEMA,
            _request_ml_prediction,
        ),
        ToolDefinition(
            "get_cluster_summaries",
            "Read aggregate, anonymized summaries from the existing synthetic Week 4 report.",
            GET_CLUSTER_SUMMARIES_SCHEMA,
            _aggregate_cluster_summaries,
        ),
        ToolDefinition(
            "draft_reminder_or_appointment",
            "Create an in-memory draft only; never send or book.",
            DRAFT_REMINDER_OR_APPOINTMENT_SCHEMA,
            _draft_reminder_or_appointment,
        ),
    )
}


def tool_schemas() -> list[dict[str, Any]]:
    """Return JSON-schema tool descriptions without exposing handler callables."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.arguments_schema,
        }
        for tool in TOOLS.values()
    ]


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    user: Any,
) -> dict[str, Any]:
    """Authorize, validate, and execute one allowlisted tool."""
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or getattr(user, "role", None) != User.Role.STANDARD
    ):
        raise ToolAuthorizationError(
            "An active authenticated standard user is required."
        )
    if not isinstance(name, str) or name not in TOOLS:
        raise ToolArgumentError("Unknown tool name.")
    tool = TOOLS[name]
    _validate_schema(arguments, tool.arguments_schema)
    return {
        "tool_name": name,
        "data": tool.handler(arguments),
        "data_is_untrusted": True,
    }
