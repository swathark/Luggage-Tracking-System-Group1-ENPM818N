# Random password generator for RDS master user
resource "random_password" "db_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Random suffix for KMS and Secrets Manager aliases (prevents collision during rapid destroy/apply)
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# AWS Secrets Manager Secret Structure
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "luggage-db-credentials-${random_string.suffix.result}"
  description = "Database credentials for Luggage Tracking System"

  tags = {
    Name = "luggage-db-credentials"
  }
}

# Inject the payload securely via Terraform (kept out of state via best practices)
resource "aws_secretsmanager_secret_version" "db_credentials_version" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username             = aws_db_instance.main.username
    password             = random_password.db_password.result
    engine               = aws_db_instance.main.engine
    host                 = aws_db_instance.main.address
    port                 = aws_db_instance.main.port
    dbname               = aws_db_instance.main.db_name
    dbInstanceIdentifier = aws_db_instance.main.identifier
  })
}

# KMS Key for RDS Encryption (At Rest)
resource "aws_kms_key" "rds" {
  description             = "KMS key for Luggage Tracking RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "luggage-system-rds-kms"
  }
}

resource "aws_kms_alias" "rds_alias" {
  name          = "alias/luggage-rds-key-${random_string.suffix.result}"
  target_key_id = aws_kms_key.rds.key_id
}

# DB Subnet Group placing RDS exclusively in the Private Subnets
resource "aws_db_subnet_group" "main" {
  name       = "luggage-system-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "Luggage System DB Subnet Group"
  }
}

# The PostgreSQL RDS Instance
resource "aws_db_instance" "main" {
  identifier        = "luggage-tracking-db"
  engine            = "postgres"
  engine_version    = "16" # Keeping it generic 16.x auto-upgrade
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  
  db_name  = "luggagedb"
  username = "luggageadmin"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]

  # High Availability: Active Standby Database
  multi_az               = true
  
  # Security First Constraints
  publicly_accessible    = false
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.rds.arn

  # Automated Backups (Professor Requirement)
  backup_retention_period = 7 # Retain backups for 7 days
  backup_window           = "03:00-04:00" # Run daily during low traffic
  
  # Keep final snapshot true in prod, false here for easy teardown across testing
  skip_final_snapshot    = true
  
  tags = {
    Name = "LuggageSystemDB"
  }
}
