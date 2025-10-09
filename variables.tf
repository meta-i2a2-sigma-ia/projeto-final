variable "aws_region" {
  description = "Região AWS"
  type        = string
  default     = "sa-east-1"
}

variable "project_name" {
  description = "Prefixo de nomes dos recursos"
  type        = string
  default     = "s3-lambda-supabase"
}

variable "s3_bucket_name" {
  description = "Nome do bucket S3 (único globalmente)"
  type        = string
}

variable "supabase_url" {
  description = "URL base do Supabase (ex.: https://xxxx.supabase.co)"
  type        = string
}

variable "supabase_service_role_key" {
  description = "Service Role Key do Supabase (NÃO compartilhe)"
  type        = string
  sensitive   = true
}

variable "supabase_table" {
  description = "Tabela de destino no Supabase"
  type        = string
  default     = "ingest_data"
}

variable "supabase_schema" {
  description = "Schema da tabela no Supabase"
  type        = string
  default     = "public"
}

variable "lambda_timeout" {
  description = "Timeout da Lambda (segundos)"
  type        = number
  default     = 160
}

variable "lambda_memory" {
  description = "Memória da Lambda (MB)"
  type        = number
  default     = 1536
}

variable "s3_event_prefix" {
  description = "Opcional: prefixo de chave para disparar eventos (ex: uploads/)"
  type        = string
  default     = ""
}

variable "s3_event_suffix" {
  description = "Opcional: sufixo de chave para disparar (ex: .csv)"
  type        = string
  default     = ".csv"
}

variable "ephemeral_storage_mb" {
  description = "Tamanho do /tmp da Lambda (512-10240 MB)"
  type        = number
  default     = 1024
}

# variables.tf

variable "lambda_name" {
  type        = string
  description = "Nome da função Lambda."
}

variable "supabase_project_ref" {
  type        = string
  description = "Project ref do Supabase (subdomínio do projeto)."
  # refs costumam ser minúsculas e números; tamanho varia entre ~10 e 32
  validation {
    condition     = can(regex("^[a-z0-9-]{10,32}$", var.supabase_project_ref))
    error_message = "supabase_project_ref deve conter 10–32 caracteres [a-z0-9-]."
  }
}

variable "supabase_access_token" {
  type        = string
  description = "Personal Access Token (PAT) para a Management API (geralmente inicia com sbp_)."
  sensitive   = true
  validation {
    condition     = can(regex("^sbp_[A-Za-z0-9_\\-]{10,}$", var.supabase_access_token))
    error_message = "supabase_access_token deve ser um PAT iniciando com 'sbp_'."
  }
}

# --- Supabase (opcionais com defaults) ---

variable "table_strategy" {
  type        = string
  description = "Estratégia para nome da tabela: 'filename' ou 'header_table'."
  default     = "filename"
  validation {
    condition     = contains(["filename", "header_table"], var.table_strategy)
    error_message = "table_strategy deve ser 'filename' ou 'header_table'."
  }
}

variable "table_prefix" {
  type        = string
  description = "Prefixo para nome das tabelas criadas."
  default     = ""
  validation {
    condition     = can(regex("^[a-zA-Z0-9_\\-]*$", var.table_prefix))
    error_message = "table_prefix deve conter apenas [a-zA-Z0-9_-]."
  }
}

variable "sample_lines" {
  type        = number
  description = "Linhas de amostra para inferência de tipos."
  default     = 300
  validation {
    condition     = var.sample_lines > 0 && var.sample_lines <= 20000
    error_message = "sample_lines deve estar entre 1 e 20000."
  }
}

variable "batch_size" {
  type        = number
  description = "Tamanho do batch para inserts via REST."
  default     = 1000
  validation {
    condition     = var.batch_size > 0 && var.batch_size <= 10000
    error_message = "batch_size deve estar entre 1 e 10000."
  }
}
