# terraform.tfvars (exemplo)

lambda_name           = "sigma-ia2a-supabase"
lambda_timeout        = 60
lambda_memory         = 2048
ephemeral_storage_mb  = 1024

# Supabase
supabase_url              = ""
supabase_project_ref      = ""
supabase_service_role_key  = "" # Service Role
supabase_access_token     = ""       # <— PAT da org/projeto

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
