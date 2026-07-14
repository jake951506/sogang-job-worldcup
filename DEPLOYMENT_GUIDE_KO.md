# Streamlit Community Cloud 배포 체크리스트

## 1. 배포 전 기능 확인

- 첫 화면에서 선호조사와 기피조사를 선택할 수 있는가?
- 조사 선택 후 이름을 입력하지 않으면 시작되지 않는가?
- 이름 입력 후 첫 경기가 열리는가?
- 마우스와 숫자 키 `1`, `2`가 모두 작동하는가?
- 조별리그 40경기와 결선 16경기, 총 56경기가 진행되는가?
- 3·4위전을 거쳐 최종 1~4위가 표시되는가?
- 한 조사 완료 후 다른 조사 계속 또는 참여 종료를 선택할 수 있는가?
- 우측 상단에 `Developed by JK`가 보이는가?

자동 테스트:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 2. Google Sheets 준비

1. 빈 Google 스프레드시트를 만듭니다.
2. Google Cloud 프로젝트를 만듭니다.
3. Google Sheets API와 Google Drive API를 활성화합니다.
4. 서비스 계정을 만들고 JSON 키를 발급합니다.
5. 스프레드시트를 JSON의 `client_email`과 공유합니다.
6. 서비스 계정에 편집자 권한을 줍니다.
7. URL의 `/d/`와 `/edit` 사이 스프레드시트 ID를 복사합니다.

서비스 계정 JSON을 Secrets 형식으로 변환합니다.

```bash
python setup_local_secrets.py /path/to/service-account.json 실제_스프레드시트_ID
```

접속 코드까지 설정하려면:

```bash
python setup_local_secrets.py /path/to/service-account.json 실제_스프레드시트_ID \
  --access-code "조사접속코드"
```

연결 확인:

```bash
pip install -r requirements.txt
python init_google_sheet.py
streamlit run streamlit_app.py
```

시험 응답 하나를 완료한 뒤 확인합니다.

- `survey_results`: 헤더 + 요약 1행
- `group_results`: 헤더 + 20행
- `match_results`: 헤더 + 56행
- `survey_results.participant_name`: 입력한 이름
- `survey_results.final_top4_json`: 1~4위 네 개
- `survey_results.unit_separation_complete`: 같은 팀 완전 분리 여부

기존 시트를 업그레이드하면 앱이 뒤쪽에 새 열을 자동 추가합니다. 헤더를 수동 변경한 시트는 먼저 백업한 뒤 복구하거나 새 스프레드시트를 사용합니다.

## 3. GitHub 업로드

```bash
git init
git add .
git commit -m "Deploy Sogang job world cup"
git branch -M main
git remote add origin https://github.com/본인아이디/저장소이름.git
git push -u origin main
```

커밋 전에 `git status`로 다음 파일이 제외되었는지 확인합니다.

- `.streamlit/secrets.toml`
- 서비스 계정 JSON
- credentials 파일

## 4. Community Cloud 배포

1. Streamlit Community Cloud에서 GitHub 계정을 연결합니다.
2. **Create app**을 선택합니다.
3. 저장소와 `main` 브랜치를 선택합니다.
4. Main file path를 `streamlit_app.py`로 지정합니다.
5. Advanced settings에서 Python 3.12를 선택합니다.
6. Secrets 입력란에 `.streamlit/secrets.toml` 전체를 붙여 넣습니다.
7. Deploy를 누릅니다.
8. 배포 URL에서 이름 입력부터 조사 종료까지 시험합니다.
9. Google Sheet에 1 + 20 + 56개 데이터 행이 추가되는지 확인합니다.

## 5. 공개 전 점검

- `[app].require_google_storage = true`인가?
- 제한된 참여자만 받아야 한다면 `access_code`를 설정했는가?
- Google Sheet가 링크 공개 상태가 아닌가?
- 서비스 계정에 편집자 권한이 있는가?
- `constants.py`의 `JOB_UNITS`가 실제 소속과 일치하는가?
- 교무팀·학사지원팀 등 같은 팀 업무가 서로 다른 조로 분산되는가?
- 기피조사에서 과거 선호 상위권도 함께 분산되는가?
- 현재 참여자의 선호 결과는 본인의 기피 시드에서 제외되는가?
- 조 1위 네 개가 서로 다른 8강 구역에 배치되는가?
- 공용 PC에서 **다음 참여자 시작**이 이름과 세션 ID를 초기화하는가?

## 관리자 통계 비밀번호 추가

Streamlit Community Cloud의 `Settings → Secrets`에서 `[app]` 구역에 다음 한 줄을 추가합니다.

```toml
admin_password = "관리자만 아는 비밀번호"
```

저장 후 앱을 Reboot하면 사이드바의 `📊 관리자 통계`에서 사용할 수 있습니다. 조사 참여용 `access_code`와 관리자용 `admin_password`는 서로 다른 값으로 설정하는 것을 권장합니다.
