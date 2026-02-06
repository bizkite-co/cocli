# Discovery Audit Results
This directory is a **Frictionless Data Package**.

### Usage with DuckDB:
```sql
SELECT * FROM read_csv('completed/results/**/*.usv', delim='\x1f', header=false);
```
