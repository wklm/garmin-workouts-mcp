"""Utility functions for parsing training plans and converting workouts."""

import re
from datetime import datetime, date
from typing import List, Tuple, Optional, Dict, Any
from .models import TrainingSession, TrainingWeek, TrainingPlan, WorkoutStep, WorkoutData


def parse_training_plan_markdown(content: str) -> TrainingPlan:
    """Parse markdown content to extract training plan data."""
    lines = content.strip().split('\n')
    
    # Extract title
    title = "Marathon Training Plan"
    for line in lines:
        if line.startswith("## ") and "Marathon Training Plan" in line:
            title = line.replace("##", "").strip()
            break
    
    # Find all training sessions by looking for table rows with dates
    all_sessions = []
    current_phase = ""
    
    for i, line in enumerate(lines):
        # Track current phase
        if line.startswith("### "):
            current_phase = line.replace("###", "").strip()
        
        # Look for table rows (skip headers and separators)
        if "|" in line and not re.match(r'\|[\s\-:]+\|', line) and not "Date" in line:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Skip empty first/last
            
            if len(cells) >= 6:  # Ensure we have all required columns
                # Check if first cell looks like a date
                try:
                    # Try to parse the date
                    datetime.strptime(cells[0], "%b %d")
                    
                    session_date = datetime.strptime(cells[0], "%b %d").replace(year=2025).date()
                    
                    # Clean garmin_mcp_description by removing surrounding quotes
                    garmin_desc = cells[5].strip()
                    if garmin_desc.startswith('"') and garmin_desc.endswith('"'):
                        garmin_desc = garmin_desc[1:-1]
                    
                    session = TrainingSession(
                        date=session_date,
                        day=cells[1],
                        session=cells[2],
                        distance=cells[3] if cells[3] else None,
                        heart_rate_target=cells[4] if cells[4] else None,
                        garmin_mcp_description=garmin_desc,
                        time=cells[6] if len(cells) > 6 else None
                    )
                    all_sessions.append((current_phase, session))
                except ValueError:
                    # Not a date, skip this row
                    continue
    
    # Sort sessions by date and group into weeks
    all_sessions.sort(key=lambda x: x[1].date)
    
    # Group sessions by week
    weeks = []
    week_number = 1
    current_week = []
    current_week_start = None
    
    for phase, session in all_sessions:
        if current_week_start is None:
            current_week_start = session.date
        
        # Check if we've moved to a new week (Monday to Sunday)
        days_since_start = (session.date - current_week_start).days
        if days_since_start >= 7 and len(current_week) > 0:
            # Save current week
            weeks.append(TrainingWeek(
                week_number=week_number,
                phase=phase,
                sessions=current_week
            ))
            week_number += 1
            current_week = []
            current_week_start = session.date
        
        current_week.append(session)
    
    # Don't forget the last week
    if current_week:
        weeks.append(TrainingWeek(
            week_number=week_number,
            phase=current_phase,
            sessions=current_week
        ))
    
    # Get start and end dates
    if all_sessions:
        start_date = min(s[1].date for s in all_sessions)
        end_date = max(s[1].date for s in all_sessions)
    else:
        start_date = date.today()
        end_date = date.today()
    
    return TrainingPlan(
        title=title,
        start_date=start_date,
        end_date=end_date,
        weeks=weeks
    )


