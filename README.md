# MechanicalPortfolio

기계식 주식 포트폴리오의 종목 선정, 순위 점검, 월간 리밸런싱과 원장 기반 성과 재현을 위한 에이전트 스킬입니다. ChatGPT Work와 Codex 로컬 환경에서 사용합니다.

현재 버전: `1.1.4`

## 이번 변경

보고서 도입문 바로 다음 첫 섹션에 `원장 기반 성과 곡선`을 배치합니다. 해당 섹션에는 포트폴리오와 지정 벤치마크의 차트 한 장, 계산 가정을 담습니다. 이미지 삽입과 발행 후 확인 절차에도 이 순서를 반영했습니다.

## 설치와 사용

릴리즈의 `mechanical-portfolio-v1.1.4.zip`을 내려받아 사용 중인 에이전트 환경의 스킬 설치 기능으로 추가합니다. Codex 로컬에서는 압축을 풀고 `mechanical-portfolio` 폴더를 해당 환경의 스킬 디렉터리에 설치합니다.

예시 요청: `기계식 포트폴리오 스킬로 현재 원장 기반 보고서를 작성해줘.`

스킬 본문과 참조 지침은 [`mechanical-portfolio/SKILL.md`](mechanical-portfolio/SKILL.md)에 있습니다. Python 헬퍼는 Python 3.9 이상과 시스템 시간대 데이터를 사용하며 외부 Python 패키지를 요구하지 않습니다.

## 운영 범위

15종목 선정, 20위 보유 버퍼, 월간 동일가중 조정과 순위 이탈 교체 규칙을 적용합니다. Yahoo 가격을 우선 사용하고 필요한 구간을 Alpaca Paper Trading과 TradingView로 보완합니다. Notion 종가 기록, 거래 원장, 기피 종목 설정은 실행 환경에서 대상과 권한을 확인합니다.

이 스킬은 모델 포트폴리오와 원장을 다루며 증권사 주문은 실행하지 않습니다. 개인별 성과 시작일과 보유 가정은 사용자 설정 또는 등록 모델에서 읽습니다. 사용자별 Notion 주소록과 실행 데이터는 배포본에 포함하지 않습니다.

## 헬퍼 검증

```bash
cd mechanical-portfolio
python3 -m unittest discover -s scripts -p 'test_mechanical.py'
```
