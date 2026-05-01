resource "random_id" "artifacts_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "app_artifacts" {
  bucket        = "luggage-app-artifacts-${random_id.artifacts_suffix.hex}"
  force_destroy = true

  tags = {
    Name = "LuggageAppArtifacts"
  }
}

resource "aws_s3_bucket_versioning" "artifacts_versioning" {
  bucket = aws_s3_bucket.app_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "archive_file" "src_code" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/app.zip"
}

resource "aws_s3_object" "app_zip_upload" {
  bucket = aws_s3_bucket.app_artifacts.id
  key    = "app.zip"
  source = data.archive_file.src_code.output_path
  etag   = data.archive_file.src_code.output_md5
}
