# MechanicalPortfolio

기계식 주식 포트폴리오의 종목 선정, 순위 점검, 월간 리밸런싱과 원장 기반 성과 재현을 위한 에이전트 스킬입니다. ChatGPT Work와 Codex 로컬 환경에서 사용합니다.

현재 버전: `1.1.8`

## 이번 변경

수동·기간제 제외 종목을 먼저 뺀 뒤 나머지 종목의 요인별 순위와 가중 점수를 계산합니다. 확정 거래는 원장을 다시 읽어 수량·현금·평가액을 검산합니다.

프리마켓 보고서에서는 장전 잠정점까지 그린 성과 곡선 한 장, 전체 1~20위의 가중 점수와 매매 판단을 담은 표, 성과·위험 지표 표 두 개를 제공합니다. 체결가를 최근 가격으로 대체한 경우에는 실제 관측 시각을 표시합니다.

## 설치와 사용

[현재 소스 ZIP](https://github.com/devninjadev/MechanicalPortfolio/archive/refs/heads/main.zip)을 내려받아 압축을 풉니다. 안쪽의 `mechanical-portfolio` 폴더가 스킬 설치 단위입니다. Codex 로컬에서는 이 폴더를 스킬 디렉터리에 복사합니다.

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
