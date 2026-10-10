from pydantic import BaseModel, Field


class Planner(BaseModel):
    """
    Placeholder planning configuration for future AI behavior.
    """

    strategy: str = Field(
        default="goal_driven",
        description="Planning strategy used by this character.",
        examples=["goal_driven"],
    )