"""
Historical Tracking Service

Tracks and analyzes performance of suggested bets and parlays over time.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func, not_
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime, timedelta
from app.models.prediction import HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg
from app.models.player import Player
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
import logging

logger = logging.getLogger(__name__)


class HistoricalTrackingService:
    """Service for tracking historical betting performance."""

    def __init__(self, db: Session):
        self.db = db

    def save_suggested_bets(self, bets: List[Dict], date_filter: date) -> int:
        """
        Save suggested bets to historical tracking.

        Args:
            bets: List of suggested bet dictionaries
            date_filter: Date these bets were generated for

        Returns:
            Number of bets saved
        """
        saved_count = 0

        for bet in bets:
            try:
                # Check if this bet already exists (avoid duplicates)
                existing = self.db.query(HistoricalSuggestedBet).filter(
                    and_(
                        HistoricalSuggestedBet.player_id == bet['player_id'],
                        HistoricalSuggestedBet.game_id == bet['game_id'],
                        HistoricalSuggestedBet.stat_type == bet['stat_type'],
                        HistoricalSuggestedBet.generated_at >= date_filter,  # Same day
                        HistoricalSuggestedBet.generated_at < date_filter + timedelta(days=1)
                    )
                ).first()

                if existing:
                    logger.info(f"Suggested bet already exists for {bet['player_name']} on {date_filter}")
                    continue

                historical_bet = HistoricalSuggestedBet(
                    player_id=bet['player_id'],
                    player_name=bet['player_name'],
                    player_team=bet.get('player_team', ''),
                    game_id=bet['game_id'],
                    game_date=bet.get('game_date', date_filter),
                    stat_type=bet['stat_type'],
                    bet_type=bet['bet_type'],
                    line=bet['line'],
                    probability=bet['probability'],
                    confidence_level=bet['confidence_level'],
                    volatility_level=bet['volatility_level'],
                    reasoning=bet.get('reasoning'),
                    hit=None  # Will be updated later when results are available
                )

                self.db.add(historical_bet)
                saved_count += 1

            except Exception as e:
                logger.error(f"Error saving suggested bet for {bet.get('player_name', 'Unknown')}: {e}")
                continue

        self.db.commit()
        logger.info(f"Saved {saved_count} suggested bets to historical tracking")
        return saved_count

    def save_parlay(self, parlay_data: Dict, legs: List[Dict], parlay_type: str) -> int:
        """
        Save a parlay to historical tracking.

        Args:
            parlay_data: Parlay information (odds, probability, etc.)
            legs: List of parlay legs
            parlay_type: Type of parlay ('suggested', 'safe_long', 'builder', 'hot_matchup')

        Returns:
            ID of saved parlay
        """
        try:
            # Create the parlay record
            parlay = HistoricalParlay(
                parlay_type=parlay_type,
                num_legs=len(legs),
                combined_probability=parlay_data['combined_probability'],
                odds_display=parlay_data['odds_display'],
                all_legs_hit=None,  # Will be updated later
                legs_hit_count=None
            )

            self.db.add(parlay)
            self.db.flush()  # Get the parlay ID

            # Create leg records
            for leg in legs:
                parlay_leg = HistoricalParlayLeg(
                    parlay_id=parlay.id,
                    player_id=leg['player_id'],
                    player_name=leg['player_name'],
                    player_team=leg['player_team'],
                    game_id=leg['game_id'],
                    stat_type=leg['stat_type'],
                    bet_type=leg['bet_type'],
                    line=leg['line'],
                    probability=leg['probability'],
                    hit=None  # Will be updated later
                )
                self.db.add(parlay_leg)

            self.db.commit()
            logger.info(f"Saved {parlay_type} parlay with {len(legs)} legs (ID: {parlay.id})")
            return parlay.id

        except Exception as e:
            logger.error(f"Error saving parlay: {e}")
            self.db.rollback()
            return 0

    def update_results(self, game_date: date) -> Dict[str, int]:
        """
        Update results for bets and parlays from a specific game date.

        Args:
            game_date: Date to update results for

        Returns:
            Dictionary with counts of updated items
        """
        updated_bets = 0
        updated_parlays = 0

        try:
            # Get all games from this date
            games = self.db.query(Game).filter(Game.game_date == game_date).all()
            game_ids = [g.game_id for g in games]

            if not games:
                logger.info(f"No games found for {game_date}")
                return {'bets_updated': 0, 'parlays_updated': 0}

            # Update individual suggested bets
            suggested_bets = self.db.query(HistoricalSuggestedBet).filter(
                HistoricalSuggestedBet.game_id.in_(game_ids)
            ).all()

            for bet in suggested_bets:
                if bet.hit is not None:  # Already resolved
                    continue

                # Get actual result from player game stats
                actual_stat = self._get_actual_stat(bet.player_id, bet.game_id, bet.stat_type)

                if actual_stat is not None:
                    # Determine if bet hit
                    if bet.line > 0:  # Over bet
                        bet.hit = actual_stat > bet.line
                    else:  # Under bet (though we store positive lines)
                        bet.hit = actual_stat < abs(bet.line)

                    bet.actual_result = actual_stat
                    updated_bets += 1
                    logger.info(f"Updated bet result: {bet.player_name} {bet.stat_type} {bet.line} - {'HIT' if bet.hit else 'MISS'} ({actual_stat})")

            # Update parlay results
            parlays = self.db.query(HistoricalParlay).filter(
                HistoricalParlay.generated_at >= game_date,
                HistoricalParlay.generated_at < game_date + timedelta(days=1)
            ).all()

            for parlay in parlays:
                if parlay.all_legs_hit is not None:  # Already resolved
                    continue

                # Check if all legs have results
                legs = self.db.query(HistoricalParlayLeg).filter(
                    HistoricalParlayLeg.parlay_id == parlay.id
                ).all()

                all_resolved = True
                legs_hit = 0

                for leg in legs:
                    if leg.hit is None:
                        # Try to update this leg's result
                        actual_stat = self._get_actual_stat(leg.player_id, leg.game_id, leg.stat_type)
                        if actual_stat is not None:
                            if leg.line > 0:  # Over bet
                                leg.hit = actual_stat > leg.line
                            else:  # Under bet
                                leg.hit = actual_stat < abs(leg.line)
                            leg.actual_result = actual_stat
                        else:
                            all_resolved = False
                            break

                    if leg.hit:
                        legs_hit += 1

                if all_resolved:
                    parlay.all_legs_hit = legs_hit == len(legs)
                    parlay.legs_hit_count = legs_hit
                    parlay.resolved_at = datetime.now()
                    updated_parlays += 1
                    logger.info(f"Updated parlay result: {parlay.parlay_type} {parlay.num_legs} legs - {'WON' if parlay.all_legs_hit else 'LOST'} ({legs_hit}/{len(legs)} legs)")

            self.db.commit()

        except Exception as e:
            logger.error(f"Error updating results for {game_date}: {e}")
            self.db.rollback()

        return {'bets_updated': updated_bets, 'parlays_updated': updated_parlays}

    def _get_actual_stat(self, player_id: int, game_id: int, stat_type: str) -> Optional[float]:
        """
        Get actual stat value from player game stats.

        Args:
            player_id: Player ID
            game_id: Game ID
            stat_type: Type of stat (points, rebounds, etc.)

        Returns:
            Actual stat value or None if not found
        """
        try:
            stat_record = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    PlayerGameStat.game_id == game_id
                )
            ).first()

            if not stat_record:
                return None

            # Map stat_type to database column
            stat_mapping = {
                'points': stat_record.points,
                'rebounds': stat_record.rebounds,
                'assists': stat_record.assists,
                'steals': stat_record.steals,
                'blocks': stat_record.blocks,
                'turnovers': stat_record.turnovers,
                'minutes': stat_record.minutes_played,
                'pts+ast+reb': (stat_record.points or 0) + (stat_record.assists or 0) + (stat_record.rebounds or 0),
                'three_pointers_made': stat_record.three_pointers_made
            }

            return stat_mapping.get(stat_type)

        except Exception as e:
            logger.error(f"Error getting actual stat for player {player_id}, game {game_id}, stat {stat_type}: {e}")
            return None

    def get_historical_performance(self, days_back: int = 30) -> Dict:
        """
        Get overall historical performance statistics.

        Args:
            days_back: How many days back to analyze

        Returns:
            Dictionary with performance statistics
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Suggested bets performance - use subquery approach to avoid issues with func.sum on boolean
        total_bets = self.db.query(func.count(HistoricalSuggestedBet.id)).filter(
            and_(
                HistoricalSuggestedBet.generated_at >= cutoff_date,
                HistoricalSuggestedBet.hit.is_not(None)
            )
        ).scalar()

        hits = self.db.query(func.count(HistoricalSuggestedBet.id)).filter(
            and_(
                HistoricalSuggestedBet.generated_at >= cutoff_date,
                HistoricalSuggestedBet.hit == True
            )
        ).scalar()

        # Parlay performance - use subquery approach
        total_parlays = self.db.query(func.count(HistoricalParlay.id)).filter(
            and_(
                HistoricalParlay.generated_at >= cutoff_date,
                HistoricalParlay.all_legs_hit.is_not(None)
            )
        ).scalar()

        wins = self.db.query(func.count(HistoricalParlay.id)).filter(
            and_(
                HistoricalParlay.generated_at >= cutoff_date,
                HistoricalParlay.all_legs_hit == True
            )
        ).scalar()

        bet_stats = type('obj', (object,), {'total': total_bets, 'hits': hits})()
        parlay_stats = type('obj', (object,), {'total': total_parlays, 'wins': wins})()

        return {
            'suggested_bets': {
                'total': bet_stats.total or 0,
                'hits': bet_stats.hits or 0,
                'hit_rate': (bet_stats.hits or 0) / (bet_stats.total or 1) * 100
            },
            'parlays': {
                'total': parlay_stats.total or 0,
                'wins': parlay_stats.wins or 0,
                'win_rate': (parlay_stats.wins or 0) / (parlay_stats.total or 1) * 100
            },
            'analyzed_days': days_back
        }

    def get_recent_results(self, limit: int = 50) -> Dict:
        """
        Get recent betting results for display.

        Args:
            limit: Maximum number of results to return

        Returns:
            Dictionary with recent results
        """
        # Get recent suggested bets (show all, not just resolved ones)
        recent_bets = self.db.query(HistoricalSuggestedBet).order_by(
            HistoricalSuggestedBet.generated_at.desc()
        ).limit(limit).all()

        # Get recent parlays (show all, not just resolved ones)
        recent_parlays = self.db.query(HistoricalParlay).order_by(
            HistoricalParlay.generated_at.desc()
        ).limit(limit // 2).all()

        # Get legs for parlays
        parlay_legs = {}
        for parlay in recent_parlays:
            legs = self.db.query(HistoricalParlayLeg).filter(
                HistoricalParlayLeg.parlay_id == parlay.id
            ).all()
            parlay_legs[parlay.id] = legs

        return {
            'suggested_bets': [self._format_bet_result(bet) for bet in recent_bets],
            'parlays': [self._format_parlay_result(parlay, parlay_legs[parlay.id]) for parlay in recent_parlays]
        }

    def _format_bet_result(self, bet: HistoricalSuggestedBet) -> Dict:
        """Format a bet result for API response."""
        return {
            'id': bet.id,
            'player_name': bet.player_name,
            'player_team': bet.player_team,
            'stat_type': bet.stat_type,
            'bet_type': bet.bet_type,
            'line': bet.line,
            'probability': bet.probability,
            'hit': bet.hit,
            'actual_result': bet.actual_result,
            'game_date': bet.game_date.isoformat() if bet.game_date else None,
            'generated_at': bet.generated_at.isoformat() if bet.generated_at else None
        }

    def _format_parlay_result(self, parlay: HistoricalParlay, legs: List[HistoricalParlayLeg]) -> Dict:
        """Format a parlay result for API response."""
        return {
            'id': parlay.id,
            'parlay_type': parlay.parlay_type,
            'num_legs': parlay.num_legs,
            'combined_probability': parlay.combined_probability,
            'odds_display': parlay.odds_display,
            'all_legs_hit': parlay.all_legs_hit,
            'legs_hit_count': parlay.legs_hit_count,
            'generated_at': parlay.generated_at.isoformat() if parlay.generated_at else None,
            'legs': [{
                'player_name': leg.player_name,
                'player_team': leg.player_team,
                'stat_type': leg.stat_type,
                'bet_type': leg.bet_type,
                'line': leg.line,
                'probability': leg.probability,
                'hit': leg.hit,
                'actual_result': leg.actual_result
            } for leg in legs]
        }