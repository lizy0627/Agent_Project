from __future__ import annotations

import ast
import json
import re
from typing import Any, Mapping

from pydantic import BaseModel, Field, model_validator

from app.core.logger import get_logger
from app.tools.registry import ToolRegistry


logger = get_logger(__name__)


class PlanStep(BaseModel):
    """One executable or reasoning step in an agent plan."""

    step_id: str = Field(..., min_length=1, description="Stable id for this step.")
    description: str = Field(..., min_length=1, description="Human-readable task description.")
    tool_name: str | None = Field(default=None, description="Tool to call, or None for no-tool work.")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool.")
    depends_on: list[str] = Field(default_factory=list, description="Step ids that must finish first.")


class AgentPlan(BaseModel):
    """Structured plan produced before the agent executes tools or answers."""

    question: str = Field(..., description="Original user question being planned.")
    steps: list[PlanStep] = Field(..., min_length=1, description="Ordered task steps.")

    @model_validator(mode="after")
    def validate_step_graph(self) -> "AgentPlan":
        """Keep the plan easy to execute by validating ids and dependencies."""

        seen: set[str] = set()
        for step in self.steps:
            missing_dependencies = [dependency for dependency in step.depends_on if dependency not in seen]
            if missing_dependencies:
                missing = ", ".join(sorted(missing_dependencies))
                raise ValueError(f"Unknown or unordered plan dependencies: {missing}")
            if step.step_id in seen:
                raise ValueError(f"Duplicate plan step_id: {step.step_id}")
            seen.add(step.step_id)
        return self


class Planner:
    """Rule-based planner kept as the deterministic fallback path."""

    DIRECT_ANSWER_STEP_ID = "direct_answer"
    TOOL_STEP_ID = "tool_1"
    FINAL_ANSWER_STEP_ID = "final_answer"

    def __init__(self, max_steps: int = 8) -> None:
        self.max_steps = max(int(max_steps), 1)

    def plan(
        self,
        question: str,
        planned_tool_call: Any | None = None,
    ) -> AgentPlan:
        """Return a direct-answer plan or a tool-backed plan for the question."""

        clean_question = str(question or "").strip()
        tool_name = self._tool_name(planned_tool_call)
        if not tool_name:
            return self.direct_answer_plan(clean_question)

        tool_args = self._tool_args(planned_tool_call)
        return self.tool_plan(clean_question, tool_name=tool_name, tool_args=tool_args)

    def direct_answer_plan(self, question: str) -> AgentPlan:
        """Plan simple questions as a single no-tool direct answer step."""

        # Simple questions stay as one no-tool step so the main flow can answer directly.
        return self._checked_plan(
            question=question,
            steps=[
                PlanStep(
                    step_id=self.DIRECT_ANSWER_STEP_ID,
                    description="Answer the user directly without calling a tool.",
                    tool_name=None,
                    tool_args={},
                    depends_on=[],
                )
            ],
        )

    def tool_plan(
        self,
        question: str,
        tool_name: str,
        tool_args: Mapping[str, Any] | None = None,
    ) -> AgentPlan:
        """Plan a tool call followed by a no-tool final answer step."""

        clean_tool_name = str(tool_name or "").strip()
        if not clean_tool_name:
            return self.direct_answer_plan(question)

        # Tool-backed plans mirror runtime order: collect tool context, then answer.
        return self._checked_plan(
            question=question,
            steps=[
                PlanStep(
                    step_id=self.TOOL_STEP_ID,
                    description=f"Call the {clean_tool_name} tool with the planned arguments.",
                    tool_name=clean_tool_name,
                    tool_args=dict(tool_args or {}),
                    depends_on=[],
                ),
                PlanStep(
                    step_id=self.FINAL_ANSWER_STEP_ID,
                    description="Generate the final answer from the available context and tool result.",
                    tool_name=None,
                    tool_args={},
                    depends_on=[self.TOOL_STEP_ID],
                ),
            ],
        )

    def _checked_plan(self, *, question: str, steps: list[PlanStep]) -> AgentPlan:
        if len(steps) > self.max_steps:
            raise ValueError(
                f"Agent plan requires {len(steps)} steps but MAX_AGENT_STEPS is {self.max_steps}."
            )
        return AgentPlan(question=question, steps=steps)

    def _tool_name(self, planned_tool_call: Any | None) -> str | None:
        if planned_tool_call is None:
            return None
        return str(getattr(planned_tool_call, "name", "") or "").strip() or None

    def _tool_args(self, planned_tool_call: Any | None) -> dict[str, Any]:
        arguments = getattr(planned_tool_call, "arguments", None)
        if isinstance(arguments, Mapping):
            return dict(arguments)
        return {}


