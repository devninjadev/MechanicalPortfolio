# Notion 종가 저장 계약

## 연결 선택

1. 실행 환경에서 `ntn` 실행 파일을 찾고 `ntn --version`, `ntn --help`를 읽는다.
2. 설치되어 있으면 `ntn whoami`와 `ntn api -X GET /v1/users/me`로 인증을 확인한다.
   실제 워크스페이스 ID와 등록 대상을 대조하고 해당 데이터소스 읽기를 시험한다.
   계정 이름 일치만으로 같은 워크스페이스라고 단정하지 않는다.
3. 없거나 실행기·인증·해당 작업 권한이 부족하면 Notion 플러그인의 현재 도구를
   탐색한다. 자기 정보/현재 접근을 읽고 등록 워크스페이스와 대조한다.
   현재 MCP에서는 `fetch`의 `id="self"`가 이 정보를 반환할 수 있다.
4. 새 환경에서 ntn이 없다고 자동 설치하거나 토큰을 요구하지 않는다.
   사용 가능한 플러그인을 먼저 쓴다. 둘 다 없으면 저장만 미완료로 보고한다.

CLI와 MCP는 같은 저장 계약과 실제 ID를 쓴다. ntn이 설치되어 있어도 Work의
실행기에 노출되지 않을 수 있다. 조회 성공으로 미시험 쓰기 권한을 확정하지 않는다.
실패한 저장을 다른 연결로 재시도할 때는 먼저 대상 키를 읽어 중복을 방지한다.
토큰·인증 파일·키체인 내용은 출력, 보고서, DB, 스킬에 저장하지 않는다.

## 이름과 등록 주소

- 허브 페이지: **`기계식 포트폴리오 · 운영 허브`**
- 종가 DB: **`기계식 포트폴리오 · 종가 기록`**
- 기피 DB: **`기계식 포트폴리오 · 기피 종목`**, [별도 수동 설정 계약](notion-exclusions.md)
- 거래 DB: **`기계식 포트폴리오 · 거래 원장`**, [모델 원장 계약](notion-ledger.md)
- 허브와 DB 설명의 표식: **`Mechanical Portfolio storage contract: mp-notion-v1`**

`world-memory-autopilot`의 이름 탐색, 계약 표식, 워크스페이스 바인딩, 불변 ID
등록, 실제 스키마 확인 방식을 참고했다. World Memory의 기존 Hub·DB·자동화는
수정하지 않는다. 이름이 비슷한 기존 투자 자료 DB를 자동 채택하지 않는다.

허브에 다음 주소록을 보존한다. 실제 도구가 반환한 ID만 넣는다.

```json
{
  "schemaVersion": "mp-notion-v1",
  "workspaceId": "<returned-workspace-uuid>",
  "hub": {"pageId": "<returned-page-uuid>", "url": "<returned-notion-url>"},
  "closes": {"dataSourceId": "<returned-close-data-source-uuid>"},
  "exclusions": {"dataSourceId": "<returned-exclusion-data-source-uuid>"},
  "trades": {"dataSourceId": "<returned-trade-data-source-uuid>",
    "activeModelId": "<registered-model-id>"}
}
```

주소록에는 가격, 조회 커서, 작업 상태, 최근 실행시각을 넣지 않는다.
스킬의 `state/notion-registry.json`이 있으면 같은 주소록의 로컬 사본으로 사용한다.
현재 워크스페이스와 정확한 ID를 읽어 확인한 뒤에만 채택한다. 이 파일이 없거나
Work에서 읽을 수 없으면 이름과 계약 표식으로 허브를 찾아 같은 주소록을 읽는다.
DB 컨테이너 ID와 데이터소스 ID는 다르다. 검색/DB 메타데이터의 컨테이너 URL과
query/create의 `data_source_id`를 서로 바꿔 쓰지 않는다.

## 최초 설치와 복구

등록 주소가 있으면 정확한 허브와 데이터소스를 읽는다. 없으면 현재 접근 규칙에
맞는 검색으로 위 이름을 찾고 정확한 후보를 읽는다. MCP 검색은 자기 정보에서
AI 검색이 사용 가능하면 그 도구를 사용하고 아니면 키워드 검색을 사용한다.
ntn은 공개 API 검색을 사용할 수 있다. 결과가 페이지 객체이면 제목은
`properties` 안의 title 속성에서, DB 객체이면 `title`에서 읽는다.
검색 결과의 `has_more`/커서를 확인한다. 불완전한 검색은 부재의 증거가 아니다.

읽기 복구는 정확한 표식, 현재 워크스페이스, 허브 주소록, 실제 데이터소스
필수 속성을 모두 확인한 **유일한** 후보만 채택한다. 후보가 여럿이거나 구조가
맞지 않으면 저장을 보류하고 정확한 대상을 확인한다. 무한 검색·전체 DB 스윕은 하지
않는다. 필요한 검색을 최대 3페이지까지 진행해도 해소되지 않으면 불완전 상태로 남긴다.

