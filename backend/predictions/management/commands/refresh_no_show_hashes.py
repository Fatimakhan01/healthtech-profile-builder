"""Deliberately refresh locally trusted hashes after model artifact replacement."""

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = REPOSITORY_ROOT / ".env"
MODEL_PATH = (
    REPOSITORY_ROOT
    / "backend"
    / "ml"
    / "artifacts"
    / "no_show_pipeline.joblib"
)
METADATA_PATH = MODEL_PATH.with_name("no_show_pipeline.metadata.json")
HASH_VARIABLES = {
    "NO_SHOW_MODEL_SHA256": MODEL_PATH,
    "NO_SHOW_MODEL_METADATA_SHA256": METADATA_PATH,
}


def calculate_hashes() -> dict[str, str]:
    hashes = {}
    for variable, artifact_path in HASH_VARIABLES.items():
        try:
            artifact_bytes = artifact_path.read_bytes()
        except FileNotFoundError as error:
            raise CommandError(
                f"Cannot refresh hashes: required artifact is missing: {artifact_path}"
            ) from error
        except OSError as error:
            raise CommandError(
                f"Cannot read required artifact {artifact_path}: {error}"
            ) from error
        hashes[variable] = hashlib.sha256(artifact_bytes).hexdigest()
    return hashes


def update_env_file(env_path: Path, values: dict[str, str]) -> None:
    try:
        original_bytes = env_path.read_bytes()
    except FileNotFoundError as error:
        raise CommandError(
            f"Cannot refresh hashes: {env_path} does not exist. "
            "Create it from .env.example first."
        ) from error
    except OSError as error:
        raise CommandError(f"Cannot read {env_path}: {error}") from error

    text = original_bytes.decode("utf-8")
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    updated = set()
    output = []

    for line in lines:
        replaced = False
        for variable, digest in values.items():
            if re.match(rf"^\s*{re.escape(variable)}\s*=", line):
                ending = "\r\n" if line.endswith("\r\n") else (
                    "\n" if line.endswith("\n") else ""
                )
                output.append(f"{variable}={digest}{ending}")
                updated.add(variable)
                replaced = True
                break
        if not replaced:
            output.append(line)

    missing = [variable for variable in values if variable not in updated]
    if missing:
        if output and not output[-1].endswith(("\n", "\r")):
            output.append(newline)
        if output and output[-1].strip():
            output.append(newline)
        output.extend(f"{variable}={values[variable]}{newline}" for variable in missing)

    updated_bytes = "".join(output).encode("utf-8")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=env_path.parent,
            prefix=f".{env_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(updated_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.chmod(temporary_path, stat.S_IMODE(env_path.stat().st_mode))
        os.replace(temporary_path, env_path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise CommandError(f"Cannot safely update {env_path}: {error}") from error


class Command(BaseCommand):
    help = (
        "Explicitly refresh local trusted SHA-256 values after replacing the "
        "Week 3 no-show artifacts."
    )

    def handle(self, *args, **options):
        hashes = calculate_hashes()
        update_env_file(ENV_PATH, hashes)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {', '.join(hashes)} in {ENV_PATH}. "
                "Restart Django to load the new trusted values."
            )
        )
