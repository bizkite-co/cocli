# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import duckdb
import logging
from typing import List, Any, cast, Optional, Tuple
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.core.paths import paths
from cocli.core.cache import get_cache_path, CACHE_FILE_NAME
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def verify_stack() -> None:
    """Verifies the full FDPE stack from model to DuckDB view."""
    campaign = "turboship" 
    print(f"--- FDPE VERIFICATION: {campaign} ---")
    
    # 1. Models & Datapackage
    print("\nStep 1: Regenerating Datapackage from Model...")
    prospect_idx = paths.campaign(campaign).index("google_maps_prospects")
    checkpoint_path = prospect_idx.checkpoint
    prospect_dp = prospect_idx.path / "datapackage.json"
    
    GoogleMapsProspect.save_datapackage(prospect_dp.parent)
    print(f"Datapackage saved to: {prospect_dp}")

    # 2. DuckDB Loading
    print("\nStep 2: Loading USVs into DuckDB...")
    con = duckdb.connect(database=':memory:')
    
    load_usv_to_duckdb(con, "items_checkpoint", checkpoint_path, prospect_dp)
    
    cache_dir = get_cache_path(campaign=campaign)
    cache_file = cache_dir / CACHE_FILE_NAME
    cache_dp = cache_dir / "datapackage.json"
    load_usv_to_duckdb(con, "items_cache", cache_file, cache_dp)

    # 3. Schema Inspection
    print("\nStep 3: Inspecting DuckDB Columns...")
    for table in ["items_checkpoint", "items_cache"]:
        res_cols: List[Tuple[Any, ...]] = con.execute(f"PRAGMA table_info('{table}')").fetchall()
        cols = [cast(str, c[1]) for c in res_cols]
        print(f"Table '{table}' columns: {', '.join(cols)}")
        
        # Verify critical columns for FDPE
        if "tags" not in cols:
            print(f"CRITICAL FAILURE: 'tags' column missing in {table}!")
        if table == "items_checkpoint" and "email" not in cols:
            print(f"CRITICAL FAILURE: 'email' column missing in {table}!")

    # 4. View Creation (The JOIN)
    print("\nStep 4: Creating Unified VIEW...")
    try:
        con.execute("""
            CREATE VIEW items AS SELECT 
                COALESCE(t1.slug, t2.slug) as slug,
                COALESCE(t1.name, t2.name) as name,
                COALESCE(t2.type, CAST('company' AS VARCHAR)) as type,
                COALESCE(t1.domain, t2.domain) as domain,
                COALESCE(t2.email, t1.email) as email,
                COALESCE(t1.phone_number, t2.phone_number) as phone_number,
                COALESCE(t2.tags, t1.tags) as tags
            FROM items_checkpoint t1 
            FULL OUTER JOIN items_cache t2 ON t1.slug = t2.slug
        """)
        print("SUCCESS: VIEW created without Binder Errors.")
        
        res_count: Optional[Tuple[Any, ...]] = con.execute("SELECT count(*) FROM items").fetchone()
        count = res_count[0] if res_count else 0
        print(f"Total results in VIEW: {count}")
        
    except Exception as e:
        print(f"FAILURE: VIEW creation failed: {e}")

if __name__ == "__main__":
    verify_stack()
