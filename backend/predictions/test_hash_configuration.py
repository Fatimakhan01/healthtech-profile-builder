"""Tests for local dotenv startup configuration and deliberate digest refresh."""

import hashlib
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .management.commands import refresh_no_show_hashes


class ProjectDotenvLoadingTests(SimpleTestCase):
    def test_django_settings_loads_repository_root_env_file(self):
        repository_root = Path(__file__).resolve().parents[2]
        settings_path = repository_root / "backend" / "config" / "settings.py"
        required_environment = {
            "DJANGO_SECRET_KEY": "test-only-secret",
            "POSTGRES_DB": "test_database",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_password",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
        }

        with (
            patch.dict(os.environ, required_environment, clear=True),
            patch("dotenv.load_dotenv") as load_dotenv,
        ):
            runpy.run_path(str(settings_path), run_name="isolated_test_settings")

        load_dotenv.assert_called_once_with(repository_root / ".env")


class RefreshNoShowHashesTests(SimpleTestCase):
    def test_hashes_are_calculated_from_both_actual_artifact_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model_path = root / "model.joblib"
            metadata_path = root / "model.metadata.json"
            model_path.write_bytes(b"synthetic model artifact")
            metadata_path.write_bytes(b'{"synthetic": true}')

            with patch.dict(
                refresh_no_show_hashes.HASH_VARIABLES,
                {
                    "NO_SHOW_MODEL_SHA256": model_path,
                    "NO_SHOW_MODEL_METADATA_SHA256": metadata_path,
                },
                clear=True,
            ):
                hashes = refresh_no_show_hashes.calculate_hashes()

        self.assertEqual(
            hashes,
            {
                "NO_SHOW_MODEL_SHA256": hashlib.sha256(
                    b"synthetic model artifact"
                ).hexdigest(),
                "NO_SHOW_MODEL_METADATA_SHA256": hashlib.sha256(
                    b'{"synthetic": true}'
                ).hexdigest(),
            },
        )

    def test_missing_artifact_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "missing.joblib"
            with patch.dict(
                refresh_no_show_hashes.HASH_VARIABLES,
                {"NO_SHOW_MODEL_SHA256": missing_path},
                clear=True,
            ):
                with self.assertRaisesMessage(CommandError, "artifact is missing"):
                    refresh_no_show_hashes.calculate_hashes()

    def test_env_update_preserves_other_settings_and_updates_hashes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "DJANGO_DEBUG=true\n"
                "NO_SHOW_MODEL_SHA256=old-model-hash\n"
                "# Keep this comment\n",
                encoding="utf-8",
            )

            refresh_no_show_hashes.update_env_file(
                env_path,
                {
                    "NO_SHOW_MODEL_SHA256": "a" * 64,
                    "NO_SHOW_MODEL_METADATA_SHA256": "b" * 64,
                },
            )

            contents = env_path.read_text(encoding="utf-8")
        self.assertIn("DJANGO_DEBUG=true\n", contents)
        self.assertIn("# Keep this comment\n", contents)
        self.assertIn(f"NO_SHOW_MODEL_SHA256={'a' * 64}\n", contents)
        self.assertIn(
            f"NO_SHOW_MODEL_METADATA_SHA256={'b' * 64}\n",
            contents,
        )
        self.assertNotIn("old-model-hash", contents)

    def test_missing_env_file_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            with self.assertRaisesMessage(CommandError, "does not exist"):
                refresh_no_show_hashes.update_env_file(
                    env_path,
                    {"NO_SHOW_MODEL_SHA256": "a" * 64},
                )

    def test_write_failure_is_reported_without_replacing_env(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            original = "DJANGO_DEBUG=true\n"
            env_path.write_text(original, encoding="utf-8")

            with patch(
                "predictions.management.commands.refresh_no_show_hashes.os.replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaisesMessage(CommandError, "Cannot safely update"):
                    refresh_no_show_hashes.update_env_file(
                        env_path,
                        {"NO_SHOW_MODEL_SHA256": "a" * 64},
                    )

            self.assertEqual(env_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
