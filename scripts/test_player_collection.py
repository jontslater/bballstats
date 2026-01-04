#!/usr/bin/env python3
"""
Test player collection - collects just a few players to verify the approach works.

This is useful for testing when the full collection is rate-limited.
"""
import sys
from pathlib import Path
import time

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.scrapers.nba_api_client import NBAAPIClient

print("🧪 Testing Player Collection...")
print("=" * 60)

client = NBAAPIClient(delay=1.5)  # Very conservative rate limiting

print("Waiting 10 seconds to avoid rate limits...")
time.sleep(10)

print("\nAttempting to fetch players...")
players_data = client.get_all_players(is_only_current_season=1, max_retries=2)

if players_data:
    print(f"\n✅ SUCCESS! Retrieved {len(players_data)} players")
    print("\nSample players:")
    for i, player in enumerate(players_data[:5], 1):
        name = player.get('DISPLAY_FIRST_LAST', player.get('PLAYER_NAME', 'N/A'))
        team = player.get('TEAM_ABBREVIATION', 'N/A')
        print(f"  {i}. {name} ({team})")
    print(f"\n✅ Player collection is working!")
    print(f"   You can now run: python scripts/collect_players.py")
else:
    print("\n❌ Failed to fetch players")
    print("\n💡 This is likely due to NBA API rate limiting.")
    print("   Solutions:")
    print("   1. Wait 10-15 minutes and try again")
    print("   2. Run the script at a different time (off-peak hours)")
    print("   3. The NBA API has strict rate limits - this is normal")
    print("\n   The script will work once rate limits reset.")


