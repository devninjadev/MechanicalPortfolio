# 가격 제공자와 검증

목차: [폴백 실행](#폴백-실행) · [Yahoo](#yahoo-1차) ·
[Alpaca Paper Trading](#alpaca-paper-trading-폴백) · [TradingView](#tradingview-폴백) ·
[종가 검증](#채택과-결측)

가격 요청은 `종목 식별자 + 거래일/기간 + 세션 + 필드 + 조정기준 + 통화`다.
각 요청별 **Yahoo → Alpaca Paper Trading → TradingView** 순서를 적용한다.
야후에서 확보하지 못한 종목·날짜·필드를 폴백하고 이미 확보한 성공 구간은 보존한다.
제공자 비교를 위한 연결 시험과 실제 폴백을 구분한다.

## 폴백 실행

| 현재 경로의 상태 | 다음 행동 |
|---|---|
| Yahoo 접근 거절·연결 불가·도구 미지원·오류·빈 응답·필요 구간 결측 | 연결된 Alpaca Paper Trading MCP의 `get_stock_bars`로 바로 조회한다. |
| 현재 환경에서 Yahoo를 쓸 수 없다는 구체적인 제한이 확인됨 | 같은 실패를 반복하지 않고 Alpaca부터 조회한다. |
| Alpaca 도구·피드가 요청 가격을 제공하지 못함 | 지원되는 역사 조회·기간 분할을 확인한 뒤 TradingView MCP 연결·관련 도구·플러그인·스킬을 찾아 조회한다. |
| 모든 승인된 경로에서 해당 가격을 얻지 못함 | 해당 값만 미확인으로 두고 가능한 다른 종목·기간의 작업을 계속한다. |

단순히 안 될 것 같다는 추측으로 폴백까지 실패했다고 단정하지 않는다. 실제로
사용 가능한 도구와 요청 범위를 확인한다. 사용자가 지정한 폴백에는 같은 확인을
반복 요구하지 않는다. 접근 제한이나 별도 승인이 명시된 작업은 그 요건을 따른다.
실패 원인·대체 경로·남은 작업은 채팅에 보고하고 분석 페이지에는 사용한 가격의
출처·기준과 분석에 영향을 주는 결측만 남긴다.

실제 연결/도구, 원천 심볼, 필드, 피드, 원천 봉시각, 수집시각, 거래일, 
정규장 마감시각, 지연, 조정기준을 남긴다. 봉 시작시각은 종가 체결시각이 아니다.
표시는 KST, 거래일 판정은 거래소 시간대와 실제 달력 기준이다.

## Yahoo 1차

실행기가 있으면 yfinance를 우선한다. 로컬은 프로젝트 venv와
`reference/yfinance_reference.md`를 확인한다. Work는 현재 런타임의 패키지와
네트워크를 확인한다. Yahoo 도구/웹이 실제 일별 OHLCV를 반환한다면 가능하다.
검색 스니펫은 일봉을 대체하지 않는다.

```python
history = yf.Ticker(yahoo_symbol).history(
    start=start_date, end=exclusive_end_date, interval="1d",
    auto_adjust=False, repair=False, prepost=False, actions=True,
)
```

`end`는 제외 경계다. 요청 거래일을 포함하도록 다음 날짜를 전달하고 실제 인덱스와
완료된 세션을 확인한다. `Close`와 `Adj Close`를 구분한다. `auto_adjust=False`는
배당 총수익률 조정을 끄며 과거 Close의 주식분할 처리까지 무조정이라고 보장하지
않는다. 분할 기준을 원장 수량과 맞춘다. Notion의 당시 명목 종가로 과거를
채울 때는 분할 역산을 기업행동 근거와 함께 수행하거나 미확인으로 남긴다.

프리마켓은 `marketState`, `preMarketPrice`, `preMarketTime`을 확인한다.
없으면 전일 종가를 참고값으로 표시하고 당일 프리마켓 가격이나 0%로 저장하지 않는다.

## Alpaca Paper Trading 폴백

사용자가 지정한 **Alpaca Paper Trading MCP**를 사용한다. 현재 Work에서는
`mcp__codex_apps__alpaca_paper_trading_get_stock_bars`가 연결된 역사 가격 도구다.
Yahoo가 거절되거나 필요한 가격을 얻지 못하면 이 도구를 직접 호출한다.
다른 환경에서 도구 이름이 달라졌으면 같은 플러그인의 시장 데이터 도구를 탐색한다.
가격 바, 스냅샷, 최근 체결, 달력의 **조회 기능**만 사용한다.
계좌 변경이나 모의·실제 주문을 가격 폴백 단계에 넣지 않는다.

일별 가격에는 `timeframe="1Day"`, 시작일과 종료일을 지정한 `start`·`end`,
`symbols`, `feed`, `adjustment`, `currency`를 전달한다. 도구의 기본 최근 5일을
그대로 사용하지 않는다. 시작 시가·체결 기준에 1분봉이 필요하면 해당 세션의
`timeframe="1Min"`을 별도로 요청한다. 최신 스냅샷만으로 과거 성과를 대신하지 않는다.

확정 종가는 합산 시장 SIP 일봉을 우선한다. 피드·기간·조정 옵션을
명시하고 `next_page_token`이 있으면 끝까지 읽는다. 현재 MCP처럼 페이지 토큰
입력이 없는 도구에서는 종목·기간을 나누어 제한 안에서 전 구간을 확보한다.
수량 제한은 모든 종목의 합계일 수 있으므로 종목·거래일별 누락을 검사한다. 당시 명목 종가는
`adjustment=raw`, 분할조정 비교 시계열은 `adjustment=split`로 용도에 맞춘다.

`dailyBar`, `prevDailyBar`, `latestTrade`는 시점과 의미가 다르다.
미완성 일봉은 채택하지 않는다. 최신 SIP 구독 권한 오류를 과거 SIP 전체의
불가로 간주하지 않는다. 역사 조회에서는 요청 `end`가 현재보다 최소 15분 이전인지
확인하고 접근 가능한 완료 구간을 조회한다. 인증 오류·접근 불가가 남으면
TradingView로 진행한다. IEX는 단일 거래소다. 공식 합산 종가로 확정하지 않고
참고값은 `추정`으로 구분한 뒤 계속 폴백한다. 도구가 지연 SIP를 지원하면
실제 지연과 완료 시점을 확인한다.

## TradingView 폴백

`https://mcp.tradingview.com/mcp`를 사용하는 등록 연결의 실제 도구를 먼저 확인한다.
현재 도구 목록·도구 검색에서 TradingView 관련 MCP와 플러그인을 찾고, 스킬 목록의
연결·조회 지침도 확인한다. 관련 스킬이 있으면 읽어 그 절차와 실제 도구 스키마를 따른다.
로컬 환경이라면 등록 MCP 설정의 주소와 도구 노출을 확인한다. 이름이나 주소만
확인하고 조회까지 성공했다고 간주하지 않는다. 발견한 연결로 가격 조회를 실제로 수행한다.
심볼 검색으로 `EXCHANGE:TICKER`, 상품 종류, 통화를 확인한다.
종가, 과거 봉, 개장 가격, 프리마켓은 별도 기능일 수 있다.

요청 거래일의 **완료된** 1D 봉을 선택한다. `summary.last_close`나 배열의
마지막 원소를 무조건 채택하지 않는다. 가격과 스크리너 성공은 별도다.
이번 연결의 OHLCV는 정규장 봉, 분할 조정, 거래소별 15분 이상 지연과 대체
피드 가능성을 알렸다. 다음 호스트의 영구 능력으로 가정하지 말고 응답을 읽는다.
마지막 미완성 봉은 제외한다. `close`·`update_mode`는 현재 관측일 수 있다.
`premarket_close=null`을 0이나 현재 프리마켓 가격으로 바꾸지 않는다.

## 채택과 결측

확정 종가는 종목·거래일·통화·정규장 일봉 종가가 맞고 실제 마감과
알려진 지연 이후에 확보했으며 조정기준이 호환되고 양수의 유한값이어야 한다.
원천 체결시각이 없어도 일봉 거래일과 실제 달력 마감으로 완료를 검증할 수 있다.
수집시각을 원천 체결시각으로 꾸미지 않는다.

마감 전, 다른 거래일, 미완성·지연 미충족, 시간외, 통화/분할 불명, 호가 혼동은
확정 저장에서 제외한다. 모두 실패하면 `미확인`이다. 전일 종가를 오늘의
새 종가 행에 복제하지 않는다. 과거 결측을 전방 채워 완전한 성과라고 주장하지 않는다.

자료:
[yfinance Ticker.history](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html),
[Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars),
[Alpaca Market Data FAQ](https://docs.alpaca.markets/docs/market-data-faq).
현재 연결의 실제 입력·출력 지원 범위를 함께 확인한다.
