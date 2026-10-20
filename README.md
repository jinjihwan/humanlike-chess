---
title: Humanlike Chess
emoji: ♟️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Humanlike Chess — 모바일/PC 웹사이트

Lichess Opening Explorer의 **실제 착수 빈도**로 오프닝 수를 추첨하고, 표본이 부족하거나 오프닝 제한을 넘으면 **Maia-3**로 계속 대국하는 개인용 웹앱입니다. 평가가 높은 수를 강제로 고르는 Stockfish 엔진은 사용하지 않습니다.

## 실행 환경

Python 3.10 이상, Maia-3 설치 가능한 **서버/컴퓨터**가 필요합니다. 휴대폰에는 Python이나 Maia 모델을 설치하지 않습니다. 서버에서 Maia-3를 실행하고 휴대폰 브라우저는 체스판을 표시합니다. 웹앱 소스는 **완성되어 있지만 인터넷에 공개 배포되어 있지는 않습니다**.

## 1. 설치

압축 해제하고 `humanlike_chess_web` 폴더에서 터미널을 열어 실행합니다.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
# 공식 Maia-3 저장소
# Git이 없다면 먼저 Git을 설치하세요.
python -m pip install git+https://github.com/CSSLab/maia3.git
# 모델을 미리 다운로드하면 대국 중 다운로드로 인한 긴 초기 대기를 피할 수 있습니다.
python -m maia3.cache --model maia3-5m
```

Maia-3 공식 문서: https://github.com/CSSLab/maia3

Maia3-23M이나 79M을 선택하려면 해당 모델도 미리 다운로드하는 것이 좋습니다.

```bash
python -m maia3.cache --model maia3-23m
python -m maia3.cache --model maia3-79m
```

## 2. 웹 서버 시작

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

PC 브라우저: **http://localhost:8000**

동일한 Wi-Fi에 연결된 휴대폰 브라우저: **http://[PC의 내부 IP 주소]:8000**

- Windows의 `ipconfig`, macOS/Linux의 `ip addr`로 PC IP를 확인하세요. 예: `http://192.168.0.10:8000`.
- PC 방화벽에서 TCP 8000 포트에 대한 **사설 네트워크** 접근 허용이 필요할 수 있습니다.
- 휴대폰이 모바일 데이터만 사용하거나 PC가 꺼져 있으면 접속되지 않습니다.
- 집 밖에서도 항상 접속하려면 서버를 클라우드에 배포해야 합니다. **이 ZIP에는 실제 도메인, 공개 서버, 호스팅은 포함되지 않습니다.** 공개 서비스에서는 인증, 접속 제한, HTTPS, 적절한 프로세스 관리 등이 필요합니다.

## 3. 사용법

1. 레이팅, 백/흑, 시간제어 통계, Maia3 모델과 오프닝 최소 표본 수를 선택합니다.
2. **대국 시작하기**를 누릅니다. 내가 흑이면 봇이 먼저 둡니다.
3. 말을 터치 → 이동할 칸을 터치하면 수를 둡니다. 폰 승격 시 기물을 선택합니다.
4. 봇이 Lichess에서 수를 택하면 **선택한 수와 그 비율**, **주요 후보 수와 비율**, **현재 포지션의 표본 수**가 표시됩니다.
5. Lichess 수를 사용할 수 없는 상황에서는 **Maia-3**라는 출처만 표시합니다. 이 경우 실제 Lichess 수 선택 비율을 만들지 않습니다.
6. **되돌리기**로 마지막 턴을 되돌리고, **PGN 저장**으로 기보를 다운로드할 수 있으며, **기권**도 지원합니다.

## 데이터 처리 및 모델

- 기본 최소 표본: **500판**. 최대 오프닝 길이: **30 plies** = 백/흑 합산 30번 착수(양측 약 15수).
- 오프닝 후보 선택은 `white + draws + black` 등장 횟수에 비례한 무작위 샘플링. 분모는 현재 포지션 전체 대국 수입니다.
- 조회된 주요 후보가 전체 대국의 **90% 미만**을 차지하면 Maia-3로 전환하여 심각하게 잘린 표본으로 수를 샘플링하지 않습니다.
- Maia-3는 `--elo`와 `--use-uci-history`, `--temperature 1.0`을 적용하며 `chess.engine.Limit(nodes=1)`로 실행합니다.
- 시간제어(블리츠·래피드·불릿·클래시컬)는 **Lichess 오프닝 필터에만 적용됩니다**. Maia-3의 수 선택에는 시간제어/남은 시간을 별도로 주입하지 않습니다.
- API 오류/속도 제한(429)이 발생하면 해당 게임의 오프닝 API 호출을 멈추고 Maia-3로 전환합니다.
- Maia-3 설치/모델이 없으면 **임의의 수로 속여서 진행하지 않고 오류와 재시도 버튼을 표시**합니다.
- 서버는 게임을 메모리에 저장하고 2시간 비활성 시 정리하며, 서버가 재시작되면 대국은 사라집니다. PGN으로 기보를 보관하세요.

## 폴더 구조

```text
humanlike_chess_web/
├── server.py                 FastAPI / 수 검증 / PGN / Maia-3 연결
├── opening_book.py           Lichess API / 실제 대국 빈도 샘플링
├── static/
│   ├── index.html            반응형 체스 웹사이트
│   ├── style.css             모바일·PC UI
│   └── app.js                터치 착수 / 보드 / 통계 표시
├── tests/
│   ├── test_opening_book.py
│   └── test_server_helpers.py
├── requirements.txt
└── README.md
```

## 테스트

```bash
python -m unittest discover -s tests -v
python -m compileall -q server.py opening_book.py
```

추가로 실제 인터넷 연결/모델 설치 후 Lichess 요청과 Maia-3 전체 대국을 검증해야 합니다. 본 프로젝트를 만든 환경에는 `python-chess`와 `maia3`가 설치되지 않아 실제 엔진 구동까지 자동 검증하지는 못했습니다.

## 출처 및 라이선스

- [Lichess Opening Explorer API](https://lichess.org/api#tag/Opening-Explorer)
- [Maia-3 공식 저장소](https://github.com/CSSLab/maia3)

Lichess API 이용 조건과 Maia-3 모델/코드 라이선스를 준수하세요. 온라인 Lichess 인간 계정에서 엔진을 사용하지 마세요.

## GitHub → Hugging Face Spaces 자동 배포

1. Hugging Face PRO 계정에서 **Docker / CPU Basic / Private** Space를 먼저 만듭니다.
2. Hugging Face 토큰을 Space 쓰기 권한으로 발급합니다 (fine-grained 권장).
3. GitHub 저장소의 Settings → Secrets and variables → Actions → New repository secret에 `HF_TOKEN`을 추가합니다.
4. `.github/workflows/sync-hf.yml`의 `huggingface_repo_id`를 실제 `HF사용자명/Space이름`으로 바꿉니다.
5. GitHub의 Actions → `Deploy to Hugging Face Space` → Run workflow를 눌러 처음 배포합니다. 그다음 `main`에 푸시할 때도 자동 업데이트됩니다.
6. Hugging Face Space의 Build logs에서 빌드를 확인하고 App 탭에서 접속합니다.

현재 실환경 Hugging Face 빌드 및 Maia-3 모델 구동은 검증되지 않았습니다.
