# KT 생활인구/이동 데이터 정제 프로젝트

## 작업 환경 (매우 중요)
- **이 폴더는 로컬**입니다. 데이터는 원격 서버에 있습니다.
- **모든 데이터 처리는 원격 서버 `wsson1` (SSH alias)에서 실행**해야 합니다.
- SSH 접속: `ssh wsson1` (key 인증, 비밀번호 불필요)
- 원격 명령 실행: `ssh wsson1 "명령어"` 또는 heredoc 사용
- 파일 전송: `scp file.py wsson1:/data_ssd/hwcho/projects/kt_mobility/scripts/`

## 원격 서버 정보
- 호스트: 172.17.3.70 (port 2234)
- 사용자: hwcho
- 프로젝트 디렉토리: `/data_ssd/hwcho/projects/kt_mobility/`
- 하드웨어: 72코어, 440GB RAM, 17TB SSD 여유

## 원격 프로젝트 구조
/data_ssd/hwcho/projects/kt_mobility/
├── pyproject.toml          # uv 프로젝트 설정
├── uv.lock                 # 의존성 lock
├── .venv/                  # uv 가상환경
├── scripts/                # Python 스크립트
├── data/
│   ├── livepop/            # 정제된 생활인구 데이터 (parquet)
│   ├── movement/           # 정제된 이동 데이터 (parquet)
│   └── mapping/            # 행정동 매핑 등 보조 데이터
└── logs/                   # 실행 로그

## Python 환경 사용법 (원격에서)
- 가상환경 자동 활성화: `cd /data_ssd/hwcho/projects/kt_mobility && uv run python script.py`
- 패키지 추가: `uv add 패키지명`
- **`pip install` 직접 쓰지 말 것** — 항상 `uv add` 사용

## 데이터 소스 (원격 서버, 모두 읽기 전용)
- 생활인구 (LivePOP): `/data_ssd/KT_data_2025/LivePOP/MSL_NATIE_LIVEPOP_YYYYMM.csv`
  - 컬럼: ETL_YMD (yyyymmdd), TIMEZN_CD (00~23 2자리 문자열), ADMDONG_CD (8자리 행정동), SEX_AGE_CD (F00, F10, ..., M75 - 성별+5세단위), POP
  - 시간 범위: 2018.01 ~ 2023.12 (총 72개월)
- 이동 (Movement): `/data_ssd/KT_data_2025/Movement/MSL_YYYYMM.csv`
  - 컬럼: ETL_YMD, TIME_CD (출퇴근 20분단위, 그외 1시간), O_CELL_ID, D_CELL_ID, SEX_CD (남/여), AGE_CD (00~80 10세단위), PURPOSE (1~7), TOTAL, AVG_DIST, AVG_TIME
- 행정동 코드 매핑: `/data_ssd/KT_data_2025/전국_누적_행정동코드_정의서_KT_20251205_code_converted.csv`
  - 컬럼: sido_cd, sido_nm, sgg_cd, sgg_nm, admdong_cd, admdong_nm
  - 수도권: sido_cd가 11(서울), 28(인천), 41(경기)
- 셀 정보: `/data_ssd/KT_data_2025/MSL_CELL_INFO.csv` (셀ID, UTM_X, UTM_Y - EPSG:5179)
- 행정동 shapefile (Phase 2용): `/data_ssd/duhwang/DATA/Work/Human_Mobility/20260212_GIS_Claude_NoWatson/GIS_DATA/{서울,경기도,인천}/(B022)국가기본도_읍면동구역경계/TN_EMD_BNDRY.shp`

## 코드값 매핑
- PURPOSE: 1=출근, 2=등교, 3=귀가, 4=쇼핑, 5=관광, 6=병원, 7=기타
- LivePOP SEX_AGE_CD: F/M + 5세 단위 (F00=0-9세, F10=10-14세, F15=15-19세, ..., F75=75세+)
- Movement AGE_CD: 10세 단위 (00=0-9세, 10=10-19세, ..., 80=80세+)

## 작업 원칙
1. **읽기 전용 데이터**: `/data_ssd/KT_data_2025/` 는 절대 수정/이동/삭제하지 말 것
2. **긴 작업은 tmux 안에서**: 1시간 이상 걸릴 작업은 `tmux new -s 작업명` 안에서 실행
3. **파일럿 먼저, 확장은 나중**: 새 처리 로직은 항상 1개월 파일로 검증 → 사용자 승인 후 전체 적용
4. **메모리 효율**: 큰 CSV는 polars streaming/lazy로 처리. 한 번에 메모리에 다 올리지 말 것
5. **출력은 parquet**: snappy 압축, 행정동 코드(admdong_cd)는 항상 String 타입
6. **로깅**: 모든 처리 결과를 logs/ 에 기록
7. **사용자 확인 없이 전체 데이터 처리 시작하지 말 것**

## 작업 패턴
1. 로컬에서 Python 스크립트 작성 (또는 scripts/ 에 직접)
2. `scp scripts/xxx.py wsson1:/data_ssd/hwcho/projects/kt_mobility/scripts/`
3. `ssh wsson1 "cd /data_ssd/hwcho/projects/kt_mobility && uv run python scripts/xxx.py"`
4. 결과 확인: `ssh wsson1 "ls -la /data_ssd/hwcho/projects/kt_mobility/data/..."`
5. 필요한 결과만 로컬로 가져오기: `scp wsson1:/data_ssd/hwcho/projects/kt_mobility/data/... ./local_data/`

## 현재 진행 상황
- [x] 환경 세팅 (uv, SSH key, 디렉토리 구조)
- [ ] Phase 1: LivePOP 정제 (시간별 인구 스냅샷, 2018~2023, 수도권 행정동)
- [ ] Phase 2: 셀-행정동 매핑 만들기 (Movement 사전 작업)
- [ ] Phase 3: Movement 정제 (이동 OD, 2018~2023, 수도권 행정동)