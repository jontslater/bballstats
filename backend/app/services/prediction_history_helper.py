"""
Prediction History Helper

Helper functions to get historical game stats for predictions.
"""
from sqlalchemy import and_, desc, or_, func
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from datetime import date
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.season import Season
from app.models.lineup import Lineup
from app.models.player import Player
from app.services.lineup_service import LineupService
from app.config.sport_config import get_sport_config


def analyze_lineup_context(
    db: Session,
    player_id: int,
    current_game_id: int,
    sport: str = 'NBA'
) -> Dict:
    """
    Analyze lineup context to detect changes that might affect player performance.

    Args:
        db: Database session
        player_id: Player ID to analyze
        current_game_id: Current game ID for comparison
        sport: Sport type

    Returns:
        Dict with lineup analysis:
        {
            'lineup_impact': str,  # Description of lineup impact
            'missing_key_players': List[str],  # Names of key missing players
            'adjusted_performance': bool,  # Whether performance might be inflated
            'confidence_modifier': float  # Confidence adjustment (-0.1 to +0.1)
        }
    """
    lineup_service = LineupService(db)

    # Get current game info
    current_game = db.query(Game).filter(Game.game_id == current_game_id).first()
    if not current_game:
        return {
            'lineup_impact': 'No lineup data available',
            'missing_key_players': [],
            'adjusted_performance': False,
            'confidence_modifier': 0.0
        }

    # Get player's team by checking which team they're playing for in the current game
    # Check if player has stats in this game or recent games to determine their team
    player_in_home_team = db.query(PlayerGameStat).filter(
        and_(
            PlayerGameStat.game_id == current_game_id,
            PlayerGameStat.player_id == player_id,
            PlayerGameStat.team_id == current_game.home_team_id
        )
    ).first()

    player_in_away_team = db.query(PlayerGameStat).filter(
        and_(
            PlayerGameStat.game_id == current_game_id,
            PlayerGameStat.player_id == player_id,
            PlayerGameStat.team_id == current_game.away_team_id
        )
    ).first()

    if player_in_home_team:
        player_team_id = current_game.home_team_id
    elif player_in_away_team:
        player_team_id = current_game.away_team_id
    else:
        # Player not found in current game, use recent games
        recent_stat = db.query(PlayerGameStat).filter(
            PlayerGameStat.player_id == player_id
        ).order_by(desc(PlayerGameStat.game_id)).first()

        if recent_stat:
            player_team_id = recent_stat.team_id
        else:
            return {
                'lineup_impact': 'Cannot determine player team',
                'missing_key_players': [],
                'adjusted_performance': False,
                'confidence_modifier': 0.0
            }

    # Get recent games for this player on their team
    recent_games = db.query(PlayerGameStat, Game).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        and_(
            PlayerGameStat.player_id == player_id,
            PlayerGameStat.team_id == player_team_id,
            Game.game_status == 'finished'
        )
    ).order_by(desc(Game.game_date)).limit(5).all()

    if not recent_games:
        return {
            'lineup_impact': 'Insufficient historical data',
            'missing_key_players': [],
            'adjusted_performance': False,
            'confidence_modifier': 0.0
        }

    # Get the player's team ID from recent games
    player_team_id = recent_games[0][0].team_id

    # Get current lineup for the player's team
    current_lineup_confirmed = lineup_service.is_lineup_confirmed(current_game_id, player_team_id)
    if not current_lineup_confirmed:
        return {
            'lineup_impact': 'Current lineup not confirmed',
            'missing_key_players': [],
            'adjusted_performance': False,
            'confidence_modifier': -0.05  # Slight penalty for uncertainty
        }

    current_starters = lineup_service.get_team_starters(current_game_id, player_team_id)
    current_starter_ids = [p.player_id for p in current_starters]

    # Analyze recent historical games for lineup changes
    lineup_impacts = []
    missing_players_overall = set()
    total_games_analyzed = 0
    games_with_missing_starters = 0

    for player_stat, game in recent_games[:3]:  # Analyze last 3 games
        total_games_analyzed += 1

        # Skip if it's the current game
        if game.game_id == current_game_id:
            continue

        # Check if lineup was confirmed for this historical game
        historical_lineup_confirmed = lineup_service.is_lineup_confirmed(game.game_id, player_team_id)

        if historical_lineup_confirmed:
            historical_starters = lineup_service.get_team_starters(game.game_id, player_team_id)
            historical_starter_ids = [p.player_id for p in historical_starters]

            # Find missing starters from current lineup
            missing_from_current = [pid for pid in current_starter_ids if pid not in historical_starter_ids]

            if missing_from_current:
                games_with_missing_starters += 1
                # Get names of missing players
                missing_player_names = []
                for pid in missing_from_current:
                    player = db.query(Player).filter(Player.player_id == pid).first()
                    if player:
                        missing_player_names.append(player.name)
                        missing_players_overall.add(player.name)

                if missing_player_names:
                    lineup_impacts.append(f"Game vs {game.away_team_id if game.home_team_id == player_team_id else game.home_team_id}: Missing {', '.join(missing_player_names[:2])}")  # Limit to 2 names

    # Calculate impact assessment
    if games_with_missing_starters > 0:
        impact_percentage = games_with_missing_starters / total_games_analyzed

        if impact_percentage >= 0.5:  # 50%+ of recent games had missing starters
            lineup_impact = f"Recent games missing key starters {games_with_missing_starters}/{total_games_analyzed} times"
            confidence_modifier = -0.15  # Significant penalty
            adjusted_performance = True
        elif impact_percentage >= 0.33:  # 33%+ of recent games
            lineup_impact = f"Some recent games missing key starters ({games_with_missing_starters}/{total_games_analyzed})"
            confidence_modifier = -0.08  # Moderate penalty
            adjusted_performance = True
        else:
            lineup_impact = f"Isolated lineup changes in recent games"
            confidence_modifier = -0.03  # Minor penalty
            adjusted_performance = False
    else:
        lineup_impact = "Consistent lineup in recent games"
        confidence_modifier = 0.02  # Slight bonus for stability
        adjusted_performance = False

    return {
        'lineup_impact': lineup_impact,
        'missing_key_players': list(missing_players_overall)[:3],  # Limit to 3 names
        'adjusted_performance': adjusted_performance,
        'confidence_modifier': confidence_modifier
    }


