import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import joblib
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from ml import train as ml_train

from . import views
from .views import DEPENDENCIES, FEATURE_NAMES, ModelArtifactUnavailable


class FakePipeline:
    classes_ = [0, 1]
    feature_names_in_ = FEATURE_NAMES

    def predict(self, features):
        return [1]

    def predict_proba(self, features):
        return [[0.27, 0.73]]


class PipelineWithoutProbabilities:
    classes_ = [0, 1]
    feature_names_in_ = FEATURE_NAMES

    def predict(self, features):
        return [1]


class PipelineWithInvalidProbabilities(FakePipeline):
    def predict_proba(self, features):
        return [[0.27]]


class PipelineWithNonFiniteProbabilities(FakePipeline):
    def predict_proba(self, features):
        return [[float("nan"), 0.73]]


class PipelineWithOutOfRangeProbabilities(FakePipeline):
    def predict_proba(self, features):
        return [[0.27, 1.73]]


class PipelineWithReorderedClasses(FakePipeline):
    classes_ = [1, 0]

    def predict_proba(self, features):
        return [[0.73, 0.27]]


class WrongSchemaPipeline(FakePipeline):
    feature_names_in_ = tuple(reversed(FEATURE_NAMES))


def build_metadata(artifact_digest, feature_names=None):
    return {
        "metadata_schema_version": 1,
        "model_version": f"no-show-{artifact_digest}",
        "display_version": "No-Show Model v1",
        "artifact_sha256": artifact_digest,
        "feature_names": list(feature_names or FEATURE_NAMES),
        "positive_class": 1,
        "python_version": platform.python_version(),
        "dependencies": {
            dependency: importlib.metadata.version(dependency)
            for dependency in DEPENDENCIES
        },
    }


