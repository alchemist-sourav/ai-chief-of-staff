import abc
from enum import Enum
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


class ToolSecurityLevel(str, Enum):
    """Classification of tool execution risk."""
    SAFE = "SAFE"        # Direct database read/write (e.g. create task, save preference)
    GUARDED = "GUARDED"  # Sensitive action requiring human approval (e.g. delete task, send email)


class ToolResult(BaseModel):
    """Standardized result returned by any tool execution."""
    success: bool
    message: str
    data: Optional[Any] = None
    requires_approval: bool = False
    approval_id: Optional[str] = None
    error: Optional[str] = None


class BaseTool(abc.ABC):
    """Abstract base class for all Chief of Staff backend tools."""

    name: str
    description: str
    security_level: ToolSecurityLevel = ToolSecurityLevel.SAFE
    args_schema: Type[BaseModel]

    def validate_args(self, arguments: Dict[str, Any]) -> BaseModel:
        """Validate raw dictionary arguments against the Pydantic schema."""
        return self.args_schema.model_validate(arguments)

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert the tool into standard OpenAI / Groq function definition schema."""
        schema = self.args_schema.model_json_schema()
        # Clean top-level schema metadata for clean LLM prompt insertion
        parameters = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
        if "$defs" in schema:
            parameters["$defs"] = schema["$defs"]

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    @abc.abstractmethod
    async def execute(
        self,
        session: AsyncSession,
        user_id: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the tool logic using trusted session and authenticated user_id."""
        pass
