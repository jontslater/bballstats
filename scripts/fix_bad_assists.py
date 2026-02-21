#!/usr/bin/env python3
"""
Fix Bad Assists Data

Identifies and fixes incorrect assists data in the database.
Looks for suspicious patterns like:
- High assists (>15) with low points (<10)
- Assists that are way higher than player's typical performance
- Assists that don't match game context

Usage:
    python scripts/fix_bad_assists.py [--game-id GAME_ID] [--player-name NAME] [--auto-fix] [--re-scrape]
"""
import sys
from pathlib import Path
from datetime import date, timedelta
from typing import List, Dict, Optional

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from app.database import SessionLocal
from app.models import Player, PlayerGameStat, Game, Team
from app.scrapers.box_score_scraper import BoxScoreScraper


def find_suspicious_assists(
    db: Session,
    game_id: Optional[int] = None,
    player_name: Optional[str] = None,
    days_back: int = 30
) -> List[Dict]:
    """
    Find player game stats with suspicious assists values.
    
    Returns:
        List of dicts with suspicious stat records
    """
    print("🔍 Searching for suspicious assists data...")
    print("=" * 60)
    
    query = db.query(PlayerGameStat, Player, Game).join(
        Player, PlayerGameStat.player_id == Player.player_id
    ).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        and_(
            PlayerGameStat.assists.isnot(None),
            PlayerGameStat.assists > 0,
            Game.game_status == 'finished',
            PlayerGameStat.minutes_played > 0
        )
    )
    
    if game_id:
        query = query.filter(PlayerGameStat.game_id == game_id)
    
    if player_name:
        query = query.filter(Player.name.ilike(f'%{player_name}%'))
    
    if days_back:
        cutoff_date = date.today() - timedelta(days=days_back)
        query = query.filter(Game.game_date >= cutoff_date)
    
    results = query.order_by(desc(Game.game_date)).all()
    
    suspicious = []
    
    for stat, player, game in results:
        assists = stat.assists or 0
        points = stat.points or 0
        rebounds = stat.rebounds or 0
        minutes = stat.minutes_played or 0
        
        # Flag suspicious patterns
        is_suspicious = False
        reason = []
        
        # Pattern 1: High assists but low points (likely column misalignment)
        if assists > 15 and points < 10:
            is_suspicious = True
            reason.append(f"High assists ({assists}) but low points ({points})")
        
        # Pattern 2: Assists way higher than typical for this player
        # Get player's average assists
        avg_assists = db.query(func.avg(PlayerGameStat.assists)).filter(
            and_(
                PlayerGameStat.player_id == player.player_id,
                PlayerGameStat.game_id != game.game_id,
                PlayerGameStat.minutes_played > 0,
                PlayerGameStat.assists.isnot(None)
            )
        ).scalar() or 0
        
        if avg_assists > 0 and assists > avg_assists * 3:
            is_suspicious = True
            reason.append(f"Assists ({assists}) is >3x player's average ({avg_assists:.1f})")
        
        # Pattern 3: Assists per minute is unrealistic (>1 assist per minute)
        if minutes > 0:
            assists_per_min = assists / minutes
            if assists_per_min > 1.0:
                is_suspicious = True
                reason.append(f"Unrealistic assists/min ({assists_per_min:.2f})")
        
        # Pattern 4: Assists >20 (very rare, double-check)
        if assists > 20:
            is_suspicious = True
            reason.append(f"Very high assists ({assists}) - verify")
        
        if is_suspicious:
            team = db.query(Team).filter(Team.team_id == stat.team_id).first()
            opponent = db.query(Team).filter(Team.team_id == stat.opponent_team_id).first()
            
            suspicious.append({
                'stat_id': stat.stat_id,
                'player_id': player.player_id,
                'player_name': player.name,
                'game_id': game.game_id,
                'game_date': game.game_date,
                'team': team.abbreviation if team else 'UNK',
                'opponent': opponent.abbreviation if opponent else 'UNK',
                'minutes': minutes,
                'points': points,
                'rebounds': rebounds,
                'assists': assists,
                'avg_assists': avg_assists,
                'reason': ' | '.join(reason)
            })
    
    return suspicious


def display_suspicious_stats(suspicious: List[Dict]):
    """Display suspicious stats in a readable format."""
    if not suspicious:
        print("✅ No suspicious assists data found!")
        return
    
    print(f"\n⚠️  Found {len(suspicious)} suspicious assists records:\n")
    
    for idx, stat in enumerate(suspicious, 1):
        print(f"{idx}. {stat['player_name']} ({stat['team']})")
        print(f"   Game: {stat['game_date']} vs {stat['opponent']}")
        print(f"   Stats: {stat['points']} PTS, {stat['rebounds']} REB, {stat['assists']} AST ({stat['minutes']} MIN)")
        print(f"   Player avg assists: {stat['avg_assists']:.1f}")
        print(f"   Reason: {stat['reason']}")
        print(f"   Stat ID: {stat['stat_id']}, Game ID: {stat['game_id']}")
        print()


