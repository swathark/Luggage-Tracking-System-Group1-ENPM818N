# Security Group encapsulating Public Edge Application Load Balancer
resource "aws_security_group" "alb_sg" {
  name        = "luggage-system-alb-sg"
  description = "Security Group capturing public frontend internet flows"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Allow inbound HTTPS strictly"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Permit HTTP primarily to funnel onto redirect protocols"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = { Name = "luggage-system-alb-sg" }
}

# Security Group confining local target Application Node clusters
resource "aws_security_group" "app_sg" {
  name        = "luggage-system-app-sg"
  description = "Security Group for private Application nodes"
  vpc_id      = aws_vpc.main.id

  # Explicitly allowing web connections natively isolated from solely external facing proxy mappings
  ingress {
    description     = "Accept routing purely from ALB security domains"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "luggage-system-app-sg"
  }
}

# Security Group for the RDS Database
resource "aws_security_group" "db_sg" {
  name        = "luggage-system-db-sg"
  description = "Security Group for RDS PostgreSQL database"
  vpc_id      = aws_vpc.main.id

  # Allow PostgreSQL traffic gracefully from the Application SG
  ingress {
    description     = "Allow PostgreSQL traffic from App EC2 Instances"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }

  # Also allow from the entire VPC CIDR so we can run scripts from jump boxes if necessary
  ingress {
    description = "Allow PostgreSQL traffic from intra-VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "luggage-system-db-sg"
  }
}
