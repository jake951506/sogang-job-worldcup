# 서강대학교 본부 20개 직무 이상형 월드컵 — Streamlit 웹앱

서강대학교 본부의 같은 20개 직무를 대상으로 **선호조사**와 **기피조사**를 독립적으로 진행하는 Streamlit 웹앱입니다.

- 선호조사: 둘 중 더 맡고 싶은 직무 선택
- 기피조사: 둘 중 더 피하고 싶은 직무 선택
- 처음 접속했을 때 둘 중 하나를 선택
- 한 조사만 완료하고 종료 가능
- 한 조사 완료 후 나머지 조사도 계속할지 직접 선택
- 첫 게임 직전에 이름 입력 필수
- 화면 우측 상단에 `Developed by JK` 표시

앱 버전: `3.1.1`

---

## 조사 진행 구조

한 조사당 다음 56경기를 진행합니다.

| 단계 | 경기 수 |
|---|---:|
| 20강 조별리그 | 40 |
| 16강 | 8 |
| 8강 | 4 |
| 4강 | 2 |
| 3·4위전 | 1 |
| 결승 | 1 |
| **합계** | **56** |

A~D조에 5개 직무씩 배치하고, 각 조에서 모든 직무가 한 번씩 맞붙습니다. 각 조 1~4위가 16강에 진출하고 5위만 탈락합니다.

16강 대진은 다음 순서입니다.

1. A조 1위 vs B조 4위
2. C조 2위 vs D조 3위
3. C조 1위 vs D조 4위
4. A조 2위 vs B조 3위
5. B조 1위 vs A조 4위
6. D조 2위 vs C조 3위
7. D조 1위 vs C조 4위
8. B조 2위 vs A조 3위

인접한 두 16강 경기가 하나의 8강 구역을 이루므로 네 조 1위는 4강 전에는 서로 만나지 않습니다. 4강 패자는 3·4위전을 치르고, 결승 결과와 합쳐 최종 1~4위를 모두 확정합니다.

---

## 참여 화면 흐름

1. 첫 화면에서 `선호조사 선택` 또는 `기피조사 선택`
2. 선택한 조사를 시작하기 직전에 이름 입력
3. 56경기 진행
4. 최종 1~4위 확인 및 Google Sheets 저장
5. 다음 중 하나 선택
   - 나머지 조사도 계속하기
   - 여기서 참여 마치기
6. 두 조사 모두 완료했거나 종료를 선택하면 완료 화면 표시

같은 참여자가 두 조사를 이어서 하면 이름과 익명 참여자 세션 ID가 유지됩니다. 공용 PC에서는 완료 화면 또는 사이드바의 **다음 참여자 시작**을 눌러 이름, 세션 ID, 완료 상태를 모두 초기화해야 합니다.

---

# 조 편성 원리

## 1. 동일 조사 과거 상위권 분산

선호와 기피의 과거 통계는 서로 구분합니다. 각 직무의 과거 조별 순위에서 다음 지표를 계산합니다.

- 조 1·2위 횟수와 비율
- 평균 조 순위
- 유효 완료 응답 수

시드 점수는 완화된 조 1·2위 비율 85%와 평균 순위 점수 15%를 합쳐 계산합니다. 초반 소수 응답에 과도하게 흔들리지 않도록 5건 분량의 사전값을 적용합니다.

20개 직무를 시드 순서대로 4개씩 5개 포트로 나누고, 모든 조가 각 포트에서 한 직무씩 받도록 배치합니다. 따라서 상위 1~4위, 5~8위, 9~12위 등은 각각 네 조로 분산됩니다.

## 2. 기피조사의 선호 결과 교차 분산

기피조사를 편성할 때 유효한 과거 선호조사 결과가 있으면 두 종류의 포트를 동시에 만족시킵니다.

- 각 조는 기피 시드 포트 1~5에서 한 직무씩 받음
- 각 조는 선호 시드 포트 1~5에서도 한 직무씩 받음

따라서 선호조사에서 상위권에 자주 나온 직무들이 기피조사의 한 조에 몰리지 않습니다. 시드 총합을 비교할 때는 기피 70%, 선호 30%의 합성 점수를 사용합니다.

현재 참여자가 선호조사를 끝낸 뒤 바로 기피조사를 하더라도 **현재 참여자의 선호 결과는 교차 시드에서 제외**하고, 앞선 참여자들의 완료 응답만 사용합니다.

과거 선호 결과가 아직 없으면 기피 시드와 같은 팀 분산 조건만 사용합니다.

## 3. 같은 팀 업무 분산

`constants.py`의 `JOB_UNITS`에 직무별 소속을 정의했습니다. 같은 팀에서 여러 업무가 출전한 경우 가능한 한 서로 다른 조에 배치합니다.

현재 분류의 주요 다중 출전 팀은 다음과 같습니다.