def fix_stat(db: Session, stat_id: int, new_assists: int):
    """Fix a specific stat record."""
    stat = db.query(PlayerGameStat).filter(PlayerGameStat.stat_id == stat_id).first()
    if not stat:
        print(f"❌ Stat ID {stat_id} not found")
        return False
    
    old_assists = stat.assists
    stat.assists = new_assists
    db.commit()
    
    print(f"✅ Updated stat ID {stat_id}: {old_assists} assists -> {new_assists} assists")
    return True


def re_scrape_game(db: Session, game_id: int):
    """Re-scrape a game to get correct stats."""
    print(f"\n🔄 Re-scraping game {game_id}...")
    
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        print(f"❌ Game {game_id} not found")
        return False
    
    home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
    away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
    
    if not home_team or not away_team:
        print(f"❌ Could not find teams for game {game_id}")
        return False
    
    # Delete existing player stats for this game
    deleted = db.query(PlayerGameStat).filter(PlayerGameStat.game_id == game_id).delete()
    print(f"   Deleted {deleted} existing stat records")
    db.commit()
    
    # Re-scrape using box score scraper
    scraper = BoxScoreScraper(db)
    try:
        stats = scraper.scrape_box_score(game, home_team, away_team)
        
        if stats and stats.get('player_stats'):
            print(f"   ✅ Re-scraped {len(stats['player_stats'])} player stats")
            
            # Save new stats
            for player_stat_data in stats['player_stats']:
                player_stat = PlayerGameStat(
                    player_id=player_stat_data['player_id'],
                    game_id=game_id,
                    team_id=player_stat_data['team_id'],
                    opponent_team_id=away_team.team_id if player_stat_data['team_id'] == home_team.team_id else home_team.team_id,
                    minutes_played=player_stat_data['minutes_played'],
                    points=player_stat_data['points'],
                    rebounds=player_stat_data['rebounds'],
                    assists=player_stat_data['assists'],
                    is_home=(player_stat_data['team_id'] == home_team.team_id)
                )
                db.add(player_stat)
            
            db.commit()
            print(f"   ✅ Saved new stats to database")
            return True
        else:
            print(f"   ⚠️  No stats found when re-scraping")
            return False
            
    except Exception as e:
        print(f"   ❌ Error re-scraping: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False


def interactive_fix(db: Session, suspicious: List[Dict]):
    """Interactive mode to fix suspicious stats."""
    if not suspicious:
        return
    
    print("\n" + "=" * 60)
    print("INTERACTIVE FIX MODE")
    print("=" * 60)
    
    for stat in suspicious:
        print(f"\n📊 {stat['player_name']} - Game {stat['game_id']} ({stat['game_date']})")
        print(f"   Current: {stat['points']} PTS, {stat['rebounds']} REB, {stat['assists']} AST")
        print(f"   Reason: {stat['reason']}")
        
        while True:
            action = input("\n   Action: [f]ix manually, [r]e-scrape game, [s]kip, [q]uit: ").strip().lower()
            
            if action == 'q':
                return
            
            elif action == 's':
                break
            
            elif action == 'f':
                try:
                    new_assists = int(input(f"   Enter correct assists (current: {stat['assists']}): "))
                    if fix_stat(db, stat['stat_id'], new_assists):
                        break
                except ValueError:
                    print("   ❌ Invalid input")
                except KeyboardInterrupt:
                    print("\n   Cancelled")
                    return
            
            elif action == 'r':
                if re_scrape_game(db, stat['game_id']):
                    print("   ✅ Game re-scraped. Please verify the data.")
                    break
                else:
                    print("   ❌ Failed to re-scrape")
            
            else:
                print("   ❌ Invalid action")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Find and fix bad assists data')
    parser.add_argument('--game-id', type=int, help='Filter by specific game ID')
    parser.add_argument('--player-name', type=str, help='Filter by player name (e.g., Kuzma)')
    parser.add_argument('--days-back', type=int, default=30, help='Look back N days (default: 30)')
    parser.add_argument('--auto-fix', action='store_true', help='Auto-fix obvious errors (high assists + low points -> set assists to 0)')
    parser.add_argument('--re-scrape', type=int, help='Re-scrape a specific game ID')
    parser.add_argument('--list-only', action='store_true', help='Only list suspicious stats, don\'t fix')
    
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        if args.re_scrape:
            # Re-scrape specific game
            re_scrape_game(db, args.re_scrape)
            return
        
        # Find suspicious stats
        suspicious = find_suspicious_assists(
            db,
            game_id=args.game_id,
            player_name=args.player_name,
            days_back=args.days_back
        )
        
        if not suspicious:
            print("✅ No suspicious assists data found!")
            return
        
        # Display results
        display_suspicious_stats(suspicious)
        
        if args.list_only:
            return
        
        # Auto-fix mode
        if args.auto_fix:
            print("\n🔧 AUTO-FIX MODE")
            print("=" * 60)
            fixed_count = 0
            
            for stat in suspicious:
                # Only auto-fix obvious errors: high assists + low points
                if stat['assists'] > 15 and stat['points'] < 10:
                    print(f"   Auto-fixing {stat['player_name']}: {stat['assists']} assists -> 0 (low points: {stat['points']})")
                    if fix_stat(db, stat['stat_id'], 0):
                        fixed_count += 1
            
            print(f"\n✅ Auto-fixed {fixed_count} records")
        
        else:
            # Interactive mode
            interactive_fix(db, suspicious)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