def get_last_n_games_for_stat(
    db: Session,
    player_id: int,
    stat_type: str,
    sport: str = 'NBA',
    n_games: int = 3,
    exclude_game_id: Optional[int] = None,
    include_lineup_analysis: bool = False,
    current_game_id: Optional[int] = None
) -> Dict:
    """
    Get the last N games for a player for a specific stat type.

    Args:
        db: Database session
        player_id: Player ID
        stat_type: Stat type (e.g., 'points', 'rebounds', 'passing_yards')
        sport: Sport type ('NBA' or 'NFL')
        n_games: Number of games to retrieve (default: 3)
        exclude_game_id: Game ID to exclude from results (e.g., current game)
        analyze_lineup_context: Whether to analyze lineup changes that might affect performance
        current_game_id: Current game ID (required if analyze_lineup_context=True)

    Returns:
        Dict containing:
        {
            'games': List of dicts with game info and stat value,
            'lineup_context': Dict with lineup analysis (if analyze_lineup_context=True)
        }
        Games format:
        [
            {
                'game_date': date,
                'opponent': str (team abbreviation),
                'value': int/float,
                'game_id': int
            },
            ...
        ]
    """
    # Get sport config for stat column mapping
    sport_config = get_sport_config(sport)
    
    # Handle combo stats specially
    combo_stats = ['pts+ast+reb', 'points_assists', 'points_rebounds', 'rebounds_assists']
    if stat_type in combo_stats and sport == 'NBA':
        # These are calculated stats, not direct columns
        stat_column = None
    else:
        # Map stat_type to PlayerGameStat column
        stat_column_map = {
            'NBA': {
                'points': 'points',
                'rebounds': 'rebounds',
                'assists': 'assists',
                'three_pointers_made': 'three_pointers_made',
                'minutes': 'minutes_played',
                'steals': 'steals',
                'blocks': 'blocks',
                'turnovers': 'turnovers',
            },
            'NFL': {
                'passing_yards': 'passing_yards',
                'passing_tds': 'passing_tds',
                'rushing_yards': 'rushing_yards',
                'rushing_tds': 'rushing_tds',
                'receptions': 'receptions',
                'receiving_yards': 'receiving_yards',
                'receiving_tds': 'receiving_tds',
                'targets': 'targets',
                'interceptions': 'interceptions',
                'completions': 'completions',
                'attempts': 'pass_attempts',
                'snaps_played': 'snaps_played',
            }
        }

        if stat_type not in stat_column_map.get(sport, {}):
            return []  # Invalid stat type for this sport

        stat_column = stat_column_map[sport][stat_type]
    
    # Build query for last N games with this stat
    combo_stats_requirements = {
        'pts+ast+reb': ['points', 'assists', 'rebounds'],
        'points_assists': ['points', 'assists'],
        'points_rebounds': ['points', 'rebounds'],
        'rebounds_assists': ['rebounds', 'assists']
    }

    if stat_type in combo_stats_requirements:
        # For combo stats, all required components must exist
        requirements = combo_stats_requirements[stat_type]
        filters = [
            PlayerGameStat.sport == sport,
            PlayerGameStat.player_id == player_id,
            Game.game_status == 'finished'
        ]
        for req in requirements:
            column_name = {'points': 'points', 'assists': 'assists', 'rebounds': 'rebounds'}[req]
            filters.append(getattr(PlayerGameStat, column_name).isnot(None))

        query = db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(and_(*filters))
    else:
        # Regular stat
        query = db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.sport == sport,
                PlayerGameStat.player_id == player_id,
                Game.game_status == 'finished',
                getattr(PlayerGameStat, stat_column).isnot(None)  # Stat must exist
            )
        )
    
    # Exclude specific game if provided
    if exclude_game_id:
        query = query.filter(Game.game_id != exclude_game_id)
    
    # Filter by time played to ensure player actually played
    if sport == 'NBA':
        query = query.filter(PlayerGameStat.minutes_played > 0)
    elif sport == 'NFL':
        # For NFL, check if player has meaningful stats (not just DNP)
        # If snaps_played exists, use it; otherwise allow all
        query = query.filter(
            (PlayerGameStat.snaps_played > 0) | 
            (PlayerGameStat.snaps_played.is_(None))
        )
    
    # Order by game date descending and limit to N games
    # Use distinct on game_id to avoid duplicates (in case there are multiple stat records per game)
    from sqlalchemy import distinct
    results = query.order_by(desc(Game.game_date)).all()
    
    # Get opponent team info
    from app.models.team import Team
    
    # Deduplicate by game_id - keep only the first occurrence of each game
    seen_game_ids = set()
    last_games = []
    
    for stat, game in results:
        # Skip if we've already seen this game_id
        if game.game_id in seen_game_ids:
            continue
        
        seen_game_ids.add(game.game_id)
        
        # Get opponent team - determine from game teams and player's team
        player_team_id = stat.team_id
        if game.home_team_id == player_team_id:
            opponent_team_id = game.away_team_id
        elif game.away_team_id == player_team_id:
            opponent_team_id = game.home_team_id
        else:
            # Fallback to stat's opponent_team_id
            opponent_team_id = stat.opponent_team_id
        
        opponent_team = db.query(Team).filter(
            and_(
                Team.team_id == opponent_team_id,
                Team.sport == sport  # Ensure team sport matches
            )
        ).first()
        opponent_abbrev = opponent_team.abbreviation if opponent_team else f"Team {opponent_team_id}"
        
        # Get stat value
        if stat_type == 'pts+ast+reb':
            # Calculate PAR: points + assists + rebounds
            stat_value = (stat.points or 0) + (stat.assists or 0) + (stat.rebounds or 0)
        elif stat_type == 'points_assists':
            # Calculate points + assists
            stat_value = (stat.points or 0) + (stat.assists or 0)
        elif stat_type == 'points_rebounds':
            # Calculate points + rebounds
            stat_value = (stat.points or 0) + (stat.rebounds or 0)
        elif stat_type == 'rebounds_assists':
            # Calculate rebounds + assists
            stat_value = (stat.rebounds or 0) + (stat.assists or 0)
        else:
            stat_value = getattr(stat, stat_column)
        
        last_games.append({
            'game_date': game.game_date.isoformat() if game.game_date else None,
            'opponent': opponent_abbrev,
            'value': int(stat_value) if stat_value is not None else None,
            'game_id': game.game_id
        })
        
        # Stop once we have N unique games
        if len(last_games) >= n_games:
            break

    # Analyze lineup context if requested
    lineup_context = None
    if include_lineup_analysis and current_game_id:
        try:
            lineup_context = analyze_lineup_context(db, player_id, current_game_id, sport)
        except Exception as e:
            # If lineup analysis fails, continue without it
            print(f"Warning: Lineup analysis failed for player {player_id}: {e}")
            lineup_context = None

    return {
        'games': last_games,
        'lineup_context': lineup_context
    }