- 교무팀: 4개
- 학사지원팀: 3개
- 전략기획팀: 3개
- 예산팀: 2개
- 인사총무팀: 2개
- 재무팀: 2개

`전임교원 급여 및 보상`과 `전임교원 신규임용`도 교무팀으로 분류했습니다. 교무팀 업무가 정확히 4개이므로, 편성 조건이 충족되는 경우 A·B·C·D조에 하나씩 배치됩니다. 기존 Google Sheets의 과거 응답과 같은 직무로 계속 집계되도록 화면에 쓰는 직무명 문자열은 변경하지 않았습니다.

편성기는 다음 조건을 함께 풉니다.

1. 동일 조사 시드 포트 분산
2. 기피조사일 때 선호 시드 포트 교차 분산
3. 같은 팀 업무의 조 내 중복 금지
4. 조별 합성 시드 점수 총합 균형

세 조건상 완전 분리가 불가능한 예외에는 조사를 중단하지 않고, 같은 팀 중복 수가 가장 적은 편성을 선택합니다. 실제 편성의 중복 여부와 편성 알고리즘 정보는 Google Sheets에 함께 저장됩니다.

---

## 프로젝트 구성

```text
sogang_job_worldcup_streamlit_v3_1_1/
├── streamlit_app.py              # 웹 UI, 이름 입력, 조사 선택·종료 흐름
├── constants.py                  # 20개 직무, 소속 분류, 앱 문구
├── seeding.py                    # 과거 시드·교차 시드·같은 팀 분산 편성기
├── tournament.py                 # 조별리그, 16강~결승, 3·4위전 엔진
├── storage.py                    # Google Sheets 저장, 재시도, 복구 JSON
├── init_google_sheet.py          # Google Sheets 연결 및 탭 초기화
├── setup_local_secrets.py        # 서비스 계정 JSON → Secrets TOML 변환
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── README.md
├── DEPLOYMENT_GUIDE_KO.md
├── TEST_RESULTS.txt
├── CHANGELOG.md
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── tests/
```

---

# 로컬 실행

Python 3.12를 권장합니다.

```bash
cd sogang_job_worldcup_streamlit_v3_1
python -m venv .venv
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

설치 및 실행:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

테스트:

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

# Google Sheets 저장 설정

## 저장 탭

앱이 첫 연결 때 다음 세 탭과 헤더를 자동 생성합니다.

| 탭 | 완료 조사 1건당 행 | 내용 |
|---|---:|---|
| `survey_results` | 1 | 이름, 조사 유형, 최종 1~4위, 조 편성·시드 메타데이터 |
| `group_results` | 20 | 직무별 조, 조 순위, 승패, 소속, 최종 1~4위 여부 |
| `match_results` | 56 | 모든 경기의 좌우 직무와 선택 결과 |

이름은 `survey_results.participant_name`에 저장됩니다. `group_results`와 `match_results`는 `response_id`로 요약 행과 연결합니다.

## 서비스 계정 준비

1. Google Drive에서 빈 스프레드시트를 만듭니다.
2. Google Cloud 프로젝트를 만듭니다.
3. Google Sheets API와 Google Drive API를 활성화합니다.
4. 서비스 계정을 만들고 JSON 키를 발급합니다.
5. 스프레드시트를 JSON의 `client_email`과 공유합니다.
6. 서비스 계정에 편집자 권한을 줍니다.
7. 스프레드시트 URL의 `/d/`와 `/edit` 사이 ID를 복사합니다.

서비스 계정 JSON을 GitHub에 올리면 안 됩니다.

## Secrets 자동 생성

```bash
python setup_local_secrets.py /path/to/service-account.json 실제_스프레드시트_ID
```

접속 코드까지 설정하려면:

```bash
python setup_local_secrets.py /path/to/service-account.json 실제_스프레드시트_ID \
  --access-code "조사접속코드"
