from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from .views import ModelArtifactUnavailable, NoShowPredictionView


class FakePipeline:
    classes_ = [0, 1]

    def predict(self, features):
        return [1]

    def predict_proba(self, features):
        return [[0.27, 0.73]]


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
            NoShowPredictionView,
            "permission_classes",
            [AllowAny],
        )
        permissions_patch.start()
        self.addCleanup(permissions_patch.stop)

    @patch("predictions.views.make_feature_frame", return_value=object())
    @patch("predictions.views.load_pipeline", return_value=FakePipeline())
    def test_valid_request_returns_synthetic_prediction(
        self,
        load_pipeline,
        make_feature_frame,
    ):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model_version"], "no-show-v1")
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
    @patch("predictions.views.load_pipeline", return_value=FakePipeline())
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
                "predicted_class",
                "predicted_label",
                "probability_no_show",
                "notice",
            },
        )
        self.assertIsInstance(response.data["probability_no_show"], float)

    @patch(
        "predictions.views.load_pipeline",
        side_effect=ModelArtifactUnavailable,
    )
    def test_missing_model_returns_safe_server_error(self, load_pipeline):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data,
            {"detail": "The prediction model is temporarily unavailable."},
        )
