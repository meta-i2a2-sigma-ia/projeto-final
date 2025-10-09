terraform {
  required_version = ">= 1.5.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  lambda_name = "${var.project_name}-ingest"
}

# --- S3 bucket (com bloqueio de acesso público)
resource "aws_s3_bucket" "ingest" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_bucket_public_access_block" "ingest" {
  bucket                  = aws_s3_bucket.ingest.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Opcional: versioning
resource "aws_s3_bucket_versioning" "ingest" {
  bucket = aws_s3_bucket.ingest.id
  versioning_configuration {
    status = "Enabled"
  }
}

# --- Role + Policy da Lambda
data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${local.lambda_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

# Permissões mínimas: logs + get do S3
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid     = "AllowCloudWatchLogs"
    effect  = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "AllowS3Read"
    effect  = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion"
    ]
    resources = [
      "${aws_s3_bucket.ingest.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_policy" {
  name   = "${local.lambda_name}-policy"
  policy = data.aws_iam_policy_document.lambda_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# --- Empacotamento da Lambda
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/${local.lambda_name}.zip"
}

# --- Log group (opcional, senão a Lambda cria)
resource "aws_cloudwatch_log_group" "lambda_lg" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14
}

# --- Lambda Function (Python 3.12)
resource "aws_lambda_function" "ingest_fn" {
  function_name    = local.lambda_name
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  environment {
    variables = {
      SUPABASE_URL               = var.supabase_url
      SUPABASE_SERVICE_ROLE_KEY  = var.supabase_service_role_key
      SUPABASE_PROJECT_REF       = var.supabase_project_ref     # opcional (logs)
      PG_SCHEMA                  = var.supabase_schema          # ex: "public"

      TABLE_STRATEGY             = var.table_strategy           # "filename" | "header_table"
      TABLE_PREFIX               = var.table_prefix             # ex: "s3_"
      SAMPLE_LINES_FOR_INFERENCE = tostring(var.sample_lines)   # ex: 300
      BATCH_SIZE                 = tostring(var.batch_size)     # ex: 1000

      # Por padrão NÃO adiciona metadados
      ADD_METADATA               = "false"                      # mude para "true" se quiser _s3_bucket/_s3_key/_ingested_at
    }
  }
  ephemeral_storage {
    size = var.ephemeral_storage_mb
  }
  depends_on = [
    aws_cloudwatch_log_group.lambda_lg,
    aws_iam_role_policy_attachment.lambda_attach
  ]
}

# --- Permissão para S3 invocar a Lambda
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest_fn.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.ingest.arn
}

# --- Notificação S3 -> Lambda (ObjectCreated) com filtros opcionais
resource "aws_s3_bucket_notification" "ingest_notify" {
  bucket = aws_s3_bucket.ingest.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest_fn.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.s3_event_prefix != "" ? var.s3_event_prefix : null
    filter_suffix       = var.s3_event_suffix != "" ? var.s3_event_suffix : null
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}
