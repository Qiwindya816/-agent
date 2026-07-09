from pathlib import Path
from agent import decide_tool
from travel_tools import (
    recommend_destination,
    plan_itinerary,
    estimate_budget
)


def run_tool(tool_name: str, user_request: str) -> str:
    if tool_name == "recommend_destination":
        return recommend_destination(user_request)

    if tool_name == "plan_itinerary":
        return plan_itinerary(user_request)

    if tool_name == "estimate_budget":
        return estimate_budget(user_request)

    return "Unknown tool."


def main():
    print("欢迎使用 Travel Assistant Agent")
    print("你可以输入：帮我推荐目的地 / 帮我规划行程 / 帮我估算预算")
    print("输入 q 退出")

    while True:
        user_request = input("\n请输入你的旅行需求：\n")

        if user_request.lower() == "q":
            break

        decision = decide_tool(user_request)

        print("\nAgent 选择的工具：")
        print(decision)

        result = run_tool(
            tool_name=decision["tool_name"],
            user_request=user_request
        )

        print("\n最终结果：")
        print(result)

        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / "travel_result.md"
        output_path.write_text(result, encoding="utf-8")

        print(f"\n结果已保存到：{output_path}")


if __name__ == "__main__":
    main()