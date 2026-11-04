"""수집기·서비스·마감 검사에서 공통으로 사용하는 서울 버스 JSON 응답 검증."""


def response_items(body):
    """정상 빈 결과를 보존하고 잘못된 응답 구조는 일관된 검증 오류로 처리한다."""
    if not isinstance(body, dict) or not isinstance(body.get("msgHeader"), dict):
        raise ValueError("invalid bus API header")
    code = str(body["msgHeader"].get("headerCd"))
    message = body.get("msgBody")
    if code == "4" and (message is None or isinstance(message, dict) and message.get("itemList") in (None, [])):
        return []  # 정상적인 '결과 없음' 뒤에 이전 버스를 다시 살리지 않는다.
    if code != "0":
        raise ValueError("unsuccessful bus API response")
    if not isinstance(message, dict) or "itemList" not in message:
        raise ValueError("invalid bus API body")
    items = message["itemList"]
    if items is None:
        return []
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ValueError("invalid bus API items")
    return items
