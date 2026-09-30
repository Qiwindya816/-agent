from schemas.itinerary import Itinerary


def render_itinerary_markdown(itinerary: Itinerary) -> str:
    """把结构化行程确定性地渲染为 Markdown。"""
    lines = [f"# {itinerary.title or '旅行行程'}"]
    overview = [
        ("出发城市", itinerary.departure_city),
        ("目的地", itinerary.destination),
        ("旅行天数", f"{itinerary.travel_days} 天" if itinerary.travel_days else None),
        ("住宿区域", itinerary.accommodation_area),
    ]
    lines.extend(f"- {label}：{value}" for label, value in overview if value)

    for day in itinerary.days:
        heading = f"## 第 {day.day} 天"
        if day.date:
            heading += f" · {day.date}"
        if day.theme:
            heading += f" · {day.theme}"
        lines.extend(["", heading])
        for activity in day.activities:
            time_range = ""
            if activity.start_time or activity.end_time:
                time_range = f"{activity.start_time or '?'}–{activity.end_time or '?'} "
            location = f"（{activity.location}）" if activity.location else ""
            cost = f"，约 {activity.estimated_cost:g} {itinerary.currency}" if activity.estimated_cost is not None else ""
            lines.append(f"- {time_range}{activity.name}{location}{cost}")
            if activity.transport_method:
                lines.append(f"  - 交通：{activity.transport_method}")
            if activity.notes:
                lines.append(f"  - 备注：{activity.notes}")
        if day.estimated_daily_cost is not None:
            lines.append(f"- 当日预计费用：{day.estimated_daily_cost:g} {itinerary.currency}")

    if itinerary.transport_options:
        lines.extend(["", "## 城际交通"])
        for option in itinerary.transport_options:
            route = " → ".join(part for part in [option.from_station, option.to_station] if part)
            basic = f"- {option.train_no or option.transport_type} {route}".strip()
            details = []
            if option.date:
                details.append(option.date)
            if option.departure_time and option.arrival_time:
                details.append(f"{option.departure_time}–{option.arrival_time}")
            if option.duration:
                details.append(f"历时 {option.duration}")
            if details:
                basic += f"（{'，'.join(details)}）"
            lines.append(basic)
            if option.seats:
                seat_text = "，".join(f"{name} {value}" for name, value in option.seats.items())
                lines.append(f"  - 座席：{seat_text}")

    if itinerary.total_estimated_cost is not None:
        lines.extend(["", "## 预计总费用", f"{itinerary.total_estimated_cost:g} {itinerary.currency}"])
    if itinerary.general_transport_advice:
        lines.extend(["", "## 总体交通建议", itinerary.general_transport_advice])
    if itinerary.assumptions:
        lines.extend(["", "## 假设", *[f"- {item}" for item in itinerary.assumptions]])
    if itinerary.warnings:
        lines.extend(["", "## 待核验事项", *[f"- {item}" for item in itinerary.warnings]])
    return "\n".join(lines).strip()
