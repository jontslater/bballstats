"""
Sport Configuration

Centralized configuration for different sports (NBA, NFL, etc.)
"""
from typing import Dict, List, Optional


SPORT_CONFIGS: Dict[str, Dict] = {
    'NBA': {
        'stat_types': ['points', 'rebounds', 'assists', 'three_pointers_made', 'minutes', 'pts+ast+reb'],
        'positions': ['PG', 'SG', 'SF', 'PF', 'C'],
        'time_unit': 'minutes_played',  # vs 'snaps_played' for NFL
        'positions_by_group': {
            'guard': ['PG', 'SG'],
            'forward': ['SF', 'PF'],
            'center': ['C']
        },
        'default_stat_type': 'points',
        'stat_type_labels': {
            'points': 'Points',
            'rebounds': 'Rebounds',
            'assists': 'Assists',
            'three_pointers_made': 'Three Pointers Made',
            'minutes': 'Minutes',
            'pts+ast+reb': 'Points + Assists + Rebounds'
        }
    },
    'NFL': {
        'stat_types': [
            'passing_yards', 'passing_tds', 'interceptions', 'completions', 'attempts',
            'rushing_yards', 'rushing_tds', 'rushing_attempts',
            'receptions', 'receiving_yards', 'receiving_tds', 'targets',
            'snaps_played', 'snap_percentage'
        ],
        'positions': ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'],
        'time_unit': 'snaps_played',
        'positions_by_group': {
            'qb': ['QB'],
            'rb': ['RB'],
            'receiver': ['WR', 'TE']
        },
        'default_stat_type': 'passing_yards',  # Position-dependent
        'stat_type_labels': {
            'passing_yards': 'Passing Yards',
            'passing_tds': 'Passing TDs',
            'interceptions': 'Interceptions',
            'completions': 'Completions',
            'attempts': 'Pass Attempts',
            'rushing_yards': 'Rushing Yards',
            'rushing_tds': 'Rushing TDs',
            'rushing_attempts': 'Rush Attempts',
            'receptions': 'Receptions',
            'receiving_yards': 'Receiving Yards',
            'receiving_tds': 'Receiving TDs',
            'targets': 'Targets',
            'snaps_played': 'Snaps Played',
            'snap_percentage': 'Snap %'
        },
        'position_default_stats': {
            'QB': ['passing_yards', 'passing_tds', 'rushing_yards'],
            'RB': ['rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards'],
            'WR': ['receptions', 'receiving_yards', 'receiving_tds', 'targets'],
            'TE': ['receptions', 'receiving_yards', 'receiving_tds', 'targets']
        }
    }
}


def get_sport_config(sport: str) -> Dict:
    """Get configuration for a specific sport."""
    if sport not in SPORT_CONFIGS:
        raise ValueError(f"Unknown sport: {sport}. Available: {list(SPORT_CONFIGS.keys())}")
    return SPORT_CONFIGS[sport]


def get_stat_types(sport: str) -> List[str]:
    """Get list of stat types for a sport."""
    config = get_sport_config(sport)
    return config['stat_types']


def get_positions(sport: str) -> List[str]:
    """Get list of positions for a sport."""
    config = get_sport_config(sport)
    return config['positions']


def get_default_stat_type(sport: str, position: Optional[str] = None) -> str:
    """Get default stat type for a sport and optionally position."""
    config = get_sport_config(sport)
    
    # For NFL, check position-specific defaults
    if sport == 'NFL' and position and 'position_default_stats' in config:
        if position in config['position_default_stats']:
            return config['position_default_stats'][position][0]
    
    return config['default_stat_type']


def get_stat_type_label(sport: str, stat_type: str) -> str:
    """Get human-readable label for a stat type."""
    config = get_sport_config(sport)
    labels = config.get('stat_type_labels', {})
    return labels.get(stat_type, stat_type.replace('_', ' ').title())


def is_valid_stat_type(sport: str, stat_type: str) -> bool:
    """Check if a stat type is valid for a sport."""
    return stat_type in get_stat_types(sport)


def is_valid_position(sport: str, position: str) -> bool:
    """Check if a position is valid for a sport."""
    return position in get_positions(sport)


def get_bettable_stat_types(sport: str) -> List[str]:
    """
    Get list of bettable stat types for a sport (excludes non-bettable stats like minutes/snaps).
    
    For NBA: points, rebounds, assists, three_pointers_made, pts+ast+reb
    For NFL: All stat types except snaps_played and snap_percentage
    """
    all_stats = get_stat_types(sport)
    
    if sport == 'NBA':
        # Only include bettable stats: points, rebounds, assists, three_pointers_made, pts+ast+reb
        bettable_stats = ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']
        return [s for s in all_stats if s in bettable_stats]
    elif sport == 'NFL':
        # Exclude snaps_played and snap_percentage (not bettable)
        excluded = ['snaps_played', 'snap_percentage']
        return [s for s in all_stats if s not in excluded]
    else:
        return all_stats

