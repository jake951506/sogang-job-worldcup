from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from storage import GoogleSheetsRepository


def main() -> int:
    secrets_path = Path(".streamlit/secrets.toml")
    if not secrets_path.exists():
        print(
            ".streamlit/secrets.toml이 없습니다. "
            "secrets.toml.example을 복사해 실제 값으로 채워 주세요.",
            file=sys.stderr,
        )
        return 1

    with secrets_path.open("rb") as file:
        secrets = tomllib.load(file)

    repository = GoogleSheetsRepository(
        credentials_info=secrets["gcp_service_account"],
        spreadsheet_id=secrets["google_sheets"]["spreadsheet_id"],
    )
    status = repository.healthcheck()
    print(f"연결 성공: {status['spreadsheet_title']}")
    print("survey_results, group_results, match_results 탭을 확인했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
