# terraform.tfvars (exemplo)

lambda_name           = "sigma-ia2a-supabase"
lambda_timeout        = 60
lambda_memory         = 2048
ephemeral_storage_mb  = 1024

# Supabase
supabase_url              = "https://lzycybdggtgmuqovwfqa.supabase.co"
supabase_project_ref      = "lzycybdggtgmuqovwfqa"
supabase_service_role_key  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6eWN5YmRnZ3RnbXVxb3Z3ZnFhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTI3MTQzMSwiZXhwIjoyMDc0ODQ3NDMxfQ.zedxIIsXP4v1yONPTgrtyLQ3gQe72NrgNj5vu2Z57KQ" # Service Role
supabase_access_token     = "sbp_4375514a28d90e77596b58b1814de58cf4ba309d"       # <— PAT da org/projeto

#
aws_region                 = "sa-east-1"
s3_bucket_name             = "sigma-ia2a-supabase"
s3_event_prefix            = "uploads/"
s3_event_suffix            = ".csv"

# Comportamento
supabase_schema  = "public"
supabase_table   = "ingest_data"
table_strategy   = "filename"
table_prefix     = "s3_"
sample_lines     = 300
batch_size       = 1000