class NoShowPredictionApiTests(SimpleTestCase):
    url = "/api/v1/predictions/no-show/"
    valid_payload = {
        "days_ahead": 14,
        "previous_no_shows": 1,
        "sms_reminder": "yes",
        "weekday": "Wednesday",
    }

    def setUp(self):
        self.client = APIClient()
        permissions_patch = patch.object(
            views.NoShowPredictionView,
            "permission_classes",
            [AllowAny],
        )
        permissions_patch.start()
        self.addCleanup(permissions_patch.stop)

    @patch("predictions.views.make_feature_frame", return_value=object())
    @patch(
        "predictions.views.load_pipeline",
        return_value=(
            FakePipeline(),
            {
                "model_version": "test-no-show-version",
                "display_version": "No-Show Model v1",
                "positive_class": 1,
            },
        ),
    )
    def test_valid_request_returns_synthetic_prediction(
        self,
        load_pipeline,
        make_feature_frame,
    ):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model_version"], "test-no-show-version")
        self.assertEqual(response.data["display_version"], "No-Show Model v1")
        self.assertEqual(response.data["predicted_class"], 1)
        self.assertEqual(response.data["predicted_label"], "no_show")
        self.assertEqual(response.data["probability_no_show"], 0.73)
        self.assertIn("synthetic", response.data["notice"])
        self.assertIn("not a clinical", response.data["notice"])
        load_pipeline.assert_called_once_with()
        make_feature_frame.assert_called_once_with(self.valid_payload)

    def test_invalid_values_and_types_return_bad_request(self):
        invalid_payloads = (
            {"days_ahead": -1},
            {"days_ahead": 61},
            {"days_ahead": True},
            {"days_ahead": "14"},
            {"previous_no_shows": -1},
            {"previous_no_shows": 6},
            {"previous_no_shows": 1.5},
            {"sms_reminder": "sometimes"},
            {"weekday": "Funday"},
        )
        for invalid_field in invalid_payloads:
            with self.subTest(invalid_field=invalid_field):
                payload = {**self.valid_payload, **invalid_field}
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_missing_fields_return_bad_request(self):
        for field in self.valid_payload:
            with self.subTest(missing_field=field):
                payload = {
                    key: value
                    for key, value in self.valid_payload.items()
                    if key != field
                }
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertIn(field, response.data)

    @patch("predictions.views.make_feature_frame", return_value=object())
    @patch(
        "predictions.views.load_pipeline",
        return_value=(
            FakePipeline(),
            {
                "model_version": "test-no-show-version",
                "display_version": "No-Show Model v1",
                "positive_class": 1,
            },
        ),
    )
    def test_response_contains_class_label_probability_and_notice(
        self,
        load_pipeline,
        make_feature_frame,
    ):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(
            set(response.data),
            {
                "model_version",
                "display_version",
                "predicted_class",
                "predicted_label",
                "probability_no_show",
                "notice",
            },
        )
        self.assertIsInstance(response.data["probability_no_show"], float)

    @patch("predictions.views.make_feature_frame", return_value=object())
    @patch(
        "predictions.views.load_pipeline",
        return_value=(
            PipelineWithInvalidProbabilities(),
            {
                "model_version": "test-no-show-version",
                "display_version": "No-Show Model v1",
                "positive_class": 1,
            },
        ),
    )
    def test_invalid_probability_output_returns_safe_server_error(
        self,
        load_pipeline,
        make_feature_frame,
    ):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data,
            {"detail": "The prediction model is temporarily unavailable."},
        )

    def test_probability_uses_actual_positive_class_index(self):
        with (
            patch(
                "predictions.views.make_feature_frame",
                return_value=object(),
            ),
            patch(
                "predictions.views.load_pipeline",
                return_value=(
                    PipelineWithReorderedClasses(),
                    {
                        "model_version": "test-no-show-version",
                        "display_version": "No-Show Model v1",
                        "positive_class": 1,
                    },
                ),
            ),
        ):
            response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["probability_no_show"], 0.73)

    def test_non_finite_and_out_of_range_probabilities_return_503(self):
        for model in (
            PipelineWithNonFiniteProbabilities(),
            PipelineWithOutOfRangeProbabilities(),
        ):
            with self.subTest(model=type(model).__name__):
                with (
                    patch(
                        "predictions.views.make_feature_frame",
                        return_value=object(),
                    ),
                    patch(
                        "predictions.views.load_pipeline",
                        return_value=(
                            model,
                            {
                                "model_version": "test-no-show-version",
                                "display_version": "No-Show Model v1",
                                "positive_class": 1,
                            },
                        ),
                    ),
                ):
                    response = self.client.post(
                        self.url,
                        self.valid_payload,
                        format="json",
                    )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

    @patch(
        "predictions.views.load_pipeline",
        side_effect=ModelArtifactUnavailable,
    )
    def test_unavailable_model_returns_safe_server_error(self, load_pipeline):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data,
            {"detail": "The prediction model is temporarily unavailable."},
        )


