"""Pydantic models for training plan data."""

from datetime import date, time
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator


class TrainingSession(BaseModel):
    """Model for a single training session."""
    date: date
    day: str
    session: str
    distance: Optional[str] = None
    heart_rate_target: Optional[str] = None
    garmin_mcp_description: str
    time_of_day: Optional[time] = Field(None, alias="time")
    
    @validator('time_of_day', pre=True, always=True)
    def parse_time(cls, v):
        """Parse time from string format."""
        if v is None:
            return None
        if isinstance(v, str):
            if v == '-' or v.strip() == '':
                return None
            # Parse formats like "7:00 AM" or "5:00 PM"
            try:
                from datetime import datetime
                return datetime.strptime(v.strip(), "%I:%M %p").time()
            except ValueError:
                return None
        return v
    
    @validator('distance', pre=True)
    def clean_distance(cls, v):
        """Clean distance string."""
        if v and v.strip() == '0km':
            return None
        return v


class TrainingWeek(BaseModel):
    """Model for a week of training."""
    week_number: int
    phase: str
    sessions: List[TrainingSession]


class TrainingPlan(BaseModel):
    """Model for the complete training plan."""
    title: str
    start_date: date
    end_date: date
    weeks: List[TrainingWeek]
    
    @property
    def all_sessions(self) -> List[TrainingSession]:
        """Get all sessions from all weeks."""
        sessions = []
        for week in self.weeks:
            sessions.extend(week.sessions)
        return sessions


class WorkoutStep(BaseModel):
    """Model for a single workout step."""
    stepName: str
    stepDescription: str
    endConditionType: str = Field(description="'time' or 'distance'")
    stepDuration: Optional[int] = Field(None, description="Duration in seconds")
    stepDistance: Optional[float] = Field(None, description="Distance value")
    distanceUnit: Optional[str] = Field(None, description="'m', 'km', or 'mile'")
    stepType: str = Field(description="'warmup', 'cooldown', 'interval', 'recovery', 'rest', 'repeat'")
    target: Optional[Dict[str, Any]] = None
    numberOfIterations: Optional[int] = None
    steps: Optional[List['WorkoutStep']] = None


# Update forward references
WorkoutStep.model_rebuild()


class WorkoutData(BaseModel):
    """Model for Garmin workout data."""
    name: str
    type: str = Field(description="'running', 'cycling', 'swimming', 'walking', 'cardio', 'strength'")
    steps: List[WorkoutStep]


class ScheduleResult(BaseModel):
    """Model for workout scheduling result."""
    date: date
    session_name: str
    workout_id: Optional[Union[str, int]] = None
    schedule_id: Optional[Union[str, int]] = None
    success: bool
    error: Optional[str] = None
    skipped: bool = False  # True if workout already exists and matches
    validation_status: Optional[str] = None  # Result of post-scheduling validation
    
    @validator('workout_id', 'schedule_id', pre=True)
    def convert_id_to_str(cls, v):
        """Convert IDs to strings if they're integers."""
        if v is not None:
            return str(v)
        return v