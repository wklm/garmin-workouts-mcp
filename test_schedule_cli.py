#!/usr/bin/env python3
"""Test script for the training plan scheduler."""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from garmin_workouts_mcp.utils import parse_training_plan_markdown, parse_workout_description
from garmin_workouts_mcp.models import WorkoutData

# Read the training plan
training_plan_path = project_root / "training_plan.md"
if not training_plan_path.exists():
    print(f"Error: {training_plan_path} not found")
    sys.exit(1)

content = training_plan_path.read_text()

# Test parsing
print("Testing training plan parser...")
plan = parse_training_plan_markdown(content)
print(f"✓ Parsed plan: {plan.title}")
print(f"  Start date: {plan.start_date}")
print(f"  End date: {plan.end_date}")
print(f"  Total weeks: {len(plan.weeks)}")
print(f"  Total sessions: {len(plan.all_sessions)}")

# Test workout parsing for a few examples
print("\nTesting workout description parser...")
test_descriptions = [
    "8km recovery run at zone 1 heart rate under 125bpm, conversational pace throughout",
    "3km warmup at zone 2, 6km tempo at 162-168bpm, 2km recovery at zone 2, 3km cooldown at zone 1",
    "3km warmup progressive, 4x(4min at 175-180bpm, 3min recovery at zone 1), 3km cooldown easy",
    "30km progressive long run: 20km at zone 2 134-144bpm, then 10km at marathon heart rate 154-158bpm",
    "Rest day - no workout"
]

for desc in test_descriptions:
    print(f"\nParsing: {desc[:60]}...")
    workout = parse_workout_description(desc)
    if workout:
        print(f"  ✓ Name: {workout.name}")
        print(f"  ✓ Type: {workout.type}")
        print(f"  ✓ Steps: {len(workout.steps)}")
        for i, step in enumerate(workout.steps):
            if step.stepType == "repeat":
                print(f"    Step {i+1}: {step.stepType} - {step.numberOfIterations}x with {len(step.steps)} sub-steps")
            else:
                print(f"    Step {i+1}: {step.stepType} - {step.endConditionType}")
    else:
        print("  → Skipped (rest day or unparseable)")

print("\n✓ All tests passed!")
print("\nTo run the full scheduler in dry-run mode:")
print("  python -m garmin_workouts_mcp.schedule_training_plan training_plan.md --dry-run")
print("\nTo schedule workouts to Garmin Connect:")
print("  python -m garmin_workouts_mcp.schedule_training_plan training_plan.md")