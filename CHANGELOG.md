# Changelog

## LangGraph multi-agent rebuild

- 将唯一运行入口切换为 `main.py` 中的 `MultiAgentTravelWorkflow`。
- 建立 Coordinator、Feedback、Planner、Tool Executor 和 Summarizer 五节点 LangGraph。
- 使用 `session_id` 作为 LangGraph thread ID，并支持注入 Checkpointer。
- 将规划、执行和总结实现迁入 `multi_agent/`。
- 删除旧 `agent/` 编排包、旧入口、兼容转发模块和旧架构文档。
- 保留工具、服务、Schema、校验器和本地仓储作为新架构基础能力。
- 将 LLM 超时和重试配置接入 OpenAI-compatible 客户端。
- 增加五节点执行顺序和统一工具结果测试。
