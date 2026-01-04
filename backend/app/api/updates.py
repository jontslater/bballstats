"""
Update Scripts API endpoints.

Allows running update scripts from the UI.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
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


@router.post("/run-full-update")
async def run_full_update():
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
        script_path = project_root / "scripts" / "update_all.py"
        
        if not script_path.exists():
            yield f"data: {json.dumps({'error': f'Update script not found at {script_path}', 'complete': True})}\n\n"
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
