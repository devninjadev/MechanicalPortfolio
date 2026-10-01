# 헬퍼 입력과 로컬 연동

## 실행 계약

스킬 폴더 기준:

```text
python3 scripts/mechanical.py <command> < input.json
python3 -m unittest discover -s scripts -p 'test_mechanical.py'
```

호스트의 실행 도구에서 스킬 폴더를 작업 디렉터리로 지정하거나 실제 절대경로를
사용한다. Python 3.9 이상과 시스템 시간대 데이터가 필요하며 외부 Python
패키지는 사용하지 않는다. Work에 로컬 Mac 경로를 복사하지 않는다.
`--help`에 실제 명령이 있다.
출력 JSON의 `ok`, 오류 코드, 보류 상태를 검사한다. 헬퍼는 외부 조회·쓰기·체결을
실행하지 않는다. 호출자가 전달한 확인 플래그는 실제 원천 근거와 연결해야 한다.
플래그를 true로 넣었다는 사실은 원천 완전성의 증거가 아니다.

## resolve-exclusions

```json
{
  "lookup_complete":true,
  "as_of":"2026-10-01T00:00:00+09:00",
  "rows":[{"page_id":"<actual-page-id>","ticker":"AAA","security_id":"NASDAQ:AAA",
    "state":"제외","starts_at":"2026-09-30T00:00:00+09:00","ends_at":null,
    "created_at":"2026-09-29T15:00:00Z","reason":"사용자 지정"}]
}
```

현재 Notion 설정의 전체 읽기와 심볼 대응 뒤 표준 입력으로 변환한다.
티커는 스크리너의 표준 티커이며 Yahoo 주식 클래스 별칭은 먼저 변환한다.
`starts_at=null`이면 실제 `created_at`을 사용한다. 날짜만 있으면 에이전트가
KST 00:00으로 정규화한다. 상태 `해제`에는 `ends_at`이 필요하며 `대기`는 무시한다.
같은 입력에 과거 `as_of`를 주면 그때 유효한 기간만 반환한다.
전체 읽기가 확인되고 `effective_complete=true`일 때만 반환 `exclusions`를
rank/decision-plan에 함께 전달한다. `exclusions=[]`도 유효한 설정이다.
`effective_complete=false`의 `resolved_exclusions`는 잠정 표시용이다.
그 목록으로 매매를 확정하지 않는다. 헬퍼는 Notion을 수정하지 않는다.

## rank

```json
{
  "source_complete": true,
  "universe_verified": true,
  "exclusions": [],
  "rows": [{"Ticker":"AAA","Company":"Example","SymbolFull":"NASDAQ:AAA",
    "MktCap_USD":20000000000,"ADTV_90D_USD":300000000,
    "PSR":2.5,"RevenueGrowth_YoY_Q_%":12}]
}
```

숫자는 단위를 변환한 값이며 이미 전체 스크리너 조건을 검증한 행이다.
예시 1행 자체는 실제 전체 시장 근거가 아니다. 결측을 먼저 Yahoo로 보정한다.
`exclusions=[]`는 수동 제외가 없는 설정을 뜻한다. 출력의 `ranked`, `data_gaps`,
`ranking_complete`를 읽는다. 결측이 있는 결과는 순위 확정에 사용하지 않는다.
명시적·근거 있는 필터 탈락은 입력 전 별도 확인 목록으로 보존한다.

## decision-plan

입력: `ranked`는 rank 결과, `ranking_complete`는 그 결과의 동일 필드,
`holdings`는 확인된 기존 티커 배열, `verified_universe_exits`는 실제 필터 탈락이
확인된 티커만, `monthly_due`는 달력과 원장으로 확인한 이번 정기 조정 필요 여부다.
`exclusions`, `target_size=15`, `buffer_rank=20`을 바꿀 수 있다.
반환은 구성 교체 `composition_trades`, 보류 종목, 목표 구성, 비중 처리 방식이다.
구성 교체가 비어 있어도 월간 비중 조정은 필요할 수 있다. 헬퍼는 수량과 가격을
받지 않으므로 비중 조정 주문·원장 이벤트를 계산했다고 주장하지 않는다.
`fills_confirmed=false`는 가격·원장 확인 전 상태다.

## next-session

