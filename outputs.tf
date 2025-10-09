output "s3_bucket_name" {
  value = aws_s3_bucket.ingest.bucket
}

output "lambda_function_name" {
  value = aws_lambda_function.ingest_fn.function_name
}

output "lambda_arn" {
  value = aws_lambda_function.ingest_fn.arn
}
