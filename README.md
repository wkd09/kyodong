# Gyodong Village CS Agent (교동마을 산지직송 CS 에이전트)

AI_TOP_100 [2026] 예선 대회용 고객 응대 AI 에이전트 백엔드 서버입니다.

## 주요 기능
- 카카오 i 오픈빌더 REST API 규격 준수 (단일 `SimpleText`, 450자 이내 축약 보장)
- 테스트 케이스 ID(`X-Aitop100-Test-Case-Id`) 발화 자동 감지 및 세션 유지
- 주최 측 액션 API(주문 조회, 배송 조회, 재배송 접수, 환불 신청, 긴급 에스컬레이션 등) 실시간 연동
- 교동마을 17개 인계 자료 및 4대 절차서(E48 결제대사, B10 권한위임, 에스컬레이션 3레인, B13 수산물중량) 룰 엔진 반영

## 실행 방법
```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port $PORT
```