```json
{
  "kind":"replacement", "observed_at":"2026-09-30T23:00:00+09:00",
  "calendar_complete":true,"calendar_start":"2026-09-30","calendar_end":"2026-10-02",
  "sessions":[
    {"session_date":"2026-09-30","open_at":"2026-09-30T13:30:00Z","close_at":"2026-09-30T20:00:00Z"},
    {"session_date":"2026-10-01","open_at":"2026-10-01T13:30:00Z","close_at":"2026-10-01T20:00:00Z"},
    {"session_date":"2026-10-02","open_at":"2026-10-02T13:30:00Z","close_at":"2026-10-02T20:00:00Z"}
  ]
}
```

`kind=initial`도 미래 첫 시가를 고른다. `kind=monthly, month=YYYY-MM`이면
해당 월 전체를 포함하는 실제 달력을 전달하고 월 첫 거래일을 고른다.
반환 시각은 **예정 기준**이며 아직 실제 첫 유효 1분봉·체결가가 아니다.
과거 월의 예정 시각을 반환했다고 누락 이벤트를 소급 기록하지 않는다.
먼저 기존 원장·당시 조건·이번 변경 권한을 확인한다.

## validate-close

입력은 `requested_security_id`, `requested_session_date`, `candidate`다.
candidate에는 `security_id, session_date, value, session="regular", interval="1d",
field, currency="USD", price_basis="regular_close_as_traded", provider, feed,
session_close_at, observed_at, delay_seconds, finalized`를 넣는다.
타임스탬프는 시간대 포함, 날짜는 미국 거래일이다. `feed_scope`가 단일 거래소 또는
미확인이면 그 값을 `single_venue`/`unknown`으로 넣는다. 가격과 원천 근거를
수집한 뒤 정규화하며 raw와 분할조정의 차이를 해소하지 않은 candidate에는
as_traded를 붙이지 않는다. `eligible_confirmed_close=true`만 확정 저장 후보다.
이 판정도 원천 응답의 의미를 읽는 대신 사용할 수 없다.

## close-plan

입력: `lookup_complete=true`, `records` 배열, `existing` 배열.
records의 필수 필드는 `security_id, session_date, currency, price_basis, status,
provider, value`다. 기존 행은 같은 필드에 실제 `page_id`를 추가한다.
검증된 상태는 `확정/추정/미확인`, provider는 `Yahoo/Alpaca Paper Trading/TradingView/미확인`이다.
미확인은 `value=null`이며 모든 기록 키는 필드에서 계산한다.
추가 출처·시각·메모 필드는 record 안에 보존한다.

`create/update/skip/conflict`를 검사하고 create/update만 실제 도구에 전달한다.
동일 값은 조회시각만 달라졌다고 갱신하지 않는다. Yahoo 숫자 정밀도의 작은
차이는 같은 값으로 처리한다. 확정 종가 변경은 실제 재검증 후
`verified_correction_keys=[key]`와 해당 record의 `correction_note`를 전달해야
수정 계획이 나온다. 이 배열은 사용자 허가 플래그가 아니라 호출자가 확보한
수정 근거의 범위다. 이전 값과 변경 이유도 보존한다.
Notion의 속성 값은 현재 연결 스키마로 변환한다. 헬퍼 반환만으로 저장 성공이 아니다.

## 기존 금융 프로젝트 어댑터

이 스킬은 자체 전략 계약을 갖고 있으며 특정 저장소가 필수는 아니다.
기존 프로젝트가 있는 로컬에서만 다음 도구를 재사용한다.

- `scripts/portfolio_cli.py --base-dir <등록 모델 디렉터리> positions --asof YYYY-MM-DD --format json`
- `scripts/portfolio_cli.py mechanical --help`와 `--input-csv`, `--no-yfinance-backfill` 등 현재 옵션.
- `scripts/portfolio_cli.py add-trade --help`: 원장 변경 요청이 있을 때만.
- 분석 전후 등록 모델 원장과 원본 비교 자료의 해시/바이트 비교.
- 금융 상담 메모리 `counsel_memory_cli.py prepare-turn`: 그 프로젝트의 현재 규칙 적용.

먼저 실제 프로젝트 경로를 확인한다. Mac 한글 파일 작업은 Python으로 NFD
정규화한 Path를 사용한다. Git 기존 변경은 보존하고 커밋·푸시는 요청 범위에 따른다.
등록 모델의 실제 디렉터리를 명시하고 원본 비교 자료와 합산하지 않는다.
모델에서 제외한 원본 이벤트를 프로젝트의 기본 경로에서 다시 가져오지 않는다.