종가 저장 요청에 전용 DB의 첫 설치가 포함되고 후보 부재를 확인했으면
허브 → 종가 DB·기피 DB·요청된 거래 DB → 실제 ID/속성 읽기 → 허브 주소록 기록 순으로 생성한다.
새 구조는 쓰기 뒤 한 번 읽어 계약을 확인한다. ntn의 공개 API가 해당 위치의
생성을 지원하지 않으면 같은 워크스페이스의 플러그인으로 그 작업을 수행한다.
부모가 지정되었다면 그 부모를 우선하고, 없으면 현재 도구가 지원하는 개인 영역을
사용한다. 도구가 필수 부모를 요구하고 개인 영역 생성도 불가능하면 그때만 위치를
확인한다. 실패가 불확실하면 정확한 locator/검색으로 결과를 먼저 확인한다.
정상 운영에는 스키마 변경·삭제·이동·과거 전체 이관을 끼워 넣지 않는다.

## 종가 스키마

한 행은 **한 종목의 한 미국 거래일의 당시 명목 정규장 종가**다.
기본 대상은 현재 보유 종목과 분석에 사용한 벤치마크다. 신규 모델은 선정 종목을
쓴다. 성과 재현에 필요한 과거 보유 종목은 요청 기간의 누락 구간만 보완한다.
스크리너 수백 종목의 전체 가격 이력을 기본 수집 대상으로 넓히지 않는다.

공통 DB에 종목·날짜별 행을 누적하고 각 종목의 필터 보기를 만든다.
종목별 보기는 `야후 티커 = 실제 심볼`로 정확히 필터하고 `미국 거래일` 내림차순으로
정렬한다. 전체 보기는 날짜 내림차순·티커 오름차순이다. 표시 열은 이름·거래일·종가·
통화·제공자·상태 위주로 두고 출처·키·시각 등의 관리 열은 숨겨도 원본 행에는 보존한다.
한 행에 여러 종목의 가격을 JSON이나 새 티커 열로 묶지 않는다. 종목마다 별도 DB를
자동 생성하지 않는다. 보기는 같은 행의 표시 방식이므로 데이터 복제나 과거 삭제가 없다.
원장·종가·기피 목록은 별도 DB이며 종가의 한 날짜를 모델 거래 이벤트로 취급하지 않는다.

| 속성 | Notion 타입 | 의미 |
|---|---|---|
| 이름 | title | 종목과 미국 거래일 |
| 기록 키 | rich_text | 중복 검사 키 |
| 종목 식별자 | rich_text | 확인한 공통 EXCHANGE:TICKER |
| 야후 티커 | rich_text | 실제 Yahoo 심볼 |
| 회사명 | rich_text | 표시 이름 |
| 미국 거래일 | date | 날짜만, KST 날짜로 치환하지 않음 |
| 종가 | number | 당시 명목 가격; 미확인은 null |
| 통화 | select | USD |
| 가격 기준 | select | regular_close_as_traded |
| 데이터 상태 | select | 확정, 추정, 미확인 |
| 제공자 | select | Yahoo, Alpaca Paper Trading, TradingView, 미확인 |
| 원천 피드 | rich_text | SIP/IEX/update_mode 등 실제 피드 |
| 원천 필드 | rich_text | Close/dailyBar.c/OHLCV.c 등 |
| 원천 조정 기준 | rich_text | raw/split/배당조정 여부, 역산 근거 |
| 정규장 마감 시각 | date | 시간 포함, KST 표시 |
| 원천 봉 시각 | date | 시간 포함; 제공되지 않으면 비움 |
| 수집 시각 | date | 시간 포함, KST 표시 |
| 출처 URL | url | 실제 가격 근거 URL; 없으면 비움 |
| 데이터 메모 | rich_text | 결측·지연·역산·수정 이유 |

MCP의 DB 생성 기능이 SQL DDL을 받으면 이 표로 `CREATE TABLE`을 구성한다.
ntn 공개 API는 위 타입의 네이티브 `properties` 정의를 전달한다.
현재 `ntn api <path> --spec`으로 설치된 버전의 요청 구조를 확인한다.
DDL을 공개 API의 properties 자리에 넣지 않는다.
페이지 본문에는 필요한 원천 근거와 수정 이유만 넣는다.
현재 Notion 날짜 속성은 시간값의 초를 분 단위로 줄여 반환할 수 있다. 수집 시각
속성은 분 단위로 정규화하고 실제 초 단위 시각은 데이터 메모에도 보존한다.
미국 거래일의 날짜 키와 정규장 마감 시각을 이 표시 정밀도와 혼동하지 않는다.

