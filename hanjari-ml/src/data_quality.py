"""API 형식 검증과 현장 검증 정책. 인원 집계의 실측 정확성은 형식 검증과 별개다."""
import datetime as dt
from functools import lru_cache
import json
from pathlib import Path

SCHEMA_VERSION = 2
MAX_SOURCE_AGE = 180
POLICY_PATH = Path(__file__).resolve().parents[1] / "config/boarding_policy.json"


def integer(value):
    if isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        return int(text) if text and text.lstrip("-").isdigit() else None
    except (TypeError, ValueError):
        return None


def passenger_count(item, slot="1"):
    """div=0은 결측, div=4는 혼잡도. 광역버스(routeType=6)는 잔여좌석 의미라 제외."""
    n = integer(item.get("reride_Num" + slot))
    if str(item.get("rerdie_Div" + slot)) != "2" or str(item.get("routeType")) != "2":
        return None
    return n if n is not None and n >= 0 else None


def source_time(value):
    try:
        if isinstance(value, str) and len(value) == 14 and value.isdigit():
            return dt.datetime.strptime(value, "%Y%m%d%H%M%S")
        return dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def source_issue(item, collected_at, slot="1"):
    if item.get("_vehicle_mismatch" + slot):
        return "vehicle_mismatch"
    if item.get("_passenger_conflict" + slot):
        return "passenger_conflict"
    if passenger_count(item, slot) is None:
        return "passenger_unavailable"
    made = source_time(item.get("mkTm"))
    if made is None or made.tzinfo is not None:
        return "source_time_unknown"
    age = (collected_at - made).total_seconds()
    if age < -5 or age > MAX_SOURCE_AGE:
        return "source_stale"
    vehicle_id = integer(item.get("vehId" + slot))
    if not str(item.get("plainNo" + slot) or "").strip() or vehicle_id is None or vehicle_id <= 0:
        return "vehicle_unknown"
    return "ok"


def valid_count(item, collected_at, slot="1"):
    return passenger_count(item, slot) if source_issue(item, collected_at, slot) == "ok" else None


@lru_cache(maxsize=4)
def _policy(path, mtime, size):
    d = json.loads(Path(path).read_text())
    if d.get("version") != 1 or type(d.get("enabled")) is not bool or not isinstance(d.get("vehicles"), list):
        raise ValueError("invalid boarding policy")
    seen = set()
    for v in d["vehicles"]:
        if not isinstance(v, dict):
            raise ValueError("invalid vehicle entry")
        key = (v.get("route"), v.get("plate"), v.get("vehicle_id"))
        if (key[0] not in ("jr03", "sb02") or not all(isinstance(x, str) and x.strip() for x in key)
                or key in seen or type(v.get("capacity")) is not int or not 1 <= v["capacity"] <= 100
                or not isinstance(v.get("evidence"), str) or not v["evidence"].strip()):
            raise ValueError("invalid verified vehicle capacity")
        seen.add(key)
    if d["enabled"] and (not isinstance(d.get("validation_evidence"), str) or not d["validation_evidence"].strip()):
        raise ValueError("field validation evidence required")
    return d


def boarding_policy():
    try:
        stat = POLICY_PATH.stat()
        return _policy(str(POLICY_PATH), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"version": 1, "enabled": False, "validation_evidence": "", "vehicles": []}


def verified_capacity(route, plate, vehicle_id):
    for v in boarding_policy()["vehicles"]:
        if (v["route"], v["plate"], v["vehicle_id"]) == (route, plate, vehicle_id):
            return v["capacity"]
    return None


def field_validation_issue(route, plate, vehicle_id):
    if not boarding_policy()["enabled"]:
        return "field_validation_pending"
    if verified_capacity(route, plate, vehicle_id) is None:
        return "capacity_unverified"
    return None


REASONS = {
    "passenger_unavailable": "차내 인원 정보를 확인할 수 없어요",
    "passenger_conflict": "같은 차량의 인원 정보가 서로 달라 확인하고 있어요",
    "source_time_unknown": "버스 정보의 제공 시각을 확인할 수 없어요",
    "source_stale": "버스 정보가 오래되어 갱신을 기다리고 있어요",
    "vehicle_unknown": "차량 식별 정보를 확인할 수 없어요",
    "vehicle_mismatch": "차량 정보가 서로 맞지 않아 확인하고 있어요",
    "field_validation_pending": "실제 인원과 제공 정보가 달라 탑승 예측을 점검하고 있어요",
    "capacity_unverified": "이 차량의 탑승 판단 기준을 확인하고 있어요",
    "model_unverified": "새 판단 기준으로 예측 결과를 다시 확인하고 있어요",
    "capacity_exceeded": "차내 인원 정보가 확인된 차량 정원을 넘어 확인이 필요해요",
    "prediction_invalid": "예측 결과를 확인하고 있어요",
    "collection_stale": "버스 정보 수집이 늦어져 갱신을 기다리고 있어요",
    "arrival_passed": "앞 버스가 지나가 다음 도착 정보를 확인하고 있어요",
    "arrival_checking": "도착 예정 시간이 지나 새 도착 정보를 확인하고 있어요",
}
