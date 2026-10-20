# PC + GitHub로 배포하는 순서

이 프로젝트는 이전에 만든 Lichess + Maia-3 인간형 체스 웹사이트를 GitHub 업로드 및 Hugging Face Docker Spaces에 맞게 묶었습니다.

## 먼저 PC에서 실행 (Windows PowerShell)

1. Python 3.11과 Git 설치.
2. 이 파일들의 상위 디렉터리에서 PowerShell 실행:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install git+https://github.com/CSSLab/maia3.git
maia3-cache --model maia3-5m
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

3. PC에서 http://localhost:8000, 같은 와이파이 스마트폰에서 http://PC내부IP:8000 접속.
   - Windows에서 `ipconfig` 명령으로 IPv4 주소 확인
   - Windows 방화벽 사설망 8000 포트 허용 필요할 수 있음
   - 상대 주소가 바뀌는 가정용 공유기에서는 내부 IP가 달라질 수 있음

## GitHub에 넣기

새 private GitHub repository `humanlike-chess` 생성. 이 프로젝트의 내용이 저장소 루트에 오도록 push:

```bash
git init
git add .
git commit -m "Initial humanlike chess web app"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/humanlike-chess.git
git push -u origin main
```

GitHub Desktop으로 폴더를 추가해도 됩니다. `.venv` 폴더나 모델 파일 `.pt`, `.env` 등은 업로드하지 마세요.

## Hugging Face에 배포하기

1. Hugging Face 계정을 준비합니다. 2026년 10월 기준 Docker Space 생성은 개인 PRO 구독 필요 ($9/월). CPU Basic의 별도 시간당 요금은 없음. 가격은 재확인하세요.
2. https://huggingface.co/new-space 에서 Space 이름 `humanlike-chess`, SDK `Docker`, Hardware `CPU Basic`, Visibility `Private`로 생성.
3. https://huggingface.co/settings/tokens 에서 `Write` 권한 토큰을 생성하되 가능하면 해당 Space 한정으로 제한.
4. GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret, 이름 `HF_TOKEN`, 값은 토큰을 붙여 넣기.
5. `.github/workflows/sync-hf.yml`의 `YOUR_HF_USERNAME`을 Hugging Face 사용자 이름으로 바꾸고 commit.
6. GitHub → Actions → Deploy to Hugging Face Space → Run workflow. 성공한 뒤 Hugging Face Space → Build logs를 확인.
7. 빌드가 완료되면 Space의 App 탭에서 대국. **Private Space**이므로 로그인 필요.

한 번 연결하면 GitHub의 `main` 브랜치에 코드를 push할 때 자동으로 배포됩니다. 개인용 앱이라 Private 상태를 추천합니다.

## 주의

- 리체스 대국 통계 API가 느리거나 막히면 Maia-3로 전환됩니다. Maia 설치 및 모델 다운로드는 빌드 과정에서 이뤄집니다.
- 최초 build는 torch와 모델을 내려받으므로 상대적으로 무거울 수 있습니다.
- 서버는 대국을 메모리에만 보관하므로 재시작하면 기록이 사라집니다. PGN 파일로 저장하세요.
- 서버에 많은 방문자가 몰리면 CPU/메모리 부족 가능성이 있습니다. 개인용 Space로 사용하세요.
- Lichess/모델 실제 네트워크 동작 및 클라우드 빌드는 환경상 검증되지 않았습니다.