def get_last_n_games_for_combo_stat(
    db: Session,
    player_id: int,
    stat1: str,
    stat2: str,
    sport: str = 'NBA',
    n_games: int = 3,
    exclude_game_id: Optional[int] = None
) -> List[Dict]:
    """
    Get the last N games for a player for a combo stat type (e.g., Points + Assists).
    
    Args:
        db: Database session
        player_id: Player ID
        stat1: First stat type (e.g., 'points')
        stat2: Second stat type (e.g., 'assists')
        sport: Sport type ('NBA' or 'NFL')
        n_games: Number of games to retrieve (default: 3)
        exclude_game_id: Game ID to exclude from results (e.g., current game)
    
    Returns:
        List of dicts with game info and combined stat value:
        [
            {
                'game_date': date,
                'opponent': str (team abbreviation),
                'value': int/float (sum of stat1 + stat2),
                'game_id': int
            },
            ...
        ]
    """
    # Map stat_type to PlayerGameStat column
    stat_column_map = {
        'NBA': {
            'points': 'points',
            'rebounds': 'rebounds',
            'assists': 'assists',
        },
        'NFL': {
            'passing_yards': 'passing_yards',
            'rushing_yards': 'rushing_yards',
            'receptions': 'receptions',
            'receiving_yards': 'receiving_yards',
        }
    }
    
    if stat1 not in stat_column_map.get(sport, {}) or stat2 not in stat_column_map.get(sport, {}):
        return []  # Invalid stat types for this sport
    
    stat1_column = stat_column_map[sport][stat1]
    stat2_column = stat_column_map[sport][stat2]
    
    # Build query for last N games with both stats
    query = db.query(PlayerGameStat, Game).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        and_(
            PlayerGameStat.sport == sport,
            PlayerGameStat.player_id == player_id,
            Game.game_status == 'finished',
            getattr(PlayerGameStat, stat1_column).isnot(None),  # Both stats must exist
            getattr(PlayerGameStat, stat2_column).isnot(None)
        )
    )
    
    # Exclude specific game if provided
    if exclude_game_id:
        query = query.filter(Game.game_id != exclude_game_id)
    
    # Filter by time played to ensure player actually played
    if sport == 'NBA':
        query = query.filter(PlayerGameStat.minutes_played > 0)
    elif sport == 'NFL':
        query = query.filter(
            (PlayerGameStat.snaps_played > 0) | 
            (PlayerGameStat.snaps_played.is_(None))
        )
    
    # Order by game date descending (don't limit yet - we'll deduplicate first)
    results = query.order_by(desc(Game.game_date)).all()
    
    # Get opponent team info
    from app.models.team import Team
    
    # Deduplicate by game_id - keep only the first occurrence of each game
    seen_game_ids = set()
    last_games = []
    
    for stat, game in results:
        # Skip if we've already seen this game_id
        if game.game_id in seen_game_ids:
            continue
        
        seen_game_ids.add(game.game_id)
        
        # Get opponent team - determine from game teams and player's team
        player_team_id = stat.team_id
        if game.home_team_id == player_team_id:
            opponent_team_id = game.away_team_id
        elif game.away_team_id == player_team_id:
            opponent_team_id = game.home_team_id
        else:
            # Fallback to stat's opponent_team_id
            opponent_team_id = stat.opponent_team_id
        
        opponent_team = db.query(Team).filter(
            and_(
                Team.team_id == opponent_team_id,
                Team.sport == sport  # Ensure team sport matches
            )
        ).first()
        opponent_abbrev = opponent_team.abbreviation if opponent_team else f"Team {opponent_team_id}"
        
        # Get combined stat value (stat1 + stat2)
        stat1_value = getattr(stat, stat1_column) or 0
        stat2_value = getattr(stat, stat2_column) or 0
        combined_value = stat1_value + stat2_value
        
        last_games.append({
            'game_date': game.game_date.isoformat() if game.game_date else None,
            'opponent': opponent_abbrev,
            'value': int(combined_value) if combined_value is not None else None,
            'game_id': game.game_id
        })
        
        # Stop once we have N unique games
        if len(last_games) >= n_games:
            break
    
    return last_games