기존 코드의 일부 기본값은 이 스킬과 다를 수 있다. 가격 캐시가 `auto_adjust=True`
또는 전방 채우기를 쓰는지 확인한다. 결측의 유니버스 이탈 판정, 10일 거래량
근사치, 자동 통계 PNG, 기본 `.md`/ZIP 출력은 그대로 사용하지 않는다.
기존 CLI 결과는 표준 필드와 저장한 근거로 다시 검사한다.
보고서 문체는 한국어이며 마지막 섹션은 결론이다. 로컬 프로젝트의
`ReportWritingStyle.md`와 `report_hygiene_harness.py`가 있으면 임시 본문 검증에
사용하되 Page 이미지 삽입은 네이티브 참조 발행 단계에서 처리한다.
Work는 같은 내용·출처·수치 검사를 수행하고 로컬 하네스 부재만으로 막지 않는다.

기존 프로젝트에서 사용 중단된 로컬 World Memory DB는 새로 조회·갱신하지 않는다.
필요한 리서치 맥락은 등록된 Notion World Memory 또는 허용된 GUI 컨텍스트를
읽고 최신 근거로 확인한다. 기계식 가격·순위를 해당 메모리의 과거 수치로 대신하지 않는다.

## continuous-ledger

사용자가 원장 재구성을 요청했을 때만 사용하는 순수 계산 헬퍼다.

```json
{
  "model_id":"example-continuous-v1",
  "source_events":["<실제 cash/trade/nav_snapshot 객체 배열>"],
  "pause_date":"2026-06-01",
  "transition_date":"2026-06-15",
  "target_size":15,
  "transition_prices":{"AAA":123.45},
  "transition_actions_verified":true,
  "pause_split_events":[],
  "rebalance_dates":["2026-07-01","2026-08-03"],
  "event_times":{"2026-06-15":"2026-06-15T13:30:00Z"}
}
```

모델 ID·날짜와 예시 문자열은 설명용이며 실제 모델 기본값이나 이벤트가 아니다.
실행 시에는 등록 모델에서 확인한 값으로 바꾼다.
`source_events`는 날짜순 원본 전체이며 cash/trade만 계산에 사용한다. 원본 NAV
스냅샷은 결과에 복사하지 않는다. `transition_prices`는 기존·신규 구성의 합집합을
모두 포함하는 같은 거래일·가격 기준의 확인된 시가다. Yahoo의 auto_adjust=False와
기업행동 조회 근거를 보존하고, 조정 여부가 해소되지 않으면 확인 플래그를 넣지 않는다.
모델 변경 구간에 분할이 있거나 기업행동 확인이 안 된 경우 별도 수량 재현 정책 없이
계산하지 않는다. 현재 헬퍼는 분할이 없는 것으로 확인한 구간만 지원한다.

보유 중 원본에 예상 밖의 거래·입출금이 있으면 멈추어 해당 지시를 확인한다.
기존 매도·BOXX 대기를 제외하고 전환일 평가금액으로 순매도·순매수를 계산한다.
이후 지정된 조정 날짜에는 동일가중을 재계산하고, 단순 교체일에는 매도대금만 새
종목에 배정하여 유지 종목의 수량을 바꾸지 않는다. 정확한 같은 날짜에 서로 다른
가격이 섞인 거래 묶음과 0이 아닌 수수료는 별도 비용·순서 정책 없이 합치지 않는다.
같은 가격의 반복 조정은 최종 구성을 한 순거래 묶음으로 재현하고 모든 원본 ID를
연결한다. 사전 이관 거래가 같은 날짜에 매수부터 나열되어 있으면 자금 흐름 재현을
위해 입금·매도 후 매수 순으로 정렬하며 정확한 실제 일중 순서를 주장하지 않는다.

출력의 `events`, `hold_period`, `transition_nav`, `holdings`, `cash`, `groups`,
`suppressed_source_event_ids`를 확인한다. 추가 외부 자금이 없고 중복 ID·음수 보유·
음수 현금이 없어야 한다. `writes_executed=false`는 계산 결과만 존재한다는 뜻이다.
별도로 실제 Notion 키·가격·수량·금액을 저장하고 읽어 확인해야 이관 완료다.
새 모델과 기존 원본을 같은 원장에 이어 붙이지 않는다.