## 키와 갱신

키는 `종목 식별자|YYYY-MM-DD|regular_close_as_traded|USD`다.
예: `NASDAQ:NVDA|2026-09-29|regular_close_as_traded|USD`.
제공자별 이름·Yahoo 클래스 표기와 공통 식별자를 먼저 대응시킨다.
포트폴리오 이름이나 제공자가 달라져도 같은 종목·거래일의 키는 같다.
합성 티커·심볼 변경의 매핑이 불명확하면 새 행을 만들기 전에 확인한다.

현재 실행에서 확보한 완료 거래일과 요청 기간의 누락 키만 조회한다.

- 0행: 새 기록을 만든다. 미확인은 종가를 비워 상태와 이유만 저장할 수 있다.
- 1행, 같은 의미의 값: 그대로 둔다. 재조회 시각만 바꾸기 위해 다시 쓰지 않는다.
- 1행, 미확인/추정 → 확인된 값: 같은 페이지를 갱신한다.
- 1행, 확정 → 미확인/추정: 기존 확정 기록을 보존한다.
- 1행, 확정 가격 불일치: 같은 세션·기준·기업행동을 재검증한다.
  실제 수정 근거가 확인되면 기존 페이지에 이전 값·새 값·수정 이유를 남긴 뒤
  갱신한다. 해소되지 않으면 충돌을 보고하고 보존한다.
- 2행 이상: 중복 충돌이다. 정상 실행에서 삭제하거나 임의 대표 행을 고르지 않는다.

`scripts/mechanical.py close-plan`은 이 판단을 지원한다. 실제 API 쓰기는 에이전트가
현재 스키마를 사용해 수행하고 결과를 확인한다. Notion은 고유키 제약을 강제하지
않으므로 같은 DB에 여러 실행을 동시에 쓰지 않는다. 다른 실행이 진행 중이면
새 create를 보류하고 키를 다시 읽는다.

## ntn와 MCP 전송

ntn 0.23.8에서 확인한 읽기/요청 형태:

```text
ntn api -X GET /v1/users/me
ntn api -X GET /v1/data_sources/<id>
ntn api -X POST /v1/search -d @request.json
ntn api -X POST /v1/data_sources/<id>/query -d @request.json
ntn api -X POST /v1/pages -d @request.json
ntn api -X PATCH /v1/pages/<id> -d @request.json
ntn api -X GET /v1/views?database_id=<id>
ntn api -X POST /v1/views -d @request.json
ntn api -X GET /v1/views/<view-id>
```

본문은 파일 또는 표준입력으로 전달하고 최신 도움말/`--spec`을 확인한다.
키 조회 필터는 공개 API에서 `{"property":"기록 키","rich_text":{"equals":key}}`다.
복수 키는 `or`로 묶고 결과 커서를 끝까지 읽는다. 날짜 범위를 조회할 때도
원천 `has_more`를 확인한다. `ntn pages create/edit`는 일반 Markdown용이며
프런트매터의 임의 속성을 무시할 수 있으므로 종가 속성 쓰기에는 `ntn api`를 쓴다.
설치된 공개 API가 보기를 지원하면 같은 ntn 연결을 우선한다. 보기 목록이 ID만
반환하면 각 ID를 읽어 이름·필터·정렬·원본 데이터소스를 확인한다. 보기 생성 요청의
`configuration.properties`는 현재 스키마의 property ID를 사용한다. 공개 API가 해당
기능을 지원하지 않으면 플러그인의 `create_view`와 현재 DSL을 확인해 보완한다.

MCP는 실제 데이터소스를 먼저 fetch하고 현재 `query_data_sources`의 rows/SQL/
view 지원과 권한을 확인한다. 정확한 plain-text 키/날짜 조회에는 지원되는
구조화 필터 또는 매개변수 SQL을 쓴다. 범위를 제한한 조회만 수행한다.
SQL의 손실된 리치텍스트를 원문 손상으로 해석하지 않는다.
저장 view에 요청 날짜가 없다고 DB 전체에 키가 없다고 간주하지 않는다.
행 쓰기는 현재 `create_pages`/`update_page` 스키마를 확인한다. 날짜는 MCP의
`date:<속성>:start`, `date:<속성>:is_datetime` 등 실제 전송 계약을 사용한다.
ntn에서는 네이티브 `{"date":{"start":...}}` 등 속성 객체를 쓴다.

쓰기 성공 응답을 캡처한다. 새 구조, 배치 삽입, 불확실 응답은 해당 키/ID를
한 번 읽어 확인하고 미완료 항목만 재시도한다. 일반 단건의 확정 성공은
불필요하게 재조회하지 않는다. 부분 성공은 완료 건수를 보존해 보고한다.
