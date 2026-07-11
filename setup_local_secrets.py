from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def toml_string(value: Any) -> str:
    """JSON 문자열 표기는 TOML 기본 문자열과 호환되며 줄바꿈을 안전하게 이스케이프한다."""
    return json.dumps(str(value), ensure_ascii=False)


def build_toml(
    credentials: dict[str, Any],
    spreadsheet_id: str,
    access_code: str,
) -> str:
    required = (
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
        "auth_provider_x509_cert_url",
        "client_x509_cert_url",
    )
    missing = [key for key in required if not credentials.get(key)]
    if missing:
        raise ValueError("서비스 계정 JSON에 필요한 항목이 없습니다: " + ", ".join(missing))

    lines = [
        "[app]",
        f"access_code = {toml_string(access_code)}",
        "require_google_storage = true",
        "",
        "[google_sheets]",
        f"spreadsheet_id = {toml_string(spreadsheet_id.strip())}",
        "",
        "[gcp_service_account]",
    ]
    for key in required:
        lines.append(f"{key} = {toml_string(credentials[key])}")
    if credentials.get("universe_domain"):
        lines.append(
            f"universe_domain = {toml_string(credentials['universe_domain'])}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Google 서비스 계정 JSON을 Streamlit용 .streamlit/secrets.toml로 변환합니다."
        )
    )
    parser.add_argument("service_account_json", type=Path)
    parser.add_argument("spreadsheet_id")
    parser.add_argument("--access-code", default="")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".streamlit/secrets.toml"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.spreadsheet_id.strip():
        parser.error("spreadsheet_id가 비어 있습니다.")
    if args.output.exists() and not args.force:
        parser.error(f"{args.output}이 이미 있습니다. 덮어쓰려면 --force를 사용하세요.")

    with args.service_account_json.open("r", encoding="utf-8") as file:
        credentials = json.load(file)
    if not isinstance(credentials, dict):
        parser.error("서비스 계정 JSON 형식이 올바르지 않습니다.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build_toml(credentials, args.spreadsheet_id, args.access_code),
        encoding="utf-8",
    )
    print(f"생성 완료: {args.output}")
    print("이 파일은 비밀정보입니다. GitHub에 커밋하지 마세요.")
    print("Streamlit Community Cloud의 Secrets 입력란에는 이 파일 전체를 붙여넣으세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
