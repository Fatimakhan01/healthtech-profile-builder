import hashlib
import hmac
import importlib.metadata
import io
import json
import logging
import os
import platform
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import NoShowPredictionSerializer


logger = logging.getLogger(__name__)
FEATURE_NAMES = (
    "days_ahead",
    "previous_no_shows",
    "sms_reminder",
    "weekday",
)
MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "ml"
    / "artifacts"
    / "no_show_pipeline.joblib"
)
MODEL_METADATA_PATH = MODEL_PATH.with_name("no_show_pipeline.metadata.json")
ARTIFACT_DIGEST_ENV = "NO_SHOW_MODEL_SHA256"
METADATA_DIGEST_ENV = "NO_SHOW_MODEL_METADATA_SHA256"
DEPENDENCIES = ("joblib", "numpy", "pandas", "scikit-learn", "scipy")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPERIMENTAL_NOTICE = (
    "Experimental prediction from a fully synthetic educational dataset; "
    "not a clinical or real-world risk estimate."
)


class ModelArtifactUnavailable(Exception):
    pass


def make_feature_frame(values):
    import pandas as pd

    return pd.DataFrame([values], columns=FEATURE_NAMES)


def _configured_digest(name):
    digest = os.environ.get(name, "").strip().lower()
    if not SHA256_PATTERN.fullmatch(digest):
        raise ModelArtifactUnavailable(f"{name} must be configured as a SHA-256.")
    return digest


def _validate_metadata(metadata, expected_artifact_digest):
    if not isinstance(metadata, dict):
        raise ModelArtifactUnavailable("Artifact metadata must be a JSON object.")

    required_fields = {
        "metadata_schema_version",
        "model_version",
        "artifact_sha256",
        "feature_names",
        "positive_class",
        "python_version",
        "dependencies",
    }
    if not required_fields.issubset(metadata):
        raise ModelArtifactUnavailable("Artifact metadata is incomplete.")
    if type(metadata["metadata_schema_version"]) is not int or metadata[
        "metadata_schema_version"
    ] != 1:
        raise ModelArtifactUnavailable("Artifact metadata schema is unsupported.")
    if (
        not isinstance(metadata["model_version"], str)
        or not metadata["model_version"].strip()
    ):
        raise ModelArtifactUnavailable("Artifact model version is invalid.")
    if metadata["model_version"] != f"no-show-{expected_artifact_digest}":
        raise ModelArtifactUnavailable("Artifact version is not bound to its digest.")
    if metadata["feature_names"] != list(FEATURE_NAMES):
        raise ModelArtifactUnavailable("Artifact feature schema does not match.")
    if type(metadata["positive_class"]) is not int or metadata["positive_class"] != 1:
        raise ModelArtifactUnavailable("Artifact positive class must be no_show=1.")
    if metadata["artifact_sha256"] != expected_artifact_digest:
        raise ModelArtifactUnavailable("Metadata does not identify this artifact.")
    if metadata["python_version"] != platform.python_version():
        raise ModelArtifactUnavailable("Artifact Python version is incompatible.")

    dependency_versions = metadata["dependencies"]
    if not isinstance(dependency_versions, dict) or set(dependency_versions) != set(
        DEPENDENCIES
    ):
        raise ModelArtifactUnavailable("Artifact dependency metadata is invalid.")
    for dependency in DEPENDENCIES:
        try:
            installed_version = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelArtifactUnavailable(
                f"Required dependency {dependency} is unavailable."
            ) from error
        if dependency_versions[dependency] != installed_version:
            raise ModelArtifactUnavailable(
                f"Artifact dependency {dependency} is incompatible."
            )


def _validate_pipeline(model):
    if not callable(getattr(model, "predict", None)):
        raise ModelArtifactUnavailable("Artifact does not support prediction.")
    if not callable(getattr(model, "predict_proba", None)):
        raise ModelArtifactUnavailable("Artifact does not support probabilities.")

    feature_names = getattr(model, "feature_names_in_", None)
    if feature_names is None or tuple(feature_names) != FEATURE_NAMES:
        raise ModelArtifactUnavailable("Artifact feature schema does not match.")

    classes = getattr(model, "classes_", None)
    if classes is None:
        raise ModelArtifactUnavailable("Artifact classes are unavailable.")
    class_values = list(classes)
    if (
        len(class_values) != 2
        or sum(value == 0 for value in class_values) != 1
        or sum(value == 1 for value in class_values) != 1
    ):
        raise ModelArtifactUnavailable("Artifact classes must include 0 and 1.")


@lru_cache(maxsize=1)
def _load_verified_pipeline(expected_artifact_digest, expected_metadata_digest):
    try:
        artifact_bytes = MODEL_PATH.read_bytes()
        actual_artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
        if not hmac.compare_digest(
            actual_artifact_digest,
            expected_artifact_digest,
        ):
            raise ModelArtifactUnavailable("Model artifact digest does not match.")

        metadata_bytes = MODEL_METADATA_PATH.read_bytes()
        actual_metadata_digest = hashlib.sha256(metadata_bytes).hexdigest()
        if not hmac.compare_digest(actual_metadata_digest, expected_metadata_digest):
            raise ModelArtifactUnavailable("Model metadata digest does not match.")
        metadata = json.loads(metadata_bytes)
        _validate_metadata(metadata, expected_artifact_digest)

        import joblib

        model = joblib.load(io.BytesIO(artifact_bytes))
        _validate_pipeline(model)
        return model, metadata
    except Exception as error:
        if isinstance(error, ModelArtifactUnavailable):
            raise
        raise ModelArtifactUnavailable from error


def load_pipeline():
    try:
        artifact_digest = _configured_digest(ARTIFACT_DIGEST_ENV)
        metadata_digest = _configured_digest(METADATA_DIGEST_ENV)
        return _load_verified_pipeline(artifact_digest, metadata_digest)
    except ModelArtifactUnavailable:
        logger.exception("Could not verify the synthetic no-show model configuration.")
        raise


load_pipeline.cache_clear = _load_verified_pipeline.cache_clear


class NoShowPredictionView(APIView):
    def post(self, request):
        serializer = NoShowPredictionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            model, metadata = load_pipeline()
            features = make_feature_frame(serializer.validated_data)
            predicted_values = np.asarray(model.predict(features))
            if predicted_values.shape != (1,) or predicted_values[0] not in (0, 1):
                raise ValueError("Model returned an invalid predicted class.")
            predicted_class = int(predicted_values[0])

            classes = list(model.classes_)
            positive_class_index = classes.index(metadata["positive_class"])
            probabilities = np.asarray(model.predict_proba(features), dtype=float)
            if probabilities.shape != (1, len(classes)):
                raise ValueError("Model returned an invalid probability shape.")
            if (
                not np.isfinite(probabilities).all()
                or (probabilities < 0).any()
                or (probabilities > 1).any()
                or not np.isclose(probabilities.sum(axis=1), 1.0).all()
            ):
                raise ValueError("Model returned invalid probabilities.")
            probability_no_show = float(probabilities[0][positive_class_index])
        except ModelArtifactUnavailable:
            return self._unavailable_response()
        except Exception:
            logger.exception("Could not produce a synthetic no-show prediction.")
            return self._unavailable_response()

        return Response(
            {
                "model_version": metadata["model_version"],
                "predicted_class": predicted_class,
                "predicted_label": "no_show" if predicted_class == 1 else "attended",
                "probability_no_show": probability_no_show,
                "notice": EXPERIMENTAL_NOTICE,
            }
        )

    @staticmethod
    def _unavailable_response():
        return Response(
            {"detail": "The prediction model is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
