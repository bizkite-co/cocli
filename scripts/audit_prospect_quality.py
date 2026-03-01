# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("prospect_audit")

def audit_quality(campaign_name: str) -> None:
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    checkpoint_path = idx_paths.checkpoint
    datapackage_path = idx_paths.path / "datapackage.json"

    if not checkpoint_path.exists() or not datapackage_path.exists():
        logger.error("Checkpoint or Datapackage missing.")
        return

    logger.info(f"Auditing Gold Index: {checkpoint_path}")
    con = duckdb.connect(database=':memory:')
    
    try:
        # Load using FDPE-compliant utility
        load_usv_to_duckdb(con, "prospects", checkpoint_path, datapackage_path)
        
        # FDPE Standardization (from duckdb_utils.py):
        # phone -> phone_number
        # company_slug -> slug
        # keyword -> tags
        
        query = """
            SELECT 
                COUNT(*) as total,
                COUNT(phone_number) FILTER (WHERE phone_number IS NOT NULL AND phone_number != '') as with_phone,
                COUNT(email) FILTER (WHERE email IS NOT NULL AND email != '') as with_email,
                COUNT(average_rating) FILTER (WHERE average_rating IS NOT NULL AND average_rating > 0) as with_rating,
                COUNT(reviews_count) FILTER (WHERE reviews_count IS NOT NULL AND reviews_count > 0) as with_reviews,
                COUNT(city) FILTER (WHERE city IS NOT NULL AND city != '') as with_city,
                COUNT(*) FILTER (
                    (phone_number IS NOT NULL AND phone_number != '') AND 
                    (city IS NOT NULL AND city != '') AND
                    (average_rating IS NOT NULL AND average_rating > 0)
                ) as ready_for_call
            FROM prospects
        """
        
        res = con.execute(query).fetchone()
        if not res:
            return

        total, phone, email, rating, reviews, city, ready = res
        
        print("\n--- GOLD PROSPECT QUALITY AUDIT ---")
        print(f"Total Unique Prospects: {total}")
        print("-" * 35)
        print(f"With Phone:            {phone} ({phone*100/total:.1f}%)")
        print(f"With Email:            {email} ({email*100/total:.1f}%)")
        print(f"With Rating:           {rating} ({rating*100/total:.1f}%)")
        print(f"With Review Count:     {reviews} ({reviews*100/total:.1f}%)")
        print(f"With City:             {city} ({city*100/total:.1f}%)")
        print("-" * 35)
        print(f"READY FOR 'TO CALL':   {ready} ({ready*100/total:.1f}%)")
        print("(Ready = Phone + City + Rating)")
        print("-" * 35)

    except Exception as e:
        logger.error(f"Audit failed: {e}")

if __name__ == "__main__":
    audit_quality("roadmap")