def parse_workout_description(description: str, session_name: str = None) -> WorkoutData:
    """Convert natural language workout description to structured WorkoutData using AI-based parsing."""
    # Check for rest day
    if "rest day" in description.lower() or description.strip() == "-":
        return None
    
    # Use session name if provided, otherwise extract from description
    if not session_name:
        session_name = description.split(',')[0].strip()
    
    # Create the AI prompt for parsing
    prompt = f"""Parse this marathon training workout into a structured format.

Session Type: {session_name}
Workout Description: {description}

Create a JSON object with this structure:
{{
    "name": "appropriate workout name based on session type",
    "type": "running",
    "steps": [
        {{
            "stepName": "short descriptive name",
            "stepDescription": "full description",
            "endConditionType": "time" or "distance",
            "stepDuration": seconds (if time-based),
            "stepDistance": number (if distance-based),
            "distanceUnit": "km" or "m",
            "stepType": "warmup", "interval", "recovery", "cooldown", or "repeat",
            "target": {{
                "type": "heart rate",
                "value": [min, max],
                "unit": "bpm"
            }},
            "numberOfIterations": number (only for repeat steps),
            "steps": [] (only for repeat steps, contains the repeated steps)
        }}
    ]
}}

Rules:
1. Generate a concise, meaningful workout name based on the session type (e.g., "Tempo Run", "Norwegian 4×4 Intervals", "Long Run", "Recovery Run")
2. Split the description into individual steps (warmup, main sets, recovery, cooldown)
3. For heart rate zones: Zone 1 = 50-125 bpm, Zone 2 = 125-144 bpm, Zone 3 = 145-158 bpm, Zone 4 = 159-172 bpm, Zone 5 = 173-192 bpm
4. For intervals like "4x(4min at 172-177bpm, 3min recovery)", create a repeat step with nested steps
5. Convert all durations to seconds (e.g., 3min = 180 seconds)
6. Convert all distances to appropriate units (km for long distances, m for short)
7. Each step should have appropriate type (warmup, interval, recovery, cooldown)

Output only valid JSON, no explanations."""

    try:
        # Parse the AI response to create structured workout data
        import json
        
        # For now, let's create a more intelligent parser that doesn't rely on external AI
        # This is a temporary implementation that's better than the regex approach
        return parse_workout_intelligently(description, session_name)
    except Exception as e:
        # Fallback to simple workout if parsing fails
        return WorkoutData(
            name=session_name or "Workout",
            type="running",
            steps=[WorkoutStep(
                stepName=session_name or "Run",
                stepDescription=description,
                endConditionType="time",
                stepDuration=1800,  # Default 30 minutes
                stepType="interval"
            )]
        )


def parse_workout_intelligently(description: str, session_name: str) -> WorkoutData:
    """Parse workout using intelligent logic to create properly structured steps."""
    # Generate appropriate workout name based on session type
    workout_name = generate_workout_name(session_name)
    
    # Split description into logical parts
    steps = []
    
    # Handle different description patterns
    if "," in description or " then " in description.lower():
        # Split by commas and "then", but be smart about parentheses
        parts = []
        current_part = ""
        paren_depth = 0
        i = 0
        
        while i < len(description):
            char = description[i]
            
            # Check for "then" separator
            if paren_depth == 0 and i + 5 < len(description) and description[i:i+5].lower() == " then":
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = ""
                i += 5  # Skip " then"
                continue
            
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = ""
                i += 1
                continue
            
            current_part += char
            i += 1
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Process each part
        for part in parts:
            parsed_steps = process_workout_segment(part)
            if parsed_steps:
                steps.extend(parsed_steps)
    else:
        # Single segment workout
        parsed_steps = process_workout_segment(description)
        if parsed_steps:
            steps.extend(parsed_steps)
    
    # If no steps parsed, create a simple workout
    if not steps:
        steps = [create_simple_step(description, session_name)]
    
    return WorkoutData(
        name=workout_name,
        type="running",
        steps=steps
    )


def generate_workout_name(session_name: str) -> str:
    """Generate an appropriate workout name based on session type."""
    # Clean up session name
    session_name = session_name.strip()
    
    # Handle special cases
    if "**" in session_name:
        # Remove markdown formatting
        session_name = session_name.replace("**", "")
    
    # Map session types to better names
    name_mappings = {
        "Recovery Run": "Easy Recovery Run",
        "Tempo Run": "Tempo Run",
        "Norwegian 4×4": "Norwegian 4×4 Intervals",
        "Threshold": "Threshold Run",
        "Easy Aerobic": "Easy Aerobic Run",
        "Long Run": "Long Run",
        "Recovery Long": "Recovery Long Run",
        "Tempo Intervals": "Tempo Interval Workout",
        "Modified Intervals": "Interval Workout",
        "Easy Run": "Easy Run",
        "Shakeout": "Shakeout Run",
        "Recovery": "Recovery Run",
        "Marathon Pace": "Marathon Pace Run",
        "Short Intervals": "Short Interval Workout",
        "Easy + Strides": "Easy Run with Strides",
        "Recovery Jog": "Recovery Jog",
        "Activation": "Pre-Race Activation",
        "MARATHON": "Marathon Race",
        "Medium Long": "Medium Long Run",
        "Easy Long": "Easy Long Run",
        "Modified 4×3": "4×3min Interval Workout",
        "Easy + Mobility": "Easy Run with Mobility",
        "Strength + Easy": "Easy Run"
    }
    
    # Check for benchmark races
    if "Benchmark" in session_name:
        return session_name.replace("**", "").strip()
    
    # Return mapped name or original if not found
    for key, value in name_mappings.items():
        if key in session_name:
            return value
    
    return session_name