def get_last_n_games_for_milestone(
    db: Session,
    player_id: int,
    milestone_type: str,  # 'points_milestone', 'rebounds_milestone', 'assists_milestone', 'double_double', 'triple_double'
    stat_type: Optional[str] = None,  # For single stat milestones: 'points', 'rebounds', 'assists'
    threshold: Optional[int] = None,  # For single stat milestones: 15, 20, 25, etc.
    sport: str = 'NBA',
    n_games: int = 3,
    exclude_game_id: Optional[int] = None
) -> List[Dict]:
    """
    Get the last N games for a player for a milestone prop (e.g., "20+ Points", "Double-Double").
    
    Args:
        db: Database session
        player_id: Player ID
        milestone_type: Type of milestone ('points_milestone', 'rebounds_milestone', 'assists_milestone', 'double_double', 'triple_double')
        stat_type: Stat type for single stat milestones ('points', 'rebounds', 'assists')
        threshold: Threshold value for single stat milestones (15, 20, 25, etc.)
        sport: Sport type ('NBA' or 'NFL')
        n_games: Number of games to retrieve (default: 3)
        exclude_game_id: Game ID to exclude from results
    
    Returns:
        List of dicts with game info and whether milestone was achieved:
        [
            {
                'game_date': date,
                'opponent': str (team abbreviation),
                'value': int/float or str (stat value for single stat, display string for double/triple double),
                'achieved': bool (whether milestone was achieved),
                'game_id': int
            },
            ...
        ]
    """
    from app.models.team import Team
    
    if milestone_type in ['points_milestone', 'rebounds_milestone', 'assists_milestone']:
        # Single stat milestone (e.g., "20+ Points")
        if not stat_type or threshold is None:
            return []
        
        # Get last N games with this stat
        result = get_last_n_games_for_stat(
            db=db,
            player_id=player_id,
            stat_type=stat_type,
            sport=sport,
            n_games=n_games,
            exclude_game_id=exclude_game_id
        )
        
        # Extract games list from result dict
        last_games = result.get('games', []) if isinstance(result, dict) else result
        
        # Add 'achieved' field (whether stat >= threshold)
        for game in last_games:
            game['achieved'] = game.get('value', 0) >= threshold if game.get('value') is not None else False
        
        return last_games
    
    elif milestone_type in ['double_double', 'triple_double']:
        # Double-double or triple-double
        # Get last N games with all required stats
        query = db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.sport == sport,
                PlayerGameStat.player_id == player_id,
                Game.game_status == 'finished',
                PlayerGameStat.points.isnot(None),
                PlayerGameStat.rebounds.isnot(None),
                PlayerGameStat.assists.isnot(None) if milestone_type == 'triple_double' else True
            )
        )
        
        if exclude_game_id:
            query = query.filter(Game.game_id != exclude_game_id)
        
        if sport == 'NBA':
            query = query.filter(PlayerGameStat.minutes_played > 0)
        elif sport == 'NFL':
            query = query.filter(
                (PlayerGameStat.snaps_played > 0) | 
                (PlayerGameStat.snaps_played.is_(None))
            )
        
        results = query.order_by(desc(Game.game_date)).all()
        
        # Deduplicate by game_id - keep only the first occurrence of each game
        seen_game_ids = set()
        last_games = []
        
        for stat, game in results:
            # Skip if we've already seen this game_id
            if game.game_id in seen_game_ids:
                continue
            
            seen_game_ids.add(game.game_id)
            
            # Get opponent team - determine from game teams and player's team
            player_team_id = stat.team_id
            if game.home_team_id == player_team_id:
                opponent_team_id = game.away_team_id
            elif game.away_team_id == player_team_id:
                opponent_team_id = game.home_team_id
            else:
                # Fallback to stat's opponent_team_id
                opponent_team_id = stat.opponent_team_id
            
            opponent_team = db.query(Team).filter(
                and_(
                    Team.team_id == opponent_team_id,
                    Team.sport == sport  # Ensure team sport matches
                )
            ).first()
            opponent_abbrev = opponent_team.abbreviation if opponent_team else f"Team {opponent_team_id}"
            
            if milestone_type == 'double_double':
                # Check if achieved double-double (10+ in at least 2 categories)
                points = stat.points or 0
                rebounds = stat.rebounds or 0
                assists = stat.assists or 0
                achieved = sum([
                    points >= 10,
                    rebounds >= 10,
                    assists >= 10
                ]) >= 2
                
                # Value: show which categories (e.g., "PTS/REB" or "PTS/AST")
                categories = []
                if points >= 10:
                    categories.append('PTS')
                if rebounds >= 10:
                    categories.append('REB')
                if assists >= 10:
                    categories.append('AST')
                value_str = '/'.join(categories) if categories else 'None'
                
            else:  # triple_double
                # Check if achieved triple-double (10+ in all 3 categories)
                points = stat.points or 0
                rebounds = stat.rebounds or 0
                assists = stat.assists or 0
                achieved = points >= 10 and rebounds >= 10 and assists >= 10
                
                value_str = f"{points}P/{rebounds}R/{assists}A"
            
            last_games.append({
                'game_date': game.game_date.isoformat() if game.game_date else None,
                'opponent': opponent_abbrev,
                'value': value_str,
                'achieved': achieved,
                'game_id': game.game_id
            })
            
            # Stop once we have N unique games
            if len(last_games) >= n_games:
                break
        
        return last_games
    
    return []


