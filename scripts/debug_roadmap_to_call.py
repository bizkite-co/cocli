# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
from cocli.core.constants import UNIT_SEP

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("debug_roadmap")

def debug_data() -> None:
    campaign = "roadmap"
    logger.info(f"--- Debugging Raw Data for: {campaign} ---")
    
    con = duckdb.connect(database=':memory:')
    
    # 1. Load Prospect Inbox (Raw Scraping Results)
    inbox_glob = "data/campaigns/roadmap/indexes/google_maps_prospects/inbox/*.usv"
    
    try:
        # Define the column names for all 56 fields to avoid DuckDB schema mismatch errors
        column_names = [f"col{i:02d}" for i in range(56)]
        columns_sql = ", ".join([f"'{name}': 'VARCHAR'" for name in column_names])
        
        # Use read_csv with explicit columns and ignore_errors=True to be resilient
        con.execute(f"""
            CREATE TABLE raw_prospects AS SELECT * FROM read_csv(
                '{inbox_glob}', 
                sep='{UNIT_SEP}', 
                header=False,
                columns={{{columns_sql}}},
                ignore_errors=True
            )
        """)
        
        # Map columns based on datapackage.json order (0-indexed)
        # col00: place_id, col02: name, col20: domain, col55: email, col03: phone, col24: reviews_count, col25: average_rating
        con.execute("""
            CREATE VIEW prospects AS SELECT 
                col00 as place_id,
                col02 as name,
                col20 as domain,
                col55 as email,
                col03 as phone,
                TRY_CAST(col25 AS DOUBLE) as average_rating,
                TRY_CAST(col24 AS BIGINT) as reviews_count,
                col11 as street_address,
                col12 as city,
                col15 as state,
                col13 as zip
            FROM raw_prospects
        """)
        
        res = con.execute("SELECT count(*) FROM prospects").fetchone()
        total = res[0] if res else 0
        logger.info(f"Total prospects in inbox: {total}")
        
        # Check contact info
        res = con.execute("""
            SELECT count(*) FROM prospects 
            WHERE (email IS NOT NULL AND email != '' AND email != 'null') 
               OR (phone IS NOT NULL AND phone != '' AND phone != 'null')
        """).fetchone()
        has_contact = res[0] if res else 0
        logger.info(f"Prospects with email or phone: {has_contact}")
        
        # Check high ratings
        res = con.execute("SELECT count(*) FROM prospects WHERE average_rating >= 4.5").fetchone()
        high_rating = res[0] if res else 0
        logger.info(f"Prospects with rating >= 4.5: {high_rating}")
        
        # Check high review count
        res = con.execute("SELECT count(*) FROM prospects WHERE reviews_count >= 20").fetchone()
        high_reviews = res[0] if res else 0
        logger.info(f"Prospects with reviews >= 20: {high_reviews}")
        
        # Combined filter used in op_compile_to_call
        res = con.execute("""
            SELECT count(*) FROM prospects 
            WHERE ((email IS NOT NULL AND email != '' AND email != 'null') OR (phone IS NOT NULL AND phone != '' AND phone != 'null'))
            AND average_rating >= 4.5
            AND reviews_count >= 20
        """).fetchone()
        combined = res[0] if res else 0
        logger.info(f"Combined (Original Filter): {combined}")
        
        if combined == 0:
            logger.info("\nSampling top 10 prospects by rating/reviews with contact info:")
            samples = con.execute("""
                SELECT name, average_rating, reviews_count, email, phone 
                FROM prospects 
                WHERE (email IS NOT NULL AND email != '' AND email != 'null') 
                   OR (phone IS NOT NULL AND phone != '' AND phone != 'null')
                ORDER BY average_rating DESC, reviews_count DESC
                LIMIT 10
            """).fetchall()
            for s in samples:
                logger.info(f"- {s[0]} | Rating: {s[1]} | Reviews: {s[2]} | Email: {s[3]} | Phone: {s[4]}")
        else:
            logger.info(f"\nExample leads ({combined} total):")
            examples = con.execute("""
                SELECT name, average_rating, reviews_count, email, phone 
                FROM prospects 
                WHERE ((email IS NOT NULL AND email != '' AND email != 'null') OR (phone IS NOT NULL AND phone != '' AND phone != 'null'))
                AND average_rating >= 4.5
                AND reviews_count >= 20
                LIMIT 5
            """).fetchall()
            for e in examples:
                logger.info(f"- {e[0]} | Rating: {e[1]} | Reviews: {e[2]} | Email: {e[3]} | Phone: {e[4]}")
                
    except Exception as e:
        logger.error(f"Error analyzing data: {e}")

if __name__ == "__main__":
    debug_data()