def process_workout_segment(segment: str) -> List[WorkoutStep]:
    """Process a single workout segment and return list of steps."""
    steps = []
    
    # Check for repeat pattern (e.g., "4x(4min at 172-177bpm, 3min recovery)")
    repeat_match = re.match(r'(\d+)[xX]\s*\(([^)]+)\)', segment)
    if repeat_match:
        iterations = int(repeat_match.group(1))
        repeat_content = repeat_match.group(2)
        
        # Parse the repeated steps
        repeat_steps = []
        inner_parts = repeat_content.split(',')
        for part in inner_parts:
            step = create_step_from_text(part.strip())
            if step:
                repeat_steps.append(step)
        
        if repeat_steps:
            repeat_step = WorkoutStep(
                stepName=f"{iterations}x Intervals",
                stepDescription=segment,
                endConditionType="repeat",
                stepType="repeat",
                numberOfIterations=iterations,
                steps=repeat_steps
            )
            steps.append(repeat_step)
    else:
        # Regular step
        step = create_step_from_text(segment)
        if step:
            steps.append(step)
    
    return steps


def create_step_from_text(text: str) -> Optional[WorkoutStep]:
    """Create a single workout step from text description."""
    # Determine step type
    step_type = determine_step_type(text)
    
    # Extract duration or distance
    duration_seconds = extract_duration(text)
    distance_km, distance_m = extract_distance(text)
    
    # Extract heart rate target
    target = extract_heart_rate_target(text)
    
    # Create step name (first 30 chars or less)
    step_name = text[:30] + "..." if len(text) > 30 else text
    
    # Build the step
    if duration_seconds:
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="time",
            stepDuration=duration_seconds,
            stepType=step_type,
            target=target
        )
    elif distance_km:
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="distance",
            stepDistance=distance_km,
            distanceUnit="km",
            stepType=step_type,
            target=target
        )
    elif distance_m:
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="distance",
            stepDistance=distance_m,
            distanceUnit="m",
            stepType=step_type,
            target=target
        )
    
    return None


def determine_step_type(text: str) -> str:
    """Determine the step type from text."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["warmup", "warm up", "warm-up"]):
        return "warmup"
    elif any(word in text_lower for word in ["cooldown", "cool down", "cool-down"]):
        return "cooldown"
    elif any(word in text_lower for word in ["recovery", "easy", "rest"]):
        return "recovery"
    else:
        return "interval"


def extract_duration(text: str) -> Optional[int]:
    """Extract duration in seconds from text."""
    # Match patterns like "20min", "3 min", "90sec", "90s"
    min_match = re.search(r'(\d+)\s*min', text)
    if min_match:
        return int(min_match.group(1)) * 60
    
    sec_match = re.search(r'(\d+)\s*(?:sec|s)\b', text)
    if sec_match:
        return int(sec_match.group(1))
    
    return None


def extract_distance(text: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract distance from text, returns (km, m)."""
    # Match km first
    km_match = re.search(r'(\d+(?:\.\d+)?)\s*km\b', text)
    if km_match:
        return float(km_match.group(1)), None
    
    # Match meters (but not "min")
    m_match = re.search(r'(\d+)\s*m\b(?!in)', text)
    if m_match:
        return None, float(m_match.group(1))
    
    return None, None


def extract_heart_rate_target(text: str) -> Optional[Dict[str, Any]]:
    """Extract heart rate target from text."""
    # Check for BPM range (e.g., "162-168bpm")
    range_match = re.search(r'(\d+)-(\d+)\s*bpm', text)
    if range_match:
        return {
            "type": "heart rate",
            "value": [int(range_match.group(1)), int(range_match.group(2))],
            "unit": "bpm"
        }
    
    # Check for single BPM value (e.g., "at 160bpm", "under 125bpm")
    single_match = re.search(r'(?:at|under|below)\s*(\d+)\s*bpm', text)
    if single_match:
        value = int(single_match.group(1))
        if "under" in text.lower() or "below" in text.lower():
            return {
                "type": "heart rate",
                "value": [50, value],
                "unit": "bpm"
            }
        else:
            return {
                "type": "heart rate",
                "value": [value - 5, value + 5],
                "unit": "bpm"
            }
    
    # Check for heart rate zones
    zone_match = re.search(r'zone\s*(\d+)', text.lower())
    if zone_match:
        zone = int(zone_match.group(1))
        zone_ranges = {
            1: [50, 125],      # Recovery: <125 bpm
            2: [125, 144],     # Easy Aerobic: 125-144 bpm
            3: [145, 158],     # Marathon Pace: 145-158 bpm
            4: [159, 172],     # Threshold: 159-172 bpm
            5: [173, 192]      # VO2max/Anaerobic: 173-192 bpm
        }
        if zone in zone_ranges:
            return {
                "type": "heart rate",
                "value": zone_ranges[zone],
                "unit": "bpm"
            }
    
    return None


