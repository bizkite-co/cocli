import csv
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict, Any, Optional
import argparse # Import argparse
import math # Import math for geographical calculations

from dateutil import tz # Import for timezone handling

# Assuming cocli is installed or available in the Python path
# Adjust imports if necessary based on how this script will be run
from cocli.core.scrape_index import ScrapedArea, ScrapeIndex
from cocli.core.config import get_cocli_base_dir
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager # Import manager
from cocli.models.website_domain_csv import WebsiteDomainCsv # Import model

# --- Configuration ---
LOG_FILE = Path(__file__).parent / "recover_data.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Paths relative to the data directory
data_home = get_cocli_base_dir()

OLD_INDEXES_DIR = data_home / "indexes"
PROSPECTS_CSV_PATH = data_home / "campaigns" / "turboship" / "scraped_data" / "google_maps_prospects.csv"
ORIGINAL_WEBSITE_DOMAINS_CSV = OLD_INDEXES_DIR / "website-domains.csv" # The existing file we will update

# --- Helper to convert datetime strings ---
def parse_datetime_str(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace(' ', 'T') # Normalize space to T for ISO format
        dt_obj = datetime.fromisoformat(dt_str)
        if dt_obj.tzinfo is None: # If naive, assume UTC
            dt_obj = dt_obj.replace(tzinfo=tz.tzutc())
        return dt_obj
    except ValueError:
        return None

# --- Helper to calculate lat_miles and lon_miles from bounds ---
def calculate_miles_from_bounds(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> tuple[float, float]:
    """
    Approximates latitude and longitude differences in miles.
    Assumes a spherical Earth with radius 3958.8 miles (average).
    """
    R = 3958.8 # Earth's radius in miles

    # Latitude difference in miles
    delta_lat_degrees = lat_max - lat_min
    lat_miles = R * math.radians(delta_lat_degrees)

    # Longitude difference in miles (depends on latitude)
    # Use the average latitude for a more accurate approximation
    avg_lat_radians = math.radians((lat_min + lat_max) / 2)
    delta_lon_degrees = lon_max - lon_min
    lon_miles = R * math.cos(avg_lat_radians) * math.radians(delta_lon_degrees)

    return round(lat_miles, 3), round(lon_miles, 3) # Round to 3 decimal places for consistency


# --- Helper for merging ScrapedArea objects ---
def merge_scraped_areas(existing_areas: List[ScrapedArea], new_areas: List[ScrapedArea]) -> List[ScrapedArea]:
    """
    Merges a list of new ScrapedArea objects into an existing list, handling duplicates
    and prioritizing newer/more complete data.
    """
    merged_map: Dict[tuple, ScrapedArea] = {}

    for area in existing_areas:
        key = (area.lat_min, area.lat_max, area.lon_min, area.lon_max)
        merged_map[key] = area
    
    for new_area in new_areas:
        key = (new_area.lat_min, new_area.lat_max, new_area.lon_min, new_area.lon_max)
        
        if key in merged_map:
            current_area = merged_map[key]
            if new_area.items_found > current_area.items_found:
                merged_map[key] = new_area
            elif new_area.items_found == current_area.items_found and new_area.scrape_date > current_area.scrape_date:
                merged_map[key] = new_area
        else:
            merged_map[key] = new_area
            
    return list(merged_map.values())


# --- Scraped Area Data Recovery ---
def recover_scraped_area_data():
    logger.info("Starting Scraped Area Data Recovery...")
    scrape_index = ScrapeIndex() # Instantiate ScrapeIndex to use its methods

    # List of all old CSV files containing ScrapedArea-like data
    old_scraped_area_csvs = [
        OLD_INDEXES_DIR / "commercial-vinyl-flooring-contractor.csv",
        OLD_INDEXES_DIR / "rubber-flooring-contractor.csv",
        OLD_INDEXES_DIR / "sports-flooring-contractor.csv",
        OLD_INDEXES_DIR / "financial-advisor.csv",
        OLD_INDEXES_DIR / "financial-planner.csv",
        OLD_INDEXES_DIR / "pacific-life.csv",
        OLD_INDEXES_DIR / "wealth-manager.csv",
    ]

    # Group old areas by phrase
    old_areas_by_phrase: Dict[str, List[ScrapedArea]] = {}

    for file_path in old_scraped_area_csvs:
        if not file_path.exists():
            logger.warning(f"Scraped Area data file not found: {file_path}. Skipping.")
            continue

        logger.info(f"Loading old Scraped Area data from: {file_path}")
        with file_path.open('r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader) # Read header

            # Dynamically get column indices.
            # We assume 'phrase', 'scrape_date', 'lat_min', 'lat_max', 'lon_min', 'lon_max' are always present
            # We will handle missing 'lat_miles', 'lon_miles', 'items_found'
            try:
                phrase_idx = header.index('phrase')
                scrape_date_idx = header.index('scrape_date')
                lat_min_idx = header.index('lat_min')
                lat_max_idx = header.index('lat_max')
                lon_min_idx = header.index('lon_min')
                lon_max_idx = header.index('lon_max')
                
                # Check for lat_miles and lon_miles existence
                has_lat_lon_miles = ('lat_miles' in header and 'lon_miles' in header)
                lat_miles_idx = header.index('lat_miles') if has_lat_lon_miles else -1
                lon_miles_idx = header.index('lon_miles') if has_lat_lon_miles else -1
                
                # Check for items_found existence
                has_items_found = ('items_found' in header)
                items_found_idx = header.index('items_found') if has_items_found else -1

            except ValueError as e:
                logger.error(f"Missing essential column in {file_path} header: {e}. Skipping this file as it doesn't match a base ScrapedArea schema.")
                continue

            for row in reader:
                try:
                    phrase = row[phrase_idx]
                    if phrase not in old_areas_by_phrase:
                        old_areas_by_phrase[phrase] = []

                    lat_min = float(row[lat_min_idx])
                    lat_max = float(row[lat_max_idx])
                    lon_min = float(row[lon_min_idx])
                    lon_max = float(row[lon_max_idx])

                    current_lat_miles = float(row[lat_miles_idx]) if has_lat_lon_miles else 0.0
                    current_lon_miles = float(row[lon_miles_idx]) if has_lat_lon_miles else 0.0
                    current_items_found = int(row[items_found_idx]) if has_items_found else 0

                    # If lat_miles/lon_miles are missing from source, calculate them
                    if not has_lat_lon_miles:
                        calculated_lat_miles, calculated_lon_miles = calculate_miles_from_bounds(lat_min, lat_max, lon_min, lon_max)
                        current_lat_miles = calculated_lat_miles
                        current_lon_miles = calculated_lon_miles
                        logger.debug(f"Calculated lat_miles={current_lat_miles}, lon_miles={current_lon_miles} for {phrase} from {file_path}")

                    # Create ScrapedArea object
                    area = ScrapedArea(
                        phrase=phrase,
                        scrape_date=parse_datetime_str(row[scrape_date_idx]) or datetime.now(tz.tzutc()),
                        lat_min=lat_min,
                        lat_max=lat_max,
                        lon_min=lon_min,
                        lon_max=lon_max,
                        lat_miles=current_lat_miles,
                        lon_miles=current_lon_miles,
                        items_found=current_items_found, # Use existing if present, else 0
                    )
                    old_areas_by_phrase[phrase].append(area)
                except Exception as e:
                    logger.error(f"Error processing row in {file_path}: {row} - {e}")
    
    # Now, for each phrase, merge old data with existing data and save
    for phrase, old_areas in old_areas_by_phrase.items():
        if not old_areas: # Skip if no areas were successfully loaded for this phrase
            continue
        logger.info(f"Merging and saving ScrapedArea data for phrase: {phrase}")
        
        # Load existing areas for this phrase
        existing_current_areas = scrape_index._load_areas_for_phrase(phrase)
        
        # Merge old and existing areas
        final_areas = merge_scraped_areas(existing_current_areas, old_areas)
        
        # Save the final merged list for this phrase
        scrape_index._save_areas_for_phrase(phrase, final_areas)
        logger.info(f"Saved {len(final_areas)} unique ScrapedArea records for '{phrase}'.")

    logger.info("Finished Scraped Area Data Recovery.")

# --- Website Domain Data Recovery (to ORIGINAL_WEBSITE_DOMAINS_CSV) ---
def recover_website_domain_data():
    logger.info("Starting Website Domain Data Recovery (to original website-domains.csv)...")
    
    manager = WebsiteDomainCsvManager() # This loads existing data from website-domains.csv

    # Load prospects.csv data
    prospects_data: List[Dict[str, Any]] = []
    if PROSPECTS_CSV_PATH.exists():
        with PROSPECTS_CSV_PATH.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prospects_data.append(row)
        logger.info(f"Loaded {len(prospects_data)} records from {PROSPECTS_CSV_PATH}")
    else:
        logger.warning(f"Prospects CSV not found: {PROSPECTS_CSV_PATH}. Skipping prospect data integration.")
        return

    # Iterate through prospects data and merge into manager's data
    for p_record in prospects_data:
        domain_from_prospects = p_record.get('Domain', '').lower()
        if not domain_from_prospects:
            logger.debug(f"Skipping prospect record with no domain: {p_record.get('Name', 'N/A')}")
            continue

        # Get existing WebsiteDomainCsv object from manager or create a new one
        existing_item = manager.get_by_domain(domain_from_prospects)
        if not existing_item:
            # Create a new WebsiteDomainCsv item
            existing_item = WebsiteDomainCsv(domain=domain_from_prospects)
            
            # Populate basic fields from prospect record
            # We must use timezone-aware datetimes consistently
            now_utc = datetime.now(tz.tzutc())
            existing_item.created_at = parse_datetime_str(p_record.get('created_at', '')) or now_utc
            existing_item.updated_at = parse_datetime_str(p_record.get('updated_at', '')) or now_utc
        
        # Merge logic for WebsiteDomainCsv fields (fill gaps in existing_item from p_record)
        # If both have values, prefer existing_item's value (website-derived is primary for this file).
        
        # company_name
        if not existing_item.company_name and p_record.get('Name'):
            existing_item.company_name = p_record['Name']
        # phone
        if not existing_item.phone and p_record.get('Phone_1'):
            existing_item.phone = p_record['Phone_1']
        # email
        # prospects.csv has no 'Email' field by default, but if it did...
        if not existing_item.email and p_record.get('Email'): 
            existing_item.email = p_record['Email']
        # address
        if not existing_item.address and p_record.get('Full_Address'):
            existing_item.address = p_record['Full_Address']

        # Social media URLs
        for social_field_wd, social_field_p in [
            ('facebook_url', 'Facebook_URL'), ('linkedin_url', 'Linkedin_URL'),
            ('instagram_url', 'Instagram_URL'), ('twitter_url', 'Twitter_URL'),
            ('youtube_url', 'Youtube_URL')
        ]:
            if not getattr(existing_item, social_field_wd) and p_record.get(social_field_p):
                setattr(existing_item, social_field_wd, p_record[social_field_p])

        # Timestamps - always take latest for updated_at, earliest for created_at
        p_created_at_dt = parse_datetime_str(p_record.get('created_at', ''))
        p_updated_at_dt = parse_datetime_str(p_record.get('updated_at', ''))

        # Ensure existing_item's timestamps are timezone-aware for comparison
        if existing_item.created_at and existing_item.created_at.tzinfo is None:
            existing_item.created_at = existing_item.created_at.replace(tzinfo=tz.tzutc())
        if existing_item.updated_at and existing_item.updated_at.tzinfo is None:
            existing_item.updated_at = existing_item.updated_at.replace(tzinfo=tz.tzutc())

        if p_created_at_dt and existing_item.created_at:
            existing_item.created_at = min(existing_item.created_at, p_created_at_dt)
        elif p_created_at_dt and not existing_item.created_at:
            existing_item.created_at = p_created_at_dt
        
        if p_updated_at_dt and existing_item.updated_at:
            existing_item.updated_at = max(existing_item.updated_at, p_updated_at_dt)
        elif p_updated_at_dt and not existing_item.updated_at:
            existing_item.updated_at = p_updated_at_dt
        
        # Call manager to add/update and save
        manager.add_or_update(existing_item) # This will save to ORIGINAL_WEBSITE_DOMAINS_CSV

    logger.info("Finished Website Domain Data Recovery (to original website-domains.csv).")


# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(description="Recover and integrate old scrape data.")
    parser.add_argument(
        "--task", 
        choices=["scraped-areas", "website-domains", "all"], 
        default="all",
        help="Specify which recovery task to run."
    )
    args = parser.parse_args()

    logger.info(f"Starting data recovery script for task: {args.task}...")

    if args.task == "scraped-areas" or args.task == "all":
        recover_scraped_area_data()
    
    if args.task == "website-domains" or args.task == "all":
        recover_website_domain_data() 
    
    logger.info("Data recovery script finished.")

if __name__ == "__main__":
    main()