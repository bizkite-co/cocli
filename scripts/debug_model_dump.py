from cocli.models.companies.company import Company

slug = "atkins-financial-group"
company = Company.get(slug)
print(f"Company: {company.name}, reviews_count: {company.reviews_count}")

# Try to set it to None and dump
company.reviews_count = None
print(f"After set to None: {company.reviews_count}")

data = company.model_dump(mode="json", exclude_none=True)
print(f"Dumped reviews_count: {data.get('reviews_count', 'NOT IN DUMP')}")
