output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "rds_endpoint" {
  description = "The fully qualified endpoint of the RDS instance"
  value       = aws_db_instance.main.endpoint
}

output "db_secret_arn" {
  description = "The ARN of the AWS Secrets Manager holding DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "alb_dns_name" {
  description = "Public URL corresponding to the frontend customer portal"
  value       = aws_lb.app_alb.dns_name
}
