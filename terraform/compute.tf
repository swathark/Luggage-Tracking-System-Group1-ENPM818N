# EC2 Instance Profile (Allow EC2 to parse Secrets and Publish Serverless events)
resource "aws_iam_role" "app_role" {
  name = "luggage_app_ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "app_permissions" {
  name = "app_backend_policy"
  role = aws_iam_role.app_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow",
        Action = ["secretsmanager:GetSecretValue"],
        Resource = aws_secretsmanager_secret.db_credentials.arn
      },
      {
        Sid    = "SecretsManagerList"
        Effect = "Allow",
        Action = ["secretsmanager:ListSecrets"],
        Resource = "*"
        # ListSecrets does not support resource-level restrictions per AWS docs
      },
      {
        Sid    = "SNSPublishAccess"
        Effect = "Allow",
        Action = ["sns:Publish"],
        Resource = aws_sns_topic.support_tickets.arn
      },
      {
        Sid    = "SNSListTopics"
        Effect = "Allow",
        Action = ["sns:ListTopics"],
        Resource = "*"
        # ListTopics does not support resource-level restrictions per AWS docs
      },
      {
        Sid    = "S3ArtifactAccess"
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:ListBucket"],
        Resource = [
          aws_s3_bucket.app_artifacts.arn,
          "${aws_s3_bucket.app_artifacts.arn}/*"
        ]
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups"
        ],
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/luggage-app/*"
      },
      {
        Sid    = "SSMParameterAccess"
        Effect = "Allow",
        Action = ["ssm:GetParameter"],
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/luggage-*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "app_profile" {
  name = "luggage_app_ec2_profile"
  role = aws_iam_role.app_role.name
}

# Permanently bind the SSM Managed Policy for console access
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.app_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Pulling base image mapping dynamically based on Amazon standard releases
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

# Blueprint for Launching Target Infrastructure securely into ASG
resource "aws_launch_template" "app_lt" {
  name_prefix   = "luggage-app-"
  image_id      = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.micro"

  vpc_security_group_ids = [aws_security_group.app_sg.id]
  
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      encrypted   = true
      volume_size = 8
      volume_type = "gp3"
    }
  }
  
  iam_instance_profile {
    name = aws_iam_instance_profile.app_profile.name
  }

  update_default_version = true

  # Start up script to pull required packages, nginx, and setup systemd for actual source code
  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    artifact_bucket = aws_s3_bucket.app_artifacts.id
  }))

  tag_specifications {
    resource_type = "instance"
    tags = { "Name" = "LuggageAppNode" }
  }
}

# The Compute Heart: Auto Scaling configuration with cost constraints mapped
resource "aws_autoscaling_group" "app_asg" {
  name                = "luggage-app-asg"
  vpc_zone_identifier = aws_subnet.private[*].id
  target_group_arns   = [aws_lb_target_group.app_tg.arn]
  health_check_type   = "ELB"
  min_size            = 1
  max_size            = 2
  desired_capacity    = 1

  # Force EC2 instances to completely delay boot sequences until the database finishes deploying
  depends_on = [aws_secretsmanager_secret_version.db_credentials_version]

  launch_template {
    id      = aws_launch_template.app_lt.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "LuggageAppNode"
    propagate_at_launch = true
  }

  tag {
    key                 = "Backup"
    value               = "Daily"
    propagate_at_launch = true
  }
}

# Map public edge boundary router (ALB) into Public Subnets bridging to the internet securely
resource "aws_lb" "app_alb" {
  name               = "luggage-app-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = aws_subnet.public[*].id
  
  # Inject Access Logs (Phase 6 requirement) securely mapping onto S3 limits seamlessly
  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    enabled = true
  }
  
  # ALB requires Bucket permissions to safely commit resources prior to Load Balancer boots
  depends_on = [aws_s3_bucket_policy.alb_logs_policy]

  tags = { "Name" = "LuggageSystemALB" }
}

# Backwards mapping protocol hooking to Instance target pools
resource "aws_lb_target_group" "app_tg" {
  name     = "luggage-app-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

# Automatically force inbound unencrypted queries toward strict HTTPS layers
resource "aws_lb_listener" "front_end_http" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# Encrypted mapping ingesting Self-Signed ACM validation to EC2 instances locally
resource "aws_lb_listener" "front_end_https" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = aws_acm_certificate.alb_cert.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app_tg.arn
  }
}