class LLMPlanGenerationError(ValueError):
    """Raised when the model cannot produce a valid executable AgentPlan."""


class LLMPlanGenerator:
    """Generate AgentPlan JSON with an LLM, then validate it before execution.

    The important interview-friendly boundary is here: the LLM is allowed to
    propose a plan, but Pydantic and the local ToolRegistry decide whether that
    plan is executable. Invalid JSON, invalid dependencies, too many steps, or
    unknown tool names all fail before the executor sees the plan.
    """

    REQUIRED_STEP_FIELDS = {"step_id", "description", "tool_name", "tool_args", "depends_on"}

    def __init__(
        self,
        llm_client: Any,
        tool_registry: ToolRegistry,
        max_steps: int = 8,
    ) -> None:
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_steps = max(int(max_steps), 1)

    def generate(self, messages: list[Mapping[str, str]], model: str | None = None) -> AgentPlan:
        """Ask the LLM for JSON and return a fully validated AgentPlan."""

        question = self._latest_user_message(messages)
        if not question:
            raise LLMPlanGenerationError("Cannot plan without a user message.")
        if self._looks_like_direct_answer_question(question):
            logger.info("LLM planner skipped for obvious direct-answer question.")
            return Planner(max_steps=self.max_steps).direct_answer_plan(question)

        available_tools = self._available_tools()
        raw_reply = self.llm_client.complete_chat(
            self._build_planner_messages(question, messages, available_tools),
            model=model,
        )
        payload = self._parse_json_object(raw_reply)
        self._require_explicit_step_fields(payload)
        plan = self._validate_plan_payload(payload, available_tools)

        logger.info(
            "LLM planner produced valid plan: steps=%s tool_names=%s",
            len(plan.steps),
            [step.tool_name for step in plan.steps if step.tool_name],
        )
        return plan

    def _build_planner_messages(
        self,
        question: str,
        messages: list[Mapping[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Create a compact planning prompt that asks for JSON only."""

        # The tool list comes directly from ToolRegistry.list_tools(), so the
        # model sees the same tool names and argument schemas the executor uses.
        tool_catalog = json.dumps(available_tools, ensure_ascii=False, indent=2)
        conversation = json.dumps(self._compact_messages(messages), ensure_ascii=False, indent=2)
        schema_hint = {
            "question": question,
            "steps": [
                {
                    "step_id": "tool_1",
                    "description": "Call a tool when it is needed.",
                    "tool_name": "one_of_available_tool_names_or_null",
                    "tool_args": {},
                    "depends_on": [],
                },
                {
                    "step_id": "final_answer",
                    "description": "Generate the final answer from context and observations.",
                    "tool_name": None,
                    "tool_args": {},
                    "depends_on": ["tool_1"],
                },
            ],
        }

        return [
            {
                "role": "system",
                "content": (
                    "You are an agent planning component. Return only one valid JSON object, "
                    "with no markdown or commentary. The JSON must match this shape exactly: "
                    f"{json.dumps(schema_hint, ensure_ascii=False)}. "
                    "Use null for tool_name when no tool is needed. "
                    "If the user question clearly needs no tool, create one direct_answer step with tool_name null. "
                    "For requests that need more than one tool call, create multiple tool steps in execution order. "
                    "Every step must include step_id, description, tool_name, tool_args, and depends_on. "
                    "Only use tool_name values from the available tools list. "
                    "Keep dependencies ordered: a step can only depend on earlier step_id values. "
                    f"Create at most {self.max_steps} steps."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Latest user question:\n{question}\n\n"
                    f"Conversation messages:\n{conversation}\n\n"
                    f"Available tools from ToolRegistry.list_tools():\n{tool_catalog}"
                ),
            },
        ]

    def _validate_plan_payload(self, payload: dict[str, Any], available_tools: list[dict[str, Any]]) -> AgentPlan:
        try:
            plan = AgentPlan.model_validate(payload)
        except Exception as exc:
            raise LLMPlanGenerationError(f"LLM plan failed Pydantic validation: {exc}") from exc

        if len(plan.steps) > self.max_steps:
            raise LLMPlanGenerationError(
                f"LLM plan requires {len(plan.steps)} steps but MAX_AGENT_STEPS is {self.max_steps}."
            )

        available_tool_names = self._tool_names(available_tools)
        for step in plan.steps:
            if step.tool_name is None:
                continue
            clean_tool_name = str(step.tool_name).strip()
            if not clean_tool_name:
                raise LLMPlanGenerationError(f"Plan step {step.step_id} has an empty tool_name.")
            if clean_tool_name != step.tool_name:
                raise LLMPlanGenerationError(f"Plan step {step.step_id} has whitespace around tool_name.")
            if clean_tool_name not in available_tool_names:
                raise LLMPlanGenerationError(
                    f"Plan step {step.step_id} requested unavailable tool_name: {clean_tool_name}"
                )
        return plan

    def _require_explicit_step_fields(self, payload: dict[str, Any]) -> None:
        """Reject partial step JSON instead of relying on Pydantic defaults."""

        steps = payload.get("steps")
        if not isinstance(steps, list):
            raise LLMPlanGenerationError("LLM plan must include a steps list.")
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise LLMPlanGenerationError(f"LLM plan step {index} must be an object.")
            missing = sorted(self.REQUIRED_STEP_FIELDS - set(step))
            if missing:
                raise LLMPlanGenerationError(f"LLM plan step {index} is missing fields: {', '.join(missing)}")

    def _parse_json_object(self, raw_reply: str) -> dict[str, Any]:
        """Parse planner JSON, tolerating common model formatting drift."""

        text = str(raw_reply or "").strip()
        if not text:
            raise LLMPlanGenerationError("LLM planner returned an empty response.")

        errors: list[str] = []
        first_object: dict[str, Any] | None = None
        for candidate in self._json_object_candidates(text):
            try:
                payload = self._load_json_object_candidate(candidate)
            except LLMPlanGenerationError as exc:
                errors.append(str(exc))
                continue

            if isinstance(payload, dict):
                unwrapped = self._unwrap_plan_payload(payload)
                if self._looks_like_plan_payload(unwrapped):
                    return unwrapped
                if first_object is None:
                    first_object = unwrapped
                continue
            errors.append("LLM planner JSON root must be an object.")

        if first_object is not None:
            return first_object
        detail = errors[-1] if errors else "No JSON object candidate found."
        raise LLMPlanGenerationError(f"LLM planner returned invalid JSON: {detail}")

    def _json_object_candidates(self, text: str) -> list[str]:
        """Return likely JSON object snippets, ordered from least to most repaired."""

        candidates: list[str] = []
        self._append_candidate(candidates, text)

        for match in re.finditer(r"```(?:json)?\s*(?P<body>.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE):
            self._append_candidate(candidates, match.group("body"))

        for snippet in self._balanced_object_snippets(text):
            self._append_candidate(candidates, snippet)

        return candidates

    def _append_candidate(self, candidates: list[str], candidate: str) -> None:
        clean_candidate = str(candidate or "").strip()
        if clean_candidate and clean_candidate not in candidates:
            candidates.append(clean_candidate)

    def _balanced_object_snippets(self, text: str) -> list[str]:
        snippets: list[str] = []
        for start, char in enumerate(text):
            if char != "{":
                continue
            end = self._balanced_object_end(text, start)
            if end is not None:
                snippets.append(text[start : end + 1])
        return snippets

    def _balanced_object_end(self, text: str, start: int) -> int | None:
        depth = 0
        in_string = False
        quote = ""
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    in_string = False
                continue
            if char in {'"', "'"}:
                in_string = True
                quote = char
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _load_json_object_candidate(self, candidate: str) -> Any:
        parser_inputs = (candidate, self._repair_json_candidate(candidate))
        for parser_input in parser_inputs:
            try:
                return json.loads(parser_input)
            except json.JSONDecodeError:
                continue

        last_error: Exception | None = None
        for parser_input in parser_inputs:
            try:
                return ast.literal_eval(parser_input)
            except (SyntaxError, ValueError) as exc:
                last_error = exc
        raise LLMPlanGenerationError(f"Could not parse JSON object candidate: {last_error}")

    def _repair_json_candidate(self, candidate: str) -> str:
        repaired = str(candidate or "").strip()
        repaired = re.sub(r"(?m)^\s*//.*$", "", repaired)
        repaired = re.sub(r"(?m)^\s*#.*$", "", repaired)
        repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    def _unwrap_plan_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if isinstance(plan, dict) and "steps" in plan:
            return plan
        return payload

    def _looks_like_plan_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload.get("steps"), list)

    def _available_tools(self) -> list[dict[str, Any]]:
        tools = self.tool_registry.list_tools()
        if not isinstance(tools, list):
            raise LLMPlanGenerationError("ToolRegistry.list_tools() did not return a list.")
        return [tool for tool in tools if isinstance(tool, dict)]

    def _tool_names(self, available_tools: list[dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for tool in available_tools:
            name = str(tool.get("name") or "").strip()
            if name:
                names.add(name)
        return names

    def _compact_messages(self, messages: list[Mapping[str, str]]) -> list[dict[str, str]]:
        compacted: list[dict[str, str]] = []
        for message in messages[-8:]:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "").strip()
            if role and content:
                compacted.append({"role": role, "content": content[:4000]})
        return compacted

    def _latest_user_message(self, messages: list[Mapping[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content") or "").strip()
        return ""

    def _looks_like_direct_answer_question(self, question: str) -> bool:
        """Conservatively skip planner LLM calls for obvious no-tool chat."""

        normalized = " ".join(str(question or "").split())
        if not normalized:
            return False
        lowered = normalized.lower()
        compact = re.sub(r"[\s，。！？,.!?、~～]+", "", lowered)

        if self._looks_like_tool_needed(lowered):
            return False

        direct_phrases = {
            "hi",
            "hithere",
            "hello",
            "hey",
            "goodmorning",
            "goodafternoon",
            "goodevening",
            "thanks",
            "thankyou",
            "thx",
            "ty",
            "howareyou",
            "whoareyou",
            "whatareyou",
            "tellmeajoke",
            "你好",
            "您好",
            "哈喽",
            "嗨",
            "早上好",
            "上午好",
            "中午好",
            "下午好",
            "晚上好",
            "谢谢",
            "多谢",
            "感谢",
            "谢啦",
            "辛苦了",
            "你是谁",
            "你好吗",
            "在吗",
            "在不在",
            "讲个笑话",
        }
        return compact in direct_phrases or compact.startswith(("thankyou", "thanks", "谢谢", "感谢", "多谢"))

    def _looks_like_tool_needed(self, lowered_question: str) -> bool:
        tool_keywords = (
            "latest",
            "recent",
            "current",
            "today",
            "tomorrow",
            "yesterday",
            "now",
            "news",
            "weather",
            "search",
            "lookup",
            "look up",
            "google",
            "browse",
            "web",
            "website",
            "webpage",
            "url",
            "http://",
            "https://",
            "www.",
            "calculate",
            "calc",
            "compute",
            "time",
            "date",
            "calendar",
            "tool",
            "mcp",
            "api",
            "file",
            "document",
            "pdf",
            "docx",
            "xlsx",
            "summarize",
            "summary",
            "first",
            "then",
            "after that",
            "最新",
            "最近",
            "当前",
            "今天",
            "明天",
            "昨天",
            "新闻",
            "天气",
            "搜索",
            "查一下",
            "查找",
            "查询",
            "联网",
            "网页",
            "网站",
            "链接",
            "浏览",
            "计算",
            "算一下",
            "等于多少",
            "时间",
            "日期",
            "几点",
            "工具",
            "调用",
            "文件",
            "文档",
            "总结",
            "摘要",
            "然后",
            "接着",
            "步骤",
            "分步骤",
        )
        if any(keyword in lowered_question for keyword in tool_keywords):
            return True
        return bool(re.search(r"\d+(?:\.\d+)?\s*(?:\*\*|[+\-*/%]|=|加|减|乘|除)\s*\d+(?:\.\d+)?", lowered_question))
