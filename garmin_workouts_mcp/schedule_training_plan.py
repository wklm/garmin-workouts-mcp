#!/usr/bin/env python3
"""CLI tool to schedule training plans from markdown files to Garmin Connect."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple

import click
import garth
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel

from .models import TrainingPlan, TrainingSession, ScheduleResult, WorkoutData
from .utils import parse_training_plan_markdown, parse_workout_description
from .garmin_workout import make_payload

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

console = Console()


class GarminWorkoutScheduler:
    """Handles scheduling workouts to Garmin Connect."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.console = console

    def login(self):
        """Login to Garmin Connect."""
        if self.dry_run:
            self.console.print("[yellow]Dry run mode - skipping Garmin login[/yellow]")
            return

        try:
            garth_home = os.environ.get("GARTH_HOME", "~/.garth")
            garth.resume(garth_home)
            self.console.print("[green]✓ Logged in using saved credentials[/green]")
        except Exception:
            email = os.environ.get("GARMIN_EMAIL")
            password = os.environ.get("GARMIN_PASSWORD")

            if not email or not password:
                self.console.print("[red]Error: Garmin credentials not found.[/red]")
                self.console.print(
                    "Please set GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
                )
                sys.exit(1)

            try:
                garth.login(email, password)
                garth.save(garth_home)
                self.console.print("[green]✓ Logged in successfully[/green]")
            except Exception as e:
                self.console.print(f"[red]Login failed: {e}[/red]")
                sys.exit(1)

    def upload_workout(self, workout_data: WorkoutData) -> Optional[str]:
        """Upload a workout to Garmin Connect."""
        if self.dry_run:
            return "dry-run-workout-id"

        try:
            payload = make_payload(workout_data.model_dump())
            result = garth.connectapi(
                "/workout-service/workout", method="POST", json=payload
            )
            workout_id = result.get("workoutId")

            if not workout_id:
                raise Exception("No workout ID returned")

            return str(workout_id)
        except Exception as e:
            logger.error(f"Failed to upload workout: {e}")
            raise

    def schedule_workout(
        self, workout_id: str, schedule_date: date, planned_workout: WorkoutData = None
    ) -> Tuple[Optional[str], bool]:
        """
        Schedule a workout on a specific date.

        Returns:
            Tuple of (schedule_id, was_skipped)
        """
        if self.dry_run:
            return ("dry-run-schedule-id", False)

        try:
            # Check if there's already a workout scheduled for this date
            calendar_data = self.get_calendar_for_date(schedule_date)

            if calendar_data:
                for item in calendar_data.get("calendarItems", []):
                    if (
                        item.get("itemType") == "workout"
                        and item.get("date") == schedule_date.isoformat()
                    ):
                        existing_schedule_id = item.get("id")
                        existing_workout_id = item.get("workoutId")

                        if existing_workout_id and planned_workout:
                            # Get details of existing workout
                            existing_workout = self.get_workout_details(
                                existing_workout_id
                            )
                            if existing_workout and self.workouts_match(
                                existing_workout, planned_workout
                            ):
                                # Workouts match - skip scheduling
                                self.console.print(
                                    f"[dim]Workout already exists on {schedule_date} and matches - skipping[/dim]"
                                )
                                return (existing_schedule_id, True)

                        # Workouts don't match or we couldn't compare - remove existing
                        if existing_schedule_id:
                            self.console.print(
                                f"[yellow]Removing non-matching workout on {schedule_date}[/yellow]"
                            )
                            self.delete_scheduled_workout(existing_schedule_id)

            # Schedule the new workout
            payload = {"date": schedule_date.isoformat()}
            endpoint = f"/workout-service/schedule/{workout_id}"
            result = garth.connectapi(endpoint, method="POST", json=payload)

            schedule_id = result.get("workoutScheduleId")
            if not schedule_id:
                raise Exception(f"Scheduling failed: {result}")

            return (str(schedule_id), False)
        except Exception as e:
            logger.error(f"Failed to schedule workout: {e}")
            raise

    def get_calendar_for_date(self, target_date: date) -> Optional[Dict[str, Any]]:
        """Get calendar data for a specific date."""
        if self.dry_run:
            return None

        try:
            endpoint = f"/calendar-service/year/{target_date.year}/month/{target_date.month - 1}/day/{target_date.day}/start/1"
            return garth.connectapi(endpoint)
        except Exception:
            return None

    def delete_scheduled_workout(self, schedule_id: str):
        """Delete a scheduled workout."""
        if self.dry_run:
            return

        try:
            endpoint = f"/workout-service/schedule/{schedule_id}"
            garth.connectapi(endpoint, method="DELETE")
        except Exception as e:
            logger.warning(f"Failed to delete scheduled workout {schedule_id}: {e}")

    def get_workout_details(self, workout_id: str) -> Optional[Dict[str, Any]]:
        """Get full workout details from Garmin Connect."""
        if self.dry_run:
            return None

        try:
            endpoint = f"/workout-service/workout/{workout_id}"
            return garth.connectapi(endpoint)
        except Exception as e:
            logger.error(f"Failed to get workout {workout_id}: {e}")
            return None

    def workouts_match(
        self, existing_workout: Dict[str, Any], planned_workout: WorkoutData
    ) -> bool:
        """Compare if existing workout matches the planned workout structure."""
        try:
            # Compare workout type
            if (
                existing_workout.get("sportType", {}).get("sportTypeKey")
                != planned_workout.type
            ):
                return False

            # Compare number of steps (segments and steps)
            existing_segments = existing_workout.get("workoutSegments", [])
            if not existing_segments:
                return False

            # For now, we'll do a simple comparison based on workout name and step count
            # This could be enhanced to do deeper structural comparison
            existing_steps = []
            for segment in existing_segments:
                existing_steps.extend(segment.get("workoutSteps", []))

            if len(existing_steps) != len(planned_workout.steps):
                return False

            # Compare workout names (if available)
            existing_name = existing_workout.get("workoutName", "").lower()
            planned_name = planned_workout.name.lower()

            # Basic name similarity check
            if existing_name and planned_name:
                # Check if names are similar enough
                if existing_name == planned_name:
                    return True
                # Check if one contains the other
                if planned_name in existing_name or existing_name in planned_name:
                    return True

            # If we can't determine by name, assume they don't match to be safe
            return False

        except Exception as e:
            logger.warning(f"Error comparing workouts: {e}")
            return False

    async def schedule_session(
        self, session: TrainingSession, retry_count: int = 3
    ) -> ScheduleResult:
        """Schedule a single training session with retry logic."""
        for attempt in range(retry_count):
            try:
                # Skip rest days
                if "rest" in session.garmin_mcp_description.lower():
                    return ScheduleResult(
                        date=session.date,
                        session_name=session.session,
                        success=True,
                        error="Rest day - skipped",
                    )

                # Parse workout from description with session name
                workout_data = parse_workout_description(
                    session.garmin_mcp_description, session.session
                )
                if not workout_data:
                    return ScheduleResult(
                        date=session.date,
                        session_name=session.session,
                        success=False,
                        error="Could not parse workout description",
                    )

                # Check for existing workout first (idempotency)
                if not self.dry_run:
                    calendar_data = self.get_calendar_for_date(session.date)
                    if calendar_data:
                        for item in calendar_data.get("calendarItems", []):
                            if (
                                item.get("itemType") == "workout"
                                and item.get("date") == session.date.isoformat()
                            ):
                                existing_workout_id = item.get("workoutId")
                                if existing_workout_id:
                                    existing_workout = self.get_workout_details(
                                        existing_workout_id
                                    )
                                    if existing_workout and self.workouts_match(
                                        existing_workout, workout_data
                                    ):
                                        # Workout already exists and matches
                                        return ScheduleResult(
                                            date=session.date,
                                            session_name=session.session,
                                            workout_id=existing_workout_id,
                                            schedule_id=item.get("id"),
                                            success=True,
                                            skipped=True,
                                        )

                # Upload workout
                workout_id = self.upload_workout(workout_data)

                # Schedule workout (with idempotency check)
                schedule_id, was_skipped = self.schedule_workout(
                    workout_id, session.date, workout_data
                )

                return ScheduleResult(
                    date=session.date,
                    session_name=session.session,
                    workout_id=workout_id if not was_skipped else None,
                    schedule_id=schedule_id,
                    success=True,
                    skipped=was_skipped,
                )

            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {session.date}: {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    return ScheduleResult(
                        date=session.date,
                        session_name=session.session,
                        success=False,
                        error=str(e),
                    )

    async def schedule_training_plan(self, plan: TrainingPlan) -> List[ScheduleResult]:
        """Schedule all sessions in a training plan."""
        results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"Scheduling {len(plan.all_sessions)} sessions...",
                total=len(plan.all_sessions),
            )

            for session in plan.all_sessions:
                progress.update(
                    task,
                    description=f"Scheduling {session.date}: {session.session[:30]}...",
                )

                result = await self.schedule_session(session)
                results.append(result)

                if result.success:
                    if result.error == "Rest day - skipped":
                        self.console.print(
                            f"[dim]Skipped {session.date}: Rest day[/dim]"
                        )
                    elif result.skipped:
                        self.console.print(
                            f"[cyan]⟳ Exists {session.date}: {session.session} (matched)[/cyan]"
                        )
                    else:
                        self.console.print(
                            f"[green]✓ Scheduled {session.date}: {session.session}[/green]"
                        )
                else:
                    self.console.print(
                        f"[red]✗ Failed {session.date}: {result.error}[/red]"
                    )

                progress.advance(task)

                # Small delay to avoid rate limiting
                if not self.dry_run:
                    await asyncio.sleep(0.5)

        return results

    async def validate_scheduled_workouts(
        self, plan: TrainingPlan, results: List[ScheduleResult]
    ) -> List[ScheduleResult]:
        """Validate that all workouts were scheduled correctly."""
        self.console.print("\n[bold]Validating scheduled workouts...[/bold]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"Validating {len(plan.all_sessions)} sessions...",
                total=len(plan.all_sessions),
            )

            for i, session in enumerate(plan.all_sessions):
                progress.update(
                    task,
                    description=f"Validating {session.date}: {session.session[:30]}...",
                )

                # Find the corresponding result
                result = next((r for r in results if r.date == session.date), None)
                if not result:
                    continue

                # Skip rest days
                if "rest" in session.garmin_mcp_description.lower():
                    result.validation_status = "Rest day - skipped"
                    progress.advance(task)
                    continue

                # Validate the workout exists on the date
                validation_status = await self.validate_session(session)
                result.validation_status = validation_status

                if validation_status == "Valid":
                    self.console.print(
                        f"[green]✓ Validated {session.date}: {session.session}[/green]"
                    )
                else:
                    self.console.print(
                        f"[red]✗ Validation failed {session.date}: {validation_status}[/red]"
                    )

                progress.advance(task)

                # Small delay to avoid rate limiting
                if not self.dry_run:
                    await asyncio.sleep(0.2)

        return results

    async def validate_session(self, session: TrainingSession) -> str:
        """Validate a single session is correctly scheduled."""
        if self.dry_run:
            return "Valid (dry-run)"

        try:
            calendar_data = self.get_calendar_for_date(session.date)
            if not calendar_data:
                return "No calendar data found"

            # Look for workout on this date
            found_workout = False
            for item in calendar_data.get("calendarItems", []):
                if (
                    item.get("itemType") == "workout"
                    and item.get("date") == session.date.isoformat()
                ):
                    found_workout = True
                    workout_id = item.get("workoutId")

                    if workout_id:
                        # Get workout details
                        workout_details = self.get_workout_details(workout_id)
                        if workout_details:
                            workout_name = workout_details.get("workoutName", "")
                            # Basic validation - check if workout exists and has a name
                            if workout_name:
                                return "Valid"
                            else:
                                return "Workout exists but has no name"
                        else:
                            return "Could not retrieve workout details"
                    else:
                        return "Scheduled but no workout ID"

            if not found_workout:
                return "No workout found on this date"

            return "Unknown validation error"

        except Exception as e:
            return f"Validation error: {str(e)}"