class ModelArtifactValidationTests(SimpleTestCase):
    url = "/api/v1/predictions/no-show/"
    valid_payload = NoShowPredictionApiTests.valid_payload

    def setUp(self):
        self.client = APIClient()
        permissions_patch = patch.object(
            views.NoShowPredictionView,
            "permission_classes",
            [AllowAny],
        )
        permissions_patch.start()
        self.addCleanup(permissions_patch.stop)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        temp_path = Path(self.temp_dir.name)
        self.artifact_path = temp_path / "pipeline.joblib"
        self.metadata_path = temp_path / "pipeline.metadata.json"
        paths_patch = patch.multiple(
            "predictions.views",
            MODEL_PATH=self.artifact_path,
            MODEL_METADATA_PATH=self.metadata_path,
        )
        paths_patch.start()
        self.addCleanup(paths_patch.stop)
        self.env_patch = patch.dict(
            os.environ,
            {
                views.ARTIFACT_DIGEST_ENV: "0" * 64,
                views.METADATA_DIGEST_ENV: "0" * 64,
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(views.load_pipeline.cache_clear)
        views.load_pipeline.cache_clear()

    def write_bundle(
        self,
        model=None,
        feature_names=None,
        write_metadata=True,
    ):
        joblib.dump(model or FakePipeline(), self.artifact_path)
        artifact_digest = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        metadata = build_metadata(artifact_digest, feature_names=feature_names)
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        os.environ[views.ARTIFACT_DIGEST_ENV] = artifact_digest
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        if write_metadata:
            self.metadata_path.write_bytes(metadata_bytes)
        views.load_pipeline.cache_clear()
        return artifact_digest

    def post_prediction(self):
        return self.client.post(self.url, self.valid_payload, format="json")

    def assert_safe_unavailable(self, response):
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data,
            {"detail": "The prediction model is temporarily unavailable."},
        )
        self.assertNotIn(self.temp_dir.name, str(response.data))

    def test_missing_artifact_returns_safe_server_error(self):
        self.assert_safe_unavailable(self.post_prediction())

    def test_missing_metadata_returns_safe_server_error(self):
        self.write_bundle(write_metadata=False)
        self.assert_safe_unavailable(self.post_prediction())

    def test_malformed_metadata_returns_safe_server_error(self):
        joblib.dump(FakePipeline(), self.artifact_path)
        artifact_digest = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        metadata_bytes = b"{malformed json"
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.ARTIFACT_DIGEST_ENV] = artifact_digest
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_digest_mismatch_is_detected_before_deserialization(self):
        self.write_bundle()
        os.environ[views.ARTIFACT_DIGEST_ENV] = "f" * 64
        views.load_pipeline.cache_clear()

        with patch("joblib.load") as deserialize:
            response = self.post_prediction()

        self.assert_safe_unavailable(response)
        deserialize.assert_not_called()

    def test_metadata_digest_mismatch_is_detected_before_deserialization(self):
        self.write_bundle()
        os.environ[views.METADATA_DIGEST_ENV] = "f" * 64
        views.load_pipeline.cache_clear()

        with patch("joblib.load") as deserialize:
            response = self.post_prediction()

        self.assert_safe_unavailable(response)
        deserialize.assert_not_called()

    def test_model_version_must_match_verified_artifact_digest(self):
        artifact_digest = self.write_bundle()
        metadata = build_metadata(artifact_digest)
        metadata["model_version"] = "no-show-unbound-version"
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_missing_display_version_returns_safe_server_error(self):
        artifact_digest = self.write_bundle()
        metadata = build_metadata(artifact_digest)
        del metadata["display_version"]
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_invalid_display_version_returns_safe_server_error(self):
        artifact_digest = self.write_bundle()
        metadata = build_metadata(artifact_digest)
        metadata["display_version"] = "No-Show Model v0"
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_incompatible_dependency_metadata_returns_safe_server_error(self):
        artifact_digest = self.write_bundle()
        metadata = build_metadata(artifact_digest)
        metadata["dependencies"]["scikit-learn"] = "0.0"
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_corrupted_artifact_returns_safe_server_error(self):
        corrupt_bytes = b"not a serialized model"
        self.artifact_path.write_bytes(corrupt_bytes)
        artifact_digest = hashlib.sha256(corrupt_bytes).hexdigest()
        metadata_bytes = json.dumps(build_metadata(artifact_digest)).encode("utf-8")
        self.metadata_path.write_bytes(metadata_bytes)
        os.environ[views.ARTIFACT_DIGEST_ENV] = artifact_digest
        os.environ[views.METADATA_DIGEST_ENV] = hashlib.sha256(
            metadata_bytes
        ).hexdigest()
        views.load_pipeline.cache_clear()

        self.assert_safe_unavailable(self.post_prediction())

    def test_metadata_schema_mismatch_returns_safe_server_error(self):
        self.write_bundle(feature_names=reversed(FEATURE_NAMES))
        self.assert_safe_unavailable(self.post_prediction())

    def test_pipeline_schema_mismatch_returns_safe_server_error(self):
        self.write_bundle(model=WrongSchemaPipeline())
        self.assert_safe_unavailable(self.post_prediction())

    def test_unsupported_probability_output_returns_safe_server_error(self):
        self.write_bundle(model=PipelineWithoutProbabilities())
        self.assert_safe_unavailable(self.post_prediction())


