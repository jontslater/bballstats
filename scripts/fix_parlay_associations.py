"""
Fix parlay associations - Ensure plays are properly associated with parlays
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.database import SessionLocal
from app.models.parlay import parlay_plays, Parlay
from app.models.user_play import UserPlay
from sqlalchemy import select, insert

def fix_parlay_associations():
    """Ensure all parlay plays are properly associated in parlay_plays table."""
    db = SessionLocal()
    try:
        parlays = db.query(Parlay).all()
        print(f"Found {len(parlays)} parlays")
        
        fixed_count = 0
        for parlay in parlays:
            print(f"\nParlay {parlay.parlay_id}: {len(parlay.plays)} plays")
            
            # Get current associations from table
            result = db.execute(
                select(parlay_plays).where(parlay_plays.c.parlay_id == parlay.parlay_id)
            ).fetchall()
            current_play_ids = {row[1] for row in result}
            
            # Get expected play IDs from relationship
            expected_play_ids = {p.play_id for p in parlay.plays}
            
            print(f"  Current in table: {current_play_ids}")
            print(f"  Expected from relationship: {expected_play_ids}")
            
            if current_play_ids != expected_play_ids:
                print(f"  ⚠️  Mismatch detected! Fixing...")
                
                # Remove old associations
                db.execute(
                    parlay_plays.delete().where(parlay_plays.c.parlay_id == parlay.parlay_id)
                )
                
                # Add correct associations
                for play in parlay.plays:
                    db.execute(
                        insert(parlay_plays).values(
                            parlay_id=parlay.parlay_id,
                            play_id=play.play_id
                        )
                    )
                
                fixed_count += 1
                print(f"  ✅ Fixed parlay {parlay.parlay_id}")
            else:
                print(f"  ✅ Already correct")
        
        if fixed_count > 0:
            db.commit()
            print(f"\n✅ Fixed {fixed_count} parlay(s)")
        else:
            print(f"\n✅ All parlays are correctly associated")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    fix_parlay_associations()





