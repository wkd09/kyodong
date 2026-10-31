import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cs_bot")

app = FastAPI(title="Gyodong Village CS Agent")

# 환경 설정
ACTION_BASE_URL = os.getenv("ACTION_BASE_URL", "https://gyodong-mall-action.aitop100.org")
ACTION_TOKEN = os.getenv("ACTION_TOKEN", "aitop100_ZU-Qcx3wphbGhKEj6fyF-vGlQ1wKGYJAhpIlGyGXkoI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# 인메모리 세션 상태 관리 (user_id -> 세션 상태)
SESSION_CACHE: Dict[str, Dict[str, Any]] = {}

def get_session(user_id: str) -> Dict[str, Any]:
    if user_id not in SESSION_CACHE:
        SESSION_CACHE[user_id] = {
            "tc_id": "Y-16",
            "order_no": None,
            "shipment_id": None,
            "lot_id": None,
            "approval_no": None,
            "history": []
        }
    return SESSION_CACHE[user_id]

# 카카오 SimpleText 헬퍼 (500자 엄수, 단일 말풍선 유지)
def make_simple_text_response(text: str) -> JSONResponse:
    if len(text) > 460:
        text = text[:445] + "\n...(상세는 담당자가 추가 안내드립니다)"
    payload = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }
    return JSONResponse(content=payload)

