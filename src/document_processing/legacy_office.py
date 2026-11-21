"""Convert legacy Microsoft Office files to the formats Docling consumes."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory

from document_processing.formats import LEGACY_OFFICE_FORMATS, matches_signature


_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_BYTES = 128 * 1024 * 1024
_PROFILE_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
  <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
    <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
    <prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
    <prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>
  </item>
  <item oor:path="/org.openoffice.Office.Writer/Content/Update">
    <prop oor:name="Link" oor:op="fuse"><value>2</value></prop>
  </item>
  <item oor:path="/org.openoffice.Office.Calc/Content/Update">
    <prop oor:name="Link" oor:op="fuse"><value>1</value></prop>
  </item>
</oor:items>
"""


def convert_legacy_office(content: bytes, suffix: str) -> tuple[bytes, str]:
    if not matches_signature(content, suffix):
        raise ValueError(f"File content does not match {suffix}")
    executable = shutil.which("soffice")
    if executable is None:
        raise RuntimeError("LibreOffice (soffice) is required for legacy Office files")

    target_suffix = LEGACY_OFFICE_FORMATS[suffix]
    with TemporaryDirectory(prefix="legacy-office-") as directory:
        root = Path(directory)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(_PROFILE_SETTINGS, encoding="utf-8")
        source = root / f"document{suffix}"
        source.write_bytes(content)
        target = root / f"document{target_suffix}"
        command = [
            executable, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
            "--convert-to", target_suffix[1:], "--outdir", str(root), str(source),
        ]
        with subprocess.Popen(
            command, cwd=root, env={"HOME": directory, "TMPDIR": directory, "LANG": "C.UTF-8"},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        ) as process:
            try:
                exit_code = process.wait(timeout=_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as error:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise ValueError("Legacy Office conversion timed out") from error
        if exit_code != 0 or not target.is_file() or target.stat().st_size == 0:
            raise ValueError(f"Could not convert the {suffix} file with LibreOffice")
        if target.stat().st_size > _MAX_OUTPUT_BYTES:
            raise ValueError("Converted Office document is too large")
        return target.read_bytes(), target_suffix