```

생성 파일:

```text
.streamlit/secrets.toml
```

이 파일은 `.gitignore`에 포함되어 있습니다.

연결 확인:

```bash
python init_google_sheet.py
```

## 기존 시트에서 업그레이드

버전 2.x 또는 3.0에서 사용하던 탭의 헤더가 앱 기본 순서를 유지하고 있다면, 3.1 앱이 필요한 새 열을 기존 헤더 뒤에 자동 추가하고 시트 열 수도 확장합니다. 기존 행은 삭제하거나 수정하지 않습니다.

다만 관리자가 헤더 이름이나 순서를 수동으로 바꾼 경우에는 자동 변경하지 않고 오류를 표시합니다. 이때는 먼저 시트를 백업한 뒤 새 빈 스프레드시트로 연결하거나 헤더를 원래 순서로 복구해야 합니다.

---

# GitHub 업로드

GitHub에서 빈 저장소를 만든 뒤 프로젝트 폴더에서 실행합니다.

```bash
git init
git add .
git commit -m "Add Sogang job world cup Streamlit app"
git branch -M main
git remote add origin https://github.com/본인아이디/저장소이름.git
git push -u origin main
```

업로드 전 반드시 확인합니다.

```bash
git status
```

다음 파일은 커밋하면 안 됩니다.

- `.streamlit/secrets.toml`
- 서비스 계정 JSON 키
- credentials 파일

---

# Streamlit Community Cloud 배포

1. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
2. GitHub 저장소 접근 권한을 승인합니다.
3. **Create app**을 누릅니다.
4. 저장소와 `main` 브랜치를 선택합니다.
5. Main file path를 `streamlit_app.py`로 지정합니다.
6. Advanced settings에서 Python 3.12를 선택합니다.
7. Secrets 입력란에 로컬 `.streamlit/secrets.toml` 전체를 붙여 넣습니다.
8. Deploy를 누릅니다.
9. 배포 주소에서 이름 입력부터 조사 종료까지 시험합니다.
10. Google Sheets에서 1 + 20 + 56행이 추가되었는지 확인합니다.

GitHub의 `main` 브랜치에 변경 사항을 push하면 연결된 앱에 새 코드가 반영됩니다.

더 간단한 체크리스트는 `DEPLOYMENT_GUIDE_KO.md`에 있습니다.

---

## 저장 안정성

저장은 다음 순서로 진행됩니다.

1. `group_results` 세부 행 저장
2. `match_results` 세부 행 저장
3. `survey_results` 요약 행을 마지막에 저장

과거 시드 계산은 `survey_results.status == completed`인 요약 행만 읽습니다. 따라서 저장 중 오류가 난 미완료 제출이 다음 조 편성에 반영되지 않습니다.

모든 행에는 `response_id`와 `row_key`가 있습니다. 같은 결과를 재저장하면 이미 기록된 행은 건너뛰어 중복을 줄입니다. 저장에 실패하면 같은 응답 ID로 다시 시도할 수 있고, 비상 복구용 JSON도 내려받을 수 있습니다.

운영 배포에서는 다음 값을 권장합니다.

```toml
[app]
require_google_storage = true
```

이 값이 `true`이면 Google Sheets가 연결되지 않은 상태에서 조사를 시작하지 못하게 막습니다.

---

## 개인정보 및 운영 주의

- 이름은 조사 결과 구분을 위해 관리자용 Google Sheet에 저장됩니다.
- 스프레드시트는 서비스 계정과 필요한 관리자에게만 공유하는 것이 좋습니다.
- 공개 링크만으로 엄격한 1인 1응답을 완전히 보장할 수는 없습니다.
- 엄격한 중복 방지가 필요하면 기관 SSO, 사번 인증 또는 일회용 참여 토큰을 추가해야 합니다.
- 파일럿과 본조사를 분리하려면 본조사용 새 스프레드시트를 만드는 것이 안전합니다.

---

## 화면 크레딧 수정

우측 상단 문구는 `constants.py`의 다음 값으로 관리합니다.

```python
APP_CREDIT = "Developed by JK"
```

문구를 바꾸려면 이 한 줄만 수정하면 됩니다.

## v3.3 선택 이유 메모와 관리자 통계

- 각 조사가 끝나면 최종 결과 화면 전에 `선택 이유 또는 추가 의견`을 선택적으로 입력할 수 있습니다.
- 메모는 최대 1,000자이며, 작성하지 않고 결과를 저장할 수도 있습니다.
- 메모는 `survey_results` 탭의 `selection_reason` 열에 응답 결과와 함께 저장됩니다.
- 기존 Google Sheet는 앱이 시작될 때 새 열을 맨 뒤에 자동 추가하므로 기존 데이터와 호환됩니다.

사이드바의 `📊 관리자 통계` 버튼을 누르면 비밀번호 확인 후 다음 내용을 볼 수 있습니다.

- 전체·선호·기피 조사별 완료 응답 수와 참여자 수
- 최종 1~4위 횟수와 가중 종합점수 차트
- 직무별 조 1위, 조 2위 이내, 조 5위 탈락, 평균 조 순위
- 참여자별 최종 1~4위와 선택 이유 메모
- 현재 필터 결과 CSV 다운로드

관리자 비밀번호는 Streamlit Secrets의 `[app]`에 추가합니다.

```toml
[app]
access_code = "조사접속코드"
admin_password = "관리자전용비밀번호"
require_google_storage = true
```

로컬 Secrets 생성 도구를 새로 실행할 때는 다음 옵션을 함께 사용할 수 있습니다.

```bash
python setup_local_secrets.py "서비스계정.json" "스프레드시트_ID" \
  --access-code "조사접속코드" \
  --admin-password "관리자전용비밀번호"
```