def create_simple_step(description: str, session_name: str) -> WorkoutStep:
    """Create a simple step when parsing fails."""
    # Try to extract any duration or distance
    duration = extract_duration(description)
    distance_km, distance_m = extract_distance(description)
    
    if duration:
        return WorkoutStep(
            stepName=session_name or "Run",
            stepDescription=description,
            endConditionType="time",
            stepDuration=duration,
            stepType="interval"
        )
    elif distance_km:
        return WorkoutStep(
            stepName=session_name or "Run",
            stepDescription=description,
            endConditionType="distance",
            stepDistance=distance_km,
            distanceUnit="km",
            stepType="interval"
        )
    else:
        # Default to 30 minute run
        return WorkoutStep(
            stepName=session_name or "Run",
            stepDescription=description,
            endConditionType="time",
            stepDuration=1800,
            stepType="interval"
        )


def parse_single_step(text: str) -> Optional[WorkoutStep]:
    """Parse a single workout step from text."""
    # Determine step type
    step_type = "interval"  # default
    if any(word in text.lower() for word in ["warmup", "warm up", "warm-up"]):
        step_type = "warmup"
    elif any(word in text.lower() for word in ["cooldown", "cool down", "cool-down"]):
        step_type = "cooldown"
    elif any(word in text.lower() for word in ["recovery", "easy", "rest"]):
        step_type = "recovery"
    
    # Extract duration or distance
    duration_match = re.search(r'(\d+)\s*min', text)
    distance_km_match = re.search(r'(\d+)\s*km\b', text)
    distance_m_match = re.search(r'(\d+)\s*m\b', text)
    
    step_name = text[:30] if len(text) > 30 else text
    
    # Parse heart rate target
    target = None
    hr_range_match = re.search(r'(\d+)-(\d+)\s*bpm', text)
    hr_single_match = re.search(r'(?:at|under|below)\s*(\d+)\s*bpm', text)
    zone_match = re.search(r'zone\s*(\d+)', text.lower())
    
    if hr_range_match:
        min_hr = int(hr_range_match.group(1))
        max_hr = int(hr_range_match.group(2))
        target = {
            "type": "heart rate",
            "value": [min_hr, max_hr],
            "unit": "bpm"
        }
    elif hr_single_match:
        hr_value = int(hr_single_match.group(1))
        if "under" in text.lower() or "below" in text.lower():
            target = {
                "type": "heart rate",
                "value": [50, hr_value],  # Assume 50 as lower bound
                "unit": "bpm"
            }
        else:
            target = {
                "type": "heart rate",
                "value": [hr_value - 5, hr_value + 5],  # Small range around target
                "unit": "bpm"
            }
    elif zone_match:
        zone = int(zone_match.group(1))
        # Define heart rate zones (approximate)
        zone_ranges = {
            1: [50, 125],      # Recovery: <125 bpm
            2: [125, 144],     # Easy Aerobic: 125-144 bpm
            3: [145, 158],     # Marathon Pace: 145-158 bpm
            4: [159, 172],     # Threshold: 159-172 bpm
            5: [173, 192]      # VO2max/Anaerobic: 173-192 bpm
        }
        if zone in zone_ranges:
            target = {
                "type": "heart rate",
                "value": zone_ranges[zone],
                "unit": "bpm"
            }
    
    # Create step based on what we found
    if duration_match:
        duration_minutes = int(duration_match.group(1))
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="time",
            stepDuration=duration_minutes * 60,
            stepType=step_type,
            target=target
        )
    elif distance_km_match:
        distance = float(distance_km_match.group(1))
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="distance",
            stepDistance=distance,
            distanceUnit="km",
            stepType=step_type,
            target=target
        )
    elif distance_m_match and not re.search(r'\d+\s*m(?:in|s)', text):  # Avoid matching "min"
        distance = float(distance_m_match.group(1))
        return WorkoutStep(
            stepName=step_name,
            stepDescription=text,
            endConditionType="distance",
            stepDistance=distance,
            distanceUnit="m",
            stepType=step_type,
            target=target
        )
    
    return None