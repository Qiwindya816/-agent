from agent.workflow import TravelWorkflow
from utils.ids import validate_user_id


def main() -> None:
    """TravelMind 命令行入口。"""
    print("欢迎使用 TravelMind。")
    while True:
        try:
            user_id = validate_user_id(input("请输入用户 ID 登录：\n"))
            break
        except ValueError as exc:
            print(exc)

    workflow = TravelWorkflow(user_id=user_id)
    print(f"登录成功：{user_id}")
    print(f"本次会话 ID：{workflow.session_id}")
    print("你可以输入旅行需求、要求修改行程、估算预算、查询天气或换算汇率。")
    print("输入 q、quit 或 exit 退出。")

    while True:
        user_input = input("\n请输入旅行需求：\n").strip()

        if user_input.lower() in {"q", "quit", "exit"}:
            print("已退出 TravelMind。")
            break

        if not user_input:
            print("请输入有效的旅行需求。")
            continue

        response = workflow.run(user_input)
        print("\n" + response)


if __name__ == "__main__":
    main()
