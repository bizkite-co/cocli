import os
import yaml
import simplekml # type: ignore
import logging

logger = logging.getLogger(__name__)

def main() -> None:
    """
    Generates a KML file with placemarks for each company tagged with "turboship".
    """
    
    data_dir = "/home/mstouffer/.local/share/data/companies"
    output_dir = "/home/mstouffer/repos/company-cli/campaigns/2025/turboship"
    kml_file_path = os.path.join(output_dir, "turboship_customers.kml")
    
    kml = simplekml.Kml()
    
    turboship_tags_files = []
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file == "tags.lst":
                file_path = os.path.join(root, file)
                with open(file_path, "r") as f:
                    if "turboship" in f.read():
                        turboship_tags_files.append(file_path)

    company_count = 0
    for tag_file in turboship_tags_files:
        company_dir = os.path.dirname(tag_file)
        index_file = os.path.join(company_dir, "_index.md")
        
        if os.path.exists(index_file):
            with open(index_file, "r") as f:
                content = f.read()
                parts = content.split('---\n')
                if len(parts) > 1:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        
                        name = frontmatter.get("name")
                        if name == "Prefloor Tools":
                            logger.debug("Found Prefloor Tools!")
                            
                        full_address = frontmatter.get("full_address")
                        city = frontmatter.get("city")
                        state = frontmatter.get("state")
                        zip_code = frontmatter.get("zip_code")
                        
                        if full_address and city and state and zip_code:
                            logger.info(f"Adding {name} to KML file.")
                            placemark = kml.newpoint(name=name)
                            placemark.address = f"{full_address}, {city}, {state} {zip_code}"
                            company_count += 1
                            
                    except yaml.YAMLError as e:
                        logger.error(f"Error parsing YAML in {index_file}: {e}")

    kml.save(kml_file_path)
    logger.info(f"KML file '{kml_file_path}' created successfully.")
    logger.info(f"Added {company_count} companies to the KML file.")