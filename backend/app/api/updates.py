"""
Update Scripts API endpoints.

Allows running update scripts from the UI.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta
from app.database import SessionLocal
import subprocess
import sys
import os
import json
import asyncio
import logging
from pathlib import Path

# Ensure os is imported for env var

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/updates", tags=["updates"])


async def read_subprocess_output(process, output_queue, progress_queue, total_steps):
    """Read stdout and stderr from subprocess and put lines into queue with progress tracking."""
    # Patterns to filter out (non-critical warnings)
    filtered_patterns = [
        'NotOpenSSLWarning',
        'urllib3',
        'warnings.warn',
        'warn(',
    ]
    
    # Step patterns for quick update
    quick_update_steps = [
        "Updating yesterday's game results",
        "Evaluating predictions",
        "Regenerating predictions",
    ]
    
    # Step patterns for full update
    full_update_steps = [
        "STEP 1:",
        "STEP 2:",
        "STEP 3:",
        "STEP 4:",
        "STEP 5:",
        "STEP 6:",
        "STEP 7:",
        "STEP 8:",
    ]
    
    current_step = 0
    step_patterns = full_update_steps if total_steps == 8 else quick_update_steps
    
    def should_filter(line_str):
        """Check if line should be filtered out."""
        line_lower = line_str.lower()
        return any(pattern.lower() in line_lower for pattern in filtered_patterns)
    
    async def check_step_progress(line_str):
        """Check if line indicates a new step and update progress."""
        nonlocal current_step
        for idx, pattern in enumerate(step_patterns):
            if pattern in line_str and idx >= current_step:
                current_step = idx + 1
                # Don't set to 100% until process actually completes
                # Cap at 95% during execution
                progress = min(95, int((current_step / total_steps) * 100))
                await progress_queue.put({
                    'progress': progress,
                    'message': line_str,
                    'step': current_step,
                    'total_steps': total_steps
                })
                break
    
    async def read_stream(stream, is_error=False):
        while True:
            line = await stream.readline()
            if not line:
                break
            line_str = line.decode('utf-8', errors='replace').strip()
            if line_str and not should_filter(line_str):
                await check_step_progress(line_str)
                await output_queue.put((line_str, is_error))
    
    # Read both streams concurrently
    await asyncio.gather(
        read_stream(process.stdout, is_error=False),
        read_stream(process.stderr, is_error=True)
    )
    await output_queue.put(None)  # Signal completion


@router.post("/collect-nba-schedule")
async def collect_nba_schedule(year: int = 2025):
    """Collect NBA schedules for a specific season using NBA.com official API."""
    try:
        # Import and run the NBA schedule collection script
        project_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(project_root / "scripts"))
        from collect_nba_schedule import fetch_nba_schedule, save_games_to_db

        # Fetch schedule
        games = fetch_nba_schedule(year)

        if games:
            # Save to database
            save_games_to_db(games)

            return {
                "success": True,
                "message": f"Collected {len(games)} games for NBA {year} season",
                "games_collected": len(games)
            }
        else:
            return {
                "success": False,
                "message": f"No games found for NBA {year} season"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-full-update")
async def run_full_update(sport: str = Query('NBA', description="Sport type (NBA or NFL)")):
    """
    Run the full update script (update_all.py) with progress updates via SSE.
    
    This will:
    1. Collect box scores for yesterday's games
    2. Update player stats
    3. Update schedules
    4. Recalculate analytics
    5. Update injuries/lineups
    6. Generate predictions
    7. Evaluate finished games
    
    Note: This is a long-running operation (2-5 minutes).
    """
    async def run_with_progress():
        # Get project root - go up from backend/app/api/updates.py to project root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        script_name = "nfl_update_all.py" if sport == 'NFL' else "update_all.py"
        script_path = project_root / "scripts" / script_name

        if not script_path.exists():
            yield f"data: {json.dumps({'error': f'{sport} update script not found at {script_path}', 'complete': True})}\n\n"
            return
        
        # Run the script - need to activate venv python
        venv_python = project_root / "backend" / "venv" / "bin" / "python3"
        if not venv_python.exists():
            # Fallback to system python
            python_cmd = sys.executable
        else:
            python_cmd = str(venv_python)
        
        try:
            yield f"data: {json.dumps({'message': 'Starting full update...', 'progress': 0, 'step': 0, 'total_steps': 8})}\n\n"
            
            # Run script with real-time output
            process = await asyncio.create_subprocess_exec(
                python_cmd, str(script_path),
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Use queues to collect output lines and progress
            output_queue = asyncio.Queue()
            progress_queue = asyncio.Queue()
            output_lines = []
            error_lines = []
            
            # Start reading output in background (8 steps for full update)
            read_task = asyncio.create_task(read_subprocess_output(process, output_queue, progress_queue, 8))
            
            # Yield lines and progress as they come in
            process_done = False
            while not process_done:
                try:
                    # Check for progress updates first
                    try:
                        progress_item = await asyncio.wait_for(progress_queue.get(), timeout=0.01)
                        yield f"data: {json.dumps(progress_item)}\n\n"
                    except asyncio.TimeoutError:
                        pass
                    
                    # Then check for output lines
                    try:
                        item = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                        if item is None:  # Completion signal from read task
                            # Check if process is actually done
                            if process.returncode is not None:
                                process_done = True
                                break
                            # Otherwise, continue waiting
                            continue
                        line_str, is_error = item
                        if is_error:
                            error_lines.append(line_str)
                        else:
                            output_lines.append(line_str)
                        # Only yield non-progress lines if they're not step indicators
                        if not any(step in line_str for step in ["STEP 1:", "STEP 2:", "STEP 3:", "STEP 4:", "STEP 5:", "STEP 6:", "STEP 7:", "STEP 8:"]):
                            yield f"data: {json.dumps({'message': line_str, 'progress': None})}\n\n"
                    except asyncio.TimeoutError:
                        # Check if process is done
                        if process.returncode is not None:
                            process_done = True
                            break
                        continue
                except Exception as e:
                    # Log error but continue
                    logger.error(f"Error in update loop: {e}")
                    continue
            
            # Wait for read task to complete
            await read_task
            
            # Wait for process to complete (with timeout)
            try:
                returncode = await asyncio.wait_for(process.wait(), timeout=600)  # 10 minute max
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                returncode = -1
                yield f"data: {json.dumps({'message': 'Update script timed out', 'progress': 100, 'complete': True, 'success': False})}\n\n"
                return
            
            # Send completion message with 100% progress
            if returncode == 0:
                output_text = '\n'.join(output_lines)
                yield f"data: {json.dumps({'message': 'Full update completed successfully', 'progress': 100, 'complete': True, 'output': output_text})}\n\n"
            else:
                output_text = '\n'.join(output_lines)
                error_text = '\n'.join(error_lines)
                yield f"data: {json.dumps({'message': 'Full update completed with errors', 'progress': 100, 'complete': True, 'success': False, 'output': output_text, 'errors': error_text})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Error running update script: {str(e)}', 'complete': True})}\n\n"
    
    return StreamingResponse(
        run_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/run-quick-update")
async def run_quick_update():
    """
    Run the quick update script (quick_update.py) with progress updates via SSE.
    
    This will:
    1. Collect box scores for yesterday's games
    2. Evaluate yesterday's predictions
    3. Generate predictions for today's games
    
    Note: This is faster (30-60 seconds).
    """
    async def run_with_progress():
        # Get project root - go up from backend/app/api/updates.py to project root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        script_path = project_root / "scripts" / "quick_update.py"
        
        if not script_path.exists():
            yield f"data: {json.dumps({'error': f'Quick update script not found at {script_path}', 'complete': True})}\n\n"
            return
        
        # Run the script - need to activate venv python
        venv_python = project_root / "backend" / "venv" / "bin" / "python3"
        if not venv_python.exists():
            # Fallback to system python
            python_cmd = sys.executable
        else:
            python_cmd = str(venv_python)
        
        try:
            yield f"data: {json.dumps({'message': 'Starting quick update...', 'progress': 0, 'step': 0, 'total_steps': 3})}\n\n"
            
            # Run script with real-time output
            process = await asyncio.create_subprocess_exec(
                python_cmd, str(script_path),
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Use queues to collect output lines and progress
            output_queue = asyncio.Queue()
            progress_queue = asyncio.Queue()
            output_lines = []
            error_lines = []
            
            # Start reading output in background (3 steps for quick update)
            read_task = asyncio.create_task(read_subprocess_output(process, output_queue, progress_queue, 3))
            
            # Yield lines and progress as they come in
            process_done = False
            while not process_done:
                try:
                    # Check for progress updates first
                    try:
                        progress_item = await asyncio.wait_for(progress_queue.get(), timeout=0.01)
                        yield f"data: {json.dumps(progress_item)}\n\n"
                    except asyncio.TimeoutError:
                        pass
                    
                    # Then check for output lines
                    try:
                        item = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                        if item is None:  # Completion signal from read task
                            # Check if process is actually done
                            if process.returncode is not None:
                                process_done = True
                                break
                            # Otherwise, continue waiting
                            continue
                        line_str, is_error = item
                        if is_error:
                            error_lines.append(line_str)
                        else:
                            output_lines.append(line_str)
                        # Yield all output lines
                        yield f"data: {json.dumps({'message': line_str, 'progress': None})}\n\n"
                    except asyncio.TimeoutError:
                        # Check if process is done
                        if process.returncode is not None:
                            process_done = True
                            break
                        continue
                except Exception as e:
                    # Log error but continue
                    logger.error(f"Error in update loop: {e}")
                    continue
            
            # Wait for read task to complete
            await read_task
            
            # Wait for process to complete (with timeout)
            try:
                returncode = await asyncio.wait_for(process.wait(), timeout=300)  # 5 minute max
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                returncode = -1
                yield f"data: {json.dumps({'message': 'Quick update script timed out', 'progress': 100, 'complete': True, 'success': False})}\n\n"
                return
            
            # Send completion message with 100% progress
            if returncode == 0:
                output_text = '\n'.join(output_lines)
                yield f"data: {json.dumps({'message': 'Quick update completed successfully', 'progress': 100, 'complete': True, 'output': output_text})}\n\n"
            else:
                output_text = '\n'.join(output_lines)
                error_text = '\n'.join(error_lines)
                yield f"data: {json.dumps({'message': 'Quick update completed with errors', 'progress': 100, 'complete': True, 'success': False, 'output': output_text, 'errors': error_text})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Error running quick update script: {str(e)}', 'complete': True})}\n\n"
    
    return StreamingResponse(
        run_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/collect-box-scores")
async def collect_box_scores(days_back: int = 1):
    """
    Collect box scores for finished games.
    
    Args:
        days_back: Number of days back to collect (default: 1 for yesterday)
    """
    # Get project root - go up from backend/app/api/updates.py to project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent.parent
    script_path = project_root / "scripts" / "collect_game_results.py"
    
    if not script_path.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"Collect game results script not found at {script_path}"
        )
    
    try:
        target_date = date.today() - timedelta(days=days_back)
        
        # Run the script - need to activate venv python
        venv_python = project_root / "backend" / "venv" / "bin" / "python3"
        if not venv_python.exists():
            # Fallback to system python
            python_cmd = sys.executable
        else:
            python_cmd = str(venv_python)
        
        result = subprocess.run(
            [python_cmd, str(script_path), "--date", target_date.isoformat()],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "message": f"Box scores collected for {target_date}",
                "output": result.stdout,
                "errors": result.stderr if result.stderr else None
            }
        else:
            return {
                "success": False,
                "message": "Box score collection completed with errors",
                "output": result.stdout,
                "errors": result.stderr
            }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Box score collection timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting box scores: {str(e)}")


@router.post("/collect-players")
async def collect_players(
    sport: str = Query("NBA", description="Sport type (NBA or NFL)"),
    use_espn: str = Query("true", description="Use ESPN scraping instead of NBA API (default: true, avoids rate limits)")
):
    """
    Collect players from ESPN (default) or NBA API and store in database with progress updates via SSE.
    
    Args:
        sport: Sport type (NBA or NFL). Default: NBA
        use_espn: Use ESPN scraping instead of NBA API. Default: "true" (ESPN) to avoid rate limits.
    
    Note: ESPN scraping is faster and has no rate limits. NBA API may take 5-10 minutes due to rate limits.
    """
    # Parse use_espn string parameter (from query string)
    # Default to ESPN if not specified (avoid NBA API rate limits)
    # Accept: 'true', 'True', '1', 'yes' -> ESPN; anything else -> NBA API
    use_espn_bool = use_espn.lower() not in ('false', '0', 'no', 'n')
    
    async def collect_with_progress():
        # Get project root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        
        # Choose the right script based on sport
        if sport == "NFL":
            # NFL players are collected through game results collection
            # Check current player count and run game results collection
            yield f"data: {json.dumps({'message': 'NFL players collected through game results. Running NFL game results collection...', 'progress': 0})}\n\n"

            try:
                from app.database import SessionLocal
                from app.models.player import Player

                db = SessionLocal()
                try:
                    initial_count = db.query(Player).filter(Player.sport == 'NFL').count()
                    yield f"data: {json.dumps({'message': f'Found {initial_count} existing NFL players', 'progress': 5})}\n\n"
                finally:
                    db.close()

                # Run NFL game results collection script
                script_path = project_root / "scripts" / "nfl_collect_game_results.py"

                if not script_path.exists():
                    yield f"data: {json.dumps({'error': f'NFL game results script not found at {script_path}', 'complete': True})}\n\n"
                    return

                # Run the NFL game results collection script
                venv_python = project_root / "backend" / "venv" / "bin" / "python3"
                if not venv_python.exists():
                    python_cmd = sys.executable
                else:
                    python_cmd = str(venv_python)

                yield f"data: {json.dumps({'message': 'Starting NFL game results collection (this collects players too)...', 'progress': 10})}\n\n"

                # Run script with yesterday's date
                from datetime import datetime, timedelta
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

                process = await asyncio.create_subprocess_exec(
                    python_cmd, str(script_path), '--date', yesterday,
                    cwd=str(project_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                # Wait for completion
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Check final player count
                    db = SessionLocal()
                    try:
                        final_count = db.query(Player).filter(Player.sport == 'NFL').count()
                        players_added = final_count - initial_count
                    finally:
                        db.close()

                    output_lines = stdout.decode().split('\n')
                    # Look for completion message
                    for line in reversed(output_lines):
                        if 'Complete:' in line and 'games created' in line:
                            yield f"data: {json.dumps({'message': f'NFL collection complete! {line.strip()}. Players: {final_count} total (+{players_added})', 'progress': 100, 'complete': True})}\n\n"
                            break
                    else:
                        yield f"data: {json.dumps({'message': f'NFL collection completed successfully. Players: {final_count} total (+{players_added})', 'progress': 100, 'complete': True})}\n\n"
                else:
                    error_msg = stderr.decode() or "Unknown error"
                    yield f"data: {json.dumps({'error': f'NFL collection failed: {error_msg}', 'complete': True})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': f'NFL player collection failed: {str(e)}', 'complete': True})}\n\n"

            return
        
        script_path = project_root / "scripts" / "collect_players.py"
        
        if not script_path.exists():
            yield f"data: {json.dumps({'error': f'Collect players script not found at {script_path}', 'complete': True})}\n\n"
            return
        
        try:
            # Run the script - need to activate venv python
            venv_python = project_root / "backend" / "venv" / "bin" / "python3"
            if not venv_python.exists():
                python_cmd = sys.executable
            else:
                python_cmd = str(venv_python)
            
            # Determine method and set message
            method = "ESPN scraping" if use_espn_bool else "NBA API"
            logger.info(f"Starting player collection: sport={sport}, use_espn={use_espn} -> {use_espn_bool}, method={method}")
            yield f"data: {json.dumps({'message': f'Starting {sport} player collection via {method}...', 'progress': 0})}\n\n"
            
            # Build command - ESPN is default, only add flag if using NBA API
            cmd = [python_cmd, '-u', str(script_path)]
            if not use_espn_bool:
                cmd.append('--use-nba-api')  # Only add flag if NOT using ESPN (ESPN is default)
                logger.info(f"Using NBA API - added --use-nba-api flag")
            else:
                logger.info(f"Using ESPN scraping - no flag needed (ESPN is default)")
            # Note: If use_espn_bool is True (default), no flag is needed - script defaults to ESPN
            
            logger.info(f"Command: {' '.join(cmd)}")
            
            # Run script with real-time output (unbuffered for immediate output)
            process = await asyncio.create_subprocess_exec(
                *cmd,  # -u for unbuffered output
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}  # Also set env var for immediate output
            )
            
            # Use queues to collect output lines and progress
            output_queue = asyncio.Queue()
            progress_queue = asyncio.Queue()
            output_lines = []
            error_lines = []
            total_players = None
            processed_players = 0
            
            async def read_stream(stream, is_error=False):
                nonlocal total_players, processed_players
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        await output_queue.put((line_str, is_error))
                        
                        # Parse progress from output
                        import re
                        
                        # Check for [PROGRESS] markers from script (new format)
                        if "[PROGRESS]" in line_str:
                            match = re.search(r'Processing player (\d+)/(\d+) \((\d+)%\)', line_str)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                progress_pct = int(match.group(3))
                                # Scale from 10% to 95% (first 10% is fetching, last 5% is saving)
                                scaled_progress = min(95, 10 + int((progress_pct / 100) * 85))
                                await progress_queue.put({
                                    'progress': scaled_progress,
                                    'message': f'Processing player {current}/{total} ({progress_pct}%)'
                                })
                        
                        # Check for "Processed X/Y players..." (existing format, every 25 players)
                        elif "Processed" in line_str and "players" in line_str:
                            match = re.search(r'Processed (\d+)/(\d+) players', line_str)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                progress_pct = int((current / total) * 100) if total > 0 else 0
                                # Scale from 10% to 95%
                                scaled_progress = min(95, 10 + int((progress_pct / 100) * 85))
                                
                                # Extract Created/Updated counts from the message
                                created_match = re.search(r'Created:\s*(\d+)', line_str)
                                updated_match = re.search(r'Updated:\s*(\d+)', line_str)
                                created = int(created_match.group(1)) if created_match else 0
                                updated = int(updated_match.group(1)) if updated_match else 0
                                
                                await progress_queue.put({
                                    'progress': scaled_progress,
                                    'message': f'Processed {current}/{total} players (Created: {created}, Updated: {updated})'
                                })
                        
                        # Look for "✅ Fetched X players"
                        elif "Fetched" in line_str and "players" in line_str:
                            match = re.search(r'Fetched (\d+) players', line_str)
                            if match:
                                total_players = int(match.group(1))
                                await progress_queue.put({
                                    'progress': 10,
                                    'message': f'Fetched {total_players} players from API',
                                    'total_players': total_players
                                })
                        
                        # Look for "Processing players..."
                        elif "Processing players..." in line_str:
                            await progress_queue.put({
                                'progress': 10,
                                'message': 'Processing players...'
                            })
                        
                        # Look for error messages (rate limiting, no data, etc.)
                        # But exclude informational messages about batching/delays (those are normal for ESPN scraping)
                        elif ("❌" in line_str or "No players data returned" in line_str) and "rate limit" in line_str.lower():
                            # Only flag as error if it's an actual error, not just informational text
                            # ESPN scraping messages like "(Waiting 30s between batches to avoid rate limits)" are NOT errors
                            if "waiting" in line_str.lower() and "retrying" in line_str.lower() and "⚠️" in line_str:
                                # This is a real NBA API rate limit warning
                                await progress_queue.put({
                                    'progress': 20,  # Show it's trying
                                    'message': 'NBA API rate limit detected - waiting and retrying... (this is normal)',
                                    'warning': True
                                })
                            elif "❌" in line_str or ("No players data returned" in line_str and "API" in line_str):
                                # This is a real error
                                await progress_queue.put({
                                    'progress': 50,  # Show partial progress even on error
                                    'message': line_str,
                                    'error': True
                                })
                        # Ignore informational messages about rate limits (normal for batching)
                        
                        # Look for final summary with Created/Updated/Skipped
                        elif ("✅ Updated:" in line_str or "✅ Created:" in line_str) and "players" in line_str:
                            created_match = re.search(r'Created:\s*(\d+)', line_str)
                            updated_match = re.search(r'Updated:\s*(\d+)', line_str)
                            skipped_match = re.search(r'Skipped:\s*(\d+)', line_str)
                            not_found_match = re.search(r'No recent games found for:\s*(\d+)', line_str)
                            
                            created = int(created_match.group(1)) if created_match else 0
                            updated = int(updated_match.group(1)) if updated_match else 0
                            skipped = int(skipped_match.group(1)) if skipped_match else 0
                            not_found = int(not_found_match.group(1)) if not_found_match else 0
                            
                            await progress_queue.put({
                                'progress': 95,
                                'message': f'Finalizing: Created {created}, Updated {updated}, Skipped {skipped}' + (f', Not found: {not_found}' if not_found > 0 else '')
                            })
                        
                        # Look for API fetch attempts
                        elif "Trying:" in line_str and ("current season" in line_str or "all players" in line_str):
                            await progress_queue.put({
                                'progress': 5,
                                'message': f'Fetching players from API: {line_str.replace("Trying:", "").strip()}'
                            })
                        
                        # Look for "SUMMARY" section (indicates completion)
                        elif "SUMMARY" in line_str or ("Total players in database" in line_str):
                            await progress_queue.put({
                                'progress': 98,
                                'message': 'Finalizing summary...'
                            })
            
            # Start reading both streams
            read_stdout = asyncio.create_task(read_stream(process.stdout, False))
            read_stderr = asyncio.create_task(read_stream(process.stderr, True))
            
            # Yield progress updates as they come in
            process_done = False
            while not process_done:
                try:
                    # Check for progress updates first
                    try:
                        progress_item = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                        yield f"data: {json.dumps(progress_item)}\n\n"
                    except asyncio.TimeoutError:
                        pass
                    
                    # Check for output lines
                    try:
                        item = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                        line_str, is_error = item
                        if is_error:
                            error_lines.append(line_str)
                        else:
                            output_lines.append(line_str)
                    except asyncio.TimeoutError:
                        # Check if process is done
                        if process.returncode is not None:
                            process_done = True
                            break
                        continue
                except Exception as e:
                    logger.error(f"Error in collect players loop: {e}")
                    continue
            
            # Wait for read tasks to complete
            await read_stdout
            await read_stderr
            
            # Wait for process to complete
            try:
                returncode = await asyncio.wait_for(process.wait(), timeout=600)  # 10 minute max
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                returncode = -1
                yield f"data: {json.dumps({'message': 'Player collection timed out', 'progress': 100, 'complete': True, 'success': False})}\n\n"
                return
            
            # Send completion message
            output_text = '\n'.join(output_lines)
            error_text = '\n'.join(error_lines)
            
            # Extract created/updated counts from output
            import re
            created_match = re.search(r"✅ Created: (\d+) players", output_text)
            updated_match = re.search(r"✅ Updated: (\d+) players", output_text)
            skipped_match = re.search(r"⚠️  Skipped: (\d+) players", output_text)
            created_count = int(created_match.group(1)) if created_match else 0
            updated_count = int(updated_match.group(1)) if updated_match else 0
            skipped_count = int(skipped_match.group(1)) if skipped_match else 0
            
            # Check if API failed (rate limit, no data, etc.)
            # But exclude informational messages - ESPN scraping messages like "(Waiting 30s between batches)" are NOT errors
            api_failed = (
                ("❌" in output_text and "No players data returned" in output_text and "API" in output_text) or
                ("Failed to fetch players" in output_text and "API" in output_text) or
                ("⚠️  API error" in output_text and "rate limit" in output_text.lower())
            ) and "ESPN scraping" not in output_text  # Don't flag ESPN scraping as API failure
            
            if returncode == 0 and not api_failed:
                yield f"data: {json.dumps({'message': f'Player collection completed successfully (Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count})', 'progress': 100, 'complete': True, 'success': True, 'output': output_text, 'created': created_count, 'updated': updated_count, 'skipped': skipped_count})}\n\n"
            elif api_failed:
                yield f"data: {json.dumps({'message': 'Player collection failed: NBA API rate limit or no data returned. Please try again in a few minutes.', 'progress': 100, 'complete': True, 'success': False, 'output': output_text, 'errors': error_text, 'api_failed': True})}\n\n"
            else:
                yield f"data: {json.dumps({'message': 'Player collection completed with errors', 'progress': 100, 'complete': True, 'success': False, 'output': output_text, 'errors': error_text})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Error collecting players: {str(e)}', 'complete': True})}\n\n"
    
    return StreamingResponse(
        collect_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/collect-injuries")
async def collect_injuries(
    sport: str = Query("NBA", description="Sport type (NBA or NFL)")
):
    """
    Collect injuries from ESPN and Rotowire and store in database with progress updates via SSE.
    
    Args:
        sport: Sport type (NBA or NFL). Default: NBA
    """
    async def collect_with_progress():
        # Get project root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        
        # Use the injury scraper directly (it's Python, not a script)
        from app.scrapers.injury_scraper import InjuryScraper
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            yield f"data: {json.dumps({'message': f'Starting {sport} injury collection...', 'progress': 0})}\n\n"
            
            scraper = InjuryScraper(db_session=db)
            
            yield f"data: {json.dumps({'message': 'Scraping ESPN injuries...', 'progress': 30})}\n\n"
            espn_injuries = scraper.scrape_espn()
            
            yield f"data: {json.dumps({'message': f'Found {len(espn_injuries)} injuries from ESPN. Scraping Rotowire...', 'progress': 60})}\n\n"
            rotowire_injuries = scraper.scrape_rotowire()
            
            yield f"data: {json.dumps({'message': f'Found {len(rotowire_injuries)} injuries from Rotowire. Processing...', 'progress': 80})}\n\n"
            
            # Process all injuries
            espn_count = 0
            rotowire_count = 0
            
            for injury_data in espn_injuries:
                try:
                    scraper._process_injury_data(injury_data)
                    espn_count += 1
                except Exception as e:
                    logger.warning(f"Error processing ESPN injury: {e}")
            
            for injury_data in rotowire_injuries:
                try:
                    scraper._process_injury_data(injury_data)
                    rotowire_count += 1
                except Exception as e:
                    logger.warning(f"Error processing Rotowire injury: {e}")
            
            db.commit()
            
            total = espn_count + rotowire_count
            result_data = {
                'message': f'{sport} injury collection completed successfully',
                'progress': 100,
                'complete': True,
                'success': True,
                'espn': espn_count,
                'rotowire': rotowire_count,
                'total': total
            }
            yield f"data: {json.dumps(result_data)}\n\n"
            
        except Exception as e:
            logger.error(f"Error collecting injuries: {e}")
            import traceback
            traceback.print_exc()
            error_data = {
                'error': f'Error collecting injuries: {str(e)}',
                'complete': True,
                'success': False
            }
            yield f"data: {json.dumps(error_data)}\n\n"
        finally:
            db.close()
    
    return StreamingResponse(
        collect_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/status")
async def get_update_status():
    """
    Get status of last update run.
    
    Returns information about when updates were last run.
    """
    # Get project root - go up from backend/app/api/updates.py to project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent.parent
    log_file = project_root / "update_log.txt"
    
    last_update = None
    if log_file.exists():
        try:
            # Read last few lines of log file
            with open(log_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    # Try to find last completion timestamp
                    for line in reversed(lines[-50:]):  # Check last 50 lines
                        if "Completed at:" in line or "✅" in line:
                            last_update = line.strip()
                            break
        except Exception:
            pass
    
    return {
        "last_update": last_update,
        "log_file_exists": log_file.exists(),
        "log_file_path": str(log_file)
    }