@click.command()
@click.argument("training_plan_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without actually scheduling")
@click.option(
    "--start-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Override start date",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(
    training_plan_file: str,
    dry_run: bool,
    start_date: Optional[datetime],
    verbose: bool,
):
    """Schedule marathon training plan from markdown file to Garmin Connect."""

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Read training plan file
    plan_path = Path(training_plan_file)
    console.print(
        Panel(
            f"[bold blue]Marathon Training Plan Scheduler[/bold blue]\n\nReading: {plan_path.name}"
        )
    )

    try:
        content = plan_path.read_text()
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        sys.exit(1)

    # Parse training plan
    with console.status("Parsing training plan..."):
        try:
            plan = parse_training_plan_markdown(content)
        except Exception as e:
            console.print(f"[red]Error parsing training plan: {e}[/red]")
            sys.exit(1)

    # Display plan summary
    table = Table(title="Training Plan Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Title", plan.title)
    table.add_row("Start Date", str(plan.start_date))
    table.add_row("End Date", str(plan.end_date))
    table.add_row("Total Weeks", str(len(plan.weeks)))
    table.add_row("Total Sessions", str(len(plan.all_sessions)))

    console.print(table)

    if dry_run:
        console.print(
            "\n[yellow]DRY RUN MODE - No workouts will be scheduled[/yellow]\n"
        )

    # Confirm before proceeding
    if not dry_run:
        if not click.confirm(
            "Do you want to schedule these workouts to Garmin Connect?"
        ):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Initialize scheduler
    scheduler = GarminWorkoutScheduler(dry_run=dry_run)

    # Login to Garmin
    scheduler.login()

    # Schedule workouts
    console.print("\n[bold]Scheduling workouts...[/bold]\n")

    # Use asyncio to run the scheduling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        results = loop.run_until_complete(scheduler.schedule_training_plan(plan))

        # Run validation phase
        if not dry_run:
            results = loop.run_until_complete(
                scheduler.validate_scheduled_workouts(plan, results)
            )
    finally:
        loop.close()

    # Display results summary
    successful = sum(1 for r in results if r.success and not r.skipped)
    failed = sum(
        1 for r in results if not r.success and r.error != "Rest day - skipped"
    )
    rest_days = sum(1 for r in results if r.error == "Rest day - skipped")
    skipped_existing = sum(1 for r in results if r.skipped)

    # Validation summary
    validated = sum(
        1
        for r in results
        if r.validation_status == "Valid" or r.validation_status == "Valid (dry-run)"
    )
    validation_failed = sum(
        1
        for r in results
        if r.validation_status
        and "Valid" not in r.validation_status
        and "Rest day" not in r.validation_status
    )

    console.print("\n[bold]Scheduling Summary:[/bold]")
    console.print(f"  [green]✓ Newly scheduled: {successful}[/green]")
    console.print(f"  [cyan]⟳ Already existed (matched): {skipped_existing}[/cyan]")
    console.print(f"  [yellow]○ Rest days: {rest_days}[/yellow]")
    console.print(f"  [red]✗ Failed: {failed}[/red]")

    if not dry_run:
        console.print("\n[bold]Validation Summary:[/bold]")
        console.print(f"  [green]✓ Validated: {validated}[/green]")
        console.print(f"  [red]✗ Validation failed: {validation_failed}[/red]")

    if failed > 0 or validation_failed > 0:
        console.print(
            "\n[red]Some workouts failed to schedule or validate. Check the logs for details.[/red]"
        )
        sys.exit(1)
    else:
        console.print("\n[green]✓ All workouts processed successfully![/green]")


if __name__ == "__main__":
    main()
