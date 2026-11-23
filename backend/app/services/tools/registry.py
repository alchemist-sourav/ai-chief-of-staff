import logging
from typing import Dict, List, Optional, Any
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tools.base import BaseTool, ToolResult, ToolSecurityLevel
from app.services.tools.task_tools import (
    CreateTaskTool,
    ListTasksTool,
    UpdateTaskTool,
    DeleteTaskTool,
)
from app.services.tools.memory_tools import (
    SaveMemoryTool,
    RetrieveMemoryTool,
)
from app.services.tools.approval_tools import (
    ProposeExternalActionTool,
)

logger = logging.getLogger("ai_chief_of_staff.tools.registry")


class ToolRegistry:
    """Central registry for discovering, validating, and executing tools safely."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Tool must be an instance of BaseTool, got {type(tool)}")
        if tool.name in self._tools:
            logger.warning(f"Overwriting previously registered tool '{tool.name}'")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool '{tool.name}' (Security: {tool.security_level.value})")

    def get(self, name: str) -> Optional[BaseTool]:
        """Look up tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Return OpenAI/Groq function calling schema definitions for all registered tools."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def dispatch(
        self,
        session: AsyncSession,
        user_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """Validate arguments and execute the requested tool with injected user_id and session.
        
        Guarantees:
        1. Tool must be explicitly registered; rejects unknown tools.
        2. Injects authenticated user_id server-side (cannot be spoofed by LLM).
        3. Validates arguments using Pydantic; rejects malformed inputs gracefully.
        4. Handles exceptions without crashing the application.
        """
        tool = self.get(tool_name)
        if not tool:
            logger.warning(f"Unauthorized tool dispatch attempted: '{tool_name}' for user {user_id}")
            return ToolResult(
                success=False,
                error="UNKNOWN_TOOL",
                message=f"Tool '{tool_name}' is not recognized or permitted.",
            )

        # Validate arguments against tool Pydantic schema
        try:
            validated_args = tool.validate_args(arguments)
        except ValidationError as ve:
            error_details = [{"loc": err["loc"], "msg": err["msg"], "type": err["type"]} for err in ve.errors()]
            logger.warning(f"Validation failed for tool '{tool_name}': {error_details}")
            return ToolResult(
                success=False,
                error="INVALID_ARGUMENTS",
                message=f"Invalid arguments for tool '{tool_name}': {error_details}",
                data={"errors": error_details},
            )

        # Execute tool
        try:
            return await tool.execute(session=session, user_id=user_id, **validated_args.model_dump())
        except Exception as e:
            logger.exception(f"Unexpected error executing tool '{tool_name}' for user {user_id}")
            return ToolResult(
                success=False,
                error="EXECUTION_ERROR",
                message=f"An unexpected error occurred while executing tool '{tool_name}': {str(e)}",
            )


def create_default_registry() -> ToolRegistry:
    """Create and populate the default Chief of Staff tool registry."""
    registry = ToolRegistry()
    registry.register(CreateTaskTool())
    registry.register(ListTasksTool())
    registry.register(UpdateTaskTool())
    registry.register(DeleteTaskTool())
    registry.register(SaveMemoryTool())
    registry.register(RetrieveMemoryTool())
    registry.register(ProposeExternalActionTool())
    return registry


# Singleton default registry
default_registry = create_default_registry()
