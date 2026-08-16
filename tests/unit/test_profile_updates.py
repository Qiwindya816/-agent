from schemas.travel_request import TravelRequest
from schemas.user_profile import UserProfile
from tools.profile_tool import extract_profile_updates


def test_long_term_profile_and_trip_request_update_independently() -> None:
    profile = UserProfile(interests=["历史", "购物"], food_preference="清淡")
    trip = TravelRequest(destination="北京", budget=3000, interests=["历史"])

    updated_profile = profile.apply_update(
        UserProfile(transport_preference="高铁"),
        remove_items={"interests": ["购物"]},
        clear_fields=["food_preference"],
    )
    updated_trip = trip.apply_update(
        TravelRequest(destination="四川", destination_level="province", destination_province="四川", budget=5000)
    )

    assert updated_profile.interests == ["历史"]
    assert updated_profile.food_preference is None
    assert updated_profile.transport_preference == "高铁"
    assert updated_trip.destination == "四川"
    assert updated_trip.destination_city is None
    assert updated_trip.budget == 5000


def test_rule_fallback_keeps_province_without_inventing_city() -> None:
    extraction = extract_profile_updates("我想去四川旅游", use_llm=False)

    assert extraction.trip_updates.destination == "四川"
    assert extraction.trip_updates.destination_level == "province"
    assert extraction.trip_updates.destination_province == "四川"
    assert extraction.trip_updates.destination_city is None
