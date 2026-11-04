"""학습과 서비스의 공통 피처 이름. 모델 라이브러리를 불러오지 않는 정적 정의."""

GROUPS = {  # 누적해서 더함
    "기본(위치·재차·시각)": ["eta", "stops_away", "r_now", "q_csv", "off_csv", "minute", "route_c", "stop_c", "bus_type_c"],
    "+배차·몰림": ["since_prev", "hw_ratio", "eta_gap", "eta2", "r2"],
    "+오늘 혼잡": ["route_load", "q_bias3", "q_prev"],
    "+수업 시작": ["class_board_win", "class_next30", "class_next60", "min_to_class"],
    "+달력": ["weekday_c", "term_c", "exam_c", "holiday_c"],
    "+정원·피크": ["is_peak", "cap", "fill_ratio"],  # 실패 분석에서 나온 것: 피크에 몰림, 정원 근처 포화
    "+앞 정류장 줄(실측)": ["q_today", "q_eb", "q_hist"],
    "+위치(정차·진행)": ["pos_dwell", "pos_frac", "q_pending"],  # 재차는 정류장 출발 때 갱신 → 정차 중이면 그 정류장 몫 미반영
    "+정밀 순승차(위치 기반)": ["q_live2", "q_today2"],
    "+쌓임속도×공백": ["q_rate", "gap_sum"],  # 구조 모델: 사람은 시간에 비례해 쌓이고 버스가 오면 비워짐  # 위치 API 출발 시각 기준 정류장별 순승차(직전 버스·최근 60분)
}
