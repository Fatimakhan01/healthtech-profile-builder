import logging
from functools import lru_cache
from pathlib import Path

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
EXPERIMENTAL_NOTICE = (
    "Experimental prediction from a fully synthetic educational dataset; "
    "not a clinical or real-world risk estimate."
)


class ModelArtifactUnavailable(Exception):
    pass


def make_feature_frame(values):
    import pandas as pd

    return pd.DataFrame([values], columns=FEATURE_NAMES)


@lru_cache(maxsize=1)
def load_pipeline():
    try:
        import joblib

        return joblib.load(MODEL_PATH)
    except Exception as error:
        logger.exception("Could not load the synthetic no-show model artifact.")
        raise ModelArtifactUnavailable from error


class NoShowPredictionView(APIView):
    def post(self, request):
        serializer = NoShowPredictionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            model = load_pipeline()
            features = make_feature_frame(serializer.validated_data)
            predicted_class = int(model.predict(features)[0])
            probability_no_show = None

            if (
                hasattr(model, "predict_proba")
                and hasattr(model, "classes_")
                and 1 in model.classes_
            ):
                positive_class_index = list(model.classes_).index(1)
                probability_no_show = float(
                    model.predict_proba(features)[0][positive_class_index]
                )
        except ModelArtifactUnavailable:
            return self._unavailable_response()
        except Exception:
            logger.exception("Could not produce a synthetic no-show prediction.")
            return self._unavailable_response()

        return Response(
            {
                "model_version": "no-show-v1",
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
