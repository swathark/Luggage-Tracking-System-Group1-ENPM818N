# ==========================================
# Centralized Backup Strategy (AWS Backup)
# ==========================================

# 1. IAM Role for AWS Backup
data "aws_iam_policy_document" "backup_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup_role" {
  name               = "luggage-aws-backup-role"
  assume_role_policy = data.aws_iam_policy_document.backup_assume_role.json
}

resource "aws_iam_role_policy_attachment" "backup_policy" {
  role       = aws_iam_role.backup_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

# 2. Backup Vault
resource "aws_backup_vault" "luggage_vault" {
  name        = "luggage-system-backup-vault"
  # Ensures `terraform destroy` wipes out backups so you don't get charged for abandoned snapshots
  force_destroy = true 
}

# 3. Backup Plan
resource "aws_backup_plan" "daily_ec2_backup" {
  name = "luggage-daily-ec2-backup-plan"

  rule {
    rule_name         = "daily-backup"
    target_vault_name = aws_backup_vault.luggage_vault.name
    schedule          = "cron(0 5 * * ? *)" # 5:00 AM UTC daily
    
    lifecycle {
      delete_after = 30 # Retain for 30 days
    }
  }
}

# 4. Backup Selection (Dynamic Tag-Based)
resource "aws_backup_selection" "ec2_selection" {
  iam_role_arn = aws_iam_role.backup_role.arn
  name         = "luggage-ec2-backup-selection"
  plan_id      = aws_backup_plan.daily_ec2_backup.id

  selection_tag {
    type  = "STRINGEQUALS"
    key   = "Backup"
    value = "Daily"
  }
}