class RealArtifactAuthenticatedIntegrationTests(TestCase):
    url = "/api/v1/predictions/no-show/"
    payload = NoShowPredictionApiTests.valid_payload

    def setUp(self):
        self.client = APIClient()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(views.load_pipeline.cache_clear)
        views.load_pipeline.cache_clear()

        self.artifact_path = views.MODEL_PATH
        if not self.artifact_path.is_file():
            self.fail(f"The trained pipeline is missing: {self.artifact_path}")

        artifact_digest = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        metadata_bytes = json.dumps(build_metadata(artifact_digest)).encode("utf-8")
        metadata_path = Path(self.temp_dir.name) / "pipeline.metadata.json"
        metadata_path.write_bytes(metadata_bytes)
        self.metadata_path_patch = patch.object(
            views,
            "MODEL_METADATA_PATH",
            metadata_path,
        )
        self.metadata_path_patch.start()
        self.addCleanup(self.metadata_path_patch.stop)
        self.env_patch = patch.dict(
            os.environ,
            {
                views.ARTIFACT_DIGEST_ENV: artifact_digest,
                views.METADATA_DIGEST_ENV: hashlib.sha256(
                    metadata_bytes
                ).hexdigest(),
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_authenticated_request_uses_saved_pipeline_and_verified_version(self):
        unauthenticated_response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )
        self.assertEqual(
            unauthenticated_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(
            email="prediction-integration@example.test",
            password="test-password-for-prediction",
        )
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        expected_digest = os.environ[views.ARTIFACT_DIGEST_ENV]
        self.assertEqual(
            response.data["model_version"],
            f"no-show-{expected_digest}",
        )
        self.assertEqual(response.data["display_version"], "No-Show Model v1")
        self.assertIn("predicted_class", response.data)
        self.assertGreaterEqual(response.data["probability_no_show"], 0)
        self.assertLessEqual(response.data["probability_no_show"], 1)
        self.assertIn("synthetic", response.data["notice"])

    def test_wrong_role_is_rejected(self):
        user_model = get_user_model()
        admin = user_model.objects.create_superuser(
            email="prediction-admin@example.test",
            password="test-password-for-prediction",
        )
        token = AccessToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_invalid_input_returns_bad_request(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            email="prediction-invalid@example.test",
            password="test-password-for-prediction",
        )
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            self.url,
            {**self.payload, "days_ahead": 61},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("days_ahead", response.data)

    def test_authenticated_missing_artifact_returns_safe_server_error(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            email="prediction-missing-model@example.test",
            password="test-password-for-prediction",
        )
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        missing_artifact = Path(self.temp_dir.name) / "missing-pipeline.joblib"

        with patch.object(views, "MODEL_PATH", missing_artifact):
            views.load_pipeline.cache_clear()
            response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data,
            {"detail": "The prediction model is temporarily unavailable."},
        )


class ModelDisplayVersionGenerationTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        artifact_path = root / "pipeline.joblib"
        metadata_path = root / "pipeline.metadata.json"
        patcher = patch.multiple(
            ml_train,
            ARTIFACT_PATH=artifact_path,
            ARTIFACT_METADATA_PATH=metadata_path,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.artifact_path = artifact_path
        self.metadata_path = metadata_path

    def write_previous_metadata(self, display_version=None):
        digest = "a" * 64
        metadata = {
            "metadata_schema_version": 1,
            "model_version": f"no-show-{digest}",
            "artifact_sha256": digest,
        }
        if display_version is not None:
            metadata["display_version"] = display_version
        self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    def test_first_training_starts_at_v1(self):
        self.assertEqual(ml_train.next_display_version(), "No-Show Model v1")

    def test_legacy_metadata_advances_to_v2(self):
        self.write_previous_metadata()

        self.assertEqual(ml_train.next_display_version(), "No-Show Model v2")

    def test_retraining_advances_saved_version_from_v1_to_v2_to_v3(self):
        self.write_previous_metadata("No-Show Model v1")
        self.assertEqual(ml_train.next_display_version(), "No-Show Model v2")

        self.write_previous_metadata("No-Show Model v2")
        self.assertEqual(ml_train.next_display_version(), "No-Show Model v3")

    def test_invalid_previous_version_refuses_to_reset_counter(self):
        self.write_previous_metadata("No-Show Model v0")

        with self.assertRaises(RuntimeError):
            ml_train.next_display_version()

    def test_missing_metadata_for_existing_artifact_refuses_to_reset_counter(self):
        self.artifact_path.write_bytes(b"existing artifact")

        with self.assertRaises(RuntimeError):
            ml_train.next_display_version()
