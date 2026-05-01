# Suffix mapping to avoid S3 bucket global naming collisions across multiple rapid deployments
resource "random_string" "obs_suffix" {
  length  = 6
  special = false
  upper   = false
}

# ==========================================
# 1. VPC Flow Logs & Native Network Telemetry
# ==========================================
resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = "/aws/vpc/luggage-flow-logs-${random_string.obs_suffix.result}"
  retention_in_days = 7
}

resource "aws_iam_role" "vpc_flow_logs_role" {
  name = "luggage_vpc_flow_logs_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "vpc_flow_logs_policy" {
  name = "luggage_vpc_flow_logs_policy"
  role = aws_iam_role.vpc_flow_logs_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      Effect   = "Allow"
      Resource = "*"
    }]
  })
}

resource "aws_flow_log" "main" {
  iam_role_arn    = aws_iam_role.vpc_flow_logs_role.arn
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.main.id
}

# ==========================================
# 2. AWS CloudTrail Logging Infrastructure
# ==========================================
resource "aws_s3_bucket" "cloudtrail_bucket" {
  bucket        = "luggage-system-cloudtrail-${random_string.obs_suffix.result}"
  force_destroy = true 
}

# S3 Policy permitting Cloudtrail to inherently write logs securely
resource "aws_s3_bucket_policy" "cloudtrail_policy" {
  bucket = aws_s3_bucket.cloudtrail_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail_bucket.arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_bucket.arn}/prefix/AWSLogs/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# Active Auditing Core
resource "aws_cloudtrail" "main" {
  name                          = "luggage-system-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_bucket.id
  s3_key_prefix                 = "prefix"
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true

  depends_on = [aws_s3_bucket_policy.cloudtrail_policy]
}

# ==========================================
# 3. Application Load Balancer Request Analytics
# ==========================================
resource "aws_s3_bucket" "alb_logs" {
  bucket        = "luggage-system-alb-logs-${random_string.obs_suffix.result}"
  force_destroy = true
}

# Retrieve specific AL2 Service accounts locally to map mapping structures
data "aws_elb_service_account" "main" {}

# Enable Edge Load balancing to serialize logs to standard buckets
resource "aws_s3_bucket_policy" "alb_logs_policy" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = { AWS = data.aws_elb_service_account.main.arn }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.alb_logs.arn}/*"
      }
    ]
  })
}

# ==========================================
# 4. Autoscaling Hardware Monitoring Context
# ==========================================
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "luggage-app-high-cpu"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "120"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors EC2 AutoScaling hardware CPU utilization exceeding 80%"

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app_asg.name
  }
}

# ==========================================
# 5. CloudWatch Management Dashboard
# ==========================================
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "LuggageSystemMetrics-${random_string.obs_suffix.result}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            [
              "AWS/EC2",
              "CPUUtilization",
              "AutoScalingGroupName",
              aws_autoscaling_group.app_asg.name
            ]
          ]
          period = 300
          stat   = "Average"
          region = "us-east-1"
          title  = "ASG CPU Utilization (Live)"
        }
      }
    ]
  })
}
