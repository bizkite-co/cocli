import csv
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict, Any, NamedTuple, Optional, Set

# Assuming cocli is installed or available in the Python path
# Adjust imports if necessary based on how this script will be run
from cocli.core.scrape_index import ScrapedArea, ScrapeIndex
from cocli.core.config import get_scraped_areas_index_dir
from cocli.core.utils import slugify # For phrase slugification

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

# Paths relative to the cocli_data directory
COCLI_DATA_HOME = Path("/home/mstouffer/.local/share/cocli_data") # IMPORTANT: Adjust if cocli_data is elsewhere

OLD_INDEXES_DIR = COCLI_DATA_HOME / "indexes"
PROSPECTS_CSV_PATH = COCLI_DATA_HOME / "campaigns" / "turboship" / "scraped_data" / "prospects.csv"
ORIGINAL_WEBSITE_DOMAINS_CSV = OLD_INDEXES_DIR / "website-domains.csv"
CENTRAL_DOMAINS_MASTER_PATH = OLD_INDEXES_DIR / "domains_master.csv" # New master file

# --- Helper to convert datetime strings ---
def parse_datetime_str(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Handle formats with and without timezone, and potential space instead of T
        dt_str = dt_str.replace(' ', 'T')
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None

# --- Central Domains Master Header ---
CENTRAL_DOMAINS_MASTER_HEADER = [
    'domain',
    'company_name',
    'gmb_name',
    'phone_website',
    'phone_gmb_primary',
    'phone_gmb_standard',
    'email',
    'address_website',
    'address_gmb_full',
    'address_gmb_street',
    'address_gmb_city',
    'address_gmb_zip',
    'address_gmb_municipality',
    'address_gmb_state',
    'address_gmb_country',
    'gmb_latitude',
    'gmb_longitude',
    'gmb_coordinates',
    'gmb_plus_code',
    'gmb_place_id',
    'gmb_categories', # Will concatenate First_category, Second_category
    'gmb_claimed',
    'gmb_reviews_count',
    'gmb_average_rating',
    'gmb_hours_raw', # All GMB hour fields as a string or JSON if needed
    'gmb_menu_link',
    'gmb_url',
    'gmb_cid',
    'gmb_knowledge_url',
    'gmb_kgmid',
    'gmb_image_url',
    'gmb_favicon',
    'gmb_review_url',
    'gmb_thumbnail_url',
    'gmb_reviews_text',
    'gmb_quotes',
    'gmb_uuid',
    'facebook_url',
    'linkedin_url',
    'instagram_url',
    'twitter_url',
    'youtube_url',
    'personnel',
    'about_us_url',
    'contact_url',
    'services_url',
    'products_url',
    'tags',
    'scraper_version',
    'associated_company_folder',
    'is_email_provider',
    'website_from_gmb', # Website from prospects.csv if different from domain
    'first_seen_at',
    'last_updated_at',
    'source_website_domains_csv_present',
    'source_prospects_csv_present'
]


# --- Scraped Area Data Recovery ---
def recover_scraped_area_data():
    logger.info("Starting Scraped Area Data Recovery...")
    scrape_index = ScrapeIndex() # Instantiate ScrapeIndex to use its methods

    scraped_area_files = [
        OLD_INDEXES_DIR / "commercial-vinyl-flooring-contractor.csv",
        OLD_INDEXES_DIR / "rubber-flooring-contractor.csv",
        OLD_INDEXES_DIR / "sports-flooring-contractor.csv",
    ]

    for file_path in scraped_area_files:
        if not file_path.exists():
            logger.warning(f"Scraped Area data file not found: {file_path}. Skipping.")
            continue

        logger.info(f"Processing Scraped Area data from: {file_path}")
        with file_path.open('r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader) # Skip header

            # Dynamically get column indices for robustness
            try:
                phrase_idx = header.index('phrase')
                scrape_date_idx = header.index('scrape_date')
                lat_min_idx = header.index('lat_min')
                lat_max_idx = header.index('lat_max')
                lon_min_idx = header.index('lon_min')
                lon_max_idx = header.index('lon_max')
                lat_miles_idx = header.index('lat_miles')
                lon_miles_idx = header.index('lon_miles')
            except ValueError as e:
                logger.error(f"Missing expected column in {file_path} header: {e}. Skipping this file.")
                continue

            for row in reader:
                try:
                    # Create ScrapedArea with items_found=0 (as it's missing in old format)
                    area = ScrapedArea(
                        phrase=row[phrase_idx],
                        scrape_date=parse_datetime_str(row[scrape_date_idx]) or datetime.now(),
                        lat_min=float(row[lat_min_idx]),
                        lat_max=float(row[lat_max_idx]),
                        lon_min=float(row[lon_min_idx]),
                        lon_max=float(row[lon_max_idx]),
                        lat_miles=float(row[lat_miles_idx]),
                        lon_miles=float(row[lon_miles_idx]),
                        items_found=0, # Default to 0 for recovered old data
                    )
                    # Add area using ScrapeIndex method - handles saving to phrase-specific CSV
                    scrape_index.add_area(
                        phrase=area.phrase,
                        bounds={
                            'lat_min': area.lat_min, 'lat_max': area.lat_max,
                            'lon_min': area.lon_min, 'lon_max': area.lon_max
                        },
                        lat_miles=area.lat_miles,
                        lon_miles=area.lon_miles,
                        items_found=area.items_found
                    )
                    logger.debug(f"Added ScrapedArea: {area.phrase}")
                except Exception as e:
                    logger.error(f"Error processing row in {file_path}: {row} - {e}")
    logger.info("Finished Scraped Area Data Recovery.")

# --- Website Domain Data Recovery (to new domains_master.csv) ---
def recover_website_domain_data():
    logger.info("Starting Website Domain Data Recovery (to new domains_master.csv)...")
    
    # --- Load existing website-domains.csv data ---
    domains_master_data: Dict[str, Dict[str, Any]] = {}

    if ORIGINAL_WEBSITE_DOMAINS_CSV.exists():
        with ORIGINAL_WEBSITE_DOMAINS_CSV.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            original_website_domains_header = reader.fieldnames if reader.fieldnames else []
            for row in reader:
                domain_key = row.get('domain', '').lower()
                if not domain_key:
                    logger.warning(f"Skipping website-domains.csv record with no domain: {row}")
                    continue
                
                # Initialize a new master record with empty values for all master header fields
                master_record = {field: '' for field in CENTRAL_DOMAINS_MASTER_HEADER}
                
                # Map fields from original website-domains.csv to master record
                for key, value in row.items():
                    if key == 'domain':
                        master_record['domain'] = value
                        master_record['website_from_gmb'] = value # Default GMB website to this
                    elif key == 'company_name': master_record['company_name'] = value
                    elif key == 'phone': master_record['phone_website'] = value
                    elif key == 'email': master_record['email'] = value
                    elif key == 'address': master_record['address_website'] = value
                    elif key == 'created_at': master_record['first_seen_at'] = value
                    elif key == 'updated_at': master_record['last_updated_at'] = value
                    elif key in CENTRAL_DOMAINS_MASTER_HEADER: # Direct map for shared social/misc fields
                        master_record[key] = value
                
                master_record['source_website_domains_csv_present'] = 'True' # Mark source
                domains_master_data[domain_key] = master_record
        logger.info(f"Loaded {len(domains_master_data)} records from {ORIGINAL_WEBSITE_DOMAINS_CSV}")
    else:
        logger.warning(f"Original Website Domains CSV not found: {ORIGINAL_WEBSITE_DOMAINS_CSV}. Starting domains_master from scratch.")

    # --- Load prospects.csv data and merge ---
    prospects_data: List[Dict[str, Any]] = []
    if PROSPECTS_CSV_PATH.exists():
        with PROSPECTS_CSV_PATH.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            prospects_header = reader.fieldnames if reader.fieldnames else []
            for row in reader:
                prospects_data.append(row)
        logger.info(f"Loaded {len(prospects_data)} records from {PROSPECTS_CSV_PATH}")
    else:
        logger.warning(f"Prospects CSV not found: {PROSPECTS_CSV_PATH}. Skipping prospect data integration.")


    for p_record in prospects_data:
        domain_from_prospects = p_record.get('Domain', '').lower()
        if not domain_from_prospects:
            logger.debug(f"Skipping prospect record with no domain: {p_record.get('Name', 'N/A')}")
            continue

        existing_master_record = domains_master_data.get(domain_from_prospects)

        if not existing_master_record:
            # Create a new master record if domain not found from website-domains.csv
            existing_master_record = {field: '' for field in CENTRAL_DOMAINS_MASTER_HEADER}
            existing_master_record['domain'] = domain_from_prospects
            existing_master_record['website_from_gmb'] = p_record.get('Website', '')
            existing_master_record['source_prospects_csv_present'] = 'True'
            domains_master_data[domain_from_prospects] = existing_master_record

        # --- Merge fields from prospect record into existing_master_record ---
        
        # Simple overwrites/fills if empty
        if p_record.get('Name') and not existing_master_record['gmb_name']:
            existing_master_record['gmb_name'] = p_record['Name']
        if p_record.get('Website') and not existing_master_record['website_from_gmb']:
            existing_master_record['website_from_gmb'] = p_record['Website']

        # Phone numbers
        if p_record.get('Phone_1') and not existing_master_record['phone_gmb_primary']:
            existing_master_record['phone_gmb_primary'] = p_record['Phone_1']
        if p_record.get('Phone_Standard_format') and not existing_master_record['phone_gmb_standard']:
            existing_master_record['phone_gmb_standard'] = p_record['Phone_Standard_format']

        # Address fields
        if p_record.get('Full_Address') and not existing_master_record['address_gmb_full']:
            existing_master_record['address_gmb_full'] = p_record['Full_Address']
        if p_record.get('Street_Address') and not existing_master_record['address_gmb_street']:
            existing_master_record['address_gmb_street'] = p_record['Street_Address']
        if p_record.get('City') and not existing_master_record['address_gmb_city']:
            existing_master_record['address_gmb_city'] = p_record['City']
        if p_record.get('Zip') and not existing_master_record['address_gmb_zip']:
            existing_master_record['address_gmb_zip'] = p_record['Zip']
        if p_record.get('Municipality') and not existing_master_record['address_gmb_municipality']:
            existing_master_record['address_gmb_municipality'] = p_record['Municipality']
        if p_record.get('State') and not existing_master_record['address_gmb_state']:
            existing_master_record['address_gmb_state'] = p_record['State']
        if p_record.get('Country') and not existing_master_record['address_gmb_country']:
            existing_master_record['address_gmb_country'] = p_record['Country']
        
        # GMB Location Data
        if p_record.get('Latitude') and not existing_master_record['gmb_latitude']:
            existing_master_record['gmb_latitude'] = p_record['Latitude']
        if p_record.get('Longitude') and not existing_master_record['gmb_longitude']:
            existing_master_record['gmb_longitude'] = p_record['Longitude']
        if p_record.get('Coordinates') and not existing_master_record['gmb_coordinates']:
            existing_master_record['gmb_coordinates'] = p_record['Coordinates']
        if p_record.get('Plus_Code') and not existing_master_record['gmb_plus_code']:
            existing_master_record['gmb_plus_code'] = p_record['Plus_Code']
        if p_record.get('Place_ID') and not existing_master_record['gmb_place_id']:
            existing_master_record['gmb_place_id'] = p_record['Place_ID']

        # GMB Categories (concatenate)
        gmb_cats = []
        if p_record.get('First_category'): gmb_cats.append(p_record['First_category'])
        if p_record.get('Second_category'): gmb_cats.append(p_record['Second_category'])
        if gmb_cats and not existing_master_record['gmb_categories']:
            existing_master_record['gmb_categories'] = "; ".join(gmb_cats)

        # Other GMB fields
        if p_record.get('Claimed_google_my_business') and not existing_master_record['gmb_claimed']:
            existing_master_record['gmb_claimed'] = p_record['Claimed_google_my_business']
        if p_record.get('Reviews_count') and not existing_master_record['gmb_reviews_count']:
            existing_master_record['gmb_reviews_count'] = p_record['Reviews_count']
        if p_record.get('Average_rating') and not existing_master_record['gmb_average_rating']:
            existing_master_record['gmb_average_rating'] = p_record['Average_rating']
        
        # GMB Hours (simple concatenation for now, could be JSON)
        gmb_hours = {}
        for day in ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            if p_record.get(day): gmb_hours[day] = p_record[day]
        if gmb_hours and not existing_master_record['gmb_hours_raw']:
            existing_master_record['gmb_hours_raw'] = str(gmb_hours) # Store as string representation of dict

        if p_record.get('Menu_Link') and not existing_master_record['gmb_menu_link']:
            existing_master_record['gmb_menu_link'] = p_record['Menu_Link']
        if p_record.get('GMB_URL') and not existing_master_record['gmb_url']:
            existing_master_record['gmb_url'] = p_record['GMB_URL']
        if p_record.get('CID') and not existing_master_record['gmb_cid']:
            existing_master_record['gmb_cid'] = p_record['CID']
        if p_record.get('Google_Knowledge_URL') and not existing_master_record['gmb_knowledge_url']:
            existing_master_record['gmb_knowledge_url'] = p_record['Google_Knowledge_URL']
        if p_record.get('Kgmid') and not existing_master_record['gmb_kgmid']:
            existing_master_record['gmb_kgmid'] = p_record['Kgmid']
        if p_record.get('Image_URL') and not existing_master_record['gmb_image_url']:
            existing_master_record['gmb_image_url'] = p_record['Image_URL']
        if p_record.get('Favicon') and not existing_master_record['gmb_favicon']:
            existing_master_record['gmb_favicon'] = p_record['Favicon']
        if p_record.get('Review_URL') and not existing_master_record['gmb_review_url']:
            existing_master_record['gmb_review_url'] = p_record['Review_URL']
        if p_record.get('Thumbnail_URL') and not existing_master_record['gmb_thumbnail_url']:
            existing_master_record['gmb_thumbnail_url'] = p_record['Thumbnail_URL']
        if p_record.get('Reviews') and not existing_master_record['gmb_reviews_text']:
            existing_master_record['gmb_reviews_text'] = p_record['Reviews']
        if p_record.get('Quotes') and not existing_master_record['gmb_quotes']:
            existing_master_record['gmb_quotes'] = p_record['Quotes']
        if p_record.get('Uuid') and not existing_master_record['gmb_uuid']:
            existing_master_record['gmb_uuid'] = p_record['Uuid']
        
        # Social media URLs (merge by prioritizing existence)
        for social_field in ['facebook_url', 'linkedin_url', 'instagram_url']:
            p_val = p_record.get(social_field.replace('_url', '_URL')) # prospects uses _URL
            if p_val and not existing_master_record[social_field]:
                existing_master_record[social_field] = p_val


        # Update timestamps
        p_created_at = parse_datetime_str(p_record.get('created_at', ''))
        p_updated_at = parse_datetime_str(p_record.get('updated_at', ''))
        master_first_seen = parse_datetime_str(existing_master_record['first_seen_at'])
        master_last_updated = parse_datetime_str(existing_master_record['last_updated_at'])

        if p_created_at:
            if master_first_seen:
                existing_master_record['first_seen_at'] = min(master_first_seen, p_created_at).isoformat()
            else:
                existing_master_record['first_seen_at'] = p_created_at.isoformat()
        
        if p_updated_at:
            if master_last_updated:
                existing_master_record['last_updated_at'] = max(master_last_updated, p_updated_at).isoformat()
            else:
                existing_master_record['last_updated_at'] = p_updated_at.isoformat()
        
        existing_master_record['source_prospects_csv_present'] = 'True'
    
    # Write updated central domains data back to CSV
    logger.info(f"Writing {len(domains_master_data)} consolidated domain records to {CENTRAL_DOMAINS_MASTER_PATH}")
    with CENTRAL_DOMAINS_MASTER_PATH.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CENTRAL_DOMAINS_MASTER_HEADER)
        writer.writeheader()
        for domain_record in domains_master_data.values():
            # Ensure row only contains fields present in the header
            writer.writerow({k: domain_record.get(k, '') for k in CENTRAL_DOMAINS_MASTER_HEADER})

    logger.info("Finished Website Domain Data Recovery.")

# --- Main Execution ---
def main():
    logger.info("Starting data recovery script...")
    recover_scraped_area_data()
    recover_website_domain_data()
    logger.info("Data recovery script finished.")

if __name__ == "__main__":
    main()