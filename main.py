"""TravelMind LangGraph 多智能体命令行入口。"""

from multi_agent.workflow import MultiAgentTravelWorkflow
from utils.ids import validate_user_id


def main() -> None:
    print("欢迎使用 TravelMind LangGraph 多智能体版本。")
    while True:
        try:
            user_id = validate_user_id(input("请输入用户 ID 登录：\n"))
            break
        except ValueError as exc:
            print(exc)

    workflow = MultiAgentTravelWorkflow(user_id=user_id)
    print(f"登录成功：{user_id}")
    print(f"本次会话 ID：{workflow.session_id}")
    print("输入 q、quit 或 exit 退出。")
    while True:
        user_input = input("\n请输入旅行需求：\n").strip()
        if user_input.lower() in {"q", "quit", "exit"}:
            print("已退出 TravelMind。")
            return
        if not user_input:
            print("请输入有效的旅行需求。")
            continue
        print("\n" + workflow.run(user_input))


if __name__ == "__main__":
    main()