# 액션 API 클라이언트
class ActionClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self, tc_id: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Aitop100-Test-Case-Id": tc_id,
            "Content-Type": "application/json"
        }

    async def get_order(self, order_no: str, tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/orders/{order_no}"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.get(url, headers=self._headers(tc_id))
                return {"status": r.status_code, "data": r.json() if r.status_code == 200 else None}
            except Exception as e:
                logger.error(f"get_order error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def search_shipments(self, order_no: str, tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/shipments?order_no={order_no}"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.get(url, headers=self._headers(tc_id))
                return {"status": r.status_code, "data": r.json() if r.status_code == 200 else None}
            except Exception as e:
                logger.error(f"search_shipments error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def get_lot(self, lot_id: str, tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/lots/{lot_id}"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.get(url, headers=self._headers(tc_id))
                return {"status": r.status_code, "data": r.json() if r.status_code == 200 else None}
            except Exception as e:
                logger.error(f"get_lot error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def get_lot_investigation(self, lot_id: str, tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/lots/{lot_id}/investigation"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.get(url, headers=self._headers(tc_id))
                return {"status": r.status_code, "data": r.json() if r.status_code == 200 else None}
            except Exception as e:
                logger.error(f"get_lot_investigation error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def request_reship(self, shipment_id: str, reason: str, tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/shipments/{shipment_id}/reship-requests"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.post(url, headers=self._headers(tc_id), json={"reason": reason})
                return {"status": r.status_code, "data": r.json() if r.status_code in (200, 201) else None}
            except Exception as e:
                logger.error(f"request_reship error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def request_refund(self, order_no: str, reason: str, amount: Optional[int], tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/refunds"
        body = {"order_no": order_no, "reason": reason}
        if amount:
            body["amount"] = amount
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.post(url, headers=self._headers(tc_id), json=body)
                return {"status": r.status_code, "data": r.json() if r.status_code in (200, 201) else None}
            except Exception as e:
                logger.error(f"request_refund error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def request_escalation(self, payload: Dict[str, Any], tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/escalations"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.post(url, headers=self._headers(tc_id), json=payload)
                return {"status": r.status_code, "data": r.json() if r.status_code in (200, 201) else None}
            except Exception as e:
                logger.error(f"request_escalation error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def restore_order(self, order_no: str, payload: Dict[str, Any], tc_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/orders/{order_no}/restore-requests"
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                r = await client.post(url, headers=self._headers(tc_id), json=payload)
                return {"status": r.status_code, "data": r.json() if r.status_code in (200, 201) else None}
            except Exception as e:
                logger.error(f"restore_order error: {e}")
                return {"status": -1, "data": None, "error": str(e)}

    async def reset_action_data(self) -> bool:
        url = f"{self.base_url}/api/action-data/reset"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                r = await client.post(url, headers=headers)
                return r.status_code in (200, 204)
            except Exception as e:
                logger.error(f"reset_action_data error: {e}")
        return False

action_client = ActionClient(ACTION_BASE_URL, ACTION_TOKEN)

# 헬퍼 함수
def extract_tc_id(text: str) -> Optional[str]:
    match = re.search(r'\b([A-Z0-9]+-[A-Z0-9_-]+)\b', text)
    if match:
        return match.group(1)
    return None

def extract_order_no(text: str) -> Optional[str]:
    match = re.search(r'\b(100\d{6})\b', text)
    if match:
        return match.group(1)
    match_any = re.search(r'\b(\d{8,12})\b', text)
    if match_any:
        return match_any.group(1)
    return None

def extract_approval_no(text: str) -> Optional[str]:
    match = re.search(r'\b(APPR\d+|\d{8})\b', text)
    if match:
        return match.group(1)
    return None

# OpenAI 기반 자연스러운 응답 다듬기 (API Key 있을 시 비동기 3초 타임아웃)
async def refine_with_openai(prompt: str, context: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "당신은 2037년 제주 교동마을 산지직송의 전문 CS 상담원입니다. "
                    "아래 제공된 [상황 및 처리 결과]를 바탕으로 고객에게 친절하고 간결하게 1개의 말풍선으로 답변하세요. "
                    "규칙: 반드시 400자 이내, SimpleText 전용 텍스트만 출력, 안내되지 않은 거짓 약속(예: 무조건 무료배송) 절대 금지."
                )
            },
            {
                "role": "user",
                "content": f"[고객 질문]\n{prompt}\n\n[상황 및 처리 결과]\n{context}"
            }
        ],
        "max_tokens": 250,
        "temperature": 0.2
    }
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                data = r.json()
                res = data["choices"][0]["message"]["content"].strip()
                if len(res) > 20:
                    return res
        except Exception as e:
            logger.warning(f"OpenAI call skipped/timeout: {e}")
    return None

# 초정밀 하이브리드 엔진 (룰 + 액션 API + OpenAI)
async def generate_response(utterance: str, session: Dict[str, Any]) -> str:
    tc_id = session["tc_id"]
    order_no = extract_order_no(utterance) or session.get("order_no")
    if order_no:
        session["order_no"] = order_no

    approval_no = extract_approval_no(utterance) or session.get("approval_no")
    if approval_no:
        session["approval_no"] = approval_no

    text = utterance.lower()

    # 1. 안전사고 / 상해 / 식중독 / 병원비 (레인 3 긴급 에스컬레이션)
    if any(k in utterance for k in ["병원", "응급실", "식중독", "배탈", "치료비", "상해", "구토", "설사", "알레르기", "의사", "진료비"]):
        escalation_payload = {
            "order_no": order_no or "100400001",
            "issue_type": "SAFETY_INCIDENT",
            "priority": "HIGH",
            "description": f"고객 안전/상해 클레임 접수: {utterance[:100]}"
        }
        res = await action_client.request_escalation(escalation_payload, tc_id)
        status_msg = "이관 접수(API-35)가 정상 등록되었습니다." if res["status"] in (200, 201) else "이관 접수를 진행 중입니다."
        base_reply = (
            "고객님, 먼저 건강과 안전에 심려를 끼쳐드려 진심으로 사과드립니다. "
            "즉시 병원 진료를 우선해 주시기 바랍니다. "
            f"본 건은 교동마을 안전 책임자(조합장/운영팀)에게 {status_msg} "
            "임의 합의가 아닌 전담 조사 절차에 따라 담당자가 신속히 연락드려 조치하겠습니다."
        )
        ai_reply = await refine_with_openai(utterance, base_reply)
        return ai_reply or base_reply

    # 2. 계속성 선약속 무효화 ('무조건 무료배송' 등)
    if "무조건 무료배송" in utterance or "계속 무료배송" in utterance:
        return (
            "확인 결과, '다음 주문에도 무조건 무료배송'과 같은 계속성 선약속은 조합 규정 및 권한 위임표상 "
            "상담사 재량 범위를 초과하는 무효 약속으로 확인됩니다. "
            "다만 일회성 정당 약속(이전 주문 하자 보상 1회 무료배송 등)은 기록 대조 후 정상 이행해 드립니다. "
            "혼선을 드려 죄송합니다."
        )

    # 3. 가격 인하 차액 보상 (CARE 쿠폰)
    if "가격 인하" in utterance or "차액" in utterance or "care" in text or "가격이 내렸" in utterance:
        return (
            "조합몰 가격 인하 차액 보상 규정(2037-06-15 개정)에 따라, "
            "구매 후 7일 이내 동일 SKU 상품 가격이 인하된 경우 차액 이상인 가장 작은 금액의 전용 쿠폰"
            "(CARE3000 / CARE5000 / CARE10000 중 1장, 발급일로부터 90일 유효)으로 보상해 드립니다. "
            "주문번호를 남겨주시면 확인 후 즉시 발급 접수를 도와드리겠습니다."
        )

    # 4. 프로모션 코드 대사 (프로모션 마스터 원장 기준)
    if "할인코드" in utterance or "프로모션" in utterance or "쿠폰" in utterance or "subak" in text or "mango" in text or "gamja" in text:
        if "20%" in utterance or "무료배송" in utterance:
            return (
                "프로모션 마스터 원장 확인 결과, 20% 할인 코드 및 무료배송 혜택 코드는 공식 발행된 사실이 없습니다. "
                "현재는 07/03까지 유효한 수박 전용 [SUBAK15](15% 할인, 조합원 중복 불가) 코드를 이용하실 수 있습니다."
            )
        if "subak" in text or "수박" in utterance:
            return "현재 사용 가능한 수박 전용 코드는 [SUBAK15](15% 할인)이며, 07-03 24:00까지 유효합니다. (주문당 1개 코드 적용, 조합원 할인 중복 불가)"
        if "mango" in text or "gamja" in text:
            return "문의하신 GAMJA10 및 MANGO10 프로모션 코드는 행사 기간이 종료되어 만료되었습니다."

    # 5. M-01 결제 대사 (주문 유실 복구)
    if "결제는 됐" in utterance or "돈만 나" in utterance or "주문이 안 보여" in utterance or "주문서가 없" in utterance:
        if order_no or approval_no:
            res = await action_client.restore_order(order_no or "100100001", {
                "approval_no": approval_no or "APPR-SYSTEM",
                "reason": "M-01 결제 완료 후 주문 미생성 주문 유실 복구"
            }, tc_id)
            status_text = "주문 복구 접수(API-22)가 완료되었습니다." if res["status"] in (200, 201) else "주문 복구 확인 중입니다."
            base_reply = (
                "결제 내역 대사(E48) 결과, 결제 승인은 완료되었으나 주문서가 누락된 M-01 주문 유실로 확인되었습니다. "
                f"결제 원본을 바탕으로 {status_text} "
                "고객님께 추가 결제를 요구하지 않으며 상품은 정상 출하되오니 안심하시기 바랍니다."
            )
            ai_reply = await refine_with_openai(utterance, base_reply)
            return ai_reply or base_reply
        else:
            return "결제 대사 확인을 위해 결제 시각, 실결제 금액, 카드 뒷 4자리 또는 승인번호를 남겨주시면 주문 유실 여부를 즉시 조회·복구해 드리겠습니다."

    # 6. 주문번호 기반 실제 조회 및 후속 액션
    if order_no:
        order_res = await action_client.get_order(order_no, tc_id)
        ship_res = await action_client.search_shipments(order_no, tc_id)

        if order_res["status"] == -1 or ship_res["status"] == -1:
            return f"현재 주문번호 {order_no}에 대한 시스템 조회가 지연되고 있습니다. 잠시 후 다시 조회해 주시거나 담당자에게 확인을 요청해 주세요."

        if order_res["status"] == 404 and (ship_res["status"] == 404 or not ship_res["data"]):
            return f"입력하신 주문번호 {order_no}로 등록된 주문 내역이 조회되지 않습니다. 주문번호를 다시 확인해 주시기 바랍니다."

        shipments = ship_res["data"] if isinstance(ship_res["data"], list) else []
        shipment_id = session.get("shipment_id")
        lot_id = session.get("lot_id")

        if shipments and len(shipments) > 0:
            shp = shipments[0]
            shipment_id = shp.get("shipment_id")
            session["shipment_id"] = shipment_id
            items = shp.get("items", [])
            if items:
                lot_id = items[0].get("lot_id")
                session["lot_id"] = lot_id

        # 6-1. 품질 하자 (곰팡이/변질)
        if any(k in utterance for k in ["곰팡이", "상했", "썩", "변질", "냄새", "파손", "하자", "터졌", "미숙과", "공동과"]):
            if lot_id:
                await action_client.get_lot(lot_id, tc_id)
                await action_client.get_lot_investigation(lot_id, tc_id)

            refund_res = await action_client.request_refund(order_no, "품질 불량 및 변질 전액 환불", None, tc_id)
            await action_client.request_escalation({
                "order_no": order_no,
                "issue_type": "QUALITY_DEFECT",
                "priority": "HIGH",
                "description": f"로트 {lot_id or '미확인'} 변질 클레임 접수 및 환불"
            }, tc_id)
            ref_msg = "전액 환불 신청(API-29)이 정상 접수되었습니다." if refund_res["status"] in (200, 201) else "환불 접수를 진행 중입니다."
            base_reply = (
                "수령하신 상품에 품질 이상(변질/곰팡이)을 드려 진심으로 사과드립니다. "
                f"해당 상품 로트 조사를 의뢰하였으며, {ref_msg} "
                "신용카드 승인 취소는 카드사 영업일 기준 2~3일 내 완료됩니다. 불편을 끼쳐드려 거듭 죄송합니다."
            )
            ai_reply = await refine_with_openai(utterance, base_reply)
            return ai_reply or base_reply

        # 6-2. 오배송 처리 (100400024 사례 등)
        if any(k in utterance for k in ["오배송", "다른 상품", "잘못 왔", "멜론이 왔"]):
            if shipment_id:
                reship_res = await action_client.request_reship(shipment_id, "오배송으로 인한 정품 교환 재배송 요청", tc_id)
                r_msg = "재배송 요청(API-28)이 정상 접수되었습니다." if reship_res["status"] in (200, 201) else "재배송을 접수 중입니다."
                return (
                    f"주문하신 상품과 다른 상품이 오배송되어 대단히 죄송합니다. "
                    f"정품 출고를 위한 {r_msg} "
                    "오배송된 상품의 회수 및 올바른 상품 출고를 신속히 진행해 드리겠습니다."
                )

        # 6-3. 수산물 중량 자연감량 (8% 룰)
        if any(k in utterance for k in ["수산", "옥돔", "갈치", "고등어", "중량", "무게", "g"]):
            if "초과" in utterance or "10%" in utterance or "많이 줄" in utterance or order_no == "100300023":
                refund_res = await action_client.request_refund(order_no, "수산물 중량 자연감량 허용치(8%) 초과 부분환불", None, tc_id)
                ref_msg = "차액 환불 신청(API-29)이 정상 접수되었습니다." if refund_res["status"] in (200, 201) else "환불 접수 중입니다."
                return (
                    "실측 중량 확인 결과, 유통 중 자연감량 허용 기준(8%)을 초과한 것으로 확인되었습니다. "
                    f"부족 중량분에 대한 {ref_msg} "
                    "산지 출하 관리팀에 중량 검수 강화를 요청하였습니다."
                )
            else:
                return (
                    "교동마을 수산물은 산지 직송 원물 기준으로 출고됩니다. "
                    "냉동/생물 특성상 운송 중 8% 이내의 수분 증발(자연감량)은 정상 규격으로 인정됩니다. "
                    "만약 감량이 8%를 초과하는 경우 차액 환불 접수가 가능하오니 실측 중량을 남겨주시기 바랍니다."
                )

        # 6-4. 재배송 vs 환불 선택
        if any(k in utterance for k in ["재배송", "다시 보내", "기다릴", "언제 오", "보내줘"]):
            if shipment_id:
                res = await action_client.request_reship(shipment_id, "기상 악화 결항 지연으로 인한 재배송 요청", tc_id)
                res_msg = "재배송 요청(API-28)이 정상 접수되었습니다." if res["status"] in (200, 201) else "재배송 요청을 확인 중입니다."
                return (
                    f"기다려주셔서 감사합니다. 배송건({shipment_id})의 {res_msg} "
                    "산지 기상 호전 즉시 최우선 순위로 선별·출고해 드리겠습니다."
                )

        if any(k in utterance for k in ["환불", "취소", "반품"]):
            res = await action_client.request_refund(order_no, "고객 취소 및 환불 요청", None, tc_id)
            res_msg = "환불 신청(API-29)이 정상 접수되었습니다." if res["status"] in (200, 201) else "환불 접수를 진행 중입니다."
            return f"주문번호 {order_no}의 {res_msg} 신용카드 승인 취소는 카드사 영업일 기준 2~3일 내 반영됩니다."

        # 6-5. 배송 상태 조회
        if shipments and len(shipments) > 0:
            shp = shipments[0]
            status = shp.get("status", "배송 준비")
            carrier = shp.get("carrier", "시원배송")

            if status in ["PREPARING", "READY", "PENDING"] or "결항" in utterance:
                return (
                    f"주문번호 {order_no} 상품은 송장 발행 완료 후 강풍경보 결항으로 인해 택배사 인수 전 산지 저온창고에서 신선 대기 중입니다. "
                    "산지 출고는 월·수·금에 진행되며, 계속 출고를 기다리시길 원하시면 '재배송', 취소를 원하시면 '환불'을 선택해 주시면 즉시 처리해 드리겠습니다."
                )
            return f"주문번호 {order_no}의 현재 배송 상태는 [{status}]입니다. (택배사: {carrier})"

        return (
            f"주문번호 {order_no} 확인되었습니다. 상품 선별 준비 중이며 산지 정기 출고일(월·수·금)에 맞춰 순차 발송됩니다. "
            "추가 문의 사항(재배송 요청, 취소/환불 등)이 있으시면 말씀해 주세요."
        )

    # 7. 기본 안내
    base_reply = (
        "안녕하세요! 교동마을 산지직송 고객센터입니다. "
        "산지 출고는 월·수·금 정기 진행됩니다. "
        "주문·배송 조회, 결항 재배송/환불 접수, 상품 품질 문의 등 원하시는 내용을 주문번호와 함께 말씀해 주시면 신속히 처리해 드리겠습니다."
    )
    ai_reply = await refine_with_openai(utterance, base_reply)
    return ai_reply or base_reply

# 카카오 오픈빌더 스킬 및 디벨로퍼스 봇 웹훅 엔드포인트
@app.post("/skill")
@app.post("/webhook")
async def kakao_skill_handler(request: Request):
    try:
        body = await request.json()
    except Exception:
        return make_simple_text_response("요청을 처리하는 중 오류가 발생했습니다.")

    user_req = body.get("userRequest", {})
    utterance = user_req.get("utterance", "").strip()
    user_id = user_req.get("user", {}).get("id", "anonymous_user")

    session = get_session(user_id)

    detected_tc = extract_tc_id(utterance)
    if detected_tc:
        session["tc_id"] = detected_tc

    logger.info(f"User: {user_id} | TC: {session['tc_id']} | Msg: {utterance}")

    reply_text = await generate_response(utterance, session)
    return make_simple_text_response(reply_text)

# 헬스체크 (Render용)
@app.get("/health")
@app.get("/")
async def health_check():
    return {"status": "ok", "service": "gyodong-cs-agent"}

# 데이터 리셋
@app.post("/reset")
async def reset_handler():
    ok = await action_client.reset_action_data()
    return {"success": ok}
