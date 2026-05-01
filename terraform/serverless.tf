# 1. Topic for Support Tickets (Fan-out Architecture)
resource "aws_sns_topic" "support_tickets" {
  name = "luggage-support-tickets-topic"
}

# 2. Queue to safely buffer processing
resource "aws_sqs_queue" "support_tickets_queue" {
  name = "luggage-support-tickets-queue"
}

# 3. Allow SNS to deliver messages to SQS seamlessly
resource "aws_sqs_queue_policy" "sns_to_sqs" {
  queue_url = aws_sqs_queue.support_tickets_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.support_tickets_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.support_tickets.arn
          }
        }
      }
    ]
  })
}

# 4. Subscribe SQS endpoint directly to the SNS Topic
resource "aws_sns_topic_subscription" "sqs_target" {
  topic_arn = aws_sns_topic.support_tickets.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.support_tickets_queue.arn
}

# 5. Build secure Execution Role for the serverless Lambda
resource "aws_iam_role" "lambda_exec" {
  name = "luggage_ticket_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Basic Logging attachment for observability
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Strict SQS permissions so Lambda can poll the queue
resource "aws_iam_role_policy" "lambda_sqs" {
  name = "lambda_sqs_policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ]
      Resource = aws_sqs_queue.support_tickets_queue.arn
    }]
  })
}

# Package the flat Python script into an archive dynamically during Terraform plan
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../src/lambda_function.py"
  output_path = "${path.module}/../src/lambda_function.zip"
}

# 6. Deploy the AWS Lambda (Serverless Compute)
resource "aws_lambda_function" "ticket_processor" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "luggage-ticket-processor"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      ENVIRONMENT = "production"
    }
  }
}

# 7. Create Event Source Mapping hooking SQS buffer to Lambda directly
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.support_tickets_queue.arn
  function_name    = aws_lambda_function.ticket_processor.arn
  batch_size       = 10
}