def get_last_n_team_totals_for_stat(
    db: Session,
    team_id: int,
    stat_type: str,
    sport: str = 'NBA',
    n_games: int = 3,
    exclude_game_id: Optional[int] = None
) -> List[Dict]:
    """
    Get the last N team totals for a specific stat type.
    
    Args:
        db: Database session
        team_id: Team ID
        stat_type: Stat type ('points', 'rebounds', 'assists')
        sport: Sport type ('NBA' or 'NFL')
        n_games: Number of games to retrieve (default: 3)
        exclude_game_id: Game ID to exclude from results
    
    Returns:
        List of dicts with game info and team total:
        [
            {
                'game_date': date,
                'opponent': str (team abbreviation),
                'value': int/float (team total for that stat),
                'game_id': int
            },
            ...
        ]
    """
    # Map stat_type to PlayerGameStat column
    stat_column_map = {
        'NBA': {
            'points': 'points',
            'rebounds': 'rebounds',
            'assists': 'assists',
        },
        'NFL': {
            'points': 'points',  # NFL also has points
        }
    }
    
    if stat_type not in stat_column_map.get(sport, {}):
        return []
    
    stat_column = stat_column_map[sport][stat_type]
    
    # Get last N games for this team
    query = db.query(Game).filter(
        and_(
            Game.sport == sport,
            or_(
                Game.home_team_id == team_id,
                Game.away_team_id == team_id
            ),
            Game.game_status == 'finished'
        )
    )
    
    if exclude_game_id:
        query = query.filter(Game.game_id != exclude_game_id)
    
    games = query.order_by(desc(Game.game_date)).limit(n_games).all()
    
    from app.models.team import Team
    
    last_games = []
    for game in games:
        # Get all player stats for this team in this game
        # Use distinct on player_id to avoid double-counting if there are duplicates
        # Group by player_id and take the max stat value (in case of duplicates)
        team_stats_subquery = db.query(
            PlayerGameStat.player_id,
            func.max(getattr(PlayerGameStat, stat_column)).label('stat_value')
        ).filter(
            and_(
                PlayerGameStat.game_id == game.game_id,
                PlayerGameStat.team_id == team_id,
                PlayerGameStat.sport == sport,
                getattr(PlayerGameStat, stat_column).isnot(None)
            )
        ).group_by(PlayerGameStat.player_id).subquery()
        
        # Sum up team total (each player counted only once)
        team_total_result = db.query(func.sum(team_stats_subquery.c.stat_value)).scalar()
        team_total = team_total_result if team_total_result is not None else 0
        
        # Get opponent team
        opponent_team_id = game.away_team_id if game.home_team_id == team_id else game.home_team_id
        opponent_team = db.query(Team).filter(Team.team_id == opponent_team_id).first()
        opponent_abbrev = opponent_team.abbreviation if opponent_team else f"Team {opponent_team_id}"
        
        last_games.append({
            'game_date': game.game_date.isoformat() if game.game_date else None,
            'opponent': opponent_abbrev,
            'value': int(team_total) if team_total is not None else None,
            'game_id': game.game_id
        })
    
    return last_games

